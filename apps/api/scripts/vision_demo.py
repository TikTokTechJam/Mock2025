"""Run the standalone visual privacy demo on an image or short video."""

from __future__ import annotations

import argparse
import asyncio
from argparse import Namespace
from pathlib import Path
from typing import Any

from privastream_api.pipeline.contracts import VideoFrame, VideoRegionDetection
from privastream_api.privacy.vision import (
    FrameContext,
    OcrDetectorConfig,
    OcrPiiDetector,
    PlateDetectorConfig,
    UltralyticsPlateDetector,
    VisualPrivacyDetector,
    VisionPrivacyService,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Redact visual privacy regions locally.")
    parser.add_argument("--input", type=Path, required=True, help="Input image or short video")
    parser.add_argument("--output", type=Path, required=True, help="Protected image or video")
    parser.add_argument("--plate", action="store_true", help="Enable the plate detector")
    parser.add_argument("--ocr-pii", action="store_true", help="Enable OCR and PII detection")
    parser.add_argument(
        "--plate-weights",
        type=Path,
        default=Path("weights/license_plate.pt"),
        help="Local YOLO-family plate weights; no model is downloaded by the demo",
    )
    parser.add_argument("--plate-confidence", type=float, default=0.45)
    parser.add_argument("--ocr-confidence", type=float, default=0.4)
    parser.add_argument("--padding", type=float, default=0.02)
    parser.add_argument("--plate-cadence", type=int, default=1)
    parser.add_argument("--ocr-cadence", type=int, default=5)
    parser.add_argument("--region-ttl", type=int, default=2)
    parser.add_argument("--ocr-language", action="append", default=None)
    parser.add_argument("--gpu", action="store_true", help="Enable OCR GPU inference")
    return parser


def _service(args: Namespace) -> VisionPrivacyService:
    detectors: list[VisualPrivacyDetector] = []
    if args.plate:
        detectors.append(
            UltralyticsPlateDetector(
                PlateDetectorConfig(
                    weights_path=args.plate_weights,
                    confidence_threshold=args.plate_confidence,
                    region_padding_ratio=args.padding,
                    cadence_frames=args.plate_cadence,
                    region_ttl_frames=args.region_ttl,
                )
            )
        )
    if args.ocr_pii:
        detectors.append(
            OcrPiiDetector(
                OcrDetectorConfig(
                    confidence_threshold=args.ocr_confidence,
                    region_padding_ratio=args.padding,
                    cadence_frames=args.ocr_cadence,
                    region_ttl_frames=args.region_ttl,
                    languages=tuple(args.ocr_language or ["en"]),
                    gpu=args.gpu,
                )
            )
        )
    if not detectors:
        raise ValueError("enable at least one detector with --plate or --ocr-pii")
    return VisionPrivacyService(detectors=detectors)


def _frame_context(image: Any, frame_index: int, timestamp_ms: int) -> FrameContext:
    if not hasattr(image, "shape"):
        raise ValueError("OpenCV returned an image without dimensions")
    height, width = image.shape[:2]
    return FrameContext(
        image=image,
        source=VideoFrame(width=width, height=height, timestamp_ms=timestamp_ms),
        frame_index=frame_index,
    )


def _redact(image: Any, regions: list[VideoRegionDetection]) -> Any:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for the demo; install the vision extra") from exc

    if not hasattr(image, "shape"):
        raise ValueError("OpenCV returned an image without dimensions")
    output = image.copy()
    height, width = output.shape[:2]
    for region in regions:
        x1 = max(0, min(width, int(region.x * width)))
        y1 = max(0, min(height, int(region.y * height)))
        x2 = max(0, min(width, int((region.x + region.width) * width)))
        y2 = max(0, min(height, int((region.y + region.height) * height)))
        if x2 <= x1 or y2 <= y1:
            continue
        roi = output[y1:y2, x1:x2]
        kernel = min(31, min(roi.shape[:2]))
        kernel = max(3, kernel if kernel % 2 else kernel - 1)
        output[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (kernel, kernel), 0)
    return output


async def _run(args: Namespace) -> None:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for the demo; install the vision extra") from exc

    service = _service(args)
    image = cv2.imread(str(args.input))
    if image is not None:
        regions = await service.detect(_frame_context(image, 0, 0))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(args.output), _redact(image, regions)):
            raise RuntimeError(f"could not write output to {args.output}")
        print(f"Processed 1 frame and emitted {len(regions)} privacy regions")
        return

    capture = cv2.VideoCapture(str(args.input))
    if not capture.isOpened():
        raise RuntimeError(f"could not open input {args.input}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(args.output),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError(f"could not open output {args.output}")

    frame_index = 0
    region_count = 0
    try:
        while True:
            has_frame, frame = capture.read()
            if not has_frame:
                break
            timestamp_ms = round(frame_index * 1000 / fps)
            regions = await service.detect(_frame_context(frame, frame_index, timestamp_ms))
            writer.write(_redact(frame, regions))
            region_count += len(regions)
            frame_index += 1
    finally:
        capture.release()
        writer.release()
    print(f"Processed {frame_index} frames and emitted {region_count} privacy regions")


def main() -> None:
    try:
        asyncio.run(_run(_parser().parse_args()))
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
