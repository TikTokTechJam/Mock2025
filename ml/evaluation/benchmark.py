"""Deterministic offline benchmark metrics and report generation.

The runner consumes normalized detector predictions and labels. Production
adapters remain responsible for producing those predictions; this module does
not load models or media and is safe to use without ML runtime dependencies.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

Box = tuple[float, float, float, float]
STANDARD_IOU_THRESHOLDS = tuple(round(0.50 + (0.05 * index), 2) for index in range(10))


class BenchmarkError(ValueError):
    """Raised when benchmark input or provenance is invalid."""


@dataclass(frozen=True, slots=True)
class GroundTruth:
    image_id: str
    class_id: str
    box: Box


@dataclass(frozen=True, slots=True)
class Prediction:
    image_id: str
    class_id: str
    box: Box
    score: float


@dataclass(frozen=True, slots=True)
class BenchmarkInput:
    fixture_version: str
    ground_truth: tuple[GroundTruth, ...]
    predictions: tuple[Prediction, ...]
    confidence_threshold: float
    configuration: dict[str, Any]
    cold_start_ms: float | None
    latency_ms: tuple[float, ...]
    frame_count: int | None
    duration_seconds: float | None
    audio_duration_seconds: float | None
    decision_lag_ms: tuple[float, ...]
    resources: dict[str, Any]

    @classmethod
    def from_mapping(cls, value: object) -> "BenchmarkInput":
        if not isinstance(value, Mapping):
            raise BenchmarkError("benchmark input must contain a JSON object")

        fixture_version = _required_string(value.get("fixture_version"), "fixture_version")
        ground_truth = _parse_ground_truth(value.get("ground_truth"))
        predictions = _parse_predictions(value.get("predictions"))
        confidence_threshold = _number(
            value.get("confidence_threshold", 0.25), "confidence_threshold"
        )
        if not 0 <= confidence_threshold <= 1:
            raise BenchmarkError("confidence_threshold must be between 0 and 1")

        configuration = value.get("configuration", {})
        if not isinstance(configuration, Mapping):
            raise BenchmarkError("configuration must be a JSON object")
        performance = value.get("performance", {})
        if not isinstance(performance, Mapping):
            raise BenchmarkError("performance must be a JSON object")

        supplied_thresholds = performance.get("iou_thresholds")
        if supplied_thresholds is not None:
            if not isinstance(supplied_thresholds, list):
                raise BenchmarkError("performance.iou_thresholds must be a JSON array")
            parsed_thresholds = tuple(
                _number(item, "performance.iou_thresholds") for item in supplied_thresholds
            )
            if parsed_thresholds != STANDARD_IOU_THRESHOLDS:
                raise BenchmarkError(
                    "performance.iou_thresholds must use the standard 0.50:0.05:0.95 profile"
                )

        resources = performance.get("resources", {})
        if not isinstance(resources, Mapping):
            raise BenchmarkError("performance.resources must be a JSON object")

        return cls(
            fixture_version=fixture_version,
            ground_truth=ground_truth,
            predictions=predictions,
            confidence_threshold=confidence_threshold,
            configuration=dict(configuration),
            cold_start_ms=_optional_number(performance.get("cold_start_ms"), "cold_start_ms"),
            latency_ms=_number_sequence(performance.get("latency_ms", []), "latency_ms"),
            frame_count=_optional_integer(performance.get("frame_count"), "frame_count"),
            duration_seconds=_optional_positive_number(
                performance.get("duration_seconds"), "duration_seconds"
            ),
            audio_duration_seconds=_optional_positive_number(
                performance.get("audio_duration_seconds"), "audio_duration_seconds"
            ),
            decision_lag_ms=_number_sequence(
                performance.get("decision_lag_ms", []), "decision_lag_ms"
            ),
            resources=dict(resources),
        )


def load_benchmark_input(path: Path) -> BenchmarkInput:
    """Load and validate one normalized benchmark input file."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BenchmarkError(f"benchmark input not found at {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"could not read benchmark input at {path}") from exc
    return BenchmarkInput.from_mapping(value)


def intersection_over_union(first: Box, second: Box) -> float:
    """Return IoU for two validated ``x1, y1, x2, y2`` boxes."""

    intersection_x1 = max(first[0], second[0])
    intersection_y1 = max(first[1], second[1])
    intersection_x2 = min(first[2], second[2])
    intersection_y2 = min(first[3], second[3])
    intersection_width = max(0.0, intersection_x2 - intersection_x1)
    intersection_height = max(0.0, intersection_y2 - intersection_y1)
    intersection_area = intersection_width * intersection_height
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    union_area = first_area + second_area - intersection_area
    return intersection_area / union_area if union_area else 0.0


def _match_counts(
    ground_truth: Sequence[GroundTruth],
    predictions: Sequence[Prediction],
    iou_threshold: float,
    confidence_threshold: float = 0.0,
) -> tuple[int, int, int]:
    truth_by_key: dict[tuple[str, str], list[GroundTruth]] = {}
    for item in ground_truth:
        truth_by_key.setdefault((item.image_id, item.class_id), []).append(item)
    matched: dict[tuple[str, str], set[int]] = {
        key: set() for key in truth_by_key
    }
    true_positive = 0
    false_positive = 0

    ranked = sorted(
        enumerate(predictions),
        key=lambda item: (-item[1].score, item[0]),
    )
    for _, prediction in ranked:
        if prediction.score < confidence_threshold:
            continue
        key = (prediction.image_id, prediction.class_id)
        candidates = truth_by_key.get(key, [])
        available = [
            (index, intersection_over_union(prediction.box, truth.box))
            for index, truth in enumerate(candidates)
            if index not in matched.setdefault(key, set())
        ]
        best = max(available, key=lambda item: item[1], default=None)
        if best is not None and best[1] >= iou_threshold:
            matched[key].add(best[0])
            true_positive += 1
        else:
            false_positive += 1

    false_negative = len(ground_truth) - true_positive
    return true_positive, false_positive, false_negative


def _average_precision(
    ground_truth: Sequence[GroundTruth],
    predictions: Sequence[Prediction],
    class_id: str,
    iou_threshold: float,
) -> float:
    truth_by_image: dict[str, list[GroundTruth]] = {}
    for item in ground_truth:
        if item.class_id == class_id:
            truth_by_image.setdefault(item.image_id, []).append(item)
    positive_count = sum(len(items) for items in truth_by_image.values())
    if positive_count == 0:
        raise BenchmarkError(f"cannot calculate AP for class without labels: {class_id}")

    ranked = sorted(
        enumerate((item for item in predictions if item.class_id == class_id)),
        key=lambda item: (-item[1].score, item[0]),
    )
    matched: dict[str, set[int]] = {image_id: set() for image_id in truth_by_image}
    true_positive: list[int] = []
    false_positive: list[int] = []
    for _, prediction in ranked:
        candidates = truth_by_image.get(prediction.image_id, [])
        available = [
            (index, intersection_over_union(prediction.box, truth.box))
            for index, truth in enumerate(candidates)
            if index not in matched.setdefault(prediction.image_id, set())
        ]
        best = max(available, key=lambda item: item[1], default=None)
        if best is not None and best[1] >= iou_threshold:
            matched[prediction.image_id].add(best[0])
            true_positive.append(1)
            false_positive.append(0)
        else:
            true_positive.append(0)
            false_positive.append(1)

    if not true_positive:
        return 0.0

    cumulative_true_positive = 0
    cumulative_false_positive = 0
    precisions: list[float] = []
    recalls: list[float] = []
    for true_positive_value, false_positive_value in zip(true_positive, false_positive):
        cumulative_true_positive += true_positive_value
        cumulative_false_positive += false_positive_value
        precisions.append(
            cumulative_true_positive / (cumulative_true_positive + cumulative_false_positive)
        )
        recalls.append(cumulative_true_positive / positive_count)

    interpolated_precision = []
    for recall_level in (index / 100 for index in range(101)):
        eligible = [
            precision for precision, recall in zip(precisions, recalls) if recall >= recall_level
        ]
        interpolated_precision.append(max(eligible, default=0.0))
    return statistics.fmean(interpolated_precision)


def calculate_metrics(data: BenchmarkInput) -> dict[str, Any]:
    """Calculate standard plate-style detection metrics."""

    if not data.ground_truth:
        raise BenchmarkError("ground_truth must contain at least one label")
    true_positive, false_positive, false_negative = _match_counts(
        data.ground_truth,
        data.predictions,
        iou_threshold=0.5,
        confidence_threshold=data.confidence_threshold,
    )
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = true_positive / (true_positive + false_negative)
    classes = sorted({item.class_id for item in data.ground_truth})
    average_precisions = {
        class_id: _average_precision(data.ground_truth, data.predictions, class_id, 0.5)
        for class_id in classes
    }
    standard_aps = {
        threshold: statistics.fmean(
            _average_precision(data.ground_truth, data.predictions, class_id, threshold)
            for class_id in classes
        )
        for threshold in STANDARD_IOU_THRESHOLDS
    }
    return {
        "precision": precision,
        "recall": recall,
        "privacy_critical_miss_rate": 1.0 - recall,
        "true_positive_count": true_positive,
        "false_positive_count": false_positive,
        "false_negative_count": false_negative,
        "mAP@0.5": standard_aps[0.5],
        "mAP@0.5:0.95": statistics.fmean(standard_aps.values()),
        "per_class_AP@0.5": average_precisions,
        "ground_truth_count": len(data.ground_truth),
        "prediction_count": len(data.predictions),
    }


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * fraction)


def calculate_performance(data: BenchmarkInput) -> dict[str, Any]:
    """Summarize steady-state latency separately from cold-start timing."""

    mean_latency = statistics.fmean(data.latency_ms) if data.latency_ms else None
    inference_fps = 1000 / mean_latency if mean_latency else None
    video_fps = (
        data.frame_count / data.duration_seconds
        if data.frame_count is not None and data.duration_seconds
        else None
    )
    decision_lag_mean = statistics.fmean(data.decision_lag_ms) if data.decision_lag_ms else None
    return {
        "cold_start_ms": data.cold_start_ms,
        "steady_state_latency_ms": {
            "sample_count": len(data.latency_ms),
            "mean": mean_latency,
            "p50": _percentile(data.latency_ms, 0.50),
            "p95": _percentile(data.latency_ms, 0.95),
            "p99": _percentile(data.latency_ms, 0.99),
        },
        "inference_fps": inference_fps,
        "video": {
            "frame_count": data.frame_count,
            "duration_seconds": data.duration_seconds,
            "fps": video_fps,
        },
        "audio": {
            "duration_seconds": data.audio_duration_seconds,
            "decision_lag_ms": {
                "sample_count": len(data.decision_lag_ms),
                "mean": decision_lag_mean,
                "p50": _percentile(data.decision_lag_ms, 0.50),
                "p95": _percentile(data.decision_lag_ms, 0.95),
                "p99": _percentile(data.decision_lag_ms, 0.99),
            },
        },
        "resources": data.resources,
    }


def build_report(
    data: BenchmarkInput,
    *,
    commit: str,
    model: str,
    model_checksums: Sequence[str],
    dataset: str,
    profile: str,
    hardware: str,
) -> dict[str, Any]:
    """Build a machine-readable report with mandatory provenance."""

    provenance = {
        "code_commit": _required_string(commit, "commit"),
        "model": {
            "id": _required_string(model, "model"),
            "sha256": _validate_checksums(model_checksums),
        },
        "dataset": {
            "id": _required_string(dataset, "dataset"),
            "fixture_version": data.fixture_version,
        },
        "profile": _required_string(profile, "profile"),
        "hardware": _required_string(hardware, "hardware"),
    }
    configuration = dict(data.configuration)
    configuration.setdefault("confidence_threshold", data.confidence_threshold)
    configuration.setdefault("iou_thresholds", list(STANDARD_IOU_THRESHOLDS))
    return {
        "schema_version": "benchmark-report-v1",
        "provenance": provenance,
        "configuration": configuration,
        "metrics": calculate_metrics(data),
        "performance": calculate_performance(data),
    }


def write_report(report: Mapping[str, Any], output: Path, markdown: Path) -> tuple[Path, Path]:
    """Write the JSON report and a concise human-readable Markdown report."""

    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown.write_text(_markdown_report(report), encoding="utf-8")
    return output, markdown


def _markdown_report(report: Mapping[str, Any]) -> str:
    provenance = report["provenance"]
    metrics = report["metrics"]
    performance = report["performance"]
    latency = performance["steady_state_latency_ms"]
    lines = [
        "# PrivaStream benchmark report",
        "",
        "## Provenance",
        "",
        f"- Code commit: `{provenance['code_commit']}`",
        f"- Model: `{provenance['model']['id']}`",
        f"- Model SHA-256: `{', '.join(provenance['model']['sha256'])}`",
        f"- Dataset: `{provenance['dataset']['id']}`",
        f"- Fixture version: `{provenance['dataset']['fixture_version']}`",
        f"- Profile: `{provenance['profile']}`",
        f"- Hardware: `{provenance['hardware']}`",
        "",
        "## Privacy metrics",
        "",
        f"- Precision: {metrics['precision']:.6f}",
        f"- Recall: {metrics['recall']:.6f}",
        f"- Privacy-critical miss rate: {metrics['privacy_critical_miss_rate']:.6f}",
        f"- mAP@0.5: {metrics['mAP@0.5']:.6f}",
        f"- mAP@0.5:0.95: {metrics['mAP@0.5:0.95']:.6f}",
        "",
        "## Performance",
        "",
        f"- Cold start: {_format_optional(performance['cold_start_ms'], ' ms')}",
        f"- Steady-state samples: {latency['sample_count']}",
        f"- Steady-state p50: {_format_optional(latency['p50'], ' ms')}",
        f"- Steady-state p95: {_format_optional(latency['p95'], ' ms')}",
        f"- Steady-state p99: {_format_optional(latency['p99'], ' ms')}",
        f"- Inference FPS: {_format_optional(performance['inference_fps'])}",
        "",
        "Raw media and prediction rows are not copied into this report.",
        "Interpret small-fixture and hardware timing results with the documented protocol.",
        "",
    ]
    return "\n".join(lines)


def _format_optional(value: float | None, suffix: str = "") -> str:
    return "not supplied" if value is None else f"{value:.6f}{suffix}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a reproducible offline PrivaStream benchmark."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Calculate metrics and write JSON and Markdown reports")
    run.add_argument("--input", type=Path, required=True, help="Normalized labels/predictions JSON")
    run.add_argument("--output", type=Path, required=True, help="Machine-readable JSON report")
    run.add_argument(
        "--markdown", type=Path, help="Human-readable report (defaults beside --output)"
    )
    run.add_argument("--model", required=True, help="Model ID and version under evaluation")
    run.add_argument(
        "--model-checksum",
        action="append",
        required=True,
        help="Model SHA-256; repeat for multiple artifacts",
    )
    run.add_argument("--dataset", required=True, help="Dataset manifest or version identifier")
    run.add_argument("--profile", required=True, help="Evaluation profile identifier")
    run.add_argument("--hardware", required=True, help="Hardware/runtime description")
    run.add_argument("--commit", required=True, help="Code commit under evaluation")
    return parser


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkError(f"{name} must be a non-empty string")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BenchmarkError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise BenchmarkError(f"{name} must be a finite number")
    return number


def _optional_number(value: object, name: str) -> float | None:
    if value is None:
        return None
    number = _number(value, name)
    if number < 0:
        raise BenchmarkError(f"{name} must not be negative")
    return number


def _optional_positive_number(value: object, name: str) -> float | None:
    number = _optional_number(value, name)
    if number is not None and number <= 0:
        raise BenchmarkError(f"{name} must be positive")
    return number


def _optional_integer(value: object, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BenchmarkError(f"{name} must be a non-negative integer")
    return value


def _number_sequence(value: object, name: str) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise BenchmarkError(f"{name} must be a JSON array")
    result = tuple(_number(item, name) for item in value)
    if any(item < 0 for item in result):
        raise BenchmarkError(f"{name} must not contain negative values")
    return result


def _parse_ground_truth(value: object) -> tuple[GroundTruth, ...]:
    if not isinstance(value, list):
        raise BenchmarkError("ground_truth must be a JSON array")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise BenchmarkError(f"ground_truth[{index}] must be a JSON object")
        result.append(
            GroundTruth(
                image_id=_required_string(item.get("image_id"), f"ground_truth[{index}].image_id"),
                class_id=_required_string(item.get("class_id"), f"ground_truth[{index}].class_id"),
                box=_parse_box(item.get("box"), f"ground_truth[{index}].box"),
            )
        )
    return tuple(result)


def _parse_predictions(value: object) -> tuple[Prediction, ...]:
    if not isinstance(value, list):
        raise BenchmarkError("predictions must be a JSON array")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise BenchmarkError(f"predictions[{index}] must be a JSON object")
        score = _number(item.get("score"), f"predictions[{index}].score")
        if not 0 <= score <= 1:
            raise BenchmarkError(f"predictions[{index}].score must be between 0 and 1")
        result.append(
            Prediction(
                image_id=_required_string(item.get("image_id"), f"predictions[{index}].image_id"),
                class_id=_required_string(item.get("class_id"), f"predictions[{index}].class_id"),
                box=_parse_box(item.get("box"), f"predictions[{index}].box"),
                score=score,
            )
        )
    return tuple(result)


def _parse_box(value: object, name: str) -> Box:
    if not isinstance(value, list) or len(value) != 4:
        raise BenchmarkError(f"{name} must be [x1, y1, x2, y2]")
    coordinates = tuple(_number(item, name) for item in value)
    if coordinates[2] <= coordinates[0] or coordinates[3] <= coordinates[1]:
        raise BenchmarkError(f"{name} must have positive width and height")
    return coordinates  # type: ignore[return-value]


def _validate_checksums(values: Sequence[str]) -> list[str]:
    if not values:
        raise BenchmarkError("at least one model checksum is required")
    checksums = []
    for value in values:
        if not isinstance(value, str) or len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise BenchmarkError("model checksums must be lowercase SHA-256 values")
        checksums.append(value)
    return checksums


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command != "run":
            raise BenchmarkError(f"unsupported benchmark command: {args.command}")
        data = load_benchmark_input(args.input)
        report = build_report(
            data,
            commit=args.commit,
            model=args.model,
            model_checksums=args.model_checksum,
            dataset=args.dataset,
            profile=args.profile,
            hardware=args.hardware,
        )
        markdown = args.markdown or args.output.with_suffix(".md")
        output, markdown = write_report(report, args.output, markdown)
    except (BenchmarkError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"JSON report: {output}")
    print(f"Markdown report: {markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
