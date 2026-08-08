"""Shared standalone service boundary for visual privacy detectors."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from privastream_api.pipeline.contracts import VideoFrame, VideoRegionDetection


class DetectorError(RuntimeError):
    """Base error for detector availability or inference failures."""


class DetectorUnavailableError(DetectorError):
    """A configured detector cannot run in the current environment."""


class DetectorExecutionError(DetectorError):
    """A detector failed while processing a frame."""


@dataclass(frozen=True, slots=True)
class FrameContext:
    """A source frame plus the metadata required by detector adapters."""

    image: Any
    source: VideoFrame
    frame_index: int = 0

    def __post_init__(self) -> None:
        if self.frame_index < 0:
            raise ValueError("frame_index must be non-negative")


class VisualPrivacyDetector(Protocol):
    """Async adapter boundary shared by plate and OCR/PII detectors."""

    async def detect(self, frame: FrameContext) -> list[VideoRegionDetection]:
        """Return normalized privacy regions for one source frame."""


@dataclass(frozen=True, slots=True)
class VisionPrivacyService:
    """Run independent visual detectors and concatenate their regions."""

    detectors: Sequence[VisualPrivacyDetector]

    async def detect(self, frame: FrameContext) -> list[VideoRegionDetection]:
        regions: list[VideoRegionDetection] = []
        for detector in self.detectors:
            regions.extend(await detector.detect(frame))
        return regions
