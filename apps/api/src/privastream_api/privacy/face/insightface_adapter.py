"""Lazy local InsightFace/ArcFace adapter for the standalone face module."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from privastream_api.privacy.face.models import FaceObservation
from privastream_api.privacy.vision.service import DetectorExecutionError, DetectorUnavailableError


@dataclass(frozen=True, slots=True)
class InsightFaceConfig:
    """Local model-pack and runtime settings; missing packs never auto-download."""

    model_root: Path = Path("models/insightface")
    model_name: str = "buffalo_l"
    providers: tuple[str, ...] = ("CPUExecutionProvider",)
    context_id: int = -1
    detection_size: tuple[int, int] = (640, 640)

    def __post_init__(self) -> None:
        if not self.model_name.strip():
            raise ValueError("model_name must not be empty")
        if not self.providers or any(not provider.strip() for provider in self.providers):
            raise ValueError("at least one execution provider is required")
        if self.detection_size[0] <= 0 or self.detection_size[1] <= 0:
            raise ValueError("detection_size must be positive")


class FaceAnalysis(Protocol):
    def prepare(self, *, ctx_id: int, det_size: tuple[int, int]) -> None:
        """Prepare the local InsightFace graph."""

    def get(self, image: object) -> Sequence[object]:
        """Return model-specific face objects."""


def _embedding(face: object) -> tuple[float, ...] | None:
    value = getattr(face, "normed_embedding", None)
    if value is None:
        value = getattr(face, "embedding", None)
    if value is None:
        return None
    try:
        return tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return (float("nan"),)


class InsightFaceFaceModel:
    """Use a local InsightFace model pack for detection and ArcFace embeddings."""

    def __init__(
        self,
        config: InsightFaceConfig | None = None,
        *,
        analysis: FaceAnalysis | None = None,
    ) -> None:
        self.config = config or InsightFaceConfig()
        self._analysis = analysis

    def _ensure_analysis(self) -> FaceAnalysis:
        if self._analysis is not None:
            return self._analysis
        model_pack = self.config.model_root / "models" / self.config.model_name
        if not model_pack.is_dir():
            raise DetectorUnavailableError(
                "local InsightFace model pack is missing; provide the configured model root"
            )
        try:
            from insightface.app import FaceAnalysis as InsightFaceAnalysis
        except ImportError as exc:
            raise DetectorUnavailableError(
                "InsightFace is required for the face adapter; install the face extra"
            ) from exc
        try:
            self._analysis = InsightFaceAnalysis(
                name=self.config.model_name,
                root=str(self.config.model_root),
                providers=list(self.config.providers),
                allowed_modules=["detection", "recognition"],
            )
            self._analysis.prepare(
                ctx_id=self.config.context_id,
                det_size=self.config.detection_size,
            )
        except Exception as exc:
            self._analysis = None
            raise DetectorUnavailableError("InsightFace model initialization failed") from exc
        return self._analysis

    def detect(self, image: object) -> Sequence[FaceObservation]:
        """Return source-pixel boxes and normalized ArcFace embeddings."""

        if image is None or not hasattr(image, "shape") or len(image.shape) < 2:
            raise DetectorExecutionError("face detector received an invalid image")
        try:
            faces = self._ensure_analysis().get(image)
        except (DetectorUnavailableError, DetectorExecutionError):
            raise
        except Exception as exc:
            raise DetectorExecutionError("face inference failed") from exc

        observations: list[FaceObservation] = []
        for face in faces:
            raw_box = getattr(face, "bbox", None)
            if raw_box is None:
                raise DetectorExecutionError("face model returned a face without a bounding box")
            try:
                coordinates = tuple(float(value) for value in raw_box)
                if len(coordinates) != 4:
                    raise ValueError
                confidence = float(getattr(face, "det_score", 0.0))
                quality = float(getattr(face, "quality", confidence))
                track_id = getattr(face, "track_id", None)
                if track_id is not None:
                    track_id = str(track_id)
                observations.append(
                    FaceObservation(
                        x1=coordinates[0],
                        y1=coordinates[1],
                        x2=coordinates[2],
                        y2=coordinates[3],
                        detection_confidence=confidence,
                        quality=quality,
                        embedding=_embedding(face),
                        track_id=track_id,
                    )
                )
            except (TypeError, ValueError) as exc:
                raise DetectorExecutionError("face model returned invalid face metadata") from exc
        return observations


__all__ = ["InsightFaceConfig", "InsightFaceFaceModel"]
