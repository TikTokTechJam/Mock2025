# face_blur

Non-whitelisted face detection for PrivaStream. Returns the regions that must be
redacted before media reaches any downstream consumer.

Recognition is a negative filter only: it decides which faces may be left alone.
Every face not positively established as whitelisted is a redaction target. This
component emits normalized detection objects and **never modifies media** —
blurring, pixelation, and covering belong to the compositor, despite the folder
name.

Status: **Implemented, Unverified.** No test, lint, type-check, or benchmark run
has been performed on this code. The similarity thresholds are placeholders, not
benchmarked values (see [Limitations](#limitations)).

Design: [`../PROJECT_OVERVIEW.md`](../PROJECT_OVERVIEW.md).
Wiring: [`../INTEGRATION_GUIDE.md`](../INTEGRATION_GUIDE.md).
Output contract: `apps/api/src/privastream_api/pipeline/contracts.py`.

## Entry points

| Purpose | Symbol |
| ------- | ------ |
| Per-frame detection | `FaceBlurDetector.detect(frame) -> tuple[VideoRegionDetection, ...]` |
| Enrollment | `WhitelistStore.enroll(consent, references)`, `enroll_identity(...)` |
| Revocation | `WhitelistStore.revoke(identity_id)`, `WhitelistStore.clear()` |
| Model adapter | `FaceAnalyzer` protocol, `InsightFaceAnalyzer` |
| Media path | `FrameSource` protocol, `BoundedFrameBuffer` |
| Safe logging | `detection_log_fields(...)`, `protection_state(...)` |
| Tuning | `FaceBlurConfig` |

`FaceBlurDetector` satisfies the `FaceDetector` protocol from `contracts.py`
(`kind = "face"`, `detect(frame) -> Sequence[VideoRegionDetection]`).

## Setup

Requires `privastream_api` on the path for the output contract; the package
finds `apps/api/src` itself when it is not installed. The core is pure Python.
InsightFace and its runtime are optional and imported lazily — only
`InsightFaceAnalyzer` needs them, and only on first use.

```python
from pathlib import Path

from face_blur import (
    BoundedFrameBuffer,
    EnrollmentConsent,
    FaceBlurConfig,
    FaceBlurDetector,
    InsightFaceAnalyzer,
    WhitelistStore,
    enroll_identity,
)

analyzer = InsightFaceAnalyzer()
whitelist = WhitelistStore(path=Path("var/whitelist.json"), config=FaceBlurConfig())

# Enrollment is explicit and opt-in. `consent_record_id` names the record the
# consent flow already created; this component never creates one.
enroll_identity(
    whitelist,
    analyzer,
    EnrollmentConsent(identity_id="creator", consent_record_id="consent-42"),
    reference_images,          # ~30 images, varied pose, lighting, distance
)

frames = BoundedFrameBuffer(max_frames=8, max_duration_ms=2_000)
detector = FaceBlurDetector(analyzer=analyzer, frames=frames, whitelist=whitelist)

frames.submit(frame, pixels)          # frame: VideoFrame, pixels: BGR array
regions = detector.detect(frame)      # pixels are released before this returns
```

Omitting `whitelist` is valid and is the safest configuration: with nothing
enrolled, every detected face is protected.

## Output

One `VideoRegionDetection` per face classified `NON_WHITELISTED` or `UNCERTAIN`,
plus every track inside its hold-over window. Whitelisted faces produce no
region.

| Property | Value |
| -------- | ----- |
| Origin | Top-left of the frame |
| Ordering | `x, y, width, height` |
| Range | Normalized `[0, 1]`, relative to frame width/height |
| Reference frame | The **processed** frame — the `VideoFrame` passed to `detect()` |
| Bounds | `x + width <= 1` and `y + height <= 1` |
| Correlation | By `timestamp_ms`; the contract has nowhere to echo `frame_id` |

`confidence` is confidence in the **redaction decision** — not the face score
and not identity similarity. Only detection quality moves it; identity
uncertainty never lowers it, because a low confidence would invite policy to
threshold away a region that exists precisely because the identity is uncertain.
Similarity scores never leave the detector.

There is no `expires_at` in the contract, so a region is active for exactly the
frame it was emitted on. A lost track keeps emitting its last stabilized box —
same `track_id`, current `timestamp_ms` — for `hold_over_ms`, then stops. The
compositor holds no expiry state of its own.

## Failure behavior

Face protection fails closed. Every failure raises `FaceDetectorUnavailable`:

* the frame's pixels are not in the bounded buffer;
* the model is unavailable, crashes, or returns invalid geometry;
* a region cannot be constructed within the contract.

Callers map that to `UNSAFE` when face protection is configured `required`, or
`DEGRADED` when `optional`, and the compositor must not emit unredacted output
while `UNSAFE`. A failure is `status = unavailable`, never `no faces detected`.
An empty tuple from `detect()` means one thing only: no face in this frame needs
redaction.

## Whitelist database

Enrollments persist in a JSON file (`storage.py`), written atomically with
owner-only permissions (`0600`) and replaced whole so a revocation can never
leave a partial list behind:

```json
{
  "version": 1,
  "identities": {
    "creator": {
      "consent_record_id": "consent-42",
      "embeddings": [[0.0123, -0.0456, "..."]]
    }
  }
}
```

The file holds biometric-derived data. It is protected by filesystem
permissions, **not encrypted**: restrict the path to the detector service, keep
it out of version control and out of backups that are not covered by the same
controls, and delete it when its enrollments are revoked. A file that exists but
cannot be parsed raises `WhitelistStorageError` rather than loading part of
itself.

Revocation deletes the identity from memory and from the file in the same call,
so the next frame treats that person as an unknown — therefore protected — face.
The in-memory copy is the only cache; nothing derived outlives a revocation.

## Configuration

`FaceBlurConfig` holds detector-local parameters only. Protection configuration
— enabled, required/optional, redaction mode, the policy confidence threshold —
is centralized elsewhere, and this detector neither knows nor cares whether the
compositor blurs, pixelates, or covers.

| Parameter | Default | Safe direction |
| --------- | ------- | -------------- |
| `match_threshold` | `0.55` | Higher = fewer strangers whitelisted |
| `uncertainty_margin` | `0.10` | Wider = more faces protected |
| `top_k` | `3` | See `PROJECT_OVERVIEW.md` §3.2 |
| `min_face_size` | `0.045` | Larger = more faces treated as UNCERTAIN |
| `min_reliable_score` | `0.60` | Higher = less trust in weak detections |
| `ema_alpha` | `0.55` | Lower = smoother = more lag = needs more padding |
| `padding` | `0.15` | Larger = safer coverage |
| `hold_over_ms` | `500` | Longer = safer |
| `track_match_iou` | `0.30` | — |
| `max_tracked_faces` | `64` | Bounds tracker memory |
| `min_redaction_confidence` | `0.85` | Floor for a redaction decision |

`ema_alpha` and `padding` are coupled: more smoothing means more lag, which
needs more padding.

## Privacy invariants

Enforced in code, not by convention:

1. `UNCERTAIN` and `UNKNOWN` faces are redacted exactly like `NON_WHITELISTED`.
   The rule lives in `FaceClassification.requires_redaction` alone.
2. No enrollment means every detected face is protected.
3. Failure raises; it is never an empty region list.
4. Embeddings never reach logs, the UI, ordinary APIs, or error messages;
   `WhitelistStore.__repr__` reports a count, and `classify()` returns a class
   rather than a score.
5. Enrollment requires an `EnrollmentConsent`; there is no path that enrolls by
   inference.
6. Revocation is total and immediate on the processing path.
7. Frames come from a bounded buffer and are released on every path, success or
   failure.
8. Padding is applied before clamping — `pad_and_clamp` does both, so the order
   cannot be reversed by a caller.

## Limitations

* **Thresholds are unbenchmarked.** `match_threshold` and `uncertainty_margin`
  are conservative placeholders. `PROJECT_OVERVIEW.md` §8 requires them to be set
  from benchmark data, biased toward protection, before production use.
* **Not production-ready on a benchmark score alone.** The security review in
  `SECURITY.md` §21 is what qualifies it. Recall on non-whitelisted faces and the
  false-negative rate are the metrics that matter.
* **Nothing here has been executed.** Tests exist in `tests/` and have not been
  run.
* **Whitelist storage is unencrypted at rest** and single-process; concurrent
  writers to one file are not coordinated.
* **A single invalid box fails the whole frame.** That is fail-closed by design,
  but a model that emits occasional degenerate boxes will stall the pipeline
  rather than drop one face.
* The non-goals in `PROJECT_OVERVIEW.md` §6 apply — notably no defense against
  adversarial evasion and no guarantee of perfect detection.

## Tests

`tests/test_face_blur.py` covers the invariants above: no-enrollment
protection, uncertainty emission, hold-over start and stop, pad-before-clamp,
fail-closed behavior, enrollment rejection reasons, and revocation across a
restart. They need only pytest and the standard library; `conftest.py` puts the
package on the path. `apps/models` declares no dependencies of its own, so pytest
comes from the runner:

```bash
uv run --project ../../../api --with pytest pytest tests
```
