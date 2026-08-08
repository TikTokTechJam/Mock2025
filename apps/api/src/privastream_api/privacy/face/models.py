"""Model-neutral types for the standalone face privacy module.

The model adapter owns detection and embedding extraction. The enrollment and
matching services own only normalized embeddings and safe metadata; raw images
and model response objects never cross this module's public boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from math import isfinite, sqrt
from typing import Protocol


@dataclass(frozen=True, slots=True, repr=False)
class FaceEmbedding:
    """An in-memory normalized embedding with a redacted representation."""

    values: tuple[float, ...] = field(repr=False)

    def __post_init__(self) -> None:
        normalized = tuple(float(value) for value in self.values)
        if not normalized:
            raise ValueError("face embedding must not be empty")
        if any(not isfinite(value) for value in normalized):
            raise ValueError("face embedding values must be finite")
        object.__setattr__(self, "values", normalized)

    @property
    def dimension(self) -> int:
        return len(self.values)

    def __repr__(self) -> str:
        return f"FaceEmbedding(dimension={self.dimension})"


def normalize_embedding(values: Sequence[float]) -> FaceEmbedding:
    """L2-normalize model output without retaining or logging raw values."""

    candidate = tuple(float(value) for value in values)
    if not candidate:
        raise ValueError("face embedding must not be empty")
    if any(not isfinite(value) for value in candidate):
        raise ValueError("face embedding values must be finite")
    magnitude = sqrt(sum(value * value for value in candidate))
    if magnitude <= 1e-12:
        raise ValueError("face embedding magnitude must be positive")
    return FaceEmbedding(tuple(value / magnitude for value in candidate))


@dataclass(frozen=True, slots=True, repr=False)
class FaceObservation:
    """One model face result in source-image pixel coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float
    detection_confidence: float
    embedding: tuple[float, ...] | None = field(default=None, repr=False)
    quality: float = 1.0
    track_id: str | None = None

    def __post_init__(self) -> None:
        coordinates = (self.x1, self.y1, self.x2, self.y2)
        if any(not isfinite(value) for value in coordinates):
            raise ValueError("face coordinates must be finite")
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("face coordinates must describe a positive box")
        for name, value in (
            ("detection_confidence", self.detection_confidence),
            ("quality", self.quality),
        ):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.embedding is not None:
            object.__setattr__(self, "embedding", tuple(float(value) for value in self.embedding))
        if self.track_id is not None and not self.track_id.strip():
            object.__setattr__(self, "track_id", None)

    def __repr__(self) -> str:
        return (
            "FaceObservation("
            f"box=({self.x1:.1f}, {self.y1:.1f}, {self.x2:.1f}, {self.y2:.1f}), "
            f"detection_confidence={self.detection_confidence:.3f}, "
            f"quality={self.quality:.3f}, track_id={self.track_id!r})"
        )


class FaceModel(Protocol):
    """Replaceable face detector and embedding-extraction boundary."""

    def detect(self, image: object) -> Sequence[FaceObservation]:
        """Return source-pixel face observations without logging model output."""
