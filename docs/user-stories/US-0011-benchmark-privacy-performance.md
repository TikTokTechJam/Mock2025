# US-0011 — Evaluate privacy quality and performance

## Actor
Developer / evaluator

## Story
As a developer or evaluator, I want repeatable privacy-accuracy and performance benchmarks so that I can compare model/configuration changes without hiding privacy-critical regressions.

## Value
The project needs evidence for both privacy quality and real-time usability; aggregate accuracy alone can conceal dangerous false negatives.

## Acceptance Criteria
- One benchmark workflow uses the same production detector/pipeline adapters as the application.
- Every run identifies code commit, model artifacts/checksums, dataset/fixture version, configuration, and hardware.
- Face benchmarks expose bystander false-allow rate and false-redact rate.
- Plate and visual/spoken PII benchmarks expose privacy-critical misses/recall.
- Latency reports include p50/p95 and p99 when sample size supports it.
- Video FPS, audio realtime/decision lag, CPU/RAM, and GPU/VRAM are captured where available.
- Cold-start/model-load time is separated from steady-state inference.
- Results are machine-readable plus human-readable.
- Original PrivaStream numbers are treated as contextual unless the evaluation protocol is genuinely comparable.

## Scope
- Benchmark manifests, accuracy metrics, latency/resource instrumentation, reporting, regression thresholds, and provenance.

## Out of Scope
- Claiming parity with the original winner without comparable evidence.
- Making unstable hardware timing mandatory in ordinary unit-test CI.

## Decisions
- Privacy-critical false negatives are first-class metrics.
- Production inference code is reused rather than duplicated in benchmark-only implementations.

## Concerns
- Small fixture sets can give misleading metrics.
- Performance results are hardware/configuration specific.

## Status Boundary
Planned engineering story until the benchmark harness covers every implemented privacy capability with reproducible metadata.

## Touched By
Issues #5, #6, #7, #9, #10, #14, #15, #16, #17, #48, #49.