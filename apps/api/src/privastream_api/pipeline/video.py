"""Model-agnostic video scheduling, temporal masking, and composition.

This module owns the production video pipeline boundary. It accepts normalized
detector output, never imports a detector implementation, and does not decide
whether a frame may be published. A privacy gate such as the one planned in
Issue #13 owns that final safety decision.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass, field
from math import ceil, floor
from time import monotonic
from typing import Literal, Protocol

from privastream_api.pipeline.contracts import (
    VideoDetectionKind,
    VideoDetectorExecutionError,
    VideoDetectorUnavailable,
    VideoFrame,
    VideoRegionDetection,
)

CompositorMode = Literal["blur", "pixelate", "cover"]
DetectorRunStatus = Literal[
    "success", "skipped", "timeout", "unavailable", "invalid", "error"
]
RenderStatus = Literal["rendered", "no_payload", "error"]


class VideoCompositionError(RuntimeError):
    """A frame payload cannot be processed by the dependency-free compositor."""


@dataclass(frozen=True, slots=True)
class RasterFrame:
    """Small dependency-free interleaved pixel surface for compositor output.

    ``data`` is row-major and uses one, three, or four bytes per pixel. The
    surface is intentionally independent of OpenCV, NumPy, and transport types;
    an adapter can convert its own frame representation at the boundary.
    """

    width: int
    height: int
    data: bytes | bytearray
    channels: int = 3

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("raster dimensions must be positive")
        if self.channels not in (1, 3, 4):
            raise ValueError("raster channels must be 1, 3, or 4")
        expected = self.width * self.height * self.channels
        if len(self.data) != expected:
            raise ValueError(f"raster data must contain exactly {expected} bytes")
        object.__setattr__(self, "data", bytes(self.data))

    @classmethod
    def solid(
        cls, width: int, height: int, color: tuple[int, ...], channels: int = 3
    ) -> RasterFrame:
        """Create a deterministic test or adapter surface filled with ``color``."""

        pixel = _color_for_channels(color, channels)
        return cls(width, height, pixel * (width * height), channels)

    def pixel(self, x: int, y: int) -> tuple[int, ...]:
        """Return one pixel for deterministic adapter and test inspection."""

        if not 0 <= x < self.width or not 0 <= y < self.height:
            raise IndexError("pixel coordinates are outside the raster")
        start = (y * self.width + x) * self.channels
        return tuple(self.data[start : start + self.channels])


@dataclass(frozen=True, slots=True)
class VideoPrivacyRegion:
    """Validated, padded, and TTL-bearing canonical video privacy region."""

    kind: VideoDetectionKind
    x: float
    y: float
    width: float
    height: float
    confidence: float
    timestamp_ms: int
    detector: str
    expires_at_ms: int
    track_id: str | None = None

    def __post_init__(self) -> None:
        # Reuse the detector contract's validation so both boundaries have the
        # same normalized-coordinate and confidence semantics.
        VideoRegionDetection(
            kind=self.kind,
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            confidence=self.confidence,
            timestamp_ms=self.timestamp_ms,
            detector=self.detector,
            track_id=self.track_id,
        )
        if self.expires_at_ms <= self.timestamp_ms:
            raise ValueError("expires_at_ms must be greater than timestamp_ms")

    @classmethod
    def from_detection(
        cls, detection: VideoRegionDetection, *, expires_at_ms: int
    ) -> VideoPrivacyRegion:
        return cls(
            kind=detection.kind,
            x=detection.x,
            y=detection.y,
            width=detection.width,
            height=detection.height,
            confidence=detection.confidence,
            timestamp_ms=detection.timestamp_ms,
            detector=detection.detector,
            expires_at_ms=expires_at_ms,
            track_id=detection.track_id,
        )

    def to_detection(self) -> VideoRegionDetection:
        """Return the normalized detector-contract representation."""

        return VideoRegionDetection(
            kind=self.kind,
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            confidence=self.confidence,
            timestamp_ms=self.timestamp_ms,
            detector=self.detector,
            track_id=self.track_id,
        )

    def pixel_bounds(self, width: int, height: int) -> tuple[int, int, int, int]:
        """Map normalized coordinates to a clamped half-open pixel rectangle."""

        left = max(0, min(width, floor(self.x * width)))
        top = max(0, min(height, floor(self.y * height)))
        right = max(left + 1, min(width, ceil((self.x + self.width) * width)))
        bottom = max(top + 1, min(height, ceil((self.y + self.height) * height)))
        return left, top, right, bottom


@dataclass(frozen=True, slots=True)
class DetectorRun:
    """Sanitized result of one detector attempt for one source frame."""

    detector: str
    status: DetectorRunStatus
    regions: tuple[VideoPrivacyRegion, ...] = ()
    duration_ms: float = 0.0
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.status in {"timeout", "unavailable", "invalid", "error"}


@dataclass(frozen=True, slots=True)
class ProtectedVideoFrame:
    """Ordered compositor output plus explicit detector execution state.

    This type deliberately does not expose a publication-safety verdict. A
    required detector failure is represented in ``detector_runs`` and must be
    evaluated by the central safety gate before output is released.
    """

    sequence: int
    source: VideoFrame
    payload: RasterFrame | None
    regions: tuple[VideoPrivacyRegion, ...]
    detector_runs: tuple[DetectorRun, ...]
    render_status: RenderStatus
    render_error: str | None = None
    queue_wait_ms: float = 0.0
    processing_ms: float = 0.0

    @property
    def frame(self) -> VideoFrame:
        """Compatibility alias for callers that use ``frame`` terminology."""

        return self.source

    @property
    def detector_failures(self) -> tuple[DetectorRun, ...]:
        return tuple(run for run in self.detector_runs if run.failed)


class VideoDetector(Protocol):
    """Model-neutral detector adapter accepted by the scheduler."""

    def detect(
        self, frame: VideoFrame
    ) -> Sequence[VideoRegionDetection] | Awaitable[Sequence[VideoRegionDetection]]:
        """Return normalized regions or an awaitable producing them."""


@dataclass(frozen=True, slots=True)
class VideoDetectorRegistration:
    """Scheduling policy for one independently registered detector."""

    name: str
    detector: VideoDetector
    cadence_frames: int = 1
    timeout_ms: int = 100
    ttl_ms: int = 250
    max_concurrency: int = 1

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("detector name must not be empty")
        if self.cadence_frames <= 0:
            raise ValueError("cadence_frames must be positive")
        if self.timeout_ms <= 0 or self.ttl_ms <= 0:
            raise ValueError("timeout_ms and ttl_ms must be positive")
        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")


@dataclass(frozen=True, slots=True)
class VideoOrchestrationConfig:
    """Bounds shared video scheduling and normalized region processing."""

    max_in_flight_frames: int = 4
    padding_px: int = 0
    overlap_iou_threshold: float = 0.0
    max_regions_per_frame: int = 256

    def __post_init__(self) -> None:
        if self.max_in_flight_frames <= 0:
            raise ValueError("max_in_flight_frames must be positive")
        if self.padding_px < 0:
            raise ValueError("padding_px must be non-negative")
        if not 0 <= self.overlap_iou_threshold <= 1:
            raise ValueError("overlap_iou_threshold must be between 0 and 1")
        if self.max_regions_per_frame <= 0:
            raise ValueError("max_regions_per_frame must be positive")


@dataclass(slots=True)
class _DetectorMetric:
    calls: int = 0
    successes: int = 0
    skipped: int = 0
    timeouts: int = 0
    failures: int = 0
    total_duration_ms: float = 0.0
    max_duration_ms: float = 0.0


@dataclass(slots=True)
class VideoMetrics:
    """Sanitized per-stage timing and queue measurements."""

    frames_submitted: int = 0
    frames_released: int = 0
    max_pending_frames: int = 0
    total_queue_wait_ms: float = 0.0
    total_processing_ms: float = 0.0
    _detectors: dict[str, _DetectorMetric] = field(default_factory=dict)

    def record_queue(self, pending_frames: int, wait_ms: float) -> None:
        self.max_pending_frames = max(self.max_pending_frames, pending_frames)
        self.total_queue_wait_ms += max(0.0, wait_ms)

    def record_run(self, run: DetectorRun) -> None:
        metric = self._detectors.setdefault(run.detector, _DetectorMetric())
        metric.calls += 1
        metric.total_duration_ms += run.duration_ms
        metric.max_duration_ms = max(metric.max_duration_ms, run.duration_ms)
        if run.status == "success":
            metric.successes += 1
        elif run.status == "skipped":
            metric.skipped += 1
        elif run.status == "timeout":
            metric.timeouts += 1
            metric.failures += 1
        else:
            metric.failures += 1

    def snapshot(self) -> dict[str, object]:
        """Return only aggregate, non-media observability data."""

        return {
            "frames_submitted": self.frames_submitted,
            "frames_released": self.frames_released,
            "max_pending_frames": self.max_pending_frames,
            "total_queue_wait_ms": round(self.total_queue_wait_ms, 3),
            "total_processing_ms": round(self.total_processing_ms, 3),
            "detectors": {
                name: {
                    "calls": metric.calls,
                    "successes": metric.successes,
                    "skipped": metric.skipped,
                    "timeouts": metric.timeouts,
                    "failures": metric.failures,
                    "total_duration_ms": round(metric.total_duration_ms, 3),
                    "max_duration_ms": round(metric.max_duration_ms, 3),
                }
                for name, metric in sorted(self._detectors.items())
            },
        }


@dataclass(slots=True)
class _StoredRegion:
    region: VideoPrivacyRegion
    detector_name: str


class TemporalRegionStore:
    """Persist detector regions across skipped or failed frames by TTL."""

    def __init__(self, *, association_iou_threshold: float = 0.3) -> None:
        if not 0 <= association_iou_threshold <= 1:
            raise ValueError("association_iou_threshold must be between 0 and 1")
        self.association_iou_threshold = association_iou_threshold
        self._regions: dict[int, _StoredRegion] = {}
        self._next_id = 0
        self._last_timestamp_ms = -1

    def update(
        self,
        *,
        detector_name: str,
        status: DetectorRunStatus,
        regions: Sequence[VideoPrivacyRegion],
        timestamp_ms: int,
    ) -> tuple[VideoPrivacyRegion, ...]:
        if timestamp_ms < self._last_timestamp_ms:
            raise ValueError("video timestamps must be monotonic")
        self._last_timestamp_ms = timestamp_ms
        self._purge(timestamp_ms)

        if status == "success":
            previous = [
                (key, stored)
                for key, stored in self._regions.items()
                if stored.detector_name == detector_name
            ]
            matched: set[int] = set()
            current_keys: set[int] = set()
            for region in regions:
                match_key = self._find_match(region, previous, matched)
                if match_key is None:
                    match_key = self._next_id
                    self._next_id += 1
                else:
                    matched.add(match_key)
                current_keys.add(match_key)
                self._regions[match_key] = _StoredRegion(region, detector_name)
            for key, _stored in previous:
                if key not in current_keys:
                    self._regions.pop(key, None)

        return self.active(timestamp_ms)

    def active(self, timestamp_ms: int) -> tuple[VideoPrivacyRegion, ...]:
        self._purge(timestamp_ms)
        return tuple(
            stored.region
            for _key, stored in sorted(
                self._regions.items(), key=lambda item: (item[1].region.timestamp_ms, item[0])
            )
        )

    def _purge(self, timestamp_ms: int) -> None:
        expired = [
            key
            for key, stored in self._regions.items()
            if stored.region.expires_at_ms <= timestamp_ms
        ]
        for key in expired:
            self._regions.pop(key, None)

    def _find_match(
        self,
        candidate: VideoPrivacyRegion,
        previous: Sequence[tuple[int, _StoredRegion]],
        matched: set[int],
    ) -> int | None:
        best_key: int | None = None
        best_iou = 0.0
        for key, stored in previous:
            if key in matched or stored.region.kind != candidate.kind:
                continue
            if candidate.track_id and candidate.track_id == stored.region.track_id:
                return key
            score = _intersection_over_union(candidate, stored.region)
            if score >= self.association_iou_threshold and score > best_iou:
                best_key = key
                best_iou = score
        return best_key


def normalize_regions(
    detections: Sequence[VideoRegionDetection | VideoPrivacyRegion],
    frame: VideoFrame,
    *,
    padding_px: int,
    ttl_ms: int,
) -> tuple[VideoPrivacyRegion, ...]:
    """Validate, pad, clamp, and add TTL metadata to detector output."""

    if padding_px < 0 or ttl_ms <= 0:
        raise ValueError("padding_px must be non-negative and ttl_ms must be positive")
    normalized: list[VideoPrivacyRegion] = []
    pad_x = padding_px / frame.width
    pad_y = padding_px / frame.height
    for item in detections:
        detection = item.to_detection() if isinstance(item, VideoPrivacyRegion) else item
        if not isinstance(detection, VideoRegionDetection):
            raise ValueError("detector returned a non-region value")
        if detection.timestamp_ms != frame.timestamp_ms:
            raise ValueError("detector region timestamp does not match source frame")
        left = max(0.0, detection.x - pad_x)
        top = max(0.0, detection.y - pad_y)
        right = min(1.0, detection.x + detection.width + pad_x)
        bottom = min(1.0, detection.y + detection.height + pad_y)
        if right <= left or bottom <= top:
            raise ValueError("detector region is empty after clamping")
        normalized.append(
            VideoPrivacyRegion(
                kind=detection.kind,
                x=left,
                y=top,
                width=right - left,
                height=bottom - top,
                confidence=detection.confidence,
                timestamp_ms=frame.timestamp_ms,
                detector=detection.detector,
                expires_at_ms=frame.timestamp_ms + ttl_ms,
                track_id=detection.track_id,
            )
        )
    return tuple(normalized)


def merge_overlapping_regions(
    regions: Sequence[VideoPrivacyRegion], *, iou_threshold: float = 0.0
) -> tuple[VideoPrivacyRegion, ...]:
    """Conservatively merge overlapping regions of the same privacy kind."""

    if not 0 <= iou_threshold <= 1:
        raise ValueError("iou_threshold must be between 0 and 1")
    merged: list[VideoPrivacyRegion] = []
    for candidate in sorted(regions, key=lambda region: (region.kind, -region.confidence)):
        match_index = next(
            (
                index
                for index, existing in enumerate(merged)
                if existing.kind == candidate.kind
                and _intersection_area(existing, candidate) > 0
                and _intersection_over_union(existing, candidate) >= iou_threshold
            ),
            None,
        )
        if match_index is None:
            merged.append(candidate)
            continue
        merged[match_index] = _merge_region(merged[match_index], candidate)
    return tuple(merged)


class VideoCompositor:
    """Apply generic visual redaction primitives to a ``RasterFrame``."""

    def __init__(
        self,
        *,
        mode: CompositorMode = "blur",
        blur_radius: int = 2,
        pixel_block_size: int = 8,
        cover_color: tuple[int, ...] = (0, 0, 0),
    ) -> None:
        if mode not in {"blur", "pixelate", "cover"}:
            raise ValueError("unsupported compositor mode")
        if blur_radius <= 0 or pixel_block_size <= 0:
            raise ValueError("blur_radius and pixel_block_size must be positive")
        self.mode = mode
        self.blur_radius = blur_radius
        self.pixel_block_size = pixel_block_size
        self.cover_color = cover_color

    def compose(
        self,
        frame: VideoFrame,
        regions: Sequence[VideoPrivacyRegion],
        *,
        full_frame: bool = False,
    ) -> RasterFrame | None:
        """Return a protected payload without deciding publication readiness."""

        if frame.payload is None:
            return None
        if not isinstance(frame.payload, RasterFrame):
            raise VideoCompositionError("video frame payload is not a RasterFrame")
        if frame.payload.width != frame.width or frame.payload.height != frame.height:
            raise VideoCompositionError("video frame and payload dimensions differ")
        if full_frame:
            return self.full_frame_safe_cover(frame)

        data = bytearray(frame.payload.data)
        for region in regions:
            bounds = region.pixel_bounds(frame.width, frame.height)
            if self.mode == "blur":
                _blur_region(data, frame.payload, bounds, self.blur_radius)
            elif self.mode == "pixelate":
                _pixelate_region(data, frame.payload, bounds, self.pixel_block_size)
            else:
                _cover_region(data, frame.payload, bounds, self.cover_color)
        return RasterFrame(frame.width, frame.height, data, frame.payload.channels)

    def full_frame_safe_cover(self, frame: VideoFrame) -> RasterFrame:
        """Cover every pixel; a safety gate decides when this is required."""

        if not isinstance(frame.payload, RasterFrame):
            raise VideoCompositionError("video frame payload is not a RasterFrame")
        data = bytearray(frame.payload.data)
        _cover_region(
            data,
            frame.payload,
            (0, 0, frame.width, frame.height),
            self.cover_color,
        )
        return RasterFrame(frame.width, frame.height, data, frame.payload.channels)


class VideoOrchestrator:
    """Schedule detectors, retain temporal masks, and release frames in order."""

    def __init__(
        self,
        *,
        config: VideoOrchestrationConfig | None = None,
        compositor: VideoCompositor | None = None,
        metrics: VideoMetrics | None = None,
    ) -> None:
        self.config = config or VideoOrchestrationConfig()
        self.compositor = compositor or VideoCompositor()
        self.metrics = metrics or VideoMetrics()
        self._registrations: list[VideoDetectorRegistration] = []
        self._limits: dict[str, asyncio.Semaphore] = {}
        self._temporal = TemporalRegionStore()
        self._in_flight = asyncio.Semaphore(self.config.max_in_flight_frames)
        self._release_condition = asyncio.Condition()
        self._next_sequence = 0
        self._next_release = 0
        self._last_timestamp_ms = -1

    @property
    def registrations(self) -> tuple[VideoDetectorRegistration, ...]:
        return tuple(self._registrations)

    def register(
        self,
        name: str,
        detector: VideoDetector,
        *,
        cadence_frames: int = 1,
        timeout_ms: int = 100,
        ttl_ms: int = 250,
        max_concurrency: int = 1,
    ) -> None:
        """Register one detector without importing its implementation."""

        if any(existing.name == name for existing in self._registrations):
            raise ValueError(f"detector {name!r} is already registered")
        registration = VideoDetectorRegistration(
            name=name,
            detector=detector,
            cadence_frames=cadence_frames,
            timeout_ms=timeout_ms,
            ttl_ms=ttl_ms,
            max_concurrency=max_concurrency,
        )
        self._registrations.append(registration)
        self._limits[name] = asyncio.Semaphore(max_concurrency)

    async def process_frame(self, frame: VideoFrame) -> ProtectedVideoFrame:
        """Process one frame and wait until all earlier frames are released."""

        if frame.timestamp_ms < self._last_timestamp_ms:
            raise ValueError("video timestamps must be monotonic")
        self._last_timestamp_ms = frame.timestamp_ms
        sequence = self._next_sequence
        self._next_sequence += 1
        self.metrics.frames_submitted += 1
        pending = self._next_sequence - self._next_release
        self.metrics.max_pending_frames = max(self.metrics.max_pending_frames, pending)
        queued_at = monotonic()

        async with self._in_flight:
            queue_wait_ms = (monotonic() - queued_at) * 1000
            self.metrics.record_queue(pending, queue_wait_ms)
            started = monotonic()
            runs = tuple(
                await asyncio.gather(
                    *(
                        self._run_detector(registration, frame, sequence)
                        for registration in self._registrations
                    )
                )
            )
            active_regions: list[VideoPrivacyRegion] = []
            for registration, run in zip(self._registrations, runs, strict=True):
                self._temporal.update(
                    detector_name=registration.name,
                    status=run.status,
                    regions=run.regions,
                    timestamp_ms=frame.timestamp_ms,
                )
            active_regions.extend(self._temporal.active(frame.timestamp_ms))
            regions = merge_overlapping_regions(
                active_regions, iou_threshold=self.config.overlap_iou_threshold
            )

            render_status: RenderStatus = "rendered"
            render_error: str | None = None
            payload: RasterFrame | None
            if len(regions) > self.config.max_regions_per_frame:
                payload = None
                render_status = "error"
                render_error = "video region limit exceeded"
            else:
                try:
                    payload = self.compositor.compose(frame, regions)
                    if payload is None:
                        render_status = "no_payload"
                except VideoCompositionError:
                    payload = None
                    render_status = "error"
                    render_error = "video composition failed"

            processing_ms = (monotonic() - started) * 1000
            self.metrics.total_processing_ms += processing_ms
            for run in runs:
                self.metrics.record_run(run)
            result = ProtectedVideoFrame(
                sequence=sequence,
                source=frame,
                payload=payload,
                regions=regions,
                detector_runs=runs,
                render_status=render_status,
                render_error=render_error,
                queue_wait_ms=queue_wait_ms,
                processing_ms=processing_ms,
            )
            await self._release_in_order(sequence)
            self.metrics.frames_released += 1
            return result

    async def _release_in_order(self, sequence: int) -> None:
        async with self._release_condition:
            while sequence != self._next_release:
                await self._release_condition.wait()
            self._next_release += 1
            self._release_condition.notify_all()

    async def _run_detector(
        self,
        registration: VideoDetectorRegistration,
        frame: VideoFrame,
        sequence: int,
    ) -> DetectorRun:
        if sequence % registration.cadence_frames:
            return DetectorRun(registration.name, "skipped")

        started = monotonic()
        status: DetectorRunStatus = "success"
        regions: tuple[VideoPrivacyRegion, ...] = ()
        error: str | None = None
        try:
            async with self._limits[registration.name]:
                result = await asyncio.wait_for(
                    self._invoke_detector(registration.detector, frame),
                    timeout=registration.timeout_ms / 1000,
                )
            if isinstance(result, (str, bytes, bytearray)) or result is None:
                raise ValueError("detector returned an invalid region sequence")
            regions = normalize_regions(
                tuple(result),
                frame,
                padding_px=self.config.padding_px,
                ttl_ms=registration.ttl_ms,
            )
        except asyncio.TimeoutError:
            status = "timeout"
            error = "detector timed out"
        except VideoDetectorUnavailable:
            status = "unavailable"
            error = "detector unavailable"
        except VideoDetectorExecutionError:
            status = "error"
            error = "detector execution failed"
        except (TypeError, ValueError):
            status = "invalid"
            error = "detector returned invalid output"
        except Exception:
            status = "error"
            error = "detector failed"
        return DetectorRun(
            detector=registration.name,
            status=status,
            regions=regions,
            duration_ms=(monotonic() - started) * 1000,
            error=error,
        )

    async def _invoke_detector(self, detector: VideoDetector, frame: VideoFrame) -> object:
        method = detector.detect
        if inspect.iscoroutinefunction(method):
            return await method(frame)
        result = await asyncio.to_thread(method, frame)
        if inspect.isawaitable(result):
            return await result
        return result


def _intersection_area(first: VideoPrivacyRegion, second: VideoPrivacyRegion) -> float:
    left = max(first.x, second.x)
    top = max(first.y, second.y)
    right = min(first.x + first.width, second.x + second.width)
    bottom = min(first.y + first.height, second.y + second.height)
    return max(0.0, right - left) * max(0.0, bottom - top)


def _intersection_over_union(first: VideoPrivacyRegion, second: VideoPrivacyRegion) -> float:
    intersection = _intersection_area(first, second)
    union = first.width * first.height + second.width * second.height - intersection
    return intersection / union if union else 0.0


def _merge_region(first: VideoPrivacyRegion, second: VideoPrivacyRegion) -> VideoPrivacyRegion:
    detectors = ",".join(sorted(set(first.detector.split(",") + second.detector.split(","))))
    return VideoPrivacyRegion(
        kind=first.kind,
        x=min(first.x, second.x),
        y=min(first.y, second.y),
        width=max(first.x + first.width, second.x + second.width) - min(first.x, second.x),
        height=max(first.y + first.height, second.y + second.height) - min(first.y, second.y),
        confidence=max(first.confidence, second.confidence),
        timestamp_ms=max(first.timestamp_ms, second.timestamp_ms),
        detector=detectors,
        expires_at_ms=max(first.expires_at_ms, second.expires_at_ms),
        track_id=first.track_id if first.track_id == second.track_id else None,
    )


def _color_for_channels(color: tuple[int, ...], channels: int) -> bytes:
    if any(not 0 <= value <= 255 for value in color):
        raise ValueError("cover colors must contain bytes between 0 and 255")
    if channels == 1:
        if not color:
            raise ValueError("cover color must not be empty")
        return bytes((round(sum(color[:3]) / min(3, len(color))),))
    if len(color) < 3:
        raise ValueError("RGB cover colors require at least three values")
    if channels == 4:
        return bytes((*color[:3], color[3] if len(color) > 3 else 255))
    return bytes(color[:3])


def _cover_region(
    data: bytearray,
    source: RasterFrame,
    bounds: tuple[int, int, int, int],
    color: tuple[int, ...],
) -> None:
    pixel = _color_for_channels(color, source.channels)
    left, top, right, bottom = bounds
    for y in range(top, bottom):
        row_start = (y * source.width + left) * source.channels
        row_end = (y * source.width + right) * source.channels
        data[row_start:row_end] = pixel * (right - left)


def _pixelate_region(
    data: bytearray,
    source: RasterFrame,
    bounds: tuple[int, int, int, int],
    block_size: int,
) -> None:
    original = source.data
    left, top, right, bottom = bounds
    for block_top in range(top, bottom, block_size):
        for block_left in range(left, right, block_size):
            sample_x = min(right - 1, block_left + block_size // 2)
            sample_y = min(bottom - 1, block_top + block_size // 2)
            sample_start = (sample_y * source.width + sample_x) * source.channels
            pixel = original[sample_start : sample_start + source.channels]
            for y in range(block_top, min(bottom, block_top + block_size)):
                for x in range(block_left, min(right, block_left + block_size)):
                    start = (y * source.width + x) * source.channels
                    data[start : start + source.channels] = pixel


def _blur_region(
    data: bytearray,
    source: RasterFrame,
    bounds: tuple[int, int, int, int],
    radius: int,
) -> None:
    original = source.data
    left, top, right, bottom = bounds
    for y in range(top, bottom):
        for x in range(left, right):
            sums = [0] * source.channels
            count = 0
            for sample_y in range(max(0, y - radius), min(source.height, y + radius + 1)):
                for sample_x in range(max(0, x - radius), min(source.width, x + radius + 1)):
                    start = (sample_y * source.width + sample_x) * source.channels
                    for channel in range(source.channels):
                        sums[channel] += original[start + channel]
                    count += 1
            start = (y * source.width + x) * source.channels
            data[start : start + source.channels] = bytes(value // count for value in sums)
