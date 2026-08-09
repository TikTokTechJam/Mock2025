# Offline benchmark runner

This directory owns the dependency-free metric and reporting boundary for
Issue #15. It accepts normalized labels and predictions from the same detector
or pipeline adapters used by the application; it does not load models, access
media providers, or duplicate runtime inference.

Run a benchmark with mandatory provenance:

```bash
python ml/evaluation/benchmark.py run \
  --input ml/evaluation/fixtures/plate-example.json \
  --output reports/plate-example.json \
  --model plate-detector:v1 \
  --model-checksum 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --dataset plate-fixture \
  --profile plate-default-640 \
  --hardware "Apple Silicon / CPU" \
  --commit 0000000000000000000000000000000000000000
```

The command writes both `reports/plate-example.json` and
`reports/plate-example.md`. The JSON input contains synthetic or authorized
normalized rows:

```json
{
  "fixture_version": "plate-fixture-v1",
  "confidence_threshold": 0.25,
  "configuration": {"image_size": 640},
  "ground_truth": [
    {"image_id": "frame-001", "class_id": "license_plate", "box": [10, 10, 50, 30]}
  ],
  "predictions": [
    {"image_id": "frame-001", "class_id": "license_plate", "box": [10, 10, 50, 30], "score": 0.9}
  ],
  "performance": {
    "iou_thresholds": [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95],
    "cold_start_ms": 120.0,
    "latency_ms": [12.0, 13.0, 11.0],
    "frame_count": 1,
    "duration_seconds": 0.04,
    "resources": {"cpu_percent": 20.0, "ram_mb": 512.0}
  }
}
```

The report includes precision, recall, privacy-critical miss rate,
mAP@0.5, mAP@0.5:0.95, per-class AP, p50/p95/p99 latency, inference FPS,
optional video FPS, audio decision lag, cold-start time, and supplied resource
measurements. AP uses 101-point interpolated precision at each IoU threshold;
the report records the standard 0.50 through 0.95 profile. Empty performance
fields remain `null` or have a zero sample count rather than being invented.

Do not commit raw/private datasets, model outputs containing unnecessary PII,
or generated reports. Benchmark storage and retention follow
`docs/SECURITY.md`.
