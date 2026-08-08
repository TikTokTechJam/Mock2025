import asyncio
from pathlib import Path

import pytest

from privastream_api.pipeline.contracts import VideoFrame
from privastream_api.privacy.vision.plate_detector import (
    LetterboxTransform,
    PlateDetectorConfig,
    UltralyticsPlateDetector,
    map_letterboxed_box_to_original,
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


def test_plate_model_failure_is_not_silently_empty() -> None:
    detector = UltralyticsPlateDetector(
        PlateDetectorConfig(weights_path=Path("unused.pt")),
        model=FailingPlateModel(),
        letterbox=_letterbox,
    )

    with pytest.raises(DetectorExecutionError):
        asyncio.run(detector.detect(_frame()))
