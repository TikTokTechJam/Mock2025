"""Model-neutral interfaces shared by PrivaStream detector modules.

The contracts in this module deliberately contain no media or ML dependency.
Detector implementations adapt their model-specific output to these types
before it reaches policy or redaction code.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Literal, Protocol

VideoDetectionKind = Literal[
    "face",
    "face_bystander",
    "license_plate",
    "text",
    "email",
    "phone",
]
AudioDetectionKind = Literal["spoken_pii"]


class VideoDetectorUnavailable(RuntimeError):
    """A configured video detector cannot run in the current environment."""


class VideoDetectorExecutionError(RuntimeError):
    """A video detector failed while processing a frame."""


def _require_non_negative(name: str, value: int) -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _require_unit_interval(name: str, value: float) -> None:
    if not isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a finite value between 0 and 1")


@dataclass(frozen=True, slots=True)
class VideoFrame:
    """Canonical source frame metadata and optional media payload."""

    width: int
    height: int
    timestamp_ms: int
    frame_id: str | None = None
    payload: object | None = None

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("frame dimensions must be positive")
        _require_non_negative("timestamp_ms", self.timestamp_ms)


@dataclass(frozen=True, slots=True)
class AudioSegment:
    """PCM segment supplied to an audio detector.

    ``samples`` contains interleaved, normalized floating-point PCM values in
    the source timeline. An empty value is allowed for metadata-only callers;
    detector implementations that need audio must reject it explicitly.
    """

    start_ms: int
    end_ms: int
    sample_rate_hz: int
    channels: int
    samples: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        _require_non_negative("start_ms", self.start_ms)
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        if self.sample_rate_hz <= 0 or self.channels <= 0:
            raise ValueError("sample rate and channel count must be positive")
        normalized_samples = tuple(self.samples)
        object.__setattr__(self, "samples", normalized_samples)
        if not normalized_samples:
            return
        if len(normalized_samples) % self.channels:
            raise ValueError("sample count must be divisible by channel count")
        for sample in normalized_samples:
            if not isfinite(sample) or not -1 <= sample <= 1:
                raise ValueError("samples must be finite normalized values between -1 and 1")
        sample_duration_ms = len(normalized_samples) / self.channels / self.sample_rate_hz * 1000
        if abs(sample_duration_ms - (self.end_ms - self.start_ms)) > 1:
            raise ValueError("segment timestamps must match the PCM sample duration")

    @property
    def duration_ms(self) -> int:
        """Return the source duration represented by this segment."""

        return self.end_ms - self.start_ms

    def mono_samples(self) -> tuple[float, ...]:
        """Downmix interleaved samples to mono without changing source time."""

        if self.channels == 1:
            return self.samples
        return tuple(
            sum(self.samples[index : index + self.channels]) / self.channels
            for index in range(0, len(self.samples), self.channels)
        )


@dataclass(frozen=True, slots=True)
class VideoRegionDetection:
    """Normalized region emitted by a face, plate, or OCR detector."""

    kind: VideoDetectionKind
    x: float
    y: float
    width: float
    height: float
    confidence: float
    timestamp_ms: int
    detector: str
    track_id: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("x", self.x),
            ("y", self.y),
            ("width", self.width),
            ("height", self.height),
            ("confidence", self.confidence),
        ):
            _require_unit_interval(name, value)
        if self.width <= 0 or self.height <= 0:
            raise ValueError("detection dimensions must be positive")
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("detection region must stay within normalized frame bounds")
        _require_non_negative("timestamp_ms", self.timestamp_ms)
        if not self.detector.strip():
            raise ValueError("detector must not be empty")


@dataclass(frozen=True, slots=True)
class AudioRedactionInterval:
    """Time interval emitted for spoken sensitive-content redaction."""

    kind: AudioDetectionKind
    start_ms: int
    end_ms: int
    confidence: float
    detector: str
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_non_negative("start_ms", self.start_ms)
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        _require_unit_interval("confidence", self.confidence)
        if not self.detector.strip():
            raise ValueError("detector must not be empty")


class FaceDetector(Protocol):
    """Detect non-whitelisted or otherwise sensitive faces in a video frame."""

    kind: Literal["face", "face_bystander"]

    def detect(self, frame: VideoFrame) -> Sequence[VideoRegionDetection]:
        """Return normalized face regions for ``frame``."""


class LicensePlateDetector(Protocol):
    """Detect license plates in a video frame."""

    kind: Literal["license_plate"]

    def detect(self, frame: VideoFrame) -> Sequence[VideoRegionDetection]:
        """Return normalized license-plate regions for ``frame``."""


class OcrDetector(Protocol):
    """Detect sensitive on-screen text regions in a video frame."""

    kind: Literal["text"]

    def detect(self, frame: VideoFrame) -> Sequence[VideoRegionDetection]:
        """Return normalized OCR regions for ``frame``."""


class AudioPiiDetector(Protocol):
    """Detect spoken sensitive information in an audio segment."""

    kind: Literal["spoken_pii"]

    def detect(self, segment: AudioSegment) -> Sequence[AudioRedactionInterval]:
        """Return time-based redaction intervals for ``segment``."""
