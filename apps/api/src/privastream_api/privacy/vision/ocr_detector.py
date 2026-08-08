"""Replaceable OCR adapter and deterministic visual-PII region detector."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Protocol

from privastream_api.pipeline.contracts import VideoRegionDetection
from privastream_api.privacy.text_pii import (
    PiiSpan,
    TextPiiRecognizer,
    TextPiiRecognizerConfig,
    TextPiiRecognizerExecutionError,
    TextPiiRecognizerUnavailable,
)
from privastream_api.privacy.vision.pii_classifier import normalize_ocr_text
from privastream_api.privacy.vision.service import (
    DetectorExecutionError,
    DetectorUnavailableError,
    FrameContext,
)

Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class OcrBlock:
    """Internal OCR output kept in memory until it becomes a privacy region."""

    text: str
    polygon: tuple[Point, ...]
    confidence: float

    def __post_init__(self) -> None:
        if len(self.polygon) < 4:
            raise ValueError("OCR polygon must contain at least four points")
        if not 0 <= self.confidence <= 1 or not isfinite(self.confidence):
            raise ValueError("OCR confidence must be between 0 and 1")


class OcrEngine(Protocol):
    """Local OCR engine boundary for EasyOCR or another provider."""

    def read(self, image: Any) -> Sequence[OcrBlock]:
        """Return OCR text, polygon, and confidence without logging text."""


@dataclass(frozen=True, slots=True)
class OcrDetectorConfig:
    """Runtime controls for OCR cadence, confidence, language, and padding."""

    confidence_threshold: float = 0.4
    region_padding_ratio: float = 0.02
    cadence_frames: int = 5
    region_ttl_frames: int = 2
    languages: tuple[str, ...] = ("en",)
    gpu: bool = False
    text_pii: TextPiiRecognizerConfig = field(default_factory=TextPiiRecognizerConfig)

    def __post_init__(self) -> None:
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")
        if not 0 <= self.region_padding_ratio <= 0.5:
            raise ValueError("region_padding_ratio must be between 0 and 0.5")
        if self.cadence_frames <= 0:
            raise ValueError("cadence_frames must be positive")
        if self.region_ttl_frames < 0:
            raise ValueError("region_ttl_frames must be non-negative")
        if not self.languages or any(not language.strip() for language in self.languages):
            raise ValueError("at least one OCR language is required")


class EasyOcrEngine:
    """Lazy EasyOCR adapter; model initialization never happens at import time."""

    def __init__(
        self,
        languages: tuple[str, ...] = ("en",),
        gpu: bool = False,
        model_storage_directory: str | None = None,
    ) -> None:
        self.languages = languages
        self.gpu = gpu
        self.model_storage_directory = model_storage_directory
        self._reader: Any | None = None

    def _ensure_reader(self) -> Any:
        if self._reader is not None:
            return self._reader
        try:
            import easyocr
        except ImportError as exc:
            raise DetectorUnavailableError(
                "EasyOCR is required for OCR; install the vision extra"
            ) from exc
        kwargs: dict[str, Any] = {"gpu": self.gpu}
        if self.model_storage_directory is not None:
            kwargs["model_storage_directory"] = self.model_storage_directory
        self._reader = easyocr.Reader(list(self.languages), **kwargs)
        return self._reader

    def read(self, image: Any) -> Sequence[OcrBlock]:
        try:
            raw_results = self._ensure_reader().readtext(image)
            blocks: list[OcrBlock] = []
            for raw_polygon, text, confidence in raw_results:
                polygon = tuple((float(point[0]), float(point[1])) for point in raw_polygon)
                blocks.append(OcrBlock(text=str(text), polygon=polygon, confidence=float(confidence)))
            return blocks
        except DetectorError:
            raise
        except Exception:
            raise DetectorExecutionError("OCR inference failed") from None


def _polygon_box(polygon: tuple[Point, ...]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _region_kind(matches: Sequence[PiiSpan]) -> str:
    kinds = {match.category for match in matches}
    return next(iter(kinds)) if len(kinds) == 1 else "custom_sensitive_text"


class OcrPiiDetector:
    """Turn sensitive OCR blocks into canonical privacy regions."""

    def __init__(
        self,
        config: OcrDetectorConfig,
        engine: OcrEngine | None = None,
        text_recognizer: TextPiiRecognizer | None = None,
    ) -> None:
        self.config = config
        self._engine = engine or EasyOcrEngine(config.languages, config.gpu)
        self._text_recognizer = text_recognizer or TextPiiRecognizer(config.text_pii)
        self._cached_regions: tuple[VideoRegionDetection, ...] = ()
        self._cached_frame_index: int | None = None

    def _cached_for(self, frame_index: int) -> list[VideoRegionDetection] | None:
        if self._cached_frame_index is None:
            return None
        age = frame_index - self._cached_frame_index
        if 0 <= age <= self.config.region_ttl_frames:
            return list(self._cached_regions)
        return None

    async def detect(self, frame: FrameContext) -> list[VideoRegionDetection]:
        if frame.frame_index % self.config.cadence_frames != 0:
            cached = self._cached_for(frame.frame_index)
            return cached if cached is not None else []

        try:
            blocks = self._engine.read(frame.image)
        except DetectorError:
            raise
        except Exception:
            raise DetectorExecutionError("OCR engine failed") from None
        regions: list[VideoRegionDetection] = []
        for block in blocks:
            if block.confidence < self.config.confidence_threshold:
                continue
            try:
                matches = self._text_recognizer.recognize(normalize_ocr_text(block.text))
            except TextPiiRecognizerUnavailable:
                raise DetectorUnavailableError("OCR text recognizer is unavailable") from None
            except TextPiiRecognizerExecutionError:
                raise DetectorExecutionError("OCR text recognizer failed") from None
            if not matches:
                continue
            x1, y1, x2, y2 = _polygon_box(block.polygon)
            padding_x = frame.source.width * self.config.region_padding_ratio
            padding_y = frame.source.height * self.config.region_padding_ratio
            x1 = max(0.0, x1 - padding_x)
            y1 = max(0.0, y1 - padding_y)
            x2 = min(float(frame.source.width), x2 + padding_x)
            y2 = min(float(frame.source.height), y2 + padding_y)
            if x2 <= x1 or y2 <= y1:
                continue
            kind = _region_kind(matches)
            if kind not in (
                "email",
                "phone_number",
                "postal_address",
                "government_id",
                "payment_identifier",
                "custom_sensitive_text",
            ):
                raise DetectorExecutionError("OCR classifier returned an unsupported region kind")
            regions.append(
                VideoRegionDetection(
                    kind=kind,
                    x=x1 / frame.source.width,
                    y=y1 / frame.source.height,
                    width=(x2 - x1) / frame.source.width,
                    height=(y2 - y1) / frame.source.height,
                    confidence=block.confidence,
                    timestamp_ms=frame.source.timestamp_ms,
                    detector="ocr-pii",
                )
            )

        self._cached_regions = tuple(regions)
        self._cached_frame_index = frame.frame_index
        return regions
