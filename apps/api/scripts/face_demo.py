"""Run standalone creator enrollment and face protection on an image or clip."""

from __future__ import annotations

import argparse
import asyncio
from argparse import Namespace
from pathlib import Path
from typing import Any

from privastream_api.pipeline.contracts import VideoFrame, VideoRegionDetection
from privastream_api.privacy.face import (
    CreatorFaceDetector,
    CreatorFaceDetectorConfig,
    CreatorFaceEnrollmentService,
    FaceEnrollmentConfig,
    InMemoryCreatorEmbeddingStore,
    InsightFaceConfig,
    InsightFaceFaceModel,
)
from privastream_api.privacy.vision.service import FrameContext


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Enroll a creator explicitly and protect non-creator faces locally."
    )
    parser.add_argument("--input", type=Path, required=True, help="Input image or short video")
    parser.add_argument("--output", type=Path, required=True, help="Protected image or video")
    parser.add_argument(
        "--enrollment",
        type=Path,
        action="append",
        default=[],
        help="Consented creator enrollment image; repeat for several samples",
    )
    parser.add_argument(
        "--consent",
        action="store_true",
        help="Confirm the creator explicitly consented to enrollment",
    )
    parser.add_argument(
        "--model-root",
        type=Path,
        default=Path("models/insightface"),
        help="Local InsightFace root containing models/<model-name>",
    )
    parser.add_argument("--model-name", default="buffalo_l")
    parser.add_argument("--match-threshold", type=float, default=0.55)
    parser.add_argument("--ambiguity-margin", type=float, default=0.05)
    return parser


def _context(image: Any, frame_index: int, timestamp_ms: int) -> FrameContext:
    if image is None or not hasattr(image, "shape") or len(image.shape) < 2:
        raise ValueError("OpenCV returned an image without dimensions")
    height, width = image.shape[:2]
    return FrameContext(
        image=image,
        source=VideoFrame(width=width, height=height, timestamp_ms=timestamp_ms),
        frame_index=frame_index,
    )


def _redact(image: Any, regions: list[VideoRegionDetection]) -> Any:
    """Apply a local demo-only blur with a small visual safety margin."""

    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for the demo; install the face extra") from exc

    output = image.copy()
    height, width = output.shape[:2]
    padding_x = max(2, round(width * 0.02))
    padding_y = max(2, round(height * 0.02))
    for region in regions:
        x1 = max(0, min(width, int(region.x * width) - padding_x))
        y1 = max(0, min(height, int(region.y * height) - padding_y))
        x2 = max(0, min(width, int((region.x + region.width) * width) + padding_x))
        y2 = max(0, min(height, int((region.y + region.height) * height) + padding_y))
        if x2 <= x1 or y2 <= y1:
            continue
        roi = output[y1:y2, x1:x2]
        if min(roi.shape[:2]) < 3:
            output[y1:y2, x1:x2] = (0, 0, 0)
            continue
        kernel = min(31, min(roi.shape[:2]))
        kernel = max(3, kernel if kernel % 2 else kernel - 1)
        output[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (kernel, kernel), 0)
    return output


def _build_detector(args: Namespace) -> tuple[CreatorFaceEnrollmentService, CreatorFaceDetector]:
    model = InsightFaceFaceModel(
        InsightFaceConfig(model_root=args.model_root, model_name=args.model_name)
    )
    store = InMemoryCreatorEmbeddingStore()
    enrollment = CreatorFaceEnrollmentService(
        model,
        store,
        FaceEnrollmentConfig(),
    )
    detector = CreatorFaceDetector(
        model,
        store,
        CreatorFaceDetectorConfig(
            creator_match_threshold=args.match_threshold,
            ambiguity_margin=args.ambiguity_margin,
        ),
    )
    return enrollment, detector


async def _run(args: Namespace) -> None:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for the demo; install the face extra") from exc

    enrollment, detector = _build_detector(args)
    if args.enrollment:
        if not args.consent:
            raise RuntimeError("--consent is required when enrollment images are supplied")
        enrollment_images = []
        for path in args.enrollment:
            image = cv2.imread(str(path))
            if image is None:
                raise RuntimeError(f"could not read enrollment image {path}")
            enrollment_images.append(image)
        result = enrollment.enroll(enrollment_images, consent=True)
        if not result.enrolled:
            reasons = ", ".join(rejection.reason for rejection in result.rejections)
            raise RuntimeError(f"enrollment did not produce a valid creator profile ({reasons})")

    image = cv2.imread(str(args.input))
    if image is not None:
        regions = await detector.detect(_context(image, 0, 0))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(args.output), _redact(image, regions)):
            raise RuntimeError(f"could not write output to {args.output}")
        print(f"Processed 1 frame and emitted {len(regions)} protected face regions")
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
    protected_count = 0
    try:
        while True:
            has_frame, frame = capture.read()
            if not has_frame:
                break
            timestamp_ms = round(frame_index * 1000 / fps)
            regions = await detector.detect(_context(frame, frame_index, timestamp_ms))
            writer.write(_redact(frame, regions))
            protected_count += len(regions)
            frame_index += 1
    finally:
        capture.release()
        writer.release()
    print(f"Processed {frame_index} frames and emitted {protected_count} protected face regions")


def main() -> None:
    try:
        asyncio.run(_run(_parser().parse_args()))
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
