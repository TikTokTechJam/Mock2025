# US-0013 — Benchmark, train, and improve the license-plate detector

## Actor
ML teammate / evaluator

## Story
As an ML teammate or evaluator, I want to measure the current license-plate detector, fine-tune it, and compare improved candidates on one fixed held-out test set so that the team can select the strongest plate model we can produce within the hackathon timebox.

## Value
A plate detector is only useful for privacy if its misses are understood and reduced. A fixed baseline → fine-tune → compare loop gives the team real numbers instead of model claims.

This story is intentionally about **ML work, not application coding**. Backend/infrastructure teammates provide the evaluation tooling and model-file integration around the ML workflow.

## Acceptance Criteria
- One fixed held-out plate evaluation set/profile is used for the baseline and every later candidate.
- Evaluation data is kept separate from training/fine-tuning data.
- Results are reported overall and, where practical, for `easy`, `medium`, and `hard` cases.
- Every serious candidate reports recall, precision, mAP@0.5, mAP@0.5:0.95, and speed on the machine used for evaluation.
- Privacy recall is the primary model-selection metric once the precision floor is reasonable.
- The target ladder is explicit:
  - **Baseline:** measure the real starting result.
  - **MVP:** at least 80% overall recall and 80% precision.
  - **Strong:** at least 90% overall recall and 85% precision.
  - **Stretch:** at least 95% overall recall and 90% precision.
- At least one real pretrained/current detector is benchmarked as the starting baseline.
- At least one fine-tuned candidate is evaluated on the exact same held-out profile.
- If time allows, one targeted iteration addresses the most important observed failure cases.
- A concise baseline-vs-best comparison identifies the strongest validated model and the highest target level actually reached.
- The ML team hands over the chosen model artifact (`.pt`, `.onnx`, etc.), metrics, model version/name, and a short training/provenance note to #14.

## Scope
### #48 — ML evaluation
- prepare/check the held-out plate evaluation set;
- run the current model;
- record baseline metrics;
- analyze false negatives/false positives and failure cases.

### #49 — ML training
- prepare training/validation data;
- fine-tune/train candidate models;
- compare candidates on the unchanged #48 test set;
- select and export the best model.

## Out of Scope
- Writing benchmark/metric tooling; #15 is a backend/infrastructure issue that provides the measurement tool.
- Writing model download/cache/runtime-loading code; #14 is a backend/infrastructure issue that takes the finished ML artifact and makes it loadable by the app.
- Rewriting runtime plate inference or source-frame geometry mapping; #19/#6 own those paths.
- Video masking/compositing; #4 owns that behavior.
- Large research sweeps that do not fit the hackathon timebox.

## Decisions
- Keep the ML loop intentionally short: baseline, one straightforward fine-tune, then at most one targeted improvement iteration unless there is clear value in continuing.
- Never report a target level that the measured results do not reach.
- Prefer higher recall for privacy while recording precision and speed trade-offs.

## Handoff

```text
#15 Infra gives ML an evaluation tool
        ↓
#48 ML measures baseline
        ↓
#49 ML trains/fine-tunes/selects best model
        ↓
best-model.pt + metrics
        ↓
#14 Infra makes the model reproducibly loadable by the app
```

## Status Boundary
Planned ML-quality story until the baseline is recorded, at least one improved candidate is evaluated on the same held-out set, and the strongest validated model is handed to the application team.

## Touched By
Issues #14, #15, #48, #49.
