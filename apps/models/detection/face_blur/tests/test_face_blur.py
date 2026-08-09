"""Tests for the privacy rules the face detector must not break.

Each test names the guarantee it protects. A change that makes one of these fail
is a privacy defect, not a test that needs updating.
"""

from __future__ import annotations

import json
import stat
from collections.abc import Sequence
from math import sqrt
from pathlib import Path
from typing import Any

import pytest
from face_blur import (
    BoundedFrameBuffer,
    DetectedFace,
    EnrollmentConsent,
    FaceBlurConfig,
    FaceBlurDetector,
    FaceClassification,
    FaceDetectorUnavailable,
    NormalizedBox,
    WhitelistStorageError,
    WhitelistStore,
    confidence_bucket,
    pad_and_clamp,
    redaction_confidence,
)
from face_blur.contracts import VideoFrame

MATCHING = (1.0, 0.0)
"""Identical to the enrolled reference, so cosine similarity is 1.0."""

BORDERLINE = (0.5, sqrt(0.75))
"""Cosine similarity 0.5 against ``MATCHING`` — inside the default uncertainty
band of [0.45, 0.55)."""

STRANGER = (0.0, 1.0)
"""Orthogonal to the reference, so similarity is 0.0."""

PIXELS = object()
"""Stand-in for frame pixels; the fake analyzer never looks at them."""


class FakeAnalyzer:
    """Returns scripted faces, one entry per call, in order."""

    def __init__(self, *frames: Sequence[DetectedFace]) -> None:
        self.frames = list(frames)
        self.calls = 0

    def analyze(self, pixels: Any) -> Sequence[DetectedFace]:
        index = min(self.calls, len(self.frames) - 1)
        self.calls += 1
        return self.frames[index]


class FailingAnalyzer:
    def analyze(self, pixels: Any) -> Sequence[DetectedFace]:
        raise RuntimeError("model crashed")


def face(
    x: float = 0.4,
    y: float = 0.4,
    width: float = 0.2,
    height: float = 0.2,
    score: float = 0.9,
    embedding: tuple[float, ...] | None = MATCHING,
) -> DetectedFace:
    return DetectedFace(x=x, y=y, width=width, height=height, score=score, embedding=embedding)


def enrolled(path: Path | None = None, config: FaceBlurConfig | None = None) -> WhitelistStore:
    store = WhitelistStore(path=path, config=config)
    store.enroll(
        EnrollmentConsent(identity_id="creator", consent_record_id="consent-1"),
        [(face(),)],
    )
    return store


def detector_for(
    analyzer: FakeAnalyzer | FailingAnalyzer,
    whitelist: WhitelistStore | None = None,
    config: FaceBlurConfig | None = None,
) -> tuple[FaceBlurDetector, BoundedFrameBuffer]:
    buffer = BoundedFrameBuffer()
    return (
        FaceBlurDetector(
            analyzer=analyzer, frames=buffer, whitelist=whitelist, config=config
        ),
        buffer,
    )


def run(
    detector: FaceBlurDetector, buffer: BoundedFrameBuffer, timestamp_ms: int = 0
) -> tuple[Any, ...]:
    frame = VideoFrame(width=1920, height=1080, timestamp_ms=timestamp_ms)
    buffer.submit(frame, PIXELS)
    return tuple(detector.detect(frame))


# --- Rule 2: no enrollment means everything is protected ---------------------


def test_every_face_is_protected_when_nothing_is_enrolled() -> None:
    detector, buffer = detector_for(FakeAnalyzer((face(), face(x=0.1, y=0.1))))

    regions = run(detector, buffer)

    assert len(regions) == 2
    assert {region.kind for region in regions} == {"face"}


def test_empty_whitelist_classifies_as_non_whitelisted_not_uncertain() -> None:
    assert WhitelistStore().classify(MATCHING) is FaceClassification.NON_WHITELISTED


# --- Recognition as a negative filter ----------------------------------------


def test_whitelisted_face_produces_no_region() -> None:
    detector, buffer = detector_for(FakeAnalyzer((face(),)), whitelist=enrolled())

    assert run(detector, buffer) == ()


def test_stranger_is_redacted_while_the_creator_is_not() -> None:
    detector, buffer = detector_for(
        FakeAnalyzer((face(), face(x=0.1, y=0.1, embedding=STRANGER))), whitelist=enrolled()
    )

    regions = run(detector, buffer)

    assert len(regions) == 1
    assert regions[0].x == pytest.approx(0.07, abs=1e-9)


# --- Rule 1: uncertain means protect -----------------------------------------


def test_borderline_similarity_is_uncertain_and_emitted() -> None:
    store = enrolled()

    assert store.classify(BORDERLINE) is FaceClassification.UNCERTAIN

    detector, buffer = detector_for(FakeAnalyzer((face(embedding=BORDERLINE),)), whitelist=store)
    assert len(run(detector, buffer)) == 1


def test_face_without_an_embedding_is_emitted() -> None:
    detector, buffer = detector_for(FakeAnalyzer((face(embedding=None),)), whitelist=enrolled())

    assert len(run(detector, buffer)) == 1


def test_face_too_small_to_classify_is_emitted_even_if_it_matches() -> None:
    tiny = face(width=0.01, height=0.01)
    detector, buffer = detector_for(FakeAnalyzer((tiny,)), whitelist=enrolled())

    assert len(run(detector, buffer)) == 1


def test_weak_detection_is_emitted_even_if_it_matches() -> None:
    detector, buffer = detector_for(FakeAnalyzer((face(score=0.2),)), whitelist=enrolled())

    assert len(run(detector, buffer)) == 1


def test_uncertainty_never_lowers_confidence_below_the_floor() -> None:
    config = FaceBlurConfig()

    for classification in (FaceClassification.UNCERTAIN, FaceClassification.NON_WHITELISTED):
        for score in (0.0, 0.5, 1.0):
            confidence = redaction_confidence(classification, score, config)
            assert config.min_redaction_confidence <= confidence <= 1.0

    assert confidence_bucket(redaction_confidence(FaceClassification.UNCERTAIN, 0.0, config)) == (
        "high"
    )


def test_confidence_is_undefined_for_a_whitelisted_face() -> None:
    with pytest.raises(ValueError):
        redaction_confidence(FaceClassification.WHITELISTED, 0.9, FaceBlurConfig())


# --- Rule 3: fail closed ------------------------------------------------------


def test_analyzer_failure_raises_instead_of_returning_no_regions() -> None:
    detector, buffer = detector_for(FailingAnalyzer())

    frame = VideoFrame(width=1920, height=1080, timestamp_ms=0)
    buffer.submit(frame, PIXELS)
    with pytest.raises(FaceDetectorUnavailable):
        detector.detect(frame)


def test_missing_frame_pixels_raise() -> None:
    detector, _ = detector_for(FakeAnalyzer((face(),)))

    with pytest.raises(FaceDetectorUnavailable):
        detector.detect(VideoFrame(width=1920, height=1080, timestamp_ms=0))


def test_frame_pixels_are_released_after_a_failure() -> None:
    detector, buffer = detector_for(FailingAnalyzer())
    frame = VideoFrame(width=1920, height=1080, timestamp_ms=0)
    buffer.submit(frame, PIXELS)

    with pytest.raises(FaceDetectorUnavailable):
        detector.detect(frame)

    assert len(buffer) == 0


def test_frame_pixels_are_released_after_success() -> None:
    detector, buffer = detector_for(FakeAnalyzer((face(),)))

    run(detector, buffer)

    assert len(buffer) == 0


# --- Coverage: padding, clamping, hold-over ----------------------------------


def test_padding_is_applied_before_clamping_at_the_frame_edge() -> None:
    padded = pad_and_clamp(NormalizedBox(x=0.0, y=0.4, width=0.2, height=0.2), padding=0.5)

    # Padding first gives [-0.1, 0.3]; clamping keeps the whole in-frame margin.
    assert padded.x == pytest.approx(0.0)
    assert padded.width == pytest.approx(0.3)


def test_a_padded_region_never_escapes_the_frame() -> None:
    detector, buffer = detector_for(
        FakeAnalyzer((face(x=0.85, y=0.85, width=0.2, height=0.2),)),
        config=FaceBlurConfig(padding=1.0),
    )

    region = run(detector, buffer)[0]

    assert region.x + region.width <= 1.0
    assert region.y + region.height <= 1.0


def test_a_lost_track_keeps_being_emitted_then_stops() -> None:
    config = FaceBlurConfig(hold_over_ms=100, ema_alpha=1.0)
    detector, buffer = detector_for(FakeAnalyzer((face(),), ()), config=config)

    live = run(detector, buffer, timestamp_ms=0)
    held = run(detector, buffer, timestamp_ms=40)
    still_held = run(detector, buffer, timestamp_ms=100)
    expired = run(detector, buffer, timestamp_ms=200)

    assert len(live) == len(held) == len(still_held) == 1
    assert held[0].track_id == live[0].track_id
    assert held[0].timestamp_ms == 40
    assert held[0].confidence == live[0].confidence
    assert expired == ()


def test_track_ids_are_stable_across_frames() -> None:
    detector, buffer = detector_for(FakeAnalyzer((face(),), (face(x=0.41),)))

    first = run(detector, buffer, timestamp_ms=0)
    second = run(detector, buffer, timestamp_ms=33)

    assert first[0].track_id == second[0].track_id


def test_smoothing_lags_the_raw_box_rather_than_snapping_to_it() -> None:
    config = FaceBlurConfig(ema_alpha=0.5, padding=0.0)
    detector, buffer = detector_for(FakeAnalyzer((face(x=0.4),), (face(x=0.5),)), config=config)

    run(detector, buffer, timestamp_ms=0)
    smoothed = run(detector, buffer, timestamp_ms=33)

    assert len(smoothed) == 1, "the moved face must continue the same track, not start a new one"
    assert smoothed[0].x == pytest.approx(0.45)


# --- Output contract ----------------------------------------------------------


def test_emitted_regions_match_the_output_contract() -> None:
    detector, buffer = detector_for(FakeAnalyzer((face(),)), config=FaceBlurConfig())

    region = run(detector, buffer, timestamp_ms=1234)[0]

    assert region.kind == "face"
    assert region.timestamp_ms == 1234
    assert region.detector == "face-detector-v1"
    assert region.track_id is not None
    assert 0.0 <= region.confidence <= 1.0


def test_an_invalid_region_from_the_model_fails_the_frame() -> None:
    class BadAnalyzer:
        def analyze(self, pixels: Any) -> Sequence[DetectedFace]:
            return (DetectedFace(x=float("nan"), y=0.1, width=0.1, height=0.1, score=0.9),)

    detector, buffer = detector_for(BadAnalyzer())  # type: ignore[arg-type]
    frame = VideoFrame(width=1920, height=1080, timestamp_ms=0)
    buffer.submit(frame, PIXELS)

    with pytest.raises(FaceDetectorUnavailable):
        detector.detect(frame)


# --- Enrollment ---------------------------------------------------------------


def test_reference_images_are_rejected_for_stated_reasons() -> None:
    store = WhitelistStore()

    result = store.enroll(
        EnrollmentConsent(identity_id="creator", consent_record_id="consent-1"),
        [
            (),
            (face(), face(x=0.1)),
            (face(width=0.01, height=0.01),),
            (face(embedding=None),),
            (face(),),
        ],
    )

    assert result.accepted == 1
    assert [rejection.reason for rejection in result.rejections] == [
        "no_face_detected",
        "multiple_faces_detected",
        "face_too_small",
        "unusable_embedding",
    ]
    assert result.is_usable


def test_an_identity_with_no_usable_reference_is_not_enrolled() -> None:
    store = WhitelistStore()

    result = store.enroll(
        EnrollmentConsent(identity_id="creator", consent_record_id="consent-1"), [()]
    )

    assert not result.is_usable
    assert store.is_empty


def test_the_store_never_exposes_embeddings() -> None:
    store = enrolled()

    assert repr(store) == "WhitelistStore(identities=1)"
    assert store.identity_ids() == ("creator",)
    assert store.reference_count("creator") == 1
    assert store.consent_record_id("creator") == "consent-1"


# --- Revocation and the JSON database ----------------------------------------


def test_enrollment_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "whitelist.json"
    enrolled(path=path)

    reopened = WhitelistStore(path=path)

    assert reopened.identity_ids() == ("creator",)
    assert reopened.classify(MATCHING) is FaceClassification.WHITELISTED


def test_the_database_is_owner_readable_only(tmp_path: Path) -> None:
    path = tmp_path / "whitelist.json"
    enrolled(path=path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_revocation_removes_the_identity_from_disk_and_memory(tmp_path: Path) -> None:
    path = tmp_path / "whitelist.json"
    store = enrolled(path=path)

    assert store.revoke("creator")

    assert store.is_empty
    assert store.classify(MATCHING) is FaceClassification.NON_WHITELISTED
    assert json.loads(path.read_text(encoding="utf-8"))["identities"] == {}
    assert WhitelistStore(path=path).is_empty


def test_a_revoked_creator_is_protected_on_the_next_frame(tmp_path: Path) -> None:
    store = enrolled(path=tmp_path / "whitelist.json")
    detector, buffer = detector_for(FakeAnalyzer((face(),)), whitelist=store)

    assert run(detector, buffer, timestamp_ms=0) == ()

    store.revoke("creator")

    assert len(run(detector, buffer, timestamp_ms=33)) == 1


def test_a_corrupt_database_raises_rather_than_loading_part_of_it(tmp_path: Path) -> None:
    path = tmp_path / "whitelist.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(WhitelistStorageError):
        WhitelistStore(path=path)


def test_a_missing_database_is_an_empty_whitelist(tmp_path: Path) -> None:
    store = WhitelistStore(path=tmp_path / "absent.json")

    assert store.is_empty
