# INTEGRATION_GUIDE.md

# Face Detection Pipeline — Integration Guide

This guide is for engineers wiring the face detection pipeline into the
PrivaStream privacy system: the contract it must satisfy, how enrollment and
configuration work, how failures propagate, and what must never cross a
boundary.

Read [`PROJECT_OVERVIEW.md`](./PROJECT_OVERVIEW.md) first for what the pipeline
does and why. This document covers how to connect it.

**Precedence.** `apps/api/src/privastream_api/pipeline/contracts.py` is the
authoritative interface. Where `PRODUCT.md` or `SECURITY.md` describe a
different shape, the code wins — see §3.1. Those documents remain authoritative
for *behavior*: fail-closed policy, conservative handling of uncertainty,
consent, logging, and retention.

---

## 1. Integration boundaries

```text
Raw media
    ↓                        ← frames in, bounded buffer, ephemeral
Detector processing           ← this component
    ↓                        ← normalized regions out, no raw media
Normalized privacy contract
    ↓
Policy evaluation             ← required/optional, thresholds, readiness
    ↓
Redaction / compositor        ← blur | pixelate | cover
    ↓
Output media
```

Rules at these boundaries (`SECURITY.md` §17):

* Raw frames and detector internals must not reach UI clients, unrelated
  services, analytics systems, or ordinary logging.
* The detector returns metadata, never media. No crops, no thumbnails, no
  embeddings.
* The compositor must never blindly trust detector output — it validates first
  (§5 below).

---

## 2. Input contract

The detector receives frame metadata plus the frame's pixel data through the
runtime's media path. Frame metadata as implemented today
(`apps/api/src/privastream_api/pipeline/contracts.py`):

```python
VideoFrame {
    width: int          # > 0
    height: int         # > 0
    timestamp_ms: int   # >= 0, source-media timeline
    frame_id: str | None
}
```

Requirements on the caller:

* Frames arrive in a **bounded** buffer with explicit limits on duration, frame
  count, and — where practical — memory (`SECURITY.md` §15). The detector must
  not build its own unbounded cache.
* `timestamp_ms` is on the **source-media** timeline, not wall clock. Redaction
  intervals and expiry are meaningless otherwise.
* Frames are discarded after processing. The detector must not retain them.

---

## 3. Output contract

### 3.1 The authoritative contract

`apps/api/src/privastream_api/pipeline/contracts.py` **is** the contract. Where
`PRODUCT.md` §6 and `SECURITY.md` §10.2 describe a `VideoRegion` that differs
from the code, the code wins and the specs are read as intent, not as fields to
implement.

| | Spec (`PRODUCT.md` §6, `SECURITY.md` §10.2) | **Authoritative** (`contracts.py`) |
| --- | --- | --- |
| Type name | `VideoRegion` | `VideoRegionDetection` |
| Category field | `category` (from `PiiCategory`) | `kind: Literal["face","license_plate","text"]` |
| Geometry | `geometry` (convention undefined) | `x, y, width, height` — normalized floats |
| Frame id | `frame_id` | *(no such field — use `timestamp_ms`)* |
| Timestamp | `timestamp` | `timestamp_ms: int` |
| Detector id | `detector_id` | `detector: str` |
| Tracking | `tracking_id` | `track_id: str \| None` |
| Expiry | `expires_at` | *(no such field — see below)* |

Do not add fields to `VideoRegionDetection` to close these gaps as part of
integrating this detector. Two of them change how the pipeline must behave:

1. **There is no `expires_at`, so expiry is not a contract value — it is
   detector behavior.** The specs require redaction to stay active until a
   region expires and require that a tracking failure not immediately expose a
   previously protected region (`PRODUCT.md` §4.1, `SECURITY.md` §14.1). With no
   expiry field, the only way to satisfy that is for **the detector to keep
   emitting the region on every frame of the hold-over window**. A region is
   active because it was emitted for the current frame, and for no other reason.
   See §3.5.
2. **`VideoDetectionKind` is the video category set, not `PiiCategory`.** The
   valid values are `face`, `license_plate`, and `text`. The six-value MVP
   taxonomy in the specs spans audio and text detectors too; for video output,
   `kind` governs. This detector emits `face` and nothing else. Detector-specific
   category strings remain prohibited — extending the set means changing the
   `Literal` in `contracts.py`.

Likewise `VideoFrame` carries an optional `frame_id`, but
`VideoRegionDetection` has no place to echo it. Correlate regions to frames by
`timestamp_ms`.

### 3.2 What this detector emits

The pipeline implements the `FaceDetector` protocol from `contracts.py`:

```python
class FaceDetector(Protocol):
    kind: Literal["face"]

    def detect(self, frame: VideoFrame) -> Sequence[VideoRegionDetection]: ...
```

It returns one region per face that must be redacted — every face classified
`NON_WHITELISTED` **or** `UNCERTAIN`, plus any track inside its hold-over window
(§3.5). Whitelisted faces produce no region.

```python
VideoRegionDetection(
    kind="face",
    x=..., y=..., width=..., height=...,   # normalized, padded, EMA-stabilized
    confidence=...,                        # [0, 1]
    timestamp_ms=frame.timestamp_ms,
    detector="face-detector-v1",           # id + version
    track_id="...",                        # stable across frames of one track
)
```

### 3.3 Coordinate convention

The API documentation must state origin, ordering, normalization range, and
whether coordinates refer to the original or processed frame
(`PRODUCT.md` §6). For this detector:

| Property | Value |
| -------- | ----- |
| Origin | Top-left of the frame |
| Ordering | `x, y, width, height` |
| Range | Normalized `[0, 1]`, relative to frame width/height |
| Reference frame | The **processed** frame — the same `VideoFrame` passed to `detect()` |
| Bounds | `x + width <= 1` and `y + height <= 1`, enforced by the dataclass |

Normalized coordinates are required because regions cross stages that may run at
different resolutions.

**Padding interacts with bounds.** The configured padding is applied *before*
clamping, then the padded box is clamped to the frame. Do not clamp first —
clamping first silently shrinks the margin exactly at the frame edge, which is
where a partially visible face is most likely to leak.

### 3.4 Confidence semantics

`confidence` is the detector's confidence **in the redaction decision**, not the
raw face-detection score and not the identity similarity score. Two distinct
signals feed it:

* detection quality (is this a face at all);
* recognition outcome (is it established as whitelisted).

A face classified `UNCERTAIN` is emitted as a region because uncertain identity
means protect. Do not emit a low `confidence` to express identity uncertainty
and then let policy threshold it away — that would invert the rule in
`PRODUCT.md` §8. The similarity score must not leave the detector; it is an
internal recognition detail.

### 3.5 Track lifetime and hold-over

Because the contract has no `expires_at` (§3.1), a region is active for exactly
the frame it was emitted on. Continued protection therefore means continued
emission.

* `track_id` is stable for the lifetime of one tracked face and is not reused.
* When a track is lost, the detector **keeps emitting** its last stabilized,
  padded box — with the same `track_id` and the current frame's `timestamp_ms` —
  for the configured hold-over window. A dropped track must not end protection
  in the same frame (`SECURITY.md` §14.1).
* Once the hold-over window elapses, the detector stops emitting that
  `track_id`. Emitting a region past its hold-over is the code-contract
  equivalent of presenting an expired region as active, which is invalid output
  (`SECURITY.md` §13).
* Hold-over regions carry the same `confidence` semantics as live ones (§3.4).
  They are protection decisions, not weakened guesses.

The consequence for the compositor: it holds no expiry state of its own. It
redacts what it is given for the frame it is given, and the detector owns the
temporal decision. That keeps one component responsible for coverage over time.

---

## 4. Configuration

Protection configuration is **centralized**, not defined per detector
(`SECURITY.md` §18). Configuration defines at minimum:

```text
category
enabled
required / optional
confidence threshold
redaction mode
detector identifier
```

Detector-local parameters that this pipeline additionally needs:

| Parameter | Purpose | Bias when tuning |
| --------- | ------- | ---------------- |
| Whitelist match threshold | Similarity above which a face is `WHITELISTED` | Higher = fewer strangers whitelisted |
| Uncertainty band | Similarity range treated as `UNCERTAIN` | Wider = more faces protected |
| Top-k (`k`) | References averaged in the comparison | See `PROJECT_OVERVIEW.md` §3.2 |
| Minimum face size | Below this, a detection is too small to classify reliably | Too small ⇒ `UNCERTAIN` ⇒ protected, never skipped |
| EMA factor | Box smoothing strength | More smoothing = more lag = needs more padding |
| Padding | Margin around the stabilized box | Larger = safer coverage |
| Track hold-over | How long protection survives a lost track | Longer = safer |

Every one of these has a safe direction. When a value is uncertain, choose the
one that protects more faces.

Two configuration rules from `SECURITY.md` §18:

* Changes to required/optional settings must be **auditable**.
* A configuration that disables a required protection must not leave the system
  reporting that protection as active.

The default redaction mode is set centrally, not by this detector. The detector
does not know or care whether the compositor blurs, pixelates, or covers.

---

## 5. Output validation

The compositor validates detector output before acting on it
(`SECURITY.md` §13). Against the code contract, invalid output is:

* a `kind` outside `VideoDetectionKind` — for this detector, anything but `face`;
* `confidence` outside `[0, 1]`, or non-finite;
* `x`, `y`, `width`, `height` outside `[0, 1]`, or non-finite;
* `width` or `height` of zero;
* `x + width > 1` or `y + height > 1` (region escapes the frame);
* negative `timestamp_ms`;
* an empty or whitespace-only `detector`;
* a region emitted past its hold-over window (§3.5).

Consequences:

| Detector policy | Invalid output causes |
| --------------- | --------------------- |
| `required` | `UNSAFE` |
| `optional` | `DEGRADED` |

`VideoRegionDetection.__post_init__` already enforces everything on that list
except hold-over: unit-interval bounds, finiteness, positive dimensions,
in-frame containment, non-empty `detector`, non-negative `timestamp_ms`. So an
invalid region raises `ValueError` at construction rather than reaching the
compositor. Construction failure is a detector failure — see §6. Do not catch it
and emit nothing; emitting nothing is
indistinguishable from "no faces present," which is exactly the confusion
`SECURITY.md` §22 forbids.

---

## 6. Failure handling

Face protection's default policy is **fail closed** (`PRODUCT.md` §9).

The pipeline enters `UNSAFE` when a required face detector:

* crashes;
* becomes unavailable (model not loaded, runtime gone);
* times out beyond its configured limit;
* produces invalid output;
* cannot satisfy its confidence/readiness requirements.

While `UNSAFE`, the compositor/streaming layer must fail closed and must not
expose unredacted output.

If face protection is configured `optional`, a failure yields `DEGRADED`, the
system may continue, and the UI must show the protection as unavailable — never
as guaranteed.

The distinction that must survive integration:

```text
detector failure  →  PII detection status = unavailable
                  ✗  PII detection status = none
```

Face-specific rules that hold regardless of failure state:

* Unknown or uncertain faces are protected.
* If no enrollment exists, **all** detected faces are protected.

---

## 7. Enrollment integration

Enrollment is an explicit, opt-in operation (`PRODUCT.md` §10,
`SECURITY.md` §6–7).

### 7.1 Enrollment flow

1. The creator explicitly initiates enrollment and provides an enrollment image
   or approved enrollment sequence.
2. The flow communicates: that a face-derived biometric representation is being
   created, why it is needed, how it is used, that it is optional, and how to
   revoke it.
3. Each reference image is validated and embedded per
   `PROJECT_OVERVIEW.md` §3.1. Rejected images are reported back so the creator
   can supply better ones.
4. Embeddings are stored grouped by identity and bound to an explicit
   enrollment record.

### 7.2 Storage requirements

The embedding store must:

* restrict access to the minimum required service/component;
* protect stored embeddings against unauthorized access;
* not expose embeddings through normal APIs;
* not write embeddings to logs;
* associate every embedding with an explicit enrollment record.

### 7.3 Revocation

On revocation, delete the embedding and **all persisted copies** the application
manages, including caches and derived storage. Subsequent frames treat that
person as an unknown face — therefore protected.

Revocation must take effect on the processing path, not just in the store. A
warm in-process whitelist cache that outlives revocation keeps someone
whitelisted after they withdrew consent. Invalidate it as part of the deletion,
not on the next natural refresh.

### 7.4 Prohibited

* Automatic enrollment.
* Inferring consent from a face's presence or repeated appearance.
* Enrolling third parties without a supported consent flow.
* Using embeddings for arbitrary identification, surveillance, unrelated
  analytics, training unrelated models, or identifying viewers.

If consent is absent, creator-whitelisting does not occur — every face is
protected.

---

## 8. Logging and diagnostics

Never log: embeddings, raw frames or crops, similarity scores tied to an
identity, raw detector payloads.

Safe diagnostic metadata:

```text
category=face
confidence_bucket=high
detector_id=face-detector-v1
status=detected
```

Exact confidence values may be bucketed or omitted where precision is
unnecessary. Detector identifiers and technical metadata may go to authorized
diagnostics interfaces — which must require authorization and must not become a
backdoor for raw PII (`SECURITY.md` §9).

---

## 9. UI integration

The UI receives protection state only:

```text
Protected: face
Confidence: high
Status: active
```

The UI must not receive face embeddings, similarity scores, identity match
results, or raw detector payloads (`PRODUCT.md` §12, `SECURITY.md` §9).

Readiness surfaces as `READY` / `DEGRADED` / `UNSAFE`. An optional protection
that is unavailable must be shown as unavailable, never as protected.

---

## 10. Benchmarking

Benchmark artifacts are separate from production media
(`SECURITY.md` §16). Benchmark data containing faces is sensitive and must
document source, permitted use, access controls, retention period, deletion
procedure, and whether the data is synthetic, consented, or otherwise
authorized.

Benchmark logs must not contain raw PII. Aggregate metrics — precision, recall,
accuracy, false-positive rate, false-negative rate, latency — may be retained.

Track separately, because they fail differently:

* **false negatives** — a non-whitelisted face left unredacted (privacy breach);
* **false positives** — a whitelisted creator redacted (usability defect);
* **coverage** — fraction of the true face area actually covered by the emitted
  box, which is what catches padding and EMA-lag failures that a per-frame
  hit/miss metric scores as a hit.

A benchmark score does not make the detector production-ready. The review in
`SECURITY.md` §21 does — see `PROJECT_OVERVIEW.md` §7.

---

## 11. Integration checklist

- [ ] Detector implements the `FaceDetector` protocol from `contracts.py`
      (`kind = "face"`, `detect(frame) -> Sequence[VideoRegionDetection]`)
- [ ] No fields added to `VideoRegionDetection`; spec-only fields (`expires_at`,
      `frame_id`, `category`) are not expected downstream
- [ ] Coordinate convention documented in the API docs, matching §3.3
- [ ] Padding applied before clamping, not after
- [ ] Frames processed from a bounded buffer and discarded after use
- [ ] Detector emits only `face` regions, only for `NON_WHITELISTED` and
      `UNCERTAIN`
- [ ] `UNCERTAIN` produces a region — not a low-confidence region that policy
      can threshold away
- [ ] Configuration centralized; required/optional changes auditable
- [ ] Detector failure yields `UNSAFE` (required) or `DEGRADED` (optional) —
      never an empty region list
- [ ] Compositor validates output before acting on it
- [ ] Dropped tracks keep emitting for the hold-over window, and stop after it
- [ ] No enrollment ⇒ all faces protected, verified end to end
- [ ] Revocation deletes every copy and invalidates the in-process cache
- [ ] No embeddings, crops, scores, or raw payloads in logs or the UI
- [ ] Security review (`SECURITY.md` §21) completed
