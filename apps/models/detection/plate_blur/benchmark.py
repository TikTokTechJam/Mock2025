"""
benchmark.py

Benchmark RF-DETR Small and YOLO11 models on the same YOLO-format
license-plate dataset.

Metrics:
    - AP50
    - AP50:95
    - Mean latency
    - Median latency
    - P95 latency
    - P99 latency
    - FPS

Latency:
    - Image loading is excluded.
    - Warm-up iterations are excluded.
    - Preprocessing + model inference + postprocessing are included.
    - Each image is benchmarked individually (batch size = 1).
"""

from pathlib import Path
import time
import csv

import cv2
import numpy as np
import torch

from ultralytics import YOLO
from rfdetr import RFDETRSmall


# ============================================================
# Configuration
# ============================================================

DATASET_DIR = Path("sg_plate_dataset")
TEST_IMAGE_DIR = DATASET_DIR / "test" / "images"

YOLO_MODEL_PATH = "yolov11/checkpoints/best.pt"
RFDETR_MODEL_PATH = "rf-detr/checkpoints/rf-detr-small.pth"

IMAGE_SIZE = 512

CONFIDENCE_THRESHOLD = 0.001
IOU_THRESHOLD = 0.5
WARMUP_RUNS = 20
BENCHMARK_RUNS = 200

DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"


# ============================================================
# Utility
# ============================================================

def get_test_images():
    """
    Get all test images.
    """

    extensions = ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp"]

    image_paths = []

    for ext in extensions:
        image_paths.extend(TEST_IMAGE_DIR.glob(ext))

    image_paths = sorted(image_paths)

    if not image_paths:
        raise RuntimeError(
            f"No test images found in {TEST_IMAGE_DIR}"
        )

    return image_paths


def load_images(image_paths):
    """
    Load all test images into memory.

    This allows us to exclude disk I/O from
    latency measurement.
    """

    images = []

    valid_paths = []

    for path in image_paths:

        image = cv2.imread(str(path))

        if image is None:
            print(f"WARNING: Could not read {path}")
            continue

        images.append(image)
        valid_paths.append(path)

    return valid_paths, images


# ============================================================
# RF-DETR adapter
# ============================================================

class RFDETRDetector:

    def __init__(self, model_path, device, resolution=512):
        print(f"Loading RF-DETR Small: {model_path}")
        self.device = device
        self.model = RFDETRSmall(
            pretrain_weights=str(model_path),
            resolution=resolution,
        )

    def predict(self, image):
        return self.model.predict(
            image,
            threshold=CONFIDENCE_THRESHOLD,
            device=self.device
        )

    def evaluate(self):
        metrics = self.model.evaluate(
            dataset_dir=str(DATASET_DIR),
            split="test",
            resolution=IMAGE_SIZE,
            batch_size=1,
            device=self.device
        )

        ap50 = metrics["test/mAP_50"]
        ap50_95 = metrics["test/mAP_50_95"]

        return ap50, ap50_95


# ============================================================
# YOLO11 adapter
# ============================================================

class YOLODetector:

    def __init__(self, model_path, device):
        print(f"Loading YOLO11: {model_path}")
        self.model = YOLO(str(model_path))
        self.device = device

    def predict(self, image):
        return self.model.predict(
            source=image,
            imgsz=IMAGE_SIZE,
            conf=CONFIDENCE_THRESHOLD,
            iou=IOU_THRESHOLD,
            device=self.device,
            verbose=False,
        )

    def evaluate(self):

        metrics = self.model.val(
            data=str(
                DATASET_DIR / "data.yaml"
            ),
            split="test",
            imgsz=IMAGE_SIZE,
            batch=1,
            conf=CONFIDENCE_THRESHOLD,
            iou=IOU_THRESHOLD,
            device=self.device,
            verbose=False,
        )

        ap50 = float(metrics.box.map50)
        ap50_95 = float(metrics.box.map)

        return ap50, ap50_95


# ============================================================
# Latency benchmark
# ============================================================

def benchmark_latency(detector, images, warmup_runs=20, benchmark_runs=200):
    """
    Benchmark single-image inference.
    Image loading is excluded.
    Returns latency statistics in milliseconds.
    """

    if len(images) == 0:
        raise RuntimeError(
            "No images available."
        )

    print(f"\nWarm-up: {warmup_runs} runs")

    # --------------------------------------------------------
    # Warm-up
    # --------------------------------------------------------

    for i in range(warmup_runs):
        image = images[i % len(images)]
        detector.predict(image)

    # Synchronize CUDA after warmup
    if torch.cuda.is_available():
        torch.cuda.synchronize()

    # --------------------------------------------------------
    # Benchmark
    # --------------------------------------------------------

    print(f"Benchmarking: {benchmark_runs} runs")

    latencies = []

    for i in range(benchmark_runs):

        image = images[
            i % len(images)
        ]

        # CUDA synchronization is important
        # because CUDA operations are asynchronous.
        if torch.cuda.is_available():
            torch.cuda.synchronize()

        start = time.perf_counter()

        detector.predict(image)

        if torch.cuda.is_available():
            torch.cuda.synchronize()

        end = time.perf_counter()

        latency_ms = (end - start) * 1000.0

        latencies.append(latency_ms)

    latencies = np.asarray(latencies,dtype=np.float64)

    mean_latency = np.mean(
        latencies
    )

    median_latency = np.median(
        latencies
    )

    p90_latency = np.percentile(
        latencies,
        90,
    )

    p95_latency = np.percentile(
        latencies,
        95,
    )

    p99_latency = np.percentile(
        latencies,
        99,
    )

    min_latency = np.min(
        latencies
    )

    max_latency = np.max(
        latencies
    )

    fps = (
        1000.0 /
        mean_latency
    )

    return {
        "mean_ms": mean_latency,
        "median_ms": median_latency,
        "p90_ms": p90_latency,
        "p95_ms": p95_latency,
        "p99_ms": p99_latency,
        "min_ms": min_latency,
        "max_ms": max_latency,
        "fps": fps,
    }


# ============================================================
# Benchmark one model
# ============================================================

def benchmark_model(name, detector, images):
    """
    Evaluate accuracy and latency.
    """

    print()
    print("=" * 70)
    print(f"Benchmarking {name}")
    print("=" * 70)

    # --------------------------------------------------------
    # Accuracy
    # --------------------------------------------------------

    print("\nEvaluating AP...")

    ap50, ap50_95 = (detector.evaluate())

    print(f"AP50:     {ap50:.4f}")

    print(f"AP50:95:  {ap50_95:.4f}")

    # --------------------------------------------------------
    # Latency
    # --------------------------------------------------------

    latency = benchmark_latency(
        detector,
        images,
        warmup_runs=WARMUP_RUNS,
        benchmark_runs=BENCHMARK_RUNS,
    )

    print("\nLatency:")

    print(
        f"Mean:     "
        f"{latency['mean_ms']:.2f} ms"
    )

    print(
        f"Median:   "
        f"{latency['median_ms']:.2f} ms"
    )

    print(
        f"P90:      "
        f"{latency['p90_ms']:.2f} ms"
    )

    print(
        f"P95:      "
        f"{latency['p95_ms']:.2f} ms"
    )

    print(
        f"P99:      "
        f"{latency['p99_ms']:.2f} ms"
    )

    print(
        f"FPS:      "
        f"{latency['fps']:.2f}"
    )

    return {
        "model": name,
        "resolution": IMAGE_SIZE,
        "device": DEVICE,
        "ap50": ap50,
        "ap50_95": ap50_95,
        **latency,
    }


# ============================================================
# Main
# ============================================================

def main():

    print("=" * 70)
    print("License Plate Detector Benchmark")
    print("=" * 70)

    print(
        f"Device:     {DEVICE}"
    )

    print(
        f"Resolution: "
        f"{IMAGE_SIZE} x {IMAGE_SIZE}"
    )

    print(
        f"Test set:   "
        f"{TEST_IMAGE_DIR}"
    )

    # --------------------------------------------------------
    # Load test images
    # --------------------------------------------------------

    image_paths = get_test_images()

    print(
        f"\nFound "
        f"{len(image_paths)} test images"
    )

    image_paths, images = (
        load_images(image_paths)
    )

    print(
        f"Loaded "
        f"{len(images)} images"
    )

    # --------------------------------------------------------
    # Load models
    # --------------------------------------------------------

    rf_detr = RFDETRDetector(RFDETR_MODEL_PATH, device=DEVICE, resolution=IMAGE_SIZE)
    yolo = YOLODetector(YOLO_MODEL_PATH, device=DEVICE)

    # --------------------------------------------------------
    # Benchmark
    # --------------------------------------------------------

    results = []

    results.append(
        benchmark_model("RF-DETR Small", rf_detr, images)
    )

    results.append(
        benchmark_model("YOLO11", yolo, images)
    )

    print()
    print("=" * 90)
    print("FINAL RESULTS")
    print("=" * 90)

    print(
        f"{'Model':<20}"
        f"{'AP50':>10}"
        f"{'AP50:95':>12}"
        f"{'Mean ms':>12}"
        f"{'P95 ms':>12}"
        f"{'FPS':>10}"
    )

    print("-" * 90)

    for result in results:
        print(
            f"{result['model']:<20}"
            f"{result['ap50']:>10.4f}"
            f"{result['ap50_95']:>12.4f}"
            f"{result['mean_ms']:>12.2f}"
            f"{result['p95_ms']:>12.2f}"
            f"{result['fps']:>10.2f}"
        )

    print("=" * 90)


if __name__ == "__main__":
    main()