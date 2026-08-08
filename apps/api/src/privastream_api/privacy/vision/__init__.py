"""Standalone license-plate and visual-PII detection adapters."""

from privastream_api.privacy.vision.ocr_detector import (
    EasyOcrEngine,
    OcrBlock,
    OcrDetectorConfig,
    OcrPiiDetector,
)
from privastream_api.privacy.vision.plate_detector import (
    LetterboxTransform,
    PlateDetectorConfig,
    UltralyticsPlateDetector,
    map_letterboxed_box_to_original,
)
from privastream_api.privacy.vision.service import (
    DetectorExecutionError,
    DetectorUnavailableError,
    FrameContext,
    VisionPrivacyService,
    VisualPrivacyDetector,
)

__all__ = [
    "DetectorExecutionError",
    "DetectorUnavailableError",
    "EasyOcrEngine",
    "FrameContext",
    "LetterboxTransform",
    "OcrBlock",
    "OcrDetectorConfig",
    "OcrPiiDetector",
    "PlateDetectorConfig",
    "UltralyticsPlateDetector",
    "VisionPrivacyService",
    "VisualPrivacyDetector",
    "map_letterboxed_box_to_original",
]
