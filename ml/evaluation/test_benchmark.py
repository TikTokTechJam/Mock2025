from pathlib import Path

import pytest

from ml.evaluation.benchmark import (
    BenchmarkError,
    BenchmarkInput,
    build_report,
    calculate_metrics,
    calculate_performance,
    load_benchmark_input,
)


FIXTURE = Path(__file__).parent / "fixtures" / "plate-example.json"


def test_plate_fixture_reports_perfect_metrics() -> None:
    data = load_benchmark_input(FIXTURE)

    metrics = calculate_metrics(data)

    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["mAP@0.5"] == 1.0
    assert metrics["mAP@0.5:0.95"] == 1.0


def test_metrics_count_low_confidence_prediction_as_missed() -> None:
    data = BenchmarkInput.from_mapping(
        {
            "fixture_version": "test-v1",
            "ground_truth": [
                {"image_id": "frame-001", "class_id": "plate", "box": [0, 0, 10, 10]}
            ],
            "predictions": [
                {
                    "image_id": "frame-001",
                    "class_id": "plate",
                    "box": [0, 0, 10, 10],
                    "score": 0.2,
                }
            ],
            "confidence_threshold": 0.5,
        }
    )

    metrics = calculate_metrics(data)

    assert metrics["precision"] == 0.0
    assert metrics["recall"] == 0.0
    assert metrics["privacy_critical_miss_rate"] == 1.0


def test_report_requires_model_checksum() -> None:
    data = load_benchmark_input(FIXTURE)

    with pytest.raises(BenchmarkError, match="checksum"):
        build_report(
            data,
            commit="abc123",
            model="plate-detector:v1",
            model_checksums=[],
            dataset="plate-fixture",
            profile="plate-default-640",
            hardware="test-cpu",
        )


def test_performance_separates_cold_start_and_steady_state() -> None:
    data = load_benchmark_input(FIXTURE)

    performance = calculate_performance(data)

    assert performance["cold_start_ms"] == 120.0
    assert performance["steady_state_latency_ms"]["sample_count"] == 4
    assert performance["inference_fps"] == pytest.approx(1000 / 12)
