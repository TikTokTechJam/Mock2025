"""YOLO-family license-plate adapter with coordinate-safe normalization."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any, Literal, Protocol

from privastream_api.pipeline.contracts import VideoFrame, VideoRegionDetection
from privastream_api.pipeline.video import VideoOrchestrator
from privastream_api.privacy.vision.service import (
    DetectorError,
    DetectorExecutionError,
    DetectorUnavailableError,
    FrameContext,
)

Box = tuple[float, float, float, float]
LetterboxFunction = Callable[[Any, int], tuple[Any, "LetterboxTransform"]]
FrameImageProvider = Callable[[VideoFrame], Any]


@dataclass(frozen=True, slots=True)
class LetterboxTransform:
    """Transform metadata needed to map model-input boxes to source pixels."""

    original_width: int
    original_height: int
    model_size: int
    scale: float
    pad_x: float
    pad_y: float


@dataclass(frozen=True, slots=True)
class PlateDetectorConfig:
    """Runtime controls for the local YOLO-family plate adapter."""

    weights_path: Path
    confidence_threshold: float = 0.45
    region_padding_ratio: float = 0.02
    model_input_size: int = 640
    cadence_frames: int = 1
    region_ttl_frames: int = 0
    class_names: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")
        if not 0 <= self.region_padding_ratio <= 0.5:
            raise ValueError("region_padding_ratio must be between 0 and 0.5")
        if self.model_input_size <= 0:
            raise ValueError("model_input_size must be positive")
        if self.cadence_frames <= 0:
            raise ValueError("cadence_frames must be positive")
        if self.region_ttl_frames < 0:
            raise ValueError("region_ttl_frames must be non-negative")


@dataclass(frozen=True, slots=True)
class PlateOrchestrationConfig:
    """#4 scheduler settings for the production plate adapter."""

    name: str = "license-plate"
    cadence_frames: int = 1
    timeout_ms: int = 100
    ttl_ms: int = 250
    max_concurrency: int = 1

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if self.cadence_frames <= 0:
            raise ValueError("cadence_frames must be positive")
        if self.timeout_ms <= 0 or self.ttl_ms <= 0:
            raise ValueError("timeout_ms and ttl_ms must be positive")
        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")


class PlateModel(Protocol):
    """Small subset of the Ultralytics model API used by this adapter."""

    def predict(
        self,
        source: Any,
        *,
        imgsz: int,
        conf: float,
        verbose: bool,
    ) -> Sequence[Any]:
        """Run inference on one already-letterboxed frame."""


def create_letterbox_transform(
    original_width: int,
    original_height: int,
    model_size: int,
) -> LetterboxTransform:
    """Calculate square letterbox scale and padding for source dimensions."""

    if original_width <= 0 or original_height <= 0 or model_size <= 0:
        raise ValueError("frame and model dimensions must be positive")
    scale = min(model_size / original_width, model_size / original_height)
    resized_width = round(original_width * scale)
    resized_height = round(original_height * scale)
    return LetterboxTransform(
        original_width=original_width,
        original_height=original_height,
        model_size=model_size,
        scale=scale,
        pad_x=(model_size - resized_width) / 2,
        pad_y=(model_size - resized_height) / 2,
    )


def letterbox_image(image: Any, model_size: int) -> tuple[Any, LetterboxTransform]:
    """Resize and pad an image using OpenCV, loaded only when the adapter runs."""

    try:
        import cv2
    except ImportError as exc:
        raise DetectorUnavailableError(
            "OpenCV is required for the plate adapter; install the vision extra"
        ) from exc

    if image is None or not hasattr(image, "shape") or len(image.shape) < 2:
        raise DetectorExecutionError("plate detector received an invalid image")
    original_height, original_width = image.shape[:2]
    transform = create_letterbox_transform(original_width, original_height, model_size)
    resized_width = round(original_width * transform.scale)
    resized_height = round(original_height * transform.scale)
    resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
    pad_left = int(transform.pad_x)
    pad_top = int(transform.pad_y)
    pad_right = model_size - resized_width - pad_left
    pad_bottom = model_size - resized_height - pad_top
    padded = cv2.copyMakeBorder(
        resized,
        pad_top,
        pad_bottom,
        pad_left,
        pad_right,
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114),
    )
    return padded, transform


def map_letterboxed_box_to_original(box: Box, transform: LetterboxTransform) -> Box:
    """Map an x1/y1/x2/y2 model-input box into clamped source pixels."""

    x1, y1, x2, y2 = box
    mapped = (
        (x1 - transform.pad_x) / transform.scale,
        (y1 - transform.pad_y) / transform.scale,
        (x2 - transform.pad_x) / transform.scale,
        (y2 - transform.pad_y) / transform.scale,
    )
    return (
        max(0.0, min(float(transform.original_width), mapped[0])),
        max(0.0, min(float(transform.original_height), mapped[1])),
        max(0.0, min(float(transform.original_width), mapped[2])),
        max(0.0, min(float(transform.original_height), mapped[3])),
    )


def _padded_box(box: Box, transform: LetterboxTransform, padding_ratio: float) -> Box:
    padding_x = transform.original_width * padding_ratio
    padding_y = transform.original_height * padding_ratio
    x1, y1, x2, y2 = box
    return (
        max(0.0, x1 - padding_x),
        max(0.0, y1 - padding_y),
        min(float(transform.original_width), x2 + padding_x),
        min(float(transform.original_height), y2 + padding_y),
    )


def _as_rows(value: Any) -> list[Any]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if value is None:
        return []
    if isinstance(value, (tuple, list)):
        return list(value)
    return [value]


def _as_scalar(value: Any, index: int, default: float = 0.0) -> float:
    values = _as_rows(value)
    if not values:
        return default
    candidate = values[index] if index < len(values) else values[-1]
    if isinstance(candidate, (tuple, list)):
        candidate = candidate[0]
    return float(candidate)


def _class_name(names: Any, class_id: int) -> str | None:
    if names is None:
        return None
    if isinstance(names, dict):
        value = names.get(class_id)
    elif isinstance(names, (tuple, list)) and class_id < len(names):
        value = names[class_id]
    else:
        value = None
    return str(value).casefold() if value is not None else None


class UltralyticsPlateDetector:
    """License-plate detector using a local YOLO-family weight file."""

    def __init__(
        self,
        config: PlateDetectorConfig,
        model: PlateModel | None = None,
        letterbox: LetterboxFunction = letterbox_image,
    ) -> None:
        self.config = config
        self._model = model
        self._letterbox = letterbox
        self._cached_regions: tuple[VideoRegionDetection, ...] = ()
        self._cached_frame_index: int | None = None

    def _ensure_model(self) -> PlateModel:
        if self._model is not None:
            return self._model
        if not self.config.weights_path.is_file():
            raise DetectorUnavailableError(
                f"plate weights not found at {self.config.weights_path}; provide a local weight file"
            )
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise DetectorUnavailableError(
                "Ultralytics is required for the plate adapter; install the vision extra"
            ) from exc
        model = YOLO(str(self.config.weights_path))
        self._model = model
        return model

    def _cached_for(self, frame_index: int) -> list[VideoRegionDetection] | None:
        if self._cached_frame_index is None:
            return None
        age = frame_index - self._cached_frame_index
        if 0 <= age <= self.config.region_ttl_frames:
            return list(self._cached_regions)
        return None

    async def detect_source_frame(self, frame: FrameContext) -> list[VideoRegionDetection]:
        """Infer once and return source-frame geometry without demo padding.

        The shared video engine owns production cadence, TTL, and padding. This
        method is the reusable inference boundary for that engine; ``detect``
        below retains the standalone module's configured behavior.
        """

        return await self._detect_once(frame, padding_ratio=0)

    async def detect(self, frame: FrameContext) -> list[VideoRegionDetection]:
        """Run the standalone detector with its local cadence, TTL, and padding."""

        if frame.frame_index % self.config.cadence_frames != 0:
            cached = self._cached_for(frame.frame_index)
            return cached if cached is not None else []

        regions = await self._detect_once(
            frame, padding_ratio=self.config.region_padding_ratio
        )
        self._cached_regions = tuple(regions)
        self._cached_frame_index = frame.frame_index
        return regions

    async def _detect_once(
        self, frame: FrameContext, *, padding_ratio: float
    ) -> list[VideoRegionDetection]:
        model_input, transform = self._letterbox(frame.image, self.config.model_input_size)
        try:
            results = self._ensure_model().predict(
                source=model_input,
                imgsz=self.config.model_input_size,
                conf=self.config.confidence_threshold,
                verbose=False,
            )
        except DetectorError:
            raise
        except Exception as exc:
            raise DetectorExecutionError("license-plate inference failed") from exc

        regions: list[VideoRegionDetection] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            coordinates = _as_rows(getattr(boxes, "xyxy", None))
            confidences = getattr(boxes, "conf", None)
            class_ids = getattr(boxes, "cls", None)
            names = getattr(result, "names", getattr(self._model, "names", None))
            for index, raw_box in enumerate(coordinates):
                if not isinstance(raw_box, (tuple, list)) or len(raw_box) != 4:
                    raise DetectorExecutionError("plate model returned an invalid bounding box")
                confidence = _as_scalar(confidences, index, default=0.0)
                if not isfinite(confidence) or confidence < self.config.confidence_threshold:
                    continue
                class_id = int(_as_scalar(class_ids, index, default=0.0))
                name = _class_name(names, class_id)
                if self.config.class_names is not None and name not in self.config.class_names:
                    continue
                mapped = map_letterboxed_box_to_original(tuple(map(float, raw_box)), transform)
                padded = _padded_box(mapped, transform, padding_ratio)
                x1, y1, x2, y2 = padded
                if x2 <= x1 or y2 <= y1:
                    continue
                regions.append(
                    VideoRegionDetection(
                        kind="license_plate",
                        x=x1 / transform.original_width,
                        y=y1 / transform.original_height,
                        width=(x2 - x1) / transform.original_width,
                        height=(y2 - y1) / transform.original_height,
                        confidence=confidence,
                        timestamp_ms=frame.source.timestamp_ms,
                        detector="yolo-license-plate",
                    )
                )

        return regions


class PlateVideoDetector:
    """Thin #6 adapter from the #19 plate detector into #4's video contract."""

    kind: Literal["license_plate"] = "license_plate"

    def __init__(
        self,
        detector: UltralyticsPlateDetector,
        *,
        image_provider: FrameImageProvider | None = None,
    ) -> None:
        self.detector = detector
        self._image_provider = image_provider or _payload_image

    async def detect(self, frame: VideoFrame) -> list[VideoRegionDetection]:
        """Return source-frame regions; scheduler policy is applied by #4."""

        image = self._image_provider(frame)
        if image is None or not hasattr(image, "shape") or len(image.shape) < 2:
            raise DetectorExecutionError(
                "plate adapter requires a model-compatible source image"
            )
        image_height, image_width = image.shape[:2]
        if image_width != frame.width or image_height != frame.height:
            raise DetectorExecutionError(
                "plate image dimensions do not match the source frame"
            )
        return await self.detector.detect_source_frame(
            FrameContext(image=image, source=frame)
        )


def _payload_image(frame: VideoFrame) -> Any:
    """Use the opaque frame payload when it is already model-compatible."""

    return frame.payload


def register_plate_detector(
    orchestrator: VideoOrchestrator,
    detector: UltralyticsPlateDetector,
    *,
    config: PlateOrchestrationConfig | None = None,
    image_provider: FrameImageProvider | None = None,
) -> PlateVideoDetector:
    """Register the plate adapter with #4 and return the registered adapter."""

    policy = config or PlateOrchestrationConfig()
    adapter = PlateVideoDetector(detector, image_provider=image_provider)
    orchestrator.register(
        policy.name,
        adapter,
        cadence_frames=policy.cadence_frames,
        timeout_ms=policy.timeout_ms,
        ttl_ms=policy.ttl_ms,
        max_concurrency=policy.max_concurrency,
    )
    return adapter
