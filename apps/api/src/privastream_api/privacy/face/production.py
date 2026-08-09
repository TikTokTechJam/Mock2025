"""Production integration boundaries for the standalone face module.

This module owns only the application adapter, enrollment lifecycle, and
readiness surface. Detection, embedding extraction, and matching remain in
``privastream_api.privacy.face``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Literal

from privastream_api.pipeline.contracts import VideoFrame, VideoRegionDetection
from privastream_api.pipeline.video import VideoOrchestrator
from privastream_api.privacy.face.detector import (
    CreatorFaceDetector,
    CreatorFaceDetectorConfig,
)
from privastream_api.privacy.face.enrollment import (
    ConsentRequiredError,
    CreatorEnrollmentStatus,
    CreatorFaceEnrollmentService,
    EnrollmentResult,
    FaceEnrollmentConfig,
    FaceEnrollmentError,
    InMemoryCreatorEmbeddingStore,
)
from privastream_api.privacy.face.insightface_adapter import (
    InsightFaceConfig,
    InsightFaceFaceModel,
)
from privastream_api.privacy.face.models import FaceModel
from privastream_api.privacy.vision.service import (
    DetectorError,
    DetectorExecutionError,
    DetectorUnavailableError,
    FrameContext,
)

FaceEnrollmentLifecycle = Literal[
    "not_enrolled",
    "enrolling",
    "enrolled",
    "replacing",
    "deleting",
]
FaceReadinessReason = Literal[
    "ready",
    "model_unavailable",
    "enrollment_not_found",
    "enrollment_corrupt",
    "enrollment_rejected",
    "detector_unavailable",
    "detector_error",
]
FaceImageProvider = Callable[[VideoFrame], object]
FaceImageDecoder = Callable[[bytes], object]


class EnrollmentAlreadyExistsError(RuntimeError):
    """A create operation was requested for an existing creator enrollment."""


class EnrollmentNotFoundError(RuntimeError):
    """A replace operation was requested without an existing enrollment."""


@dataclass(frozen=True, slots=True)
class FaceEnrollmentLifecycleStatus:
    """Safe lifecycle state for the creator enrollment repository."""

    state: FaceEnrollmentLifecycle
    enrollment: CreatorEnrollmentStatus | None
    reason_code: FaceReadinessReason | None


@dataclass(frozen=True, slots=True)
class FaceOrchestrationConfig:
    """#4 scheduler settings for the production face adapter."""

    name: str = "face"
    cadence_frames: int = 1
    timeout_ms: int = 100
    ttl_ms: int = 250
    max_concurrency: int = 1

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if self.cadence_frames <= 0:
            raise ValueError("cadence_frames must be positive")
        if self.timeout_ms <= 0 or self.ttl_ms <= 0:
            raise ValueError("timeout_ms and ttl_ms must be positive")
        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")


@dataclass(frozen=True, slots=True)
class FaceProductionConfig:
    """Production choices delegated to the standalone face implementation."""

    model: InsightFaceConfig = field(default_factory=InsightFaceConfig)
    detector: CreatorFaceDetectorConfig = field(default_factory=CreatorFaceDetectorConfig)
    enrollment: FaceEnrollmentConfig = field(default_factory=FaceEnrollmentConfig)
    orchestration: FaceOrchestrationConfig = field(default_factory=FaceOrchestrationConfig)
    required: bool = True
    max_sample_bytes: int = 5_000_000

    def __post_init__(self) -> None:
        if self.max_sample_bytes <= 0:
            raise ValueError("max_sample_bytes must be positive")

    @classmethod
    def from_environment(cls) -> "FaceProductionConfig":
        """Read deployment choices without loading a model or changing #18 policy."""

        providers = tuple(
            provider.strip()
            for provider in os.getenv(
                "PRIVASTREAM_FACE_PROVIDERS", "CPUExecutionProvider"
            ).split(",")
            if provider.strip()
        )
        model = InsightFaceConfig(
            model_root=Path(os.getenv("PRIVASTREAM_FACE_MODEL_ROOT", "models/insightface")),
            model_name=os.getenv("PRIVASTREAM_FACE_MODEL_NAME", "buffalo_l"),
            providers=providers or ("CPUExecutionProvider",),
            context_id=int(os.getenv("PRIVASTREAM_FACE_CONTEXT_ID", "-1")),
            detection_size=int(os.getenv("PRIVASTREAM_FACE_DETECTION_SIZE", "640")),
        )
        detector = CreatorFaceDetectorConfig(
            detector_id=os.getenv("PRIVASTREAM_FACE_DETECTOR_ID", "insightface-arcface"),
            minimum_detection_confidence=float(
                os.getenv("PRIVASTREAM_FACE_MIN_DETECTION_CONFIDENCE", "0.5")
            ),
            minimum_quality=float(os.getenv("PRIVASTREAM_FACE_MIN_QUALITY", "0.5")),
            creator_match_threshold=float(
                os.getenv("PRIVASTREAM_FACE_MATCH_THRESHOLD", "0.55")
            ),
            ambiguity_margin=float(os.getenv("PRIVASTREAM_FACE_AMBIGUITY_MARGIN", "0.05")),
        )
        orchestration = FaceOrchestrationConfig(
            name=os.getenv("PRIVASTREAM_FACE_SCHEDULER_NAME", "face"),
            cadence_frames=int(os.getenv("PRIVASTREAM_FACE_CADENCE_FRAMES", "1")),
            timeout_ms=int(os.getenv("PRIVASTREAM_FACE_TIMEOUT_MS", "100")),
            ttl_ms=int(os.getenv("PRIVASTREAM_FACE_TTL_MS", "250")),
            max_concurrency=int(os.getenv("PRIVASTREAM_FACE_MAX_CONCURRENCY", "1")),
        )
        return cls(model=model, detector=detector, orchestration=orchestration)


class FaceEnrollmentRepository:
    """Process-local production repository with explicit #3 lifecycle states.

    The repository owns the lifecycle around #18's replaceable embedding store.
    The current foundation has no database persistence contract, so the
    repository is intentionally process-local and keeps raw images out of its
    state. A durable implementation can replace this boundary without changing
    the enrollment service or detector.
    """

    def __init__(
        self,
        model: FaceModel,
        *,
        config: FaceEnrollmentConfig | None = None,
        store: InMemoryCreatorEmbeddingStore | None = None,
    ) -> None:
        self.store = store or InMemoryCreatorEmbeddingStore()
        self.service = CreatorFaceEnrollmentService(model, self.store, config)
        self._state: FaceEnrollmentLifecycle = (
            "enrolled" if self.store.status() is not None else "not_enrolled"
        )
        self._reason_code: FaceReadinessReason | None = (
            None if self._state == "enrolled" else "enrollment_not_found"
        )
        self._lock = RLock()

    def status(self) -> FaceEnrollmentLifecycleStatus:
        with self._lock:
            enrollment = self.service.status()
            if self._state == "enrolled" and enrollment is None:
                return FaceEnrollmentLifecycleStatus(
                    state="not_enrolled",
                    enrollment=None,
                    reason_code="enrollment_corrupt",
                )
            return FaceEnrollmentLifecycleStatus(
                state=self._state,
                enrollment=enrollment,
                reason_code=self._reason_code,
            )

    def create(self, samples: Sequence[object], *, consent: bool) -> EnrollmentResult:
        with self._lock:
            if self.service.status() is not None:
                raise EnrollmentAlreadyExistsError("creator enrollment already exists")
            return self._enroll(samples, consent=consent, replacing=False)

    def replace(self, samples: Sequence[object], *, consent: bool) -> EnrollmentResult:
        with self._lock:
            if self.service.status() is None:
                raise EnrollmentNotFoundError("creator enrollment does not exist")
            return self._enroll(samples, consent=consent, replacing=True)

    def _enroll(
        self,
        samples: Sequence[object],
        *,
        consent: bool,
        replacing: bool,
    ) -> EnrollmentResult:
        previous_state: FaceEnrollmentLifecycle = (
            "replacing" if replacing else "not_enrolled"
        )
        previous_reason: FaceReadinessReason | None = None if replacing else "enrollment_not_found"
        self._state = "replacing" if replacing else "enrolling"
        self._reason_code = None
        try:
            result = self.service.enroll(samples, consent=consent)
        except ConsentRequiredError:
            self._state = "enrolled" if replacing else previous_state
            self._reason_code = "enrollment_rejected" if replacing else "enrollment_not_found"
            raise
        except FaceEnrollmentError:
            self._state = "enrolled" if replacing else previous_state
            self._reason_code = previous_reason
            raise
        if result.enrolled:
            self._state = "enrolled"
            self._reason_code = None
            return result

        rejection_reasons = {rejection.reason for rejection in result.rejections}
        if "detector_unavailable" in rejection_reasons:
            reason: FaceReadinessReason = "detector_unavailable"
        elif "detector_error" in rejection_reasons:
            reason = "detector_error"
        else:
            reason = "enrollment_rejected"
        self._state = "enrolled" if replacing else previous_state
        self._reason_code = reason
        return result

    def delete(self) -> bool:
        with self._lock:
            if self.service.status() is None:
                self._state = "not_enrolled"
                self._reason_code = "enrollment_not_found"
                return False
            self._state = "deleting"
            self._reason_code = None
            try:
                deleted = self.service.delete()
            except Exception:
                self._state = "enrolled"
                self._reason_code = "enrollment_corrupt"
                raise
            self._state = "not_enrolled"
            self._reason_code = "enrollment_not_found"
            return deleted


class FaceReadinessTracker:
    """Expose sanitized face capability state for the future #13 gate."""

    def __init__(
        self,
        repository: FaceEnrollmentRepository,
        config: FaceProductionConfig,
        *,
        model_available: Callable[[], bool],
    ) -> None:
        self.repository = repository
        self.config = config
        self._model_available = model_available
        self._last_detector_failure: FaceReadinessReason | None = None
        self._lock = RLock()

    def record_success(self) -> None:
        with self._lock:
            self._last_detector_failure = None

    def record_failure(self, reason: FaceReadinessReason) -> None:
        if reason not in {"detector_unavailable", "detector_error"}:
            raise ValueError("invalid detector failure reason")
        with self._lock:
            self._last_detector_failure = reason

    def snapshot(self) -> "FaceCapabilityReadiness":
        with self._lock:
            enrollment = self.repository.status()
            reason = self._last_detector_failure
            if reason is None and not self._model_available():
                reason = "model_unavailable"
            if reason is None:
                reason = enrollment.reason_code
            ready = reason is None and enrollment.state == "enrolled"
            return FaceCapabilityReadiness(
                enabled=True,
                required=self.config.required,
                ready=ready,
                reason_code=reason,
                detector_id=self.config.detector.detector_id,
                model_name=self.config.model.model_name,
                providers=self.config.model.providers,
                enrollment_state=enrollment.state,
            )


@dataclass(frozen=True, slots=True)
class FaceCapabilityReadiness:
    """Safe capability input consumed by #13; it is not a publication decision."""

    enabled: bool
    required: bool
    ready: bool
    reason_code: FaceReadinessReason | None
    detector_id: str
    model_name: str
    providers: tuple[str, ...]
    enrollment_state: FaceEnrollmentLifecycle


class FaceVideoDetector:
    """Thin adapter from #18's detector to #4's canonical video interface."""

    kind: Literal["face_bystander"] = "face_bystander"

    def __init__(
        self,
        detector: CreatorFaceDetector,
        readiness: FaceReadinessTracker,
        *,
        image_provider: FaceImageProvider | None = None,
    ) -> None:
        self.detector = detector
        self.readiness = readiness
        self._image_provider = image_provider or _payload_image

    async def detect(self, frame: VideoFrame) -> list[VideoRegionDetection]:
        image = self._image_provider(frame)
        if image is None:
            error = DetectorExecutionError("face adapter requires a model-compatible source image")
            self.readiness.record_failure("detector_error")
            raise error
        try:
            regions = await self.detector.detect(FrameContext(image=image, source=frame))
        except DetectorUnavailableError:
            self.readiness.record_failure("detector_unavailable")
            raise
        except DetectorError:
            self.readiness.record_failure("detector_error")
            raise
        except Exception:
            self.readiness.record_failure("detector_error")
            raise
        self.readiness.record_success()
        return regions


def _payload_image(frame: VideoFrame) -> object:
    return frame.payload


def _default_decode_image(payload: bytes) -> object:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise DetectorUnavailableError(
            "OpenCV and NumPy are required for HTTP face enrollment; install the face extra"
        ) from exc
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise FaceEnrollmentError("enrollment sample is not a readable image")
    return image


class ProductionFaceIntegration:
    """Own the #5 production wiring while delegating face behavior to #18."""

    def __init__(
        self,
        model: FaceModel,
        *,
        config: FaceProductionConfig | None = None,
        repository: FaceEnrollmentRepository | None = None,
        image_decoder: FaceImageDecoder | None = None,
        model_available: Callable[[], bool] | None = None,
    ) -> None:
        self.config = config or FaceProductionConfig()
        self.repository = repository or FaceEnrollmentRepository(
            model,
            config=self.config.enrollment,
        )
        self.readiness = FaceReadinessTracker(
            self.repository,
            self.config,
            model_available=model_available or (lambda: True),
        )
        self.detector = CreatorFaceDetector(
            model,
            self.repository.store,
            self.config.detector,
        )
        self.adapter = FaceVideoDetector(self.detector, self.readiness)
        self._image_decoder = image_decoder or _default_decode_image

    @classmethod
    def from_environment(cls) -> "ProductionFaceIntegration":
        config = FaceProductionConfig.from_environment()
        model = InsightFaceFaceModel(config.model)
        return cls(
            model,
            config=config,
            model_available=lambda: (
                config.model.model_root / "models" / config.model.model_name
            ).is_dir(),
        )

    def register(self, orchestrator: VideoOrchestrator) -> FaceVideoDetector:
        adapter = register_face_detector(
            orchestrator,
            self.detector,
            config=self.config.orchestration,
            readiness=self.readiness,
        )
        self.adapter = adapter
        return adapter

    def create_enrollment(self, samples: Sequence[object], *, consent: bool) -> EnrollmentResult:
        return self.repository.create(samples, consent=consent)

    def replace_enrollment(
        self,
        samples: Sequence[object],
        *,
        consent: bool,
    ) -> EnrollmentResult:
        return self.repository.replace(samples, consent=consent)

    def delete_enrollment(self) -> bool:
        return self.repository.delete()

    def enrollment_status(self) -> FaceEnrollmentLifecycleStatus:
        return self.repository.status()

    def readiness_status(self) -> FaceCapabilityReadiness:
        return self.readiness.snapshot()

    def decode_sample(self, payload: bytes) -> object:
        return self._image_decoder(payload)


def register_face_detector(
    orchestrator: VideoOrchestrator,
    detector: CreatorFaceDetector,
    *,
    config: FaceOrchestrationConfig | None = None,
    readiness: FaceReadinessTracker | None = None,
    image_provider: FaceImageProvider | None = None,
) -> FaceVideoDetector:
    """Register the #18 detector with #4 without importing model code there."""

    if readiness is None:
        raise ValueError("readiness tracker is required for production registration")
    policy = config or FaceOrchestrationConfig()
    adapter = FaceVideoDetector(detector, readiness, image_provider=image_provider)
    orchestrator.register(
        policy.name,
        adapter,
        cadence_frames=policy.cadence_frames,
        timeout_ms=policy.timeout_ms,
        ttl_ms=policy.ttl_ms,
        max_concurrency=policy.max_concurrency,
    )
    return adapter


__all__ = [
    "EnrollmentAlreadyExistsError",
    "EnrollmentNotFoundError",
    "FaceCapabilityReadiness",
    "FaceEnrollmentLifecycle",
    "FaceEnrollmentLifecycleStatus",
    "FaceEnrollmentRepository",
    "FaceOrchestrationConfig",
    "FaceProductionConfig",
    "FaceReadinessTracker",
    "FaceVideoDetector",
    "ProductionFaceIntegration",
    "register_face_detector",
]
