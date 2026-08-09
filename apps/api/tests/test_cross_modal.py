from __future__ import annotations

import pytest

from privastream_api.pipeline.contracts import AudioRedactionInterval, VideoFrame
from privastream_api.pipeline.cross_modal import (
    CrossModalConfig,
    CrossModalSynchronizer,
    FaceGeometry,
)


def _frame(timestamp_ms: int) -> VideoFrame:
    return VideoFrame(width=100, height=100, timestamp_ms=timestamp_ms)


def _face(
    *,
    x: float = 0.2,
    y: float = 0.1,
    width: float = 0.3,
    height: float = 0.4,
    track_id: str | None = "speaker",
    active_speaker_score: float | None = None,
) -> FaceGeometry:
    return FaceGeometry(
        x=x,
        y=y,
        width=width,
        height=height,
        confidence=0.95,
        track_id=track_id,
        active_speaker_score=active_speaker_score,
    )


def _interval(start_ms: int, end_ms: int) -> AudioRedactionInterval:
    return AudioRedactionInterval(
        kind="spoken_pii",
        start_ms=start_ms,
        end_ms=end_ms,
        confidence=0.9,
        detector="test-spoken-pii",
        reason="phone_number",
    )


def test_sensitive_interval_releases_the_overlapping_frame_deterministically() -> None:
    synchronizer = CrossModalSynchronizer(
        CrossModalConfig(frame_duration_ms=50, pre_padding_ms=0, post_padding_ms=0)
    )

    assert synchronizer.submit_frame(_frame(0), (_face(),)).status == "pending"
    first = synchronizer.ingest_audio((), watermark_ms=50)
    assert first.decisions[0].status == "no_sensitive_speech"

    assert synchronizer.submit_frame(_frame(100), (_face(),)).status == "pending"
    released = synchronizer.ingest_audio((_interval(100, 150),), watermark_ms=150)

    decision = released.decisions[0]
    assert decision.status == "protected"
    assert decision.association == "mouth"
    assert decision.intervals == (_interval(100, 150),)
    assert len(decision.regions) == 1
    assert decision.regions[0].y == pytest.approx(0.32)
    assert decision.regions[0].height == pytest.approx(0.16)


def test_padding_selects_an_interval_before_the_frame_and_after_the_audio() -> None:
    synchronizer = CrossModalSynchronizer(
        CrossModalConfig(frame_duration_ms=30, pre_padding_ms=20, post_padding_ms=20)
    )

    assert synchronizer.submit_frame(_frame(100), (_face(),)).status == "pending"
    released = synchronizer.ingest_audio((_interval(110, 115),), watermark_ms=150)

    assert released.decisions[0].status == "protected"


def test_ambiguous_faces_use_full_face_fallback_for_all_candidates() -> None:
    synchronizer = CrossModalSynchronizer(
        CrossModalConfig(frame_duration_ms=30, pre_padding_ms=0, post_padding_ms=0)
    )
    faces = (_face(x=0.1, track_id="left"), _face(x=0.6, track_id="right"))

    synchronizer.submit_frame(_frame(0), faces)
    released = synchronizer.ingest_audio((_interval(0, 20),), watermark_ms=30)

    decision = released.decisions[0]
    assert decision.status == "protected"
    assert decision.association == "face_fallback"
    assert [region.track_id for region in decision.regions] == ["left", "right"]
    assert decision.regions[0].width == 0.3


def test_unique_active_speaker_hint_allows_mouth_protection() -> None:
    synchronizer = CrossModalSynchronizer(
        CrossModalConfig(frame_duration_ms=30, pre_padding_ms=0, post_padding_ms=0)
    )
    faces = (
        _face(x=0.1, track_id="quiet", active_speaker_score=0.4),
        _face(x=0.6, track_id="speaker", active_speaker_score=0.9),
    )

    synchronizer.submit_frame(_frame(0), faces)
    released = synchronizer.ingest_audio((_interval(0, 20),), watermark_ms=30)

    decision = released.decisions[0]
    assert decision.association == "mouth"
    assert [region.track_id for region in decision.regions] == ["speaker"]


def test_missing_face_association_is_an_explicit_unsafe_result() -> None:
    synchronizer = CrossModalSynchronizer(
        CrossModalConfig(frame_duration_ms=30, pre_padding_ms=0, post_padding_ms=0)
    )

    synchronizer.submit_frame(_frame(0), ())
    released = synchronizer.ingest_audio((_interval(0, 20),), watermark_ms=30)

    decision = released.decisions[0]
    assert released.status == "unsafe"
    assert decision.status == "unsafe_no_face_association"
    assert not decision.cross_modal_complete


def test_buffer_overflow_does_not_wait_indefinitely() -> None:
    synchronizer = CrossModalSynchronizer(
        CrossModalConfig(
            frame_duration_ms=30,
            pre_padding_ms=0,
            post_padding_ms=0,
            max_pending_frames=1,
            max_buffer_ms=100,
        )
    )

    synchronizer.submit_frame(_frame(0), (_face(),))
    overflow = synchronizer.submit_frame(_frame(30), (_face(),))

    assert overflow.status == "unsafe"
    assert overflow.decisions[0].status == "unsafe_buffer_overflow"
    assert synchronizer.pending_frames == 1
    assert synchronizer.metrics.buffer_overflow_frames == 1


def test_late_audio_decisions_are_returned_and_counted() -> None:
    synchronizer = CrossModalSynchronizer(
        CrossModalConfig(frame_duration_ms=30, pre_padding_ms=0, post_padding_ms=0)
    )

    synchronizer.ingest_audio((), watermark_ms=100)
    update = synchronizer.ingest_audio((_interval(10, 20),), watermark_ms=100)

    assert update.status == "unsafe"
    assert update.reason_code == "unsafe_late_audio"
    assert update.late_intervals == (_interval(10, 20),)
    assert synchronizer.metrics.late_audio_decisions == 1


def test_timestamp_discontinuity_fails_pending_frames_closed() -> None:
    synchronizer = CrossModalSynchronizer()

    synchronizer.submit_frame(_frame(100), (_face(),))
    update = synchronizer.submit_frame(_frame(99), (_face(),))

    assert update.status == "unsafe"
    assert update.reason_code == "unsafe_timestamp_discontinuity"
    assert update.decisions[0].status == "unsafe_timestamp_discontinuity"
