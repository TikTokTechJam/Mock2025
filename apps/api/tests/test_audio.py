from __future__ import annotations

from collections.abc import Sequence

from privastream_api.pipeline.audio import (
    AudioNormalizer,
    AudioNormalizerConfig,
    AudioPipeline,
    AudioPipelineConfig,
    SpeechSegmenter,
    SpeechSegmenterConfig,
)
from privastream_api.pipeline.contracts import AudioChunk, AudioSegment
from privastream_api.pipeline.spoken_pii import SpeechWindow, TranscriptWord


class AlwaysVoiceVad:
    def detect(self, segment: AudioSegment) -> Sequence[SpeechWindow]:
        return (SpeechWindow(segment.start_ms, segment.end_ms),)


class FixedWindowVad:
    def detect(self, segment: AudioSegment) -> Sequence[SpeechWindow]:
        if segment.end_ms <= 200 or segment.start_ms >= 300:
            return ()
        return (SpeechWindow(200, 300),)


class FixedTranscriber:
    def __init__(self, words: Sequence[TranscriptWord] = ()) -> None:
        self.words = tuple(words)
        self.calls = 0

    def transcribe(
        self, segment: AudioSegment, windows: Sequence[SpeechWindow]
    ) -> Sequence[TranscriptWord]:
        self.calls += 1
        return self.words


class FailingTranscriber:
    def transcribe(
        self, segment: AudioSegment, windows: Sequence[SpeechWindow]
    ) -> Sequence[TranscriptWord]:
        raise RuntimeError("model failure")


def _chunk(start_ms: int, sequence_id: int, duration_ms: int = 100) -> AudioChunk:
    sample_count = duration_ms * 16_000 // 1000
    return AudioChunk(
        start_timestamp_ms=start_ms,
        sample_rate_hz=16_000,
        channels=1,
        pcm_format="float32",
        samples=(0.2,) * sample_count,
        sequence_id=sequence_id,
    )


def test_audio_chunk_end_timestamp_uses_sample_count_exactly() -> None:
    chunk = AudioChunk(
        start_timestamp_ms=0,
        sample_rate_hz=44_100,
        channels=1,
        pcm_format="float32",
        samples=(0.0,),
        sequence_id=0,
    )

    assert chunk.end_timestamp_ms.numerator == 1000
    assert chunk.end_timestamp_ms.denominator == 44_100


def test_normalizer_downmixes_stereo_and_resamples_to_canonical_rate() -> None:
    chunk = AudioChunk(
        start_timestamp_ms=5_000,
        sample_rate_hz=8_000,
        channels=2,
        pcm_format="float32",
        samples=(0.4, -0.2) * 800,
        sequence_id=3,
    )

    normalized = AudioNormalizer(AudioNormalizerConfig(16_000)).normalize(chunk)

    assert normalized.channels == 1
    assert normalized.sample_rate_hz == 16_000
    assert normalized.start_timestamp_ms == 5_000
    assert normalized.frame_count == 1_600
    assert normalized.samples[0] == 0.1


def test_segmenter_keeps_pre_and_post_roll_without_unbounded_buffering() -> None:
    segmenter = SpeechSegmenter(
        FixedWindowVad(),
        SpeechSegmenterConfig(
            pre_roll_ms=100,
            post_roll_ms=100,
            max_segment_ms=1_000,
            ring_buffer_ms=500,
        ),
    )

    assert segmenter.push(_chunk(0, 0)) == ()
    assert segmenter.push(_chunk(100, 1)) == ()
    assert segmenter.push(_chunk(200, 2)) == ()
    segments = segmenter.push(_chunk(300, 3))

    assert len(segments) == 1
    assert segments[0].start_timestamp_ms == 100
    assert segments[0].end_timestamp_ms == 400


def test_pipeline_rejects_timestamp_discontinuity_as_unsafe() -> None:
    pipeline = AudioPipeline(AlwaysVoiceVad(), FixedTranscriber())

    result = pipeline.process((_chunk(0, 0), _chunk(300, 1)))

    assert result.status == "unsafe_timestamp_discontinuity"


def test_pipeline_marks_queue_overflow_unsafe() -> None:
    transcriber = FixedTranscriber()
    pipeline = AudioPipeline(
        AlwaysVoiceVad(),
        transcriber,
        AudioPipelineConfig(
            max_queued_segments=1,
            segmenter=SpeechSegmenterConfig(
                pre_roll_ms=0,
                post_roll_ms=0,
                max_segment_ms=100,
                ring_buffer_ms=100,
            ),
        ),
    )

    result = pipeline.process((_chunk(0, 0), _chunk(100, 1)))

    assert result.status == "unsafe_queue_overflow"
    assert transcriber.calls == 0


def test_pipeline_does_not_convert_transcription_failure_to_empty_success() -> None:
    pipeline = AudioPipeline(AlwaysVoiceVad(), FailingTranscriber())

    result = pipeline.process((_chunk(0, 0),))

    assert result.status == "unsafe_transcription_failure"
