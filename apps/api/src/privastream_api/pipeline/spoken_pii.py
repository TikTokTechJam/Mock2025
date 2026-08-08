"""Standalone spoken-PII detection and local audio redaction.

The module keeps raw PCM and transcript words in memory for one call only. It
does not log, persist, or expose transcript text. Model-specific integrations
adapt their results to the normalized pipeline contracts before policy and
rendering consume them.
"""

from __future__ import annotations

import argparse
import re
import sys
import wave
from array import array
from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil, floor, isfinite, sqrt
from pathlib import Path
from typing import Any, Protocol

from privastream_api.pipeline.contracts import AudioRedactionInterval, AudioSegment


@dataclass(frozen=True, slots=True)
class SpeechWindow:
    """A source-timestamped interval that contains enough speech to transcribe."""

    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("speech window timestamps must be non-negative and ordered")


class VoiceActivityDetector(Protocol):
    def detect(self, segment: AudioSegment) -> Sequence[SpeechWindow]:
        """Return bounded speech windows in the segment's source timeline."""


@dataclass(frozen=True, slots=True)
class EnergyVadConfig:
    """Configuration for the dependency-free VAD baseline."""

    frame_ms: int = 30
    rms_threshold: float = 0.015
    min_speech_ms: int = 120
    merge_gap_ms: int = 90
    max_window_ms: int = 15_000

    def __post_init__(self) -> None:
        if self.frame_ms <= 0 or self.min_speech_ms <= 0 or self.max_window_ms <= 0:
            raise ValueError("VAD durations must be positive")
        if self.merge_gap_ms < 0:
            raise ValueError("merge_gap_ms must be non-negative")
        if not isfinite(self.rms_threshold) or not 0 <= self.rms_threshold <= 1:
            raise ValueError("rms_threshold must be between 0 and 1")


class EnergyVoiceActivityDetector:
    """Use short-time RMS energy to avoid transcribing continuous silence.

    This is the local, dependency-free baseline. It is intentionally bounded
    and can be replaced by ``SileroVoiceActivityDetector`` without changing
    the detector or redaction contracts.
    """

    def __init__(self, config: EnergyVadConfig | None = None) -> None:
        self.config = config or EnergyVadConfig()

    def detect(self, segment: AudioSegment) -> tuple[SpeechWindow, ...]:
        samples = segment.mono_samples()
        if not samples:
            raise ValueError("audio segment has no PCM samples")
        frame_samples = max(1, round(segment.sample_rate_hz * self.config.frame_ms / 1000))
        voiced_frames: list[SpeechWindow] = []
        for offset in range(0, len(samples), frame_samples):
            frame = samples[offset : offset + frame_samples]
            if not frame:
                continue
            rms = sqrt(sum(sample * sample for sample in frame) / len(frame))
            if rms < self.config.rms_threshold:
                continue
            start_ms = segment.start_ms + round(offset / segment.sample_rate_hz * 1000)
            end_ms = min(
                segment.end_ms,
                segment.start_ms + round((offset + len(frame)) / segment.sample_rate_hz * 1000),
            )
            if end_ms > start_ms:
                voiced_frames.append(SpeechWindow(start_ms, end_ms))

        merged: list[SpeechWindow] = []
        for window in voiced_frames:
            if merged and window.start_ms - merged[-1].end_ms <= self.config.merge_gap_ms:
                merged[-1] = SpeechWindow(merged[-1].start_ms, window.end_ms)
            else:
                merged.append(window)

        bounded: list[SpeechWindow] = []
        for window in merged:
            if window.end_ms - window.start_ms < self.config.min_speech_ms:
                continue
            start_ms = window.start_ms
            while start_ms < window.end_ms:
                end_ms = min(start_ms + self.config.max_window_ms, window.end_ms)
                if end_ms - start_ms >= self.config.min_speech_ms:
                    bounded.append(SpeechWindow(start_ms, end_ms))
                start_ms = end_ms
        return tuple(bounded)


class SileroVoiceActivityDetector:
    """Optional Silero VAD adapter with the same source-time output contract."""

    def __init__(self, min_speech_ms: int = 120, max_window_ms: int = 15_000) -> None:
        if min_speech_ms <= 0 or max_window_ms <= 0:
            raise ValueError("Silero VAD durations must be positive")
        self.min_speech_ms = min_speech_ms
        self.max_window_ms = max_window_ms
        self._model: Any | None = None

    def detect(self, segment: AudioSegment) -> tuple[SpeechWindow, ...]:
        if not segment.samples:
            raise ValueError("audio segment has no PCM samples")
        if segment.sample_rate_hz not in (8000, 16000):
            raise ValueError("Silero VAD requires an 8 kHz or 16 kHz input segment")
        try:
            import torch  # type: ignore[import-not-found]
            from silero_vad import (  # type: ignore[import-not-found]
                get_speech_timestamps,
                load_silero_vad,
            )
        except ImportError as error:
            raise RuntimeError(
                "Silero VAD is optional; install the audio dependency extra to use it"
            ) from error
        if self._model is None:
            self._model = load_silero_vad()
        timestamps = get_speech_timestamps(
            torch.tensor(segment.mono_samples(), dtype=torch.float32),
            self._model,
            sampling_rate=segment.sample_rate_hz,
            min_speech_duration_ms=self.min_speech_ms,
        )
        windows: list[SpeechWindow] = []
        for timestamp in timestamps:
            start_ms = segment.start_ms + round(timestamp["start"] / segment.sample_rate_hz * 1000)
            end_ms = min(
                segment.end_ms,
                segment.start_ms + round(timestamp["end"] / segment.sample_rate_hz * 1000),
            )
            while start_ms < end_ms:
                window_end = min(start_ms + self.max_window_ms, end_ms)
                windows.append(SpeechWindow(start_ms, window_end))
                start_ms = window_end
        return tuple(windows)


@dataclass(frozen=True, slots=True)
class TranscriptWord:
    """A word timestamp returned by a local ASR implementation."""

    text: str
    start_ms: int
    end_ms: int
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("transcript word must not be empty")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("transcript word timestamps must be ordered")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("transcript confidence must be between 0 and 1")


class LocalTranscriber(Protocol):
    def transcribe(
        self, segment: AudioSegment, windows: Sequence[SpeechWindow]
    ) -> Sequence[TranscriptWord]:
        """Return word timestamps anchored to the original audio timeline."""


class FasterWhisperTranscriber:
    """Lazy local Faster-Whisper adapter using word-level timestamps."""

    def __init__(
        self,
        model_size: str = "small",
        language: str | None = "en",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        if not model_size.strip():
            raise ValueError("model_size must not be empty")
        self.model_size = model_size
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self._model: Any | None = None

    @property
    def is_ready(self) -> bool:
        """Report whether the model has been loaded in this process."""

        return self._model is not None

    def load(self) -> None:
        """Load the model once without transcribing any media."""

        self._get_model()

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel  # type: ignore[import-not-found]
            except ImportError as error:
                raise RuntimeError(
                    "Faster-Whisper is optional; install the audio dependency extra"
                ) from error
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def transcribe(
        self, segment: AudioSegment, windows: Sequence[SpeechWindow]
    ) -> tuple[TranscriptWord, ...]:
        try:
            import numpy as np  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError("Faster-Whisper requires numpy") from error
        model = self._get_model()
        samples = np.asarray(segment.mono_samples(), dtype=np.float32)
        words: list[TranscriptWord] = []
        for window in windows:
            start = max(
                0,
                floor((window.start_ms - segment.start_ms) * segment.sample_rate_hz / 1000),
            )
            end = min(
                len(samples),
                ceil((window.end_ms - segment.start_ms) * segment.sample_rate_hz / 1000),
            )
            if end <= start:
                continue
            segments, _ = model.transcribe(
                samples[start:end],
                language=self.language,
                word_timestamps=True,
                vad_filter=False,
            )
            for transcribed_segment in segments:
                for word in transcribed_segment.words or ():
                    word_start = window.start_ms + round(float(word.start) * 1000)
                    word_end = window.start_ms + round(float(word.end) * 1000)
                    word_start = max(window.start_ms, word_start)
                    word_end = min(window.end_ms, word_end)
                    if word_end <= word_start:
                        continue
                    words.append(
                        TranscriptWord(
                            text=word.word,
                            start_ms=word_start,
                            end_ms=word_end,
                            confidence=float(word.probability),
                        )
                    )
        return tuple(words)


_DIGIT_WORDS = {
    "zero": "0",
    "oh": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}
_EMAIL_PATTERN = re.compile(
    r"[a-z0-9][a-z0-9._%+\-]*(?:\s*@\s*)[a-z0-9][a-z0-9.\-]*(?:\s*\.\s*)[a-z]{2,}",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(r"(?<!\d)\+?\d(?:[\s().\-]*\d){6,}(?!\d)")


def _normalize_spoken_token(token: str) -> str:
    normalized = token.strip().lower()
    if normalized in _DIGIT_WORDS:
        return _DIGIT_WORDS[normalized]
    replacements = {
        "at": "@",
        "dot": ".",
        "period": ".",
        "underscore": "_",
        "dash": "-",
        "hyphen": "-",
        "plus": "+",
    }
    return replacements.get(normalized, normalized.strip(" ,;:!?"))


def _find_interval(
    match: re.Match[str], text_spans: Sequence[tuple[int, int, TranscriptWord]]
) -> tuple[int, int, float] | None:
    covered = [
        word
        for start, end, word in text_spans
        if end > match.start() and start < match.end()
    ]
    if not covered:
        return None
    return (
        min(word.start_ms for word in covered),
        max(word.end_ms for word in covered),
        min(word.confidence for word in covered),
    )


def detect_spoken_pii(
    words: Sequence[TranscriptWord], detector: str = "spoken-pii-regex"
) -> tuple[AudioRedactionInterval, ...]:
    """Find phone/email spans while retaining only normalized interval output."""

    if not words:
        return ()
    normalized_words = [_normalize_spoken_token(word.text) for word in words]
    text_spans: list[tuple[int, int, TranscriptWord]] = []
    pieces: list[str] = []
    cursor = 0
    for normalized, word in zip(normalized_words, words, strict=True):
        if not normalized:
            continue
        if pieces:
            pieces.append(" ")
            cursor += 1
        start = cursor
        pieces.append(normalized)
        cursor += len(normalized)
        text_spans.append((start, cursor, word))
    normalized_text = "".join(pieces)
    intervals: list[AudioRedactionInterval] = []
    email_matches = list(_EMAIL_PATTERN.finditer(normalized_text))
    for match in email_matches:
        interval = _find_interval(match, text_spans)
        if interval is None:
            continue
        start_ms, end_ms, confidence = interval
        intervals.append(
            AudioRedactionInterval(
                kind="spoken_pii",
                start_ms=start_ms,
                end_ms=end_ms,
                confidence=confidence,
                detector=detector,
                reason="email",
            )
        )
    for match in _PHONE_PATTERN.finditer(normalized_text):
        if any(
            match.start() < email.end() and match.end() > email.start()
            for email in email_matches
        ):
            continue
        interval = _find_interval(match, text_spans)
        if interval is None:
            continue
        start_ms, end_ms, confidence = interval
        intervals.append(
            AudioRedactionInterval(
                kind="spoken_pii",
                start_ms=start_ms,
                end_ms=end_ms,
                confidence=confidence,
                detector=detector,
                reason="phone_number",
            )
        )
    return tuple(sorted(intervals, key=lambda interval: (interval.start_ms, interval.end_ms)))


@dataclass(frozen=True, slots=True)
class RedactionConfig:
    padding_ms: int = 250
    merge_gap_ms: int = 100

    def __post_init__(self) -> None:
        if self.padding_ms < 0 or self.merge_gap_ms < 0:
            raise ValueError("redaction padding and merge gap must be non-negative")


def normalize_redaction_intervals(
    intervals: Sequence[AudioRedactionInterval],
    segment: AudioSegment,
    config: RedactionConfig | None = None,
) -> tuple[AudioRedactionInterval, ...]:
    """Pad, clamp, sort, and merge intervals in source audio time."""

    policy = config or RedactionConfig()
    padded: list[AudioRedactionInterval] = []
    for interval in intervals:
        start_ms = max(segment.start_ms, interval.start_ms - policy.padding_ms)
        end_ms = min(segment.end_ms, interval.end_ms + policy.padding_ms)
        if end_ms <= start_ms:
            continue
        padded.append(
            AudioRedactionInterval(
                kind=interval.kind,
                start_ms=start_ms,
                end_ms=end_ms,
                confidence=interval.confidence,
                detector=interval.detector,
                reason=interval.reason,
            )
        )
    padded.sort(key=lambda interval: (interval.start_ms, interval.end_ms))
    merged: list[AudioRedactionInterval] = []
    for interval in padded:
        if not merged or interval.start_ms > merged[-1].end_ms + policy.merge_gap_ms:
            merged.append(interval)
            continue
        previous = merged[-1]
        reasons = [reason for reason in (previous.reason, interval.reason) if reason]
        merged[-1] = AudioRedactionInterval(
            kind="spoken_pii",
            start_ms=previous.start_ms,
            end_ms=max(previous.end_ms, interval.end_ms),
            confidence=max(previous.confidence, interval.confidence),
            detector=previous.detector,
            reason=", ".join(dict.fromkeys(reasons)) or None,
        )
    return tuple(merged)


class SpokenPiiDetector:
    """Compose VAD, local ASR, PII extraction, and interval policy."""

    kind = "spoken_pii"

    def __init__(
        self,
        vad: VoiceActivityDetector,
        transcriber: LocalTranscriber,
        redaction: RedactionConfig | None = None,
        max_audio_ms: int = 120_000,
    ) -> None:
        if max_audio_ms <= 0:
            raise ValueError("max_audio_ms must be positive")
        self.vad = vad
        self.transcriber = transcriber
        self.redaction = redaction or RedactionConfig()
        self.max_audio_ms = max_audio_ms

    def detect(self, segment: AudioSegment) -> tuple[AudioRedactionInterval, ...]:
        if not segment.samples:
            raise ValueError("spoken-PII detection requires PCM samples")
        if segment.duration_ms > self.max_audio_ms:
            raise ValueError("audio segment exceeds the configured in-memory limit")
        windows = self.vad.detect(segment)
        if not windows:
            return ()
        words = self.transcriber.transcribe(segment, windows)
        raw_intervals = detect_spoken_pii(words)
        return normalize_redaction_intervals(raw_intervals, segment, self.redaction)


def read_pcm16_wav(path: Path, start_ms: int = 0, max_audio_ms: int = 120_000) -> AudioSegment:
    """Read a bounded PCM16 WAV into normalized samples without persisting audio."""

    with wave.open(str(path), "rb") as wav:
        if wav.getcomptype() != "NONE" or wav.getsampwidth() != 2:
            raise ValueError("demo input must be uncompressed PCM16 WAV")
        frame_count = wav.getnframes()
        sample_rate_hz = wav.getframerate()
        channels = wav.getnchannels()
        duration_ms = round(frame_count / sample_rate_hz * 1000)
        if duration_ms <= 0 or duration_ms > max_audio_ms:
            raise ValueError("WAV duration is outside the configured demo limit")
        pcm = array("h")
        pcm.frombytes(wav.readframes(frame_count))
    if pcm.itemsize != 2:
        raise RuntimeError("platform does not expose 16-bit PCM values")
    if sys.byteorder != "little":
        pcm.byteswap()
    samples = tuple(value / 32768 for value in pcm)
    return AudioSegment(
        start_ms=start_ms,
        end_ms=start_ms + duration_ms,
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        samples=samples,
    )


def mute_pcm16_wav(
    input_path: Path,
    output_path: Path,
    intervals: Sequence[AudioRedactionInterval],
    source_start_ms: int = 0,
) -> None:
    """Write a copy of a PCM16 WAV with only selected source intervals muted."""

    if source_start_ms < 0:
        raise ValueError("source_start_ms must be non-negative")
    with wave.open(str(input_path), "rb") as source:
        params = source.getparams()
        if source.getcomptype() != "NONE" or source.getsampwidth() != 2:
            raise ValueError("demo input must be uncompressed PCM16 WAV")
        frame_count = source.getnframes()
        frames = array("h")
        frames.frombytes(source.readframes(frame_count))
    if sys.byteorder != "little":
        frames.byteswap()
    frame_rate = params.framerate
    channels = params.nchannels
    for interval in intervals:
        first_frame = max(0, floor((interval.start_ms - source_start_ms) * frame_rate / 1000))
        last_frame = min(frame_count, ceil((interval.end_ms - source_start_ms) * frame_rate / 1000))
        for frame_index in range(first_frame, last_frame):
            offset = frame_index * channels
            for channel in range(channels):
                frames[offset + channel] = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as destination:
        destination.setparams(params)
        destination.writeframes(frames.tobytes())


def _build_demo_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mute spoken phone/email PII in a PCM16 WAV")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", default="en")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--vad", choices=("energy", "silero"), default="energy")
    parser.add_argument("--padding-ms", type=int, default=250)
    parser.add_argument("--merge-gap-ms", type=int, default=100)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    from privastream_api.pipeline.audio import AudioPipeline, chunks_from_segment

    args = _build_demo_parser().parse_args(argv)
    segment = read_pcm16_wav(args.input)
    vad: VoiceActivityDetector
    if args.vad == "silero":
        vad = SileroVoiceActivityDetector()
    else:
        vad = EnergyVoiceActivityDetector()
    pipeline = AudioPipeline(
        vad=vad,
        transcriber=FasterWhisperTranscriber(
            model_size=args.model,
            language=args.language,
            device=args.device,
            compute_type=args.compute_type,
        ),
        redaction=RedactionConfig(
            padding_ms=args.padding_ms,
            merge_gap_ms=args.merge_gap_ms,
        ),
    )
    result = pipeline.process(chunks_from_segment(segment))
    if result.status not in ("ok", "no_speech"):
        raise RuntimeError(f"audio processing failed closed: {result.status}")
    intervals = result.redaction_intervals
    mute_pcm16_wav(args.input, args.output, intervals)
    print(f"redaction_intervals={len(intervals)}")


if __name__ == "__main__":
    main()
