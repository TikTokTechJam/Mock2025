import asyncio
import inspect

import pytest

from privastream_api.pipeline.contracts import (
    VideoDetectorUnavailable,
    VideoFrame,
    VideoRegionDetection,
)
from privastream_api.pipeline.video import (
    RasterFrame,
    VideoCompositor,
    VideoOrchestrator,
    VideoOrchestrationConfig,
    merge_overlapping_regions,
    normalize_regions,
)


def _detection(timestamp_ms: int, *, x: float = 0.2) -> VideoRegionDetection:
    return VideoRegionDetection(
        kind="license_plate",
        x=x,
        y=0.2,
        width=0.2,
        height=0.2,
        confidence=0.9,
        timestamp_ms=timestamp_ms,
        detector="mock-plate",
    )


class FixedDetector:
    def __init__(self, result=(), *, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    async def detect(self, frame: VideoFrame):
        self.calls += 1
        if self.error:
            raise self.error
        result = self.result(frame.timestamp_ms) if callable(self.result) else self.result
        if inspect.isawaitable(result):
            return await result
        return result


def _frame(timestamp_ms: int, *, payload: bool = True) -> VideoFrame:
    return VideoFrame(
        width=10,
        height=10,
        timestamp_ms=timestamp_ms,
        payload=RasterFrame.solid(10, 10, (10, 20, 30)) if payload else None,
    )


def test_normalize_regions_pads_and_clamps_to_frame_bounds() -> None:
    normalized = normalize_regions(
        (_detection(100, x=0.02),),
        VideoFrame(width=100, height=100, timestamp_ms=100),
        padding_px=5,
        ttl_ms=50,
    )

    assert normalized[0].x == 0
    assert normalized[0].y == 0.15
    assert normalized[0].width == pytest.approx(0.27)
    assert normalized[0].expires_at_ms == 150


def test_same_kind_overlapping_regions_merge_conservatively() -> None:
    frame = VideoFrame(width=100, height=100, timestamp_ms=100)
    regions = normalize_regions(
        (_detection(100, x=0.2), _detection(100, x=0.3)),
        frame,
        padding_px=0,
        ttl_ms=100,
    )

    merged = merge_overlapping_regions(regions)

    assert len(merged) == 1
    assert merged[0].x == 0.2
    assert merged[0].width == pytest.approx(0.3)
    assert merged[0].confidence == 0.9


def test_cadence_ttl_preserves_skipped_masks_then_expires() -> None:
    detector = FixedDetector(lambda timestamp: (_detection(timestamp),) if timestamp == 0 else ())
    orchestrator = VideoOrchestrator(
        config=VideoOrchestrationConfig(),
        compositor=VideoCompositor(mode="cover"),
    )
    orchestrator.register("plate", detector, cadence_frames=2, ttl_ms=50)

    first, skipped, expired = asyncio.run(
        _process_three(orchestrator, (_frame(0), _frame(25), _frame(60)))
    )

    assert first.detector_runs[0].status == "success"
    assert skipped.detector_runs[0].status == "skipped"
    assert len(first.regions) == 1
    assert len(skipped.regions) == 1
    assert expired.detector_runs[0].status == "success"
    assert expired.regions == ()


def test_detector_failure_is_explicit_and_not_an_empty_success() -> None:
    detector = FixedDetector(error=VideoDetectorUnavailable())
    orchestrator = VideoOrchestrator()
    orchestrator.register("plate", detector)

    result = asyncio.run(orchestrator.process_frame(_frame(0, payload=False)))

    assert result.detector_runs[0].status == "unavailable"
    assert result.detector_runs[0].error == "detector unavailable"
    assert result.detector_failures
    assert result.regions == ()


def test_orchestrator_releases_concurrent_frames_in_sequence_order() -> None:
    async def delayed(frame: VideoFrame):
        if frame.timestamp_ms == 0:
            await asyncio.sleep(0.02)
        return (_detection(frame.timestamp_ms),)

    orchestrator = VideoOrchestrator()
    orchestrator.register("plate", FixedDetector(delayed))

    async def run() -> tuple:
        first = asyncio.create_task(orchestrator.process_frame(_frame(0)))
        second = asyncio.create_task(orchestrator.process_frame(_frame(1)))
        return await asyncio.gather(first, second)

    results = asyncio.run(run())

    assert [result.sequence for result in results] == [0, 1]
    assert orchestrator.metrics.frames_released == 2


def test_compositor_cover_and_full_frame_safe_cover_are_deterministic() -> None:
    source = _frame(0)
    region = normalize_regions(
        (_detection(0, x=0.2),), source, padding_px=0, ttl_ms=100
    )[0]
    compositor = VideoCompositor(mode="cover", cover_color=(255, 0, 0))

    protected = compositor.compose(source, (region,))
    safe = compositor.full_frame_safe_cover(source)

    assert protected is not None
    assert protected.pixel(2, 2) == (255, 0, 0)
    assert protected.pixel(0, 0) == (10, 20, 30)
    assert all(pixel == (255, 0, 0) for pixel in [safe.pixel(0, 0), safe.pixel(9, 9)])


async def _process_three(orchestrator: VideoOrchestrator, frames: tuple[VideoFrame, ...]):
    return tuple([await orchestrator.process_frame(frame) for frame in frames])
