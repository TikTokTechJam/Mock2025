import asyncio
from collections.abc import Sequence

import pytest

from privastream_api.pipeline.contracts import VideoFrame
from privastream_api.pipeline.video import (
    RasterFrame,
    VideoOrchestrator,
    VideoOrchestrationConfig,
)
from privastream_api.privacy.text_pii import PiiSpan, TextPiiRecognizerUnavailable
from privastream_api.privacy.vision.ocr_detector import (
    OcrBlock,
    OcrDetectorConfig,
    OcrOrchestrationConfig,
    OcrPiiDetector,
    OcrVideoDetector,
    register_ocr_detector,
)
from privastream_api.privacy.vision.service import DetectorExecutionError, FrameContext


class FakeOcrEngine:
    def __init__(self, blocks: list[OcrBlock]) -> None:
        self.blocks = blocks

    def read(self, image: object) -> list[OcrBlock]:
        return self.blocks


class FailingOcrEngine:
    def read(self, image: object) -> list[OcrBlock]:
        raise RuntimeError("secret@example.com must never appear in logs")


class UnavailableTextRecognizer:
    def recognize(self, text: str) -> Sequence[PiiSpan]:
        raise TextPiiRecognizerUnavailable("contextual recognizer unavailable")


class FakeImage:
    shape = (100, 200, 3)


def _frame() -> FrameContext:
    return FrameContext(
        image=object(),
        source=VideoFrame(width=200, height=100, timestamp_ms=123),
    )


def test_email_and_phone_regions_map_to_original_frame() -> None:
    detector = OcrPiiDetector(
        OcrDetectorConfig(region_padding_ratio=0, cadence_frames=1, region_ttl_frames=0),
        engine=FakeOcrEngine(
            [
                OcrBlock(
                    "owner@example.com",
                    ((20, 10), (120, 10), (120, 30), (20, 30)),
                    0.95,
                ),
                OcrBlock(
                    "+65 8123 4567",
                    ((40, 50), (140, 50), (140, 70), (40, 70)),
                    0.9,
                ),
                OcrBlock(
                    "Benign shop sign",
                    ((0, 0), (100, 0), (100, 8), (0, 8)),
                    0.99,
                ),
            ]
        ),
    )

    regions = asyncio.run(detector.detect(_frame()))

    assert [region.kind for region in regions] == ["email", "phone_number"]
    assert regions[0].x == 0.1
    assert regions[0].width == 0.5
    assert regions[1].y == 0.5


def test_ocr_failure_surfaces_without_returning_empty_regions() -> None:
    detector = OcrPiiDetector(
        OcrDetectorConfig(cadence_frames=1),
        engine=FailingOcrEngine(),
    )

    with pytest.raises(DetectorExecutionError, match="^OCR engine failed$"):
        asyncio.run(detector.detect(_frame()))


def test_ocr_cadence_reuses_regions_for_short_ttl() -> None:
    detector = OcrPiiDetector(
        OcrDetectorConfig(cadence_frames=2, region_ttl_frames=1, region_padding_ratio=0),
        engine=FakeOcrEngine(
            [OcrBlock("owner@example.com", ((0, 0), (100, 0), (100, 20), (0, 20)), 0.9)]
        ),
    )

    first = asyncio.run(detector.detect(_frame()))
    cached_frame = FrameContext(image=object(), source=_frame().source, frame_index=1)
    cached = asyncio.run(detector.detect(cached_frame))

    assert first == cached


def test_source_frame_inference_omits_standalone_padding() -> None:
    detector = OcrPiiDetector(
        OcrDetectorConfig(
            region_padding_ratio=0.1,
            cadence_frames=1,
            region_ttl_frames=0,
        ),
        engine=FakeOcrEngine(
            [
                OcrBlock(
                    "owner@example.com",
                    ((20, 10), (120, 10), (120, 30), (20, 30)),
                    0.9,
                )
            ]
        ),
    )

    source_regions = asyncio.run(detector.detect_source_frame(_frame()))
    standalone_regions = asyncio.run(detector.detect(_frame()))

    assert source_regions[0].x == 0.1
    assert source_regions[0].y == 0.1
    assert source_regions[0].width == 0.5
    assert source_regions[0].height == 0.2
    assert standalone_regions[0].x == 0
    assert standalone_regions[0].y == 0
    assert standalone_regions[0].width == 0.7
    assert standalone_regions[0].height == 0.4


def test_ocr_adapter_registers_with_scheduler_and_applies_padding_once() -> None:
    detector = OcrPiiDetector(
        OcrDetectorConfig(region_padding_ratio=0.1, cadence_frames=1),
        engine=FakeOcrEngine(
            [
                OcrBlock(
                    "owner@example.com",
                    ((20, 10), (120, 10), (120, 30), (20, 30)),
                    0.9,
                )
            ]
        ),
    )
    orchestrator = VideoOrchestrator(
        config=VideoOrchestrationConfig(padding_px=5),
    )
    adapter = register_ocr_detector(
        orchestrator,
        detector,
        config=OcrOrchestrationConfig(name="ocr", cadence_frames=1, ttl_ms=100),
        image_provider=lambda _frame: FakeImage(),
    )

    result = asyncio.run(
        orchestrator.process_frame(
            VideoFrame(
                width=200,
                height=100,
                timestamp_ms=123,
                payload=RasterFrame.solid(200, 100, (10, 20, 30)),
            )
        )
    )

    assert isinstance(orchestrator.registrations[0].detector, OcrVideoDetector)
    assert orchestrator.registrations[0].detector is adapter
    assert result.detector_runs[0].status == "success"
    assert len(result.regions) == 1
    assert result.regions[0].x == pytest.approx(0.075)
    assert result.regions[0].y == pytest.approx(0.05)
    assert result.regions[0].width == pytest.approx(0.55)
    assert result.regions[0].height == pytest.approx(0.3)
    assert result.regions[0].expires_at_ms == 223


def test_ocr_adapter_benign_text_is_successful_zero_detection() -> None:
    detector = OcrPiiDetector(
        OcrDetectorConfig(cadence_frames=1),
        engine=FakeOcrEngine(
            [
                OcrBlock(
                    "Benign shop sign",
                    ((0, 0), (100, 0), (100, 20), (0, 20)),
                    0.99,
                )
            ]
        ),
    )
    orchestrator = VideoOrchestrator()
    register_ocr_detector(
        orchestrator,
        detector,
        config=OcrOrchestrationConfig(name="ocr", cadence_frames=1),
        image_provider=lambda _frame: FakeImage(),
    )

    result = asyncio.run(
        orchestrator.process_frame(
            VideoFrame(
                width=200,
                height=100,
                timestamp_ms=123,
                payload=RasterFrame.solid(200, 100, (10, 20, 30)),
            )
        )
    )

    assert result.detector_runs[0].status == "success"
    assert not result.detector_failures
    assert result.regions == ()


def test_ocr_engine_failure_reaches_scheduler_as_detector_error() -> None:
    detector = OcrPiiDetector(
        OcrDetectorConfig(cadence_frames=1),
        engine=FailingOcrEngine(),
    )
    orchestrator = VideoOrchestrator()
    register_ocr_detector(
        orchestrator,
        detector,
        config=OcrOrchestrationConfig(name="ocr", cadence_frames=1),
        image_provider=lambda _frame: FakeImage(),
    )

    result = asyncio.run(
        orchestrator.process_frame(
            VideoFrame(
                width=200,
                height=100,
                timestamp_ms=123,
                payload=RasterFrame.solid(200, 100, (10, 20, 30)),
            )
        )
    )

    assert result.detector_runs[0].status == "error"
    assert result.detector_runs[0].error == "detector execution failed"
    assert result.detector_failures
    assert result.regions == ()


def test_ocr_recognizer_unavailability_reaches_scheduler() -> None:
    detector = OcrPiiDetector(
        OcrDetectorConfig(cadence_frames=1),
        engine=FakeOcrEngine(
            [
                OcrBlock(
                    "owner@example.com",
                    ((20, 10), (120, 10), (120, 30), (20, 30)),
                    0.9,
                )
            ]
        ),
        text_recognizer=UnavailableTextRecognizer(),
    )
    orchestrator = VideoOrchestrator()
    register_ocr_detector(
        orchestrator,
        detector,
        config=OcrOrchestrationConfig(name="ocr", cadence_frames=1),
        image_provider=lambda _frame: FakeImage(),
    )

    result = asyncio.run(
        orchestrator.process_frame(
            VideoFrame(
                width=200,
                height=100,
                timestamp_ms=123,
                payload=RasterFrame.solid(200, 100, (10, 20, 30)),
            )
        )
    )

    assert result.detector_runs[0].status == "unavailable"
    assert result.detector_runs[0].error == "detector unavailable"
    assert result.detector_failures
    assert result.regions == ()
