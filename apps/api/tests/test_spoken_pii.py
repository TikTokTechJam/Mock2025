from __future__ import annotations

from collections.abc import Sequence

from privastream_api.pipeline.contracts import AudioRedactionInterval, AudioSegment
from privastream_api.pipeline.spoken_pii import (
    EnergyVoiceActivityDetector,
    RedactionConfig,
    SpeechWindow,
    SpokenPiiDetector,
    TranscriptWord,
    detect_spoken_pii,
    normalize_redaction_intervals,
)


class FixedVad:
    def detect(self, segment: AudioSegment) -> Sequence[SpeechWindow]:
        return (SpeechWindow(segment.start_ms, segment.end_ms),)


class FixedTranscriber:
    def __init__(self, words: Sequence[TranscriptWord]) -> None:
        self.words = words
        self.calls = 0

    def transcribe(
        self, segment: AudioSegment, windows: Sequence[SpeechWindow]
    ) -> Sequence[TranscriptWord]:
        self.calls += 1
        return self.words


def _segment(start_ms: int = 0, duration_ms: int = 500) -> AudioSegment:
    sample_rate_hz = 16_000
    sample_count = duration_ms * sample_rate_hz // 1000
    return AudioSegment(
        start_ms=start_ms,
        end_ms=start_ms + duration_ms,
        sample_rate_hz=sample_rate_hz,
        channels=1,
        samples=(0.2,) * sample_count,
    )


def test_spoken_phone_number_is_normalized_to_one_padded_interval() -> None:
    words = tuple(
        TranscriptWord(text=word, start_ms=index * 30, end_ms=(index + 1) * 30)
        for index, word in enumerate("five five five one two three four five six seven".split())
    )
    intervals = detect_spoken_pii(words)

    assert len(intervals) == 1
    assert intervals[0].reason == "phone_number"
    assert intervals[0].start_ms == 0
    assert intervals[0].end_ms == 300


def test_email_speech_tokens_are_normalized() -> None:
    words = tuple(
        TranscriptWord(text=word, start_ms=index * 100, end_ms=(index + 1) * 100)
        for index, word in enumerate("alice at example dot com".split())
    )

    intervals = detect_spoken_pii(words)

    assert len(intervals) == 1
    assert intervals[0].reason == "email"
    assert intervals[0].start_ms == 0
    assert intervals[0].end_ms == 500


def test_silence_does_not_call_transcriber() -> None:
    segment = AudioSegment(
        start_ms=0,
        end_ms=300,
        sample_rate_hz=16_000,
        channels=1,
        samples=(0.0,) * 4_800,
    )
    transcriber = FixedTranscriber(())
    detector = SpokenPiiDetector(EnergyVoiceActivityDetector(), transcriber)

    assert detector.detect(segment) == ()
    assert transcriber.calls == 0


def test_pipeline_preserves_source_timestamp_offset() -> None:
    segment = _segment(start_ms=5_000)
    words = (
        TranscriptWord("alice", 5_100, 5_200),
        TranscriptWord("at", 5_200, 5_300),
        TranscriptWord("example", 5_300, 5_400),
        TranscriptWord("dot", 5_400, 5_500),
        TranscriptWord("com", 5_500, 5_600),
    )
    detector = SpokenPiiDetector(
        FixedVad(),
        FixedTranscriber(words),
        redaction=RedactionConfig(padding_ms=0),
    )

    intervals = detector.detect(segment)

    assert len(intervals) == 1
    assert intervals[0].start_ms == 5_100
    assert intervals[0].end_ms == 5_600


def test_intervals_are_padded_clamped_and_merged() -> None:
    segment = _segment(start_ms=1_000)
    intervals = (
        AudioRedactionInterval("spoken_pii", 1_050, 1_100, 0.7, "test", "phone_number"),
        AudioRedactionInterval("spoken_pii", 1_160, 1_200, 0.9, "test", "email"),
    )

    normalized = normalize_redaction_intervals(
        intervals, segment, RedactionConfig(padding_ms=50, merge_gap_ms=20)
    )

    assert len(normalized) == 1
    assert normalized[0].start_ms == 1_000
    assert normalized[0].end_ms == 1_250
    assert normalized[0].confidence == 0.9
    assert normalized[0].reason == "phone_number, email"
