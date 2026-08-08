"""Conservative creator-vs-bystander matching over normalized face regions."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from privastream_api.pipeline.contracts import VideoFrame, VideoRegionDetection
from privastream_api.privacy.face.enrollment import InMemoryCreatorEmbeddingStore
from privastream_api.privacy.face.models import FaceModel, FaceObservation, normalize_embedding
from privastream_api.privacy.vision.service import (
    DetectorError,
    DetectorExecutionError,
    FrameContext,
)

FaceMatchStatus = Literal[
    "creator",
    "unknown",
    "ambiguous",
    "low_quality",
    "embedding_failed",
    "no_enrollment",
]


@dataclass(frozen=True, slots=True)
class CreatorFaceDetectorConfig:
    """Matching thresholds; the detector owns no production padding policy."""

    detector_id: str = "insightface-arcface"
    minimum_detection_confidence: float = 0.5
    minimum_quality: float = 0.5
    creator_match_threshold: float = 0.55
    ambiguity_margin: float = 0.05

    def __post_init__(self) -> None:
        if not self.detector_id.strip():
            raise ValueError("detector_id must not be empty")
        for name, value in (
            ("minimum_detection_confidence", self.minimum_detection_confidence),
            ("minimum_quality", self.minimum_quality),
            ("creator_match_threshold", self.creator_match_threshold),
            ("ambiguity_margin", self.ambiguity_margin),
        ):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.creator_match_threshold + self.ambiguity_margin > 1:
            raise ValueError("creator match threshold plus ambiguity margin must be at most 1")


@dataclass(frozen=True, slots=True)
class FaceIdentityDecision:
    """Safe match decision; an uncertain decision is always protected."""

    status: FaceMatchStatus
    similarity: float | None = None

    def __post_init__(self) -> None:
        if self.similarity is not None and (
            not isfinite(self.similarity) or not -1 <= self.similarity <= 1
        ):
            raise ValueError("similarity must be between -1 and 1")


def _clamp_pixel(value: float, upper_bound: int) -> float:
    return max(0.0, min(float(upper_bound), value))


def normalize_face_region(
    observation: FaceObservation,
    frame: VideoFrame,
    *,
    detector_id: str,
) -> VideoRegionDetection:
    """Clamp model pixel coordinates and emit a valid shared region."""

    x1 = _clamp_pixel(observation.x1, frame.width)
    y1 = _clamp_pixel(observation.y1, frame.height)
    x2 = _clamp_pixel(observation.x2, frame.width)
    y2 = _clamp_pixel(observation.y2, frame.height)
    if x2 <= x1 or y2 <= y1:
        raise DetectorExecutionError("face detector returned an invalid source-frame box")
    return VideoRegionDetection(
        kind="face_bystander",
        x=x1 / frame.width,
        y=y1 / frame.height,
        width=(x2 - x1) / frame.width,
        height=(y2 - y1) / frame.height,
        confidence=observation.detection_confidence,
        timestamp_ms=frame.timestamp_ms,
        detector=detector_id,
        track_id=observation.track_id,
    )


class CreatorFaceDetector:
    """Detect faces and emit only faces that must remain protected."""

    kind: Literal["face_bystander"] = "face_bystander"

    def __init__(
        self,
        model: FaceModel,
        store: InMemoryCreatorEmbeddingStore,
        config: CreatorFaceDetectorConfig | None = None,
    ) -> None:
        self.model = model
        self.store = store
        self.config = config or CreatorFaceDetectorConfig()

    def classify(self, observation: FaceObservation) -> FaceIdentityDecision:
        """Classify one observation without exposing its embedding."""

        if self.store.status() is None:
            return FaceIdentityDecision("no_enrollment")
        if observation.detection_confidence < self.config.minimum_detection_confidence:
            return FaceIdentityDecision("low_quality")
        if observation.quality < self.config.minimum_quality:
            return FaceIdentityDecision("low_quality")
        if observation.embedding is None:
            return FaceIdentityDecision("embedding_failed")
        try:
            candidate = normalize_embedding(observation.embedding)
        except (TypeError, ValueError):
            return FaceIdentityDecision("embedding_failed")
        similarity = self.store.compare(candidate)
        if similarity is None:
            return FaceIdentityDecision("unknown")
        if similarity >= self.config.creator_match_threshold + self.config.ambiguity_margin:
            return FaceIdentityDecision("creator", similarity)
        if similarity >= self.config.creator_match_threshold - self.config.ambiguity_margin:
            return FaceIdentityDecision("ambiguous", similarity)
        return FaceIdentityDecision("unknown", similarity)

    async def detect(self, frame: FrameContext | VideoFrame) -> list[VideoRegionDetection]:
        """Return normalized bystander regions for a source image/frame."""

        context = frame if isinstance(frame, FrameContext) else FrameContext(frame.payload, frame)
        try:
            observations = tuple(self.model.detect(context.image))
        except DetectorError:
            raise
        except Exception as exc:
            raise DetectorExecutionError("face detector failed") from exc

        protected: list[VideoRegionDetection] = []
        for observation in observations:
            decision = self.classify(observation)
            if decision.status == "creator":
                continue
            protected.append(
                normalize_face_region(
                    observation,
                    context.source,
                    detector_id=self.config.detector_id,
                )
            )
        return protected
