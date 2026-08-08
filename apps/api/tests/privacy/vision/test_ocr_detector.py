import asyncio

import pytest

from privastream_api.pipeline.contracts import VideoFrame
from privastream_api.privacy.vision.ocr_detector import OcrBlock, OcrDetectorConfig, OcrPiiDetector
from privastream_api.privacy.vision.service import DetectorExecutionError, FrameContext


class FakeOcrEngine:
    def __init__(self, blocks: list[OcrBlock]) -> None:
        self.blocks = blocks

    def read(self, image: object) -> list[OcrBlock]:
        return self.blocks


class FailingOcrEngine:
    def read(self, image: object) -> list[OcrBlock]:
        raise RuntimeError("secret@example.com must never appear in logs")


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
