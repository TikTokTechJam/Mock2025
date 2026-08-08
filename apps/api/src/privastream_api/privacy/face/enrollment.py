"""Explicit creator enrollment and in-memory embedding lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from math import isfinite
from secrets import token_hex
from threading import RLock
from time import time_ns

from privastream_api.pipeline.contracts import VideoDetectorExecutionError, VideoDetectorUnavailable
from privastream_api.privacy.face.models import FaceEmbedding, FaceModel, normalize_embedding
from privastream_api.privacy.vision.service import DetectorError


def _now_ms() -> int:
    return time_ns() // 1_000_000


class FaceEnrollmentError(ValueError):
    """The enrollment request cannot produce a valid creator identity."""


class ConsentRequiredError(FaceEnrollmentError):
    """Enrollment was attempted without explicit creator consent."""


@dataclass(frozen=True, slots=True)
class FaceEnrollmentConfig:
    """Bounds and quality requirements for a small consented sample set."""

    max_samples: int = 8
    min_valid_samples: int = 1
    minimum_detection_confidence: float = 0.5
    minimum_quality: float = 0.5

    def __post_init__(self) -> None:
        if self.max_samples <= 0:
            raise ValueError("max_samples must be positive")
        if self.min_valid_samples <= 0 or self.min_valid_samples > self.max_samples:
            raise ValueError("min_valid_samples must be within max_samples")
        for name, value in (
            ("minimum_detection_confidence", self.minimum_detection_confidence),
            ("minimum_quality", self.minimum_quality),
        ):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class CreatorEnrollmentStatus:
    """Safe enrollment metadata; no embedding values are exposed."""

    enrollment_id: str
    sample_count: int
    embedding_dimension: int
    created_at_ms: int
    updated_at_ms: int


@dataclass(frozen=True, slots=True)
class EnrollmentRejection:
    """Safe feedback for one rejected enrollment sample."""

    sample_index: int
    reason: str


@dataclass(frozen=True, slots=True)
class EnrollmentResult:
    """Enrollment outcome with sanitized acceptance and rejection metadata."""

    status: CreatorEnrollmentStatus | None
    accepted_samples: int
    rejections: tuple[EnrollmentRejection, ...] = ()

    @property
    def enrolled(self) -> bool:
        return self.status is not None


@dataclass(frozen=True, slots=True, repr=False)
class _CreatorEmbeddingRecord:
    status: CreatorEnrollmentStatus
    embedding: FaceEmbedding = field(repr=False)


def _cosine_similarity(left: FaceEmbedding, right: FaceEmbedding) -> float:
    if left.dimension != right.dimension:
        raise ValueError("face embeddings must have the same dimension")
    score = sum(a * b for a, b in zip(left.values, right.values, strict=True))
    return max(-1.0, min(1.0, score))


class InMemoryCreatorEmbeddingStore:
    """Single-creator hackathon store with explicit replacement and deletion."""

    def __init__(self, *, clock_ms: Callable[[], int] | None = None) -> None:
        self._clock_ms = clock_ms or _now_ms
        self._record: _CreatorEmbeddingRecord | None = None
        self._lock = RLock()

    def replace(self, embedding: FaceEmbedding, *, sample_count: int) -> CreatorEnrollmentStatus:
        if sample_count <= 0:
            raise ValueError("sample_count must be positive")
        now = self._clock_ms()
        if now < 0:
            raise ValueError("clock_ms must be non-negative")
        with self._lock:
            created_at_ms = self._record.status.created_at_ms if self._record is not None else now
            status = CreatorEnrollmentStatus(
                enrollment_id=token_hex(12),
                sample_count=sample_count,
                embedding_dimension=embedding.dimension,
                created_at_ms=created_at_ms,
                updated_at_ms=now,
            )
            self._record = _CreatorEmbeddingRecord(status=status, embedding=embedding)
            return status

    def status(self) -> CreatorEnrollmentStatus | None:
        with self._lock:
            return self._record.status if self._record is not None else None

    def compare(self, candidate: FaceEmbedding) -> float | None:
        with self._lock:
            if self._record is None:
                return None
            if candidate.dimension != self._record.embedding.dimension:
                return None
            return _cosine_similarity(candidate, self._record.embedding)

    def delete(self) -> bool:
        with self._lock:
            existed = self._record is not None
            self._record = None
            return existed


def _aggregate_embeddings(embeddings: Sequence[FaceEmbedding]) -> FaceEmbedding:
    if not embeddings:
        raise ValueError("at least one embedding is required")
    dimension = embeddings[0].dimension
    if any(embedding.dimension != dimension for embedding in embeddings):
        raise ValueError("all enrollment embeddings must have the same dimension")
    average = tuple(
        sum(embedding.values[index] for embedding in embeddings) / len(embeddings)
        for index in range(dimension)
    )
    return normalize_embedding(average)


class CreatorFaceEnrollmentService:
    """Create, replace, inspect, and delete one explicitly consented creator."""

    def __init__(
        self,
        model: FaceModel,
        store: InMemoryCreatorEmbeddingStore,
        config: FaceEnrollmentConfig | None = None,
    ) -> None:
        self.model = model
        self.store = store
        self.config = config or FaceEnrollmentConfig()

    def enroll(self, samples: Sequence[object], *, consent: bool) -> EnrollmentResult:
        """Process consented samples without retaining the source images."""

        if not consent:
            raise ConsentRequiredError("explicit creator consent is required for enrollment")
        if not samples:
            raise FaceEnrollmentError("at least one enrollment sample is required")
        if len(samples) > self.config.max_samples:
            raise FaceEnrollmentError(
                f"at most {self.config.max_samples} enrollment samples are accepted"
            )

        accepted: list[FaceEmbedding] = []
        rejections: list[EnrollmentRejection] = []
        for sample_index, sample in enumerate(samples):
            try:
                observations = tuple(self.model.detect(sample))
            except VideoDetectorUnavailable:
                rejections.append(EnrollmentRejection(sample_index, "detector_unavailable"))
                continue
            except VideoDetectorExecutionError:
                rejections.append(EnrollmentRejection(sample_index, "detector_error"))
                continue
            except DetectorError:
                rejections.append(EnrollmentRejection(sample_index, "detector_error"))
                continue
            except Exception:
                rejections.append(EnrollmentRejection(sample_index, "detector_error"))
                continue

            if not observations:
                rejections.append(EnrollmentRejection(sample_index, "no_face"))
                continue
            if len(observations) != 1:
                rejections.append(EnrollmentRejection(sample_index, "ambiguous_multi_face"))
                continue

            observation = observations[0]
            if observation.detection_confidence < self.config.minimum_detection_confidence:
                rejections.append(EnrollmentRejection(sample_index, "low_detection_confidence"))
                continue
            if observation.quality < self.config.minimum_quality:
                rejections.append(EnrollmentRejection(sample_index, "low_quality"))
                continue
            if observation.embedding is None:
                rejections.append(EnrollmentRejection(sample_index, "embedding_failed"))
                continue
            try:
                accepted.append(normalize_embedding(observation.embedding))
            except (TypeError, ValueError):
                rejections.append(EnrollmentRejection(sample_index, "invalid_embedding"))

        if len(accepted) < self.config.min_valid_samples:
            rejections.append(EnrollmentRejection(-1, "insufficient_valid_samples"))
            return EnrollmentResult(
                status=None,
                accepted_samples=len(accepted),
                rejections=tuple(rejections),
            )

        try:
            aggregate = _aggregate_embeddings(accepted)
        except ValueError:
            rejections.append(EnrollmentRejection(-1, "incompatible_embeddings"))
            return EnrollmentResult(
                status=None,
                accepted_samples=len(accepted),
                rejections=tuple(rejections),
            )

        status = self.store.replace(aggregate, sample_count=len(accepted))
        return EnrollmentResult(
            status=status,
            accepted_samples=len(accepted),
            rejections=tuple(rejections),
        )

    def status(self) -> CreatorEnrollmentStatus | None:
        return self.store.status()

    def delete(self) -> bool:
        return self.store.delete()
