import asyncio

import pytest

from privastream_api.pipeline.contracts import VideoFrame
from privastream_api.privacy.face import (
    ConsentRequiredError,
    CreatorFaceDetector,
    CreatorFaceDetectorConfig,
    CreatorFaceEnrollmentService,
    FaceObservation,
    InMemoryCreatorEmbeddingStore,
    InsightFaceFaceModel,
)
from privastream_api.privacy.vision.service import DetectorExecutionError, FrameContext


class FakeFaceModel:
    def __init__(self, results: dict[object, tuple[FaceObservation, ...]]) -> None:
        self.results = results

    def detect(self, image: object) -> tuple[FaceObservation, ...]:
        return self.results.get(image, ())


def _observation(
    embedding: tuple[float, ...] | None,
    *,
    x1: float = 20,
    y1: float = 10,
    x2: float = 60,
    y2: float = 70,
    confidence: float = 0.95,
    quality: float = 0.95,
) -> FaceObservation:
    return FaceObservation(
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
        detection_confidence=confidence,
        quality=quality,
        embedding=embedding,
    )


def _context(image: object = "frame") -> FrameContext:
    return FrameContext(image=image, source=VideoFrame(width=100, height=100, timestamp_ms=123))


def test_enrollment_requires_consent_and_rejects_ambiguous_samples() -> None:
    model = FakeFaceModel(
        {
            "none": (),
            "multi": (_observation((1.0, 0.0)), _observation((1.0, 0.0))),
            "valid": (_observation((1.0, 0.0)),),
        }
    )
    service = CreatorFaceEnrollmentService(model, InMemoryCreatorEmbeddingStore())

    with pytest.raises(ConsentRequiredError):
        service.enroll(["valid"], consent=False)

    result = service.enroll(["none", "multi", "valid"], consent=True)

    assert result.enrolled
    assert result.accepted_samples == 1
    assert result.status is not None
    assert result.status.sample_count == 1
    assert [rejection.reason for rejection in result.rejections] == [
        "no_face",
        "ambiguous_multi_face",
    ]


def test_enrollment_replaces_and_deletes_without_exposing_embedding_values() -> None:
    model = FakeFaceModel(
        {
            "creator": (_observation((1.0, 0.0)),),
            "replacement": (_observation((0.0, 1.0)),),
        }
    )
    store = InMemoryCreatorEmbeddingStore(clock_ms=lambda: 100)
    service = CreatorFaceEnrollmentService(model, store)

    first = service.enroll(["creator"], consent=True)
    second = service.enroll(["replacement"], consent=True)

    assert first.status is not None
    assert second.status is not None
    assert first.status.enrollment_id != second.status.enrollment_id
    assert repr(store).find("1.0") == -1
    assert service.delete()
    assert service.status() is None
    assert not service.delete()


def test_no_enrollment_protects_every_detected_face_and_normalizes_bounds() -> None:
    model = FakeFaceModel(
        {
            "frame": (
                _observation((1.0, 0.0), x1=-10, y1=-5, x2=60, y2=70),
                _observation((0.0, 1.0), x1=70, y1=70, x2=120, y2=120),
            )
        }
    )
    detector = CreatorFaceDetector(model, InMemoryCreatorEmbeddingStore())

    regions = asyncio.run(detector.detect(_context()))

    assert len(regions) == 2
    assert all(region.kind == "face_bystander" for region in regions)
    assert regions[0].x == 0
    assert regions[0].y == 0
    assert regions[0].width == 0.6
    assert regions[1].x == 0.7
    assert regions[1].width == 0.3


def test_creator_match_is_hidden_but_unknown_and_ambiguous_faces_are_protected() -> None:
    model = FakeFaceModel(
        {
            "creator": (_observation((1.0, 0.0)),),
            "mixed": (
                _observation((1.0, 0.0)),
                _observation((0.0, 1.0)),
                _observation((0.6, 0.8)),
                _observation(None, confidence=0.95),
                _observation((1.0, 0.0), confidence=0.2),
            ),
        }
    )
    store = InMemoryCreatorEmbeddingStore()
    enrollment = CreatorFaceEnrollmentService(model, store)
    enrollment.enroll(["creator"], consent=True)
    detector = CreatorFaceDetector(
        model,
        store,
        CreatorFaceDetectorConfig(creator_match_threshold=0.55, ambiguity_margin=0.05),
    )

    regions = asyncio.run(detector.detect(_context("mixed")))

    assert len(regions) == 4
    assert all(region.kind == "face_bystander" for region in regions)


def test_deleted_enrollment_treats_previous_creator_as_unknown() -> None:
    model = FakeFaceModel({"creator": (_observation((1.0, 0.0)),)})
    store = InMemoryCreatorEmbeddingStore()
    enrollment = CreatorFaceEnrollmentService(model, store)
    enrollment.enroll(["creator"], consent=True)
    detector = CreatorFaceDetector(model, store)

    assert asyncio.run(detector.detect(_context("creator"))) == []
    enrollment.delete()
    assert len(asyncio.run(detector.detect(_context("creator")))) == 1


class FailingFaceModel:
    def detect(self, image: object) -> tuple[FaceObservation, ...]:
        raise RuntimeError("embedding should not be logged")


def test_face_model_failure_is_explicit() -> None:
    detector = CreatorFaceDetector(FailingFaceModel(), InMemoryCreatorEmbeddingStore())

    with pytest.raises(DetectorExecutionError, match="^face detector failed$"):
        asyncio.run(detector.detect(_context()))


class FakeImage:
    shape = (100, 200, 3)


class FakeInsightFace:
    def prepare(self, *, ctx_id: int, det_size: tuple[int, int]) -> None:
        assert ctx_id == -1
        assert det_size == (640, 640)

    def get(self, image: object) -> list[object]:
        return [
            type(
                "Face",
                (),
                {
                    "bbox": [-4, 10, 80, 60],
                    "det_score": 0.9,
                    "normed_embedding": [1.0, 0.0],
                },
            )()
        ]


def test_insightface_adapter_maps_local_model_output_without_importing_it_at_module_load() -> None:
    model = InsightFaceFaceModel(analysis=FakeInsightFace())

    observations = model.detect(FakeImage())

    assert len(observations) == 1
    assert observations[0].x1 == -4
    assert observations[0].embedding == (1.0, 0.0)
