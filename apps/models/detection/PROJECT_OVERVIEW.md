# PROJECT_OVERVIEW.md

# Face Detection & Whitelist Pipeline — Project Overview

## 1. What this component is

This is the **face detector** for the PrivaStream privacy/redaction system. It
examines each video frame and returns the regions that must be redacted before
the media is exposed to any downstream consumer.

It is a privacy component, not an identity-recognition product. Recognition is
used only as a negative filter — to decide which faces may be left alone. Every
face not positively established as whitelisted is returned as a redaction
target.

Position in the system:

```text
Raw frames
    ↓
Face detection pipeline   ← this component
    ↓
Normalized privacy contract
    ↓
Policy evaluation
    ↓
Redaction / compositor
    ↓
Output media
```

The component emits normalized detection objects. It does **not** blur,
pixelate, cover, draw, or encode media — redaction belongs to the compositor.

Sources: [`OVERVIEW.md`](./OVERVIEW.md) (pipeline design),
[`../PRODUCT.md`](../PRODUCT.md) (product guarantees),
[`../SECURITY.md`](../SECURITY.md) (security and data handling).

**Precedence.** Where those documents conflict with
`apps/api/src/privastream_api/pipeline/contracts.py`, the code is authoritative.
The specs define required *behavior* — fail-closed, conservative uncertainty,
consent, retention — and that behavior still binds; the code defines the *shape*
of what crosses the boundary.

---

## 2. Primary objective

> Minimize the probability that a non-whitelisted face is left partially or
> completely unblurred.

This ranks above recognition accuracy, throughput, and media availability. Where
they conflict, the pipeline chooses protection. Two consequences shape every
design decision below:

1. **False negatives are the expensive failure.** Blurring a whitelisted
   creator by mistake is a usability defect. Failing to blur a bystander is a
   privacy breach.
2. **Uncertainty is not absence.** An ambiguous or low-quality recognition
   result is treated as non-whitelisted, never as "probably the creator."

---

## 3. Pipeline stages

### 3.1 Whitelist database (enrollment time)

A whitelist identity is represented by **multiple reference embeddings**, never
one. The reference set — roughly 30 images per identity in the design target —
deliberately spans varied head poses and viewing angles, lighting conditions,
facial expressions, distances/scales, and partial pose variations.

For each reference image:

| Step | Behavior |
| ---- | -------- |
| Detect | InsightFace face detection on the reference image |
| Extract | ArcFace embedding for the detected face |
| Normalize | L2-normalize if the recognition implementation requires it |
| Validate | Reject unusable images (below) |
| Store | Group the surviving embedding under its identity |

A reference image is **rejected** when:

* no face is detected;
* multiple faces are detected (the intended subject is ambiguous);
* the detected face is too small or otherwise invalid.

Rejection is a normal outcome, not an error. It prevents a mislabeled or
ambiguous reference from silently widening the whitelist — the one enrollment
failure that would cause a stranger to go unblurred at inference time.

### 3.2 Whitelist comparison strategy

A query embedding is compared against an identity's whole reference set. The
candidate aggregations named in the design are maximum cosine similarity, top-k
similarity, centroid/mean embedding, or another justified method.

**Chosen: top-k mean cosine similarity** (small k, e.g. 3), falling back to max
similarity for identities whose validated reference set is smaller than k.

| Method | Behavior | Trade-off |
| ------ | -------- | --------- |
| **Max similarity** | Match if any single reference is close enough | Most permissive and most pose-robust, but a single outlier or partially mislabeled reference can whitelist a stranger — a privacy failure |
| **Centroid / mean** | Match against one averaged embedding | Compact and fast, but averaging ~30 varied poses and lighting conditions blurs the identity; under-matches profile and low-light views, so the creator is blurred constantly |
| **Top-k mean** *(chosen)* | Average the k highest similarities | Requires consistent agreement from several references rather than one lucky match, so a lone bad reference cannot whitelist a stranger; retains pose robustness because the k nearest references are typically those closest to the query pose |

The cost of top-k mean is that it is marginally stricter than max similarity, so
the creator is blurred slightly more often at the edges of the reference
distribution. Given the objective in §2, that is the correct direction to err.

Comparison always operates over the full validated reference set when more than
one reference exists.

### 3.3 Per-frame processing

```text
frame
  ↓
InsightFace face detection
  ↓
all detected face bounding boxes
  ↓
ArcFace embedding for each face
  ↓
comparison against whitelist
  ↓
WHITELISTED / NON_WHITELISTED / UNCERTAIN
```

Every visible face is detected first, then classified. Embedding extraction is
never skipped for a detected face: a face that is detected but unclassified is
an unclassified face, and is treated as protected.

### 3.4 Classification

| Class | Meaning | Redaction outcome |
| ----- | ------- | ----------------- |
| `WHITELISTED` | Sufficiently similar to a whitelist identity | Not redacted |
| `NON_WHITELISTED` | Does not sufficiently match any whitelist identity | **Redacted** |
| `UNKNOWN / UNCERTAIN` | Insufficient-quality or ambiguous recognition result | **Redacted** — treated conservatively as non-whitelisted |

`UNCERTAIN` collapsing into "redact" is the most important rule in this
component. It is required by `PRODUCT.md` §2.1 and §8 and `SECURITY.md` §12: an
uncertain identity match must never leave a face unprotected.

### 3.5 Tracking and temporal stabilization

> The source `OVERVIEW.md` is truncated partway through its per-frame section;
> its detailed tracking, EMA, threshold, and output subsections are missing.
> What follows reflects the requirements stated in that document's numbered
> Context list (items 7–10) and should be reconciled once the full design is
> restored.

Detected faces are tracked across consecutive frames, and emitted bounding boxes
are stabilized temporally using **tracking plus an exponential moving average
(EMA)**. Stabilization serves two purposes:

1. **Visual stability** — raw per-frame boxes jitter, which makes the redacted
   region shimmer and draws attention to it.
2. **Coverage continuity** — a track carries protection through frames where
   detection momentarily flickers. A tracking failure must not immediately
   expose a region protected in the previous frame (`SECURITY.md` §14.1).

A small **configurable padding** is applied around the stabilized box before
emission, absorbing residual localization error and EMA lag. This satisfies the
requirement that the redaction region cover the detected region with sufficient
margin (`PRODUCT.md` §4.1).

Because EMA lags a fast-moving subject, padding and track expiry are what keep
that lag from exposing the edge of a face. Tune them together, not
independently.

### 3.6 Output

Stabilized, padded boxes for all `NON_WHITELISTED` and `UNCERTAIN` faces are
returned to the video post-processing stage for blurring, as
`VideoRegionDetection` objects from
`apps/api/src/privastream_api/pipeline/contracts.py` — the authoritative output
contract. The exact fields, coordinate convention, and hold-over semantics are
in [`INTEGRATION_GUIDE.md`](./INTEGRATION_GUIDE.md).

Because that contract has no expiry field, continued protection is expressed by
continued emission: a lost track keeps producing its last stabilized box for the
configured hold-over window rather than handing the compositor an expiry to
honor.

---

## 4. Privacy and security posture

The following is required by `../SECURITY.md` and `../PRODUCT.md`, not optional
hardening.

### 4.1 Enrollment is explicit and opt-in

An identity is whitelisted only through an explicit enrollment action by that
person. The pipeline must never:

* automatically enroll anyone;
* infer consent from a face appearing, or appearing repeatedly;
* enroll a third party without a supported consent flow;
* use an enrollment embedding for anything but whitelist matching.

**If no identity is enrolled, every detected face is protected.** That is the
correct default state, not a degraded one.

### 4.2 Embeddings are biometric-derived data

Face embeddings are classified as biometric-derived and highly sensitive
(`SECURITY.md` §3, §6). They persist **only while an enrollment is active**, are
never created as a side effect of detection, are never logged, and are never
exposed through ordinary APIs or to the UI.

Per-frame query embeddings are transient: they produce a similarity score and
are discarded with the frame.

On revocation the stored embedding is deleted — including caches and derived
copies — and that identity reverts to being an unknown, therefore protected,
face.

### 4.3 Raw media is ephemeral

Frames enter a bounded buffer, are processed, produce normalized detections, and
are discarded. No persisting frames for convenience or debugging, and no
unbounded media cache. Deliberate frame retention is a separate, explicitly
controlled feature with its own retention policy.

### 4.4 Fail closed

Face protection's default failure policy is **fail closed** (`PRODUCT.md` §9). A
crash, timeout, unavailable model, or invalid output moves the pipeline to
`UNSAFE`, and the compositor must not emit unredacted output while `UNSAFE`.

From `SECURITY.md` §22:

> Failure to detect PII is not equivalent to proof that PII is absent.

A detector failure means `status = unavailable`. It never means `no faces
detected`.

### 4.5 Logging and UI

Ordinary logs may carry category, detector id, status, and bucketed confidence.
They must not carry embeddings, raw frames, crops, or raw detector payloads. The
UI receives protection state only — e.g. `category: face, status: protected` —
never the underlying recognition result or similarity score.

---

## 5. Readiness states

| State | Condition |
| ----- | --------- |
| `READY` | All required protections available and within configured requirements |
| `DEGRADED` | An optional protection is unavailable or below requirement |
| `UNSAFE` | A required protection cannot guarantee its configured protection |

Whether a face-detector failure yields `UNSAFE` or `DEGRADED` depends on whether
face protection is configured `required` or `optional`; the default policy for
face is fail closed. An optional protection must never be presented to the user
as a guarantee.

---

## 6. Non-goals

This component does not:

* identify or name arbitrary people;
* perform surveillance, analytics, or relationship inference;
* guarantee perfect face detection or perfect recognition;
* guarantee complete or irreversible anonymization;
* defend against adversarial inputs crafted to evade detection;
* protect against contextual re-identification;
* protect content after redacted output has left the system.

It also inherits the MVP non-goals in `PRODUCT.md` §11 and the threat-model
exclusions in `SECURITY.md` §19 — notably that a compromised host, runtime, or
model is out of scope. The product must not make claims stronger than the
configured detector supports.

---

## 7. Production readiness

Per `SECURITY.md` §21, a benchmark score does not make this detector
production-ready. Review before enabling in production:

1. taxonomy compatibility;
2. output-contract compatibility;
3. confidence semantics;
4. failure behavior;
5. raw-data handling;
6. logging behavior;
7. retention behavior;
8. redaction coverage;
9. required/optional policy;
10. privacy impact.

Aggregate metrics (precision, recall, false-positive/negative rate, latency) may
be retained. Benchmark media containing faces is sensitive and needs a
documented source, permitted use, access controls, retention period, and
deletion procedure.

For this component, **recall on non-whitelisted faces and the false-negative
rate are the metrics that matter**. A high overall accuracy figure that conceals
a non-trivial false-negative rate describes a system that leaks faces.

---

## 8. Open items

| Item | Status |
| ---- | ------ |
| `OVERVIEW.md` truncated | Tracking, EMA, threshold, and output sections are absent from the source design; reconstructed here from its Context list. Restore and reconcile. |
| Similarity thresholds | Concrete match and uncertainty threshold values are not fixed in the source design; set them from benchmark data, biased toward protection. |
| Spec vs. code contract | `contracts.py` is authoritative; the `VideoRegion` shape in `PRODUCT.md` §6 / `SECURITY.md` §10.2 is intent, not fields to implement. The specs are the documents that need updating, not the code. See `INTEGRATION_GUIDE.md` §3.1. |
