"""Timestamped streaming audio ingestion and transcription orchestration.

This module owns the production-shaped audio boundary for the local API
package. It does not expose transcript text through logs or HTTP responses. Raw
samples and transcript words remain in memory for the bounded processing call.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite
from time import monotonic
from typing import Literal

from privastream_api.pipeline.contracts import AudioChunk, AudioRedactionInterval, AudioSegment
from privastream_api.pipeline.spoken_pii import (
    LocalTranscriber,
    RedactionConfig,
    SpeechWindow,
    TranscriptWord,
    VoiceActivityDetector,
    detect_spoken_pii,
    normalize_redaction_intervals,
)


AudioProcessingStatus = Literal[
    "ok",
    "no_speech",
    "unsafe_input",
    "unsafe_timestamp_discontinuity",
    "unsafe_vad_failure",
    "unsafe_queue_overflow",
    "unsafe_transcription_failure",
    "unsafe_deadline",
]


@dataclass(frozen=True, slots=True)
class SpeechSegment:
    """A bounded, source-timestamped normalized speech segment."""

    start_timestamp_ms: int
    end_timestamp_ms: int
    sample_rate_hz: int
    samples: tuple[float, ...]
    sequence_id: int

    def __post_init__(self) -> None:
        if self.start_timestamp_ms < 0 or self.end_timestamp_ms <= self.start_timestamp_ms:
            raise ValueError("speech segment timestamps must be non-negative and ordered")
        if self.sample_rate_hz <= 0 or not self.samples:
            raise ValueError("speech segment must contain samples at a positive sample rate")
        if any(not isfinite(sample) or not -1 <= sample <= 1 for sample in self.samples):
            raise ValueError("speech segment samples must be finite values between -1 and 1")
        expected_duration_ms = len(self.samples) * 1000 / self.sample_rate_hz
        if abs(expected_duration_ms - (self.end_timestamp_ms - self.start_timestamp_ms)) > 1:
            raise ValueError("speech segment timestamps must match sample duration")

    @property
    def duration_ms(self) -> int:
        return self.end_timestamp_ms - self.start_timestamp_ms

    def as_audio_segment(self) -> AudioSegment:
        return AudioSegment(
            start_ms=self.start_timestamp_ms,
            end_ms=self.end_timestamp_ms,
            sample_rate_hz=self.sample_rate_hz,
            channels=1,
            samples=self.samples,
        )


@dataclass(frozen=True, slots=True)
class AudioNormalizerConfig:
    """Canonical model input format."""

    sample_rate_hz: int = 16_000

    def __post_init__(self) -> None:
        if self.sample_rate_hz <= 0:
            raise ValueError("canonical sample rate must be positive")


class AudioNormalizer:
    """Convert chunks to mono normalized float samples at one model rate."""

    def __init__(self, config: AudioNormalizerConfig | None = None) -> None:
        self.config = config or AudioNormalizerConfig()

    def normalize(self, chunk: AudioChunk) -> AudioChunk:
        samples = chunk.normalized_samples()
        mono = self._downmix(samples, chunk.channels)
        if chunk.sample_rate_hz != self.config.sample_rate_hz:
            mono = self._resample(mono, chunk.sample_rate_hz, self.config.sample_rate_hz)
        return AudioChunk(
            start_timestamp_ms=chunk.start_timestamp_ms,
            sample_rate_hz=self.config.sample_rate_hz,
            channels=1,
            pcm_format="float32",
            samples=mono,
            sequence_id=chunk.sequence_id,
        )

    @staticmethod
    def _downmix(samples: tuple[float, ...], channels: int) -> tuple[float, ...]:
        if channels == 1:
            return samples
        return tuple(
            sum(samples[offset : offset + channels]) / channels
            for offset in range(0, len(samples), channels)
        )

    @staticmethod
    def _resample(
        samples: tuple[float, ...], source_rate_hz: int, target_rate_hz: int
    ) -> tuple[float, ...]:
        target_count = max(1, round(len(samples) * target_rate_hz / source_rate_hz))
        if target_count <= 0:
            return ()
        if len(samples) == 1:
            return (samples[0],) * target_count
        output: list[float] = []
        scale = source_rate_hz / target_rate_hz
        for index in range(target_count):
            source_position = min(index * scale, len(samples) - 1)
            left = int(source_position)
            right = min(left + 1, len(samples) - 1)
            fraction = source_position - left
            output.append(samples[left] + (samples[right] - samples[left]) * fraction)
        return tuple(output)


@dataclass(frozen=True, slots=True)
class SpeechSegmenterConfig:
    """Boundaries for pre/post roll, ring buffering, and long speech."""

    pre_roll_ms: int = 150
    post_roll_ms: int = 250
    max_segment_ms: int = 15_000
    segment_overlap_ms: int = 0
    ring_buffer_ms: int = 1_000

    def __post_init__(self) -> None:
        if self.pre_roll_ms < 0 or self.post_roll_ms < 0:
            raise ValueError("speech roll durations must be non-negative")
        if self.max_segment_ms <= 0:
            raise ValueError("max_segment_ms must be positive")
        if not 0 <= self.segment_overlap_ms < self.max_segment_ms:
            raise ValueError("segment overlap must be non-negative and shorter than max duration")
        if self.ring_buffer_ms < self.pre_roll_ms:
            raise ValueError("ring buffer must hold at least the configured pre-roll")


class SpeechSegmenter:
    """Turn normalized chunks into bounded speech segments.

    The ring buffer retains only the configured pre-roll context. VAD runs on
    that bounded context plus the newest chunk, while active speech is split at
    deterministic sample boundaries before it can grow without limit.
    """

    def __init__(
        self,
        vad: VoiceActivityDetector,
        config: SpeechSegmenterConfig | None = None,
    ) -> None:
        self.vad = vad
        self.config = config or SpeechSegmenterConfig()
        self._ring: deque[AudioChunk] = deque()
        self._active_samples: list[float] = []
        self._active_start_ms: int | None = None
        self._last_voice_end_ms: int | None = None
        self._last_chunk_end_ms: Fraction | None = None
        self._last_sequence_id: int | None = None
        self._next_segment_id = 0

    def push(self, chunk: AudioChunk) -> tuple[SpeechSegment, ...]:
        self._validate_chunk(chunk)
        self._ring.append(chunk)
        self._trim_ring()
        analysis = self._join_chunks(tuple(self._ring))
        windows = tuple(self.vad.detect(analysis))
        current_windows = tuple(
            window
            for window in windows
            if window.end_ms > chunk.start_timestamp_ms
            and window.start_ms < int(chunk.end_timestamp_ms)
        )

        emitted: list[SpeechSegment] = []
        if current_windows:
            first_voice_ms = min(window.start_ms for window in current_windows)
            voice_end_ms = max(window.end_ms for window in current_windows)
            self._start_or_append(chunk, first_voice_ms, voice_end_ms)
            self._last_voice_end_ms = voice_end_ms
            emitted.extend(self._split_complete_segments())
        elif self._active_start_ms is not None:
            if self._last_voice_end_ms is None:
                raise RuntimeError("active speech segment has no voice end timestamp")
            self._append_chunk_samples(
                chunk,
                chunk.start_timestamp_ms,
                min(int(chunk.end_timestamp_ms), self._last_voice_end_ms + self.config.post_roll_ms),
            )
            if (
                self._last_voice_end_ms is not None
                and int(chunk.end_timestamp_ms) - self._last_voice_end_ms
                >= self.config.post_roll_ms
            ):
                if self._active_samples:
                    emitted.append(self._emit_active())
                self._reset_active()

        return tuple(emitted)

    def flush(self) -> tuple[SpeechSegment, ...]:
        if self._active_start_ms is None:
            return ()
        if not self._active_samples:
            self._reset_active()
            return ()
        segment = self._emit_active()
        self._reset_active()
        return (segment,)

    def _validate_chunk(self, chunk: AudioChunk) -> None:
        if chunk.channels != 1 or chunk.pcm_format != "float32":
            raise ValueError("SpeechSegmenter requires normalized mono float32 chunks")
        if self._last_sequence_id is not None and chunk.sequence_id <= self._last_sequence_id:
            raise ValueError("audio sequence ids must increase")
        if self._last_chunk_end_ms is not None and chunk.start_timestamp_ms < self._last_chunk_end_ms:
            raise ValueError("audio chunks overlap on the source timeline")
        self._last_sequence_id = chunk.sequence_id
        self._last_chunk_end_ms = chunk.end_timestamp_ms

    def _trim_ring(self) -> None:
        if not self._ring:
            return
        newest_end = self._ring[-1].end_timestamp_ms
        while len(self._ring) > 1:
            oldest = self._ring[0]
            if newest_end - oldest.start_timestamp_ms <= self.config.ring_buffer_ms:
                break
            self._ring.popleft()

    def _start_or_append(self, chunk: AudioChunk, first_voice_ms: int, voice_end_ms: int) -> None:
        if self._active_start_ms is None:
            pre_roll_start = first_voice_ms - self.config.pre_roll_ms
            preceding = tuple(
                item
                for item in self._ring
                if item.sequence_id != chunk.sequence_id
                and item.end_timestamp_ms > pre_roll_start
                and item.end_timestamp_ms <= chunk.start_timestamp_ms
            )
            context_start_ms = (
                max(pre_roll_start, preceding[0].start_timestamp_ms)
                if preceding
                else max(pre_roll_start, chunk.start_timestamp_ms)
            )
            self._active_start_ms = context_start_ms
            for item in preceding:
                self._append_chunk_samples(item, max(pre_roll_start, item.start_timestamp_ms), item.end_timestamp_ms)
            self._append_chunk_samples(
                chunk,
                max(pre_roll_start, chunk.start_timestamp_ms),
                min(int(chunk.end_timestamp_ms), voice_end_ms + self.config.post_roll_ms),
            )
            return
        self._append_chunk_samples(
            chunk,
            chunk.start_timestamp_ms,
            min(int(chunk.end_timestamp_ms), voice_end_ms + self.config.post_roll_ms),
        )

    def _append_chunk_samples(self, chunk: AudioChunk, start_ms: int, end_ms: int) -> None:
        start_index = max(
            0, round((start_ms - chunk.start_timestamp_ms) * chunk.sample_rate_hz / 1000)
        )
        end_index = min(
            chunk.frame_count,
            round((end_ms - chunk.start_timestamp_ms) * chunk.sample_rate_hz / 1000),
        )
        if end_index > start_index:
            self._active_samples.extend(chunk.normalized_samples()[start_index:end_index])

    def _split_complete_segments(self) -> list[SpeechSegment]:
        if self._active_start_ms is None:
            return []
        max_samples = round(self.config.max_segment_ms * self._sample_rate_hz())
        overlap_samples = round(self.config.segment_overlap_ms * self._sample_rate_hz())
        emitted: list[SpeechSegment] = []
        while len(self._active_samples) >= max_samples:
            segment_samples = tuple(self._active_samples[:max_samples])
            end_ms = self._active_start_ms + round(
                len(segment_samples) * 1000 / self._sample_rate_hz()
            )
            emitted.append(
                SpeechSegment(
                    start_timestamp_ms=self._active_start_ms,
                    end_timestamp_ms=end_ms,
                    sample_rate_hz=self._sample_rate_hz(),
                    samples=segment_samples,
                    sequence_id=self._next_segment_id,
                )
            )
            self._next_segment_id += 1
            retained_start = max_samples - overlap_samples
            self._active_samples = self._active_samples[retained_start:]
            self._active_start_ms = end_ms - round(
                overlap_samples * 1000 / self._sample_rate_hz()
            )
        return emitted

    def _emit_active(self) -> SpeechSegment:
        if self._active_start_ms is None or not self._active_samples:
            raise RuntimeError("cannot emit an empty speech segment")
        end_ms = self._active_start_ms + round(
            len(self._active_samples) * 1000 / self._sample_rate_hz()
        )
        segment = SpeechSegment(
            start_timestamp_ms=self._active_start_ms,
            end_timestamp_ms=end_ms,
            sample_rate_hz=self._sample_rate_hz(),
            samples=tuple(self._active_samples),
            sequence_id=self._next_segment_id,
        )
        self._next_segment_id += 1
        return segment

    def _reset_active(self) -> None:
        self._active_samples = []
        self._active_start_ms = None
        self._last_voice_end_ms = None

    def _sample_rate_hz(self) -> int:
        if not self._ring:
            raise RuntimeError("speech segmenter has no audio sample rate")
        return self._ring[-1].sample_rate_hz

    @staticmethod
    def _join_chunks(chunks: Sequence[AudioChunk]) -> AudioSegment:
        if not chunks:
            raise ValueError("cannot analyze an empty chunk sequence")
        first = chunks[0]
        if any(
            chunk.sample_rate_hz != first.sample_rate_hz
            or chunk.channels != first.channels
            or chunk.pcm_format != first.pcm_format
            for chunk in chunks
        ):
            raise ValueError("analysis chunks must share one normalized format")
        samples = tuple(sample for chunk in chunks for sample in chunk.normalized_samples())
        end_ms = round(float(chunks[-1].end_timestamp_ms))
        return AudioSegment(
            start_ms=first.start_timestamp_ms,
            end_ms=end_ms,
            sample_rate_hz=first.sample_rate_hz,
            channels=first.channels,
            samples=samples,
        )


@dataclass(frozen=True, slots=True)
class TimestampedTranscript:
    """In-memory transcription anchored to one source-timeline segment."""

    segment_sequence_id: int
    start_ms: int
    end_ms: int
    words: tuple[TranscriptWord, ...]

    @property
    def text(self) -> str:
        return " ".join(word.text.strip() for word in self.words)


@dataclass(frozen=True, slots=True)
class AudioProcessingResult:
    """Sanitized outcome of one bounded audio processing call."""

    status: AudioProcessingStatus
    speech_segments: tuple[SpeechSegment, ...] = ()
    transcripts: tuple[TimestampedTranscript, ...] = ()
    redaction_intervals: tuple[AudioRedactionInterval, ...] = ()
    queue_depth: int = 0
    processing_elapsed_ms: int = 0


@dataclass(frozen=True, slots=True)
class AudioPipelineConfig:
    """Bounded processing and timeline policy."""

    canonical_sample_rate_hz: int = 16_000
    max_queued_segments: int = 4
    max_queued_duration_ms: int = 30_000
    max_workers: int = 1
    transcription_deadline_ms: int = 5_000
    timestamp_tolerance_ms: int = 1
    segmenter: SpeechSegmenterConfig = SpeechSegmenterConfig()

    def __post_init__(self) -> None:
        if self.canonical_sample_rate_hz <= 0:
            raise ValueError("canonical sample rate must be positive")
        if self.max_queued_segments <= 0 or self.max_queued_duration_ms <= 0:
            raise ValueError("queue limits must be positive")
        if self.max_workers <= 0 or self.transcription_deadline_ms <= 0:
            raise ValueError("worker and deadline limits must be positive")
        if self.timestamp_tolerance_ms < 0:
            raise ValueError("timestamp tolerance must be non-negative")


class AudioPipeline:
    """Normalize, segment, and transcribe timestamped audio with backpressure."""

    def __init__(
        self,
        vad: VoiceActivityDetector,
        transcriber: LocalTranscriber,
        config: AudioPipelineConfig | None = None,
        redaction: RedactionConfig | None = None,
    ) -> None:
        self.config = config or AudioPipelineConfig()
        self.normalizer = AudioNormalizer(
            AudioNormalizerConfig(self.config.canonical_sample_rate_hz)
        )
        self.vad = vad
        self.transcriber = transcriber
        self.redaction = redaction or RedactionConfig()

    def process(self, chunks: Sequence[AudioChunk]) -> AudioProcessingResult:
        started = monotonic()
        source_chunks = tuple(chunks)
        if not source_chunks:
            return AudioProcessingResult(status="no_speech")
        try:
            self._validate_source_timeline(source_chunks)
        except ValueError:
            return AudioProcessingResult(
                status="unsafe_timestamp_discontinuity",
                processing_elapsed_ms=self._elapsed_ms(started),
            )
        try:
            normalized = tuple(self.normalizer.normalize(chunk) for chunk in source_chunks)
            segmenter = SpeechSegmenter(self.vad, self.config.segmenter)
            segments: list[SpeechSegment] = []
            for chunk in normalized:
                segments.extend(segmenter.push(chunk))
            segments.extend(segmenter.flush())
        except ValueError:
            return AudioProcessingResult(
                status="unsafe_input",
                processing_elapsed_ms=self._elapsed_ms(started),
            )
        except Exception:
            return AudioProcessingResult(
                status="unsafe_vad_failure",
                processing_elapsed_ms=self._elapsed_ms(started),
            )

        if not segments:
            return AudioProcessingResult(
                status="no_speech",
                processing_elapsed_ms=self._elapsed_ms(started),
            )
        queued_duration_ms = sum(segment.duration_ms for segment in segments)
        if (
            len(segments) > self.config.max_queued_segments
            or queued_duration_ms > self.config.max_queued_duration_ms
        ):
            return AudioProcessingResult(
                status="unsafe_queue_overflow",
                speech_segments=tuple(segments),
                queue_depth=len(segments),
                processing_elapsed_ms=self._elapsed_ms(started),
            )

        executor = ThreadPoolExecutor(max_workers=self.config.max_workers)
        futures: list[Future[tuple[TimestampedTranscript, tuple]]] = []
        try:
            for segment in segments:
                futures.append(executor.submit(self._process_segment, segment))
            deadline = monotonic() + self.config.transcription_deadline_ms / 1000
            transcripts: list[TimestampedTranscript] = []
            intervals = []
            for future in futures:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    executor.shutdown(wait=False, cancel_futures=True)
                    return AudioProcessingResult(
                        status="unsafe_deadline",
                        speech_segments=tuple(segments),
                        queue_depth=len(futures),
                        processing_elapsed_ms=self._elapsed_ms(started),
                    )
                try:
                    transcript, segment_intervals = future.result(timeout=remaining)
                except TimeoutError:
                    executor.shutdown(wait=False, cancel_futures=True)
                    return AudioProcessingResult(
                        status="unsafe_deadline",
                        speech_segments=tuple(segments),
                        queue_depth=len(futures),
                        processing_elapsed_ms=self._elapsed_ms(started),
                    )
                except Exception:
                    executor.shutdown(wait=False, cancel_futures=True)
                    return AudioProcessingResult(
                        status="unsafe_transcription_failure",
                        speech_segments=tuple(segments),
                        queue_depth=len(futures),
                        processing_elapsed_ms=self._elapsed_ms(started),
                    )
                transcripts.append(transcript)
                intervals.extend(segment_intervals)
            executor.shutdown(wait=True, cancel_futures=True)
        except Exception:
            executor.shutdown(wait=False, cancel_futures=True)
            return AudioProcessingResult(
                status="unsafe_transcription_failure",
                speech_segments=tuple(segments),
                queue_depth=len(futures),
                processing_elapsed_ms=self._elapsed_ms(started),
            )
        return AudioProcessingResult(
            status="ok",
            speech_segments=tuple(segments),
            transcripts=tuple(transcripts),
            redaction_intervals=tuple(intervals),
            queue_depth=len(futures),
            processing_elapsed_ms=self._elapsed_ms(started),
        )

    def _process_segment(
        self, segment: SpeechSegment
    ) -> tuple[TimestampedTranscript, tuple]:
        audio_segment = segment.as_audio_segment()
        words = tuple(
            word
            for word in self.transcriber.transcribe(
                audio_segment,
                (SpeechWindow(segment.start_timestamp_ms, segment.end_timestamp_ms),),
            )
            if segment.start_timestamp_ms <= word.start_ms < word.end_ms <= segment.end_timestamp_ms
        )
        transcript = TimestampedTranscript(
            segment_sequence_id=segment.sequence_id,
            start_ms=segment.start_timestamp_ms,
            end_ms=segment.end_timestamp_ms,
            words=words,
        )
        intervals = normalize_redaction_intervals(
            detect_spoken_pii(words), audio_segment, self.redaction
        )
        return transcript, intervals

    def _validate_source_timeline(self, chunks: Sequence[AudioChunk]) -> None:
        previous: AudioChunk | None = None
        for chunk in chunks:
            if previous is not None:
                if chunk.sequence_id != previous.sequence_id + 1:
                    raise ValueError("audio sequence ids are discontinuous")
                gap = Fraction(chunk.start_timestamp_ms) - previous.end_timestamp_ms
                if abs(gap) > self.config.timestamp_tolerance_ms:
                    raise ValueError("audio timestamps are discontinuous")
            previous = chunk

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, round((monotonic() - started) * 1000))


def chunks_from_segment(
    segment: AudioSegment, chunk_duration_ms: int = 30
) -> tuple[AudioChunk, ...]:
    """Feed a bounded prerecorded segment through the same chunk boundary."""

    if chunk_duration_ms <= 0:
        raise ValueError("chunk_duration_ms must be positive")
    frames_per_chunk = max(1, round(segment.sample_rate_hz * chunk_duration_ms / 1000))
    chunks: list[AudioChunk] = []
    frame_count = len(segment.samples) // segment.channels
    for sequence_id, frame_offset in enumerate(range(0, frame_count, frames_per_chunk)):
        frame_end = min(frame_count, frame_offset + frames_per_chunk)
        sample_start = frame_offset * segment.channels
        sample_end = frame_end * segment.channels
        chunks.append(
            AudioChunk(
                start_timestamp_ms=segment.start_ms
                + round(frame_offset * 1000 / segment.sample_rate_hz),
                sample_rate_hz=segment.sample_rate_hz,
                channels=segment.channels,
                pcm_format="float32",
                samples=segment.samples[sample_start:sample_end],
                sequence_id=sequence_id,
            )
        )
    return tuple(chunks)


def chunk_from_segment(segment: AudioSegment, sequence_id: int = 0) -> AudioChunk:
    """Adapt one bounded segment to the streaming input contract."""

    chunks = chunks_from_segment(segment, chunk_duration_ms=max(1, segment.duration_ms))
    if not chunks:
        raise ValueError("cannot create a chunk from an empty segment")
    chunk = chunks[0]
    return AudioChunk(
        start_timestamp_ms=chunk.start_timestamp_ms,
        sample_rate_hz=chunk.sample_rate_hz,
        channels=chunk.channels,
        pcm_format=chunk.pcm_format,
        samples=chunk.samples,
        sequence_id=sequence_id,
    )
