# US-0013 — Benchmark, train, and improve the license-plate detector

## Actor
ML developer / evaluator

## Story
As an ML developer or evaluator, I want to benchmark, fine-tune, and improve the license-plate detector against one fixed held-out evaluation profile so that I can measure real progress and select the strongest privacy detector we can produce within the hackathon timebox.

## Value
A plate detector is only useful for privacy if its misses are understood and reduced. A fixed benchmark plus a short baseline → fine-tune → targeted-improvement loop gives the team real numbers instead of model claims and prevents us from spending hackathon time on unmeasured training.

## Acceptance Criteria
- One versioned held-out plate evaluation profile is used for the baseline and every later candidate.
- Evaluation data is separated from training/fine-tuning data with no known leakage.
- Results are reported overall and for explicit `easy`, `medium`, and `hard` plate buckets.
- Every model report includes recall, precision, mAP@0.5, mAP@0.5:0.95, and latency/FPS on named reference hardware/configuration.
- Privacy recall is the primary selection metric once the precision floor is satisfied.
- The target ladder is explicit:
  - **Baseline:** measure the actual starting result; no score is assumed.
  - **MVP:** at least 80% overall recall and 80% precision.
  - **Strong:** at least 90% overall recall and 85% precision.
  - **Stretch:** at least 95% overall recall and 90% precision.
- At least one real pretrained detector is benchmarked as the starting baseline.
- At least one fine-tuned candidate is benchmarked on the exact same evaluation profile.
- If time allows, one targeted iteration addresses observed failure modes such as small, angled, low-light, motion-blurred, or occluded plates.
- A concise baseline → candidate comparison identifies the strongest validated model and the highest target level actually reached.
- The chosen artifact is handed to the existing #14 model-manifest/bootstrap path; no large model weights or private/raw datasets are committed to Git.

## Scope
- Plate-specific evaluation data/profile and difficulty buckets.
- Baseline measurement.
- Plate-specific fine-tuning/training experiments.
- Hard-case analysis and targeted augmentation/mining.
- Candidate comparison and best-model selection.

## Out of Scope
- Building another generic benchmark framework; #15 owns the shared runner, metrics, provenance, and reports.
- Building another generic training/artifact system; #14 owns training infrastructure, dataset/model manifests, artifact metadata, bootstrap, and cache resolution.
- Rewriting runtime plate inference or source-frame geometry mapping; #19/#6 own those paths.
- Changing the held-out evaluation set after seeing candidate results just to improve scores.
- Requiring the Stretch target if hackathon time or available data does not support it.

## Decisions
- Keep the experiment loop intentionally short: baseline, one straightforward fine-tune, then at most one targeted improvement iteration unless there is clear value in continuing.
- Never report a target level that the measured results do not reach.
- Prefer higher recall for privacy, while maintaining the stated precision floor and recording latency trade-offs.

## Concerns
- Small or geographically narrow datasets can overstate real-world quality.
- Repeatedly tuning against the held-out set can create evaluation overfitting.
- Accuracy gains that make inference too slow for the intended live cadence may not be the best production choice.

## Status Boundary
Planned ML-quality story until the fixed baseline is recorded, at least one improved candidate is evaluated on the same profile, and the strongest validated detector is selected with reproducible evidence.

## Touched By
Issues #14, #15, #48, #49.
