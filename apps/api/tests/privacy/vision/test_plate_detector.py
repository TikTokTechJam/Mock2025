import asyncio
from pathlib import Path

import pytest

from privastream_api.pipeline.contracts import VideoFrame
from privastream_api.pipeline.video import (
    RasterFrame,
    VideoOrchestrator,
    VideoOrchestrationConfig,
)
from privastream_api.privacy.vision.plate_detector import (
    LetterboxTransform,
    PlateDetectorConfig,
    PlateOrchestrationConfig,
    PlateVideoDetector,
    UltralyticsPlateDetector,
    map_letterboxed_box_to_original,
    register_plate_detector,
)
from privastream_api.privacy.vision.service import DetectorExecutionError, FrameContext


class FakeBoxes:
    xyxy = [[20.0, 110.0, 80.0, 150.0], [0.0, 80.0, 200.0, 160.0]]
    conf = [0.9, 0.8]
    cls = [0, 0]


class FakeResult:
    boxes = FakeBoxes()
    names = {0: "license_plate"}


class FakePlateModel:
    names = {0: "license_plate"}

    def predict(self, source: object, *, imgsz: int, conf: float, verbose: bool) -> list[FakeResult]:
        return [FakeResult()]


class FailingPlateModel:
    def predict(self, source: object, *, imgsz: int, conf: float, verbose: bool) -> list[FakeResult]:
        raise RuntimeError("model failure")


class OnePlateBoxes:
    xyxy = [[20.0, 110.0, 80.0, 150.0]]
    conf = [0.9]
    cls = [0]


class OnePlateResult:
    boxes = OnePlateBoxes()
    names = {0: "license_plate"}


class OnePlateModel:
    names = {0: "license_plate"}

    def predict(
        self, source: object, *, imgsz: int, conf: float, verbose: bool
    ) -> list[OnePlateResult]:
        return [OnePlateResult()]


class EmptyBoxes:
    xyxy: list[list[float]] = []
    conf: list[float] = []
    cls: list[float] = []


class EmptyResult:
    boxes = EmptyBoxes()
    names = {0: "license_plate"}


class EmptyPlateModel:
    names = {0: "license_plate"}

    def predict(
        self, source: object, *, imgsz: int, conf: float, verbose: bool
    ) -> list[EmptyResult]:
        return [EmptyResult()]


class FakeImage:
    shape = (100, 200, 3)


def _transform() -> LetterboxTransform:
    return LetterboxTransform(
        original_width=200,
        original_height=100,
        model_size=200,
        scale=1,
        pad_x=0,
        pad_y=50,
    )


def _letterbox(image: object, model_size: int) -> tuple[object, LetterboxTransform]:
    return object(), _transform()


def _frame() -> FrameContext:
    return FrameContext(
        image=object(),
        source=VideoFrame(width=200, height=100, timestamp_ms=456),
    )


def test_letterbox_coordinates_map_to_original_resolution() -> None:
    assert map_letterboxed_box_to_original((20, 110, 80, 150), _transform()) == (20, 60, 80, 100)


def test_multiple_plate_boxes_become_normalized_regions() -> None:
    detector = UltralyticsPlateDetector(
        PlateDetectorConfig(
            weights_path=Path("unused.pt"),
            confidence_threshold=0.5,
            region_padding_ratio=0,
        ),
        model=FakePlateModel(),
        letterbox=_letterbox,
    )

    regions = asyncio.run(detector.detect(_frame()))

    assert len(regions) == 2
    assert regions[0].kind == "license_plate"
    assert regions[0].x == 0.1
    assert regions[0].y == 0.6
    assert regions[1].x == 0
    assert regions[1].y == 0.3
    assert regions[1].width == 1
    assert regions[1].height == 0.7


def test_source_frame_inference_omits_standalone_padding() -> None:
    detector = UltralyticsPlateDetector(
        PlateDetectorConfig(
            weights_path=Path("unused.pt"),
            region_padding_ratio=0.1,
        ),
        model=OnePlateModel(),
        letterbox=_letterbox,
    )

    source_regions = asyncio.run(
        detector.detect_source_frame(
            FrameContext(image=FakeImage(), source=_frame().source)
        )
    )
    standalone_regions = asyncio.run(
        detector.detect(FrameContext(image=FakeImage(), source=_frame().source))
    )

    assert source_regions[0].x == 0.1
    assert source_regions[0].y == 0.6
    assert source_regions[0].width == 0.3
    assert source_regions[0].height == 0.4
    assert standalone_regions[0].x == 0
    assert standalone_regions[0].y == 0.5
    assert standalone_regions[0].width == 0.5
    assert standalone_regions[0].height == 0.5


def test_plate_adapter_registers_with_scheduler_and_applies_padding_once() -> None:
    detector = UltralyticsPlateDetector(
        PlateDetectorConfig(
            weights_path=Path("unused.pt"),
            region_padding_ratio=0.1,
        ),
        model=OnePlateModel(),
        letterbox=_letterbox,
    )
    orchestrator = VideoOrchestrator(
        config=VideoOrchestrationConfig(padding_px=5),
    )
    adapter = register_plate_detector(
        orchestrator,
        detector,
        config=PlateOrchestrationConfig(name="plate", ttl_ms=100),
        image_provider=lambda _frame: FakeImage(),
    )

    result = asyncio.run(
        orchestrator.process_frame(
            VideoFrame(
                width=200,
                height=100,
                timestamp_ms=456,
                payload=RasterFrame.solid(200, 100, (10, 20, 30)),
            )
        )
    )

    assert isinstance(orchestrator.registrations[0].detector, PlateVideoDetector)
    assert orchestrator.registrations[0].detector is adapter
    assert result.detector_runs[0].status == "success"
    assert len(result.regions) == 1
    assert result.regions[0].x == pytest.approx(0.075)
    assert result.regions[0].y == pytest.approx(0.55)
    assert result.regions[0].width == pytest.approx(0.35)
    assert result.regions[0].height == pytest.approx(0.45)
    assert result.regions[0].expires_at_ms == 556


def test_plate_adapter_failure_reaches_scheduler_as_detector_error() -> None:
    detector = UltralyticsPlateDetector(
        PlateDetectorConfig(weights_path=Path("unused.pt")),
        model=FailingPlateModel(),
        letterbox=_letterbox,
    )
    orchestrator = VideoOrchestrator()
    register_plate_detector(
        orchestrator,
        detector,
        image_provider=lambda _frame: FakeImage(),
    )

    result = asyncio.run(
        orchestrator.process_frame(
            VideoFrame(
                width=200,
                height=100,
                timestamp_ms=456,
                payload=RasterFrame.solid(200, 100, (10, 20, 30)),
            )
        )
    )

    assert result.detector_runs[0].status == "error"
    assert result.detector_runs[0].error == "detector execution failed"
    assert result.detector_failures
    assert result.regions == ()


def test_plate_adapter_zero_detections_are_a_successful_result() -> None:
    detector = UltralyticsPlateDetector(
        PlateDetectorConfig(weights_path=Path("unused.pt")),
        model=EmptyPlateModel(),
        letterbox=_letterbox,
    )
    orchestrator = VideoOrchestrator()
    register_plate_detector(
        orchestrator,
        detector,
        image_provider=lambda _frame: FakeImage(),
    )

    result = asyncio.run(
        orchestrator.process_frame(
            VideoFrame(
                width=200,
                height=100,
                timestamp_ms=456,
                payload=RasterFrame.solid(200, 100, (10, 20, 30)),
            )
        )
    )

    assert result.detector_runs[0].status == "success"
    assert not result.detector_failures
    assert result.regions == ()


def test_plate_model_failure_is_not_silently_empty() -> None:
    detector = UltralyticsPlateDetector(
        PlateDetectorConfig(weights_path=Path("unused.pt")),
        model=FailingPlateModel(),
        letterbox=_letterbox,
    )

    with pytest.raises(DetectorExecutionError):
        asyncio.run(detector.detect(_frame()))
