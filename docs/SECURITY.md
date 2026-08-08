# Security

## Current implementation boundaries

The API spoken-PII path keeps PCM samples and transcript words in process
memory for one bounded audio-pipeline invocation. The normalizer and ring
buffer retain only the configured media window, and the transcription queue is
bounded by segment count and duration. It does not log transcript text,
detected PII, raw samples, or provider/model errors, and writes only the
explicitly requested muted audio output. The audio pipeline applies intervals
to the original source chunks before returning a safe release decision; failed,
late, or unclassified processing remains blocked. Model caches and output files
remain local operator-controlled artifacts outside the current product
retention contract.

The browser media demo requests explicit camera and microphone permission,
keeps capture and processed tracks in browser memory, and does not upload them
to the API. Permission denial, device disconnect, transport failure, or
processor failure stops the output without attaching raw capture as a fallback.
This is a local demo boundary, not an authentication, authorization, or
production delivery guarantee.

The creator console adds mock-only façades for enrollment, readiness, safety,
and media sessions. Enrollment is consent-gated in the UI, displays no raw
sample, transcript, PII value, or embedding, and presents deletion as a mock
state transition. The protected-output component accepts only a typed protected
stream handle; an unprotected source handle is rendered separately. These mock
states do not authorize a user, create biometric data, or establish backend
readiness.

The shared video engine accepts normalized detector regions, validates and
clamps them, and exposes only sanitized detector status and aggregate timing
metrics. It does not log raw media, OCR values, plate text, or detector payloads.
Its full-frame safe-cover primitive is available to the central safety gate but
the engine does not decide whether output may be published. The production plate
adapter validates the source-image boundary, emits only normalized plate
geometry, and preserves unavailable or execution failures for the scheduler
rather than converting them to empty detections.

The centralized `PrivacyGate` accepts only sanitized capability observations,
source-timeline watermarks, lag, liveness, and explicit control events. It
returns a safe publication action and reason code without inspecting media or
exposing detector payloads. Required failures, missing coverage, unhealthy
liveness, and panic remain fail-closed; a future transport must apply the
decision before publication.

The standalone face module requires explicit creator consent before enrollment,
keeps only one aggregate embedding in the in-memory hackathon store while the
enrollment is active, and supports replacement/deletion. Enrollment images are
not stored by the service, and face embeddings are not present in status,
runner summaries, or ordinary representations. The local runner is not an
authenticated product boundary.

The shared text-PII recognizer keeps normalized text and transcript/OCR spans in
memory only for the active call. It returns categories, confidence, character
offsets, and non-sensitive source identifiers; it does not return matched text
or log/persist classifier payloads. Its detailed contract and modality handoff
are documented in [PRIVACY_TEXT_PII.md](PRIVACY_TEXT_PII.md).

## Detailed security and privacy specification

## 1. Purpose

This document defines the security and privacy requirements for the privacy/redaction system.

The system processes potentially sensitive video, audio, transcripts, OCR output, and biometric-derived information.

The primary security objective is to minimize exposure of raw media and detected PII while ensuring that required privacy protections cannot silently fail.

---

## 2. Security Principles

The implementation follows these principles:

1. **Ephemeral processing by default**
2. **Data minimization**
3. **Explicit creator consent**
4. **Biometric data minimization**
5. **No raw PII in ordinary logs**
6. **Fail closed for required protections**
7. **Shared detector contracts**
8. **Least-privilege access**
9. **Explicit retention periods**
10. **No security guarantee beyond configured detector capabilities**

---

## 3. Data Classification

The following data classes are considered sensitive:

| Data                        | Classification     | Default retention                        |
| --------------------------- | ------------------ | ---------------------------------------- |
| Raw video frames            | Sensitive media    | Ephemeral                                |
| Raw audio                   | Sensitive media    | Ephemeral                                |
| Transcripts                 | Sensitive          | Ephemeral                                |
| OCR output                  | Sensitive          | Ephemeral                                |
| Detected PII values         | Highly sensitive   | Do not persist                           |
| Face embeddings             | Biometric-derived  | Only while explicitly enrolled           |
| Detector regions            | Sensitive metadata | Ephemeral unless required                |
| Detector confidence         | Internal metadata  | Ephemeral / minimal diagnostic retention |
| Configuration               | Operational        | Persistent                               |
| Aggregate benchmark metrics | Non-PII            | Persistent                               |
| Benchmark raw media         | Sensitive          | Explicitly controlled                    |

---

## 4. Raw Media Lifecycle

Raw media must be processed ephemerally by default.

### 4.1 Video

Video frames should:

1. enter the bounded processing buffer;
2. be processed by the configured detectors;
3. produce normalized detection objects;
4. be passed to the compositor/redaction stage;
5. be discarded when no longer required.

The system must not persist raw frames merely for convenience or debugging.

Any intentional persistence of raw frames must be an explicit, separately controlled feature.

### 4.2 Audio

Audio buffers follow the same lifecycle:

```text
input
  ↓
bounded buffer
  ↓
detector
  ↓
redaction decision
  ↓
compositor
  ↓
discard
```

Audio must not be retained after the configured processing window.

### 4.3 Transcripts

Transcripts may contain directly identifying information and must therefore be treated as sensitive.

Transcripts are ephemeral by default.

They must not be written to ordinary application logs.

If transcripts are intentionally persisted for debugging or benchmarking, this must be explicitly enabled and governed by a separate retention policy.

---

## 5. PII Handling

Detected PII values must not be persisted by default.

Examples include:

* phone numbers;
* email addresses;
* identity numbers;
* address strings;
* OCR-extracted license plate text;
* transcript text containing PII.

Detectors should return normalized metadata rather than raw PII whenever possible.

For example, a detector should return:

```text
category = phone_number
confidence = 0.96
start_timestamp = ...
end_timestamp = ...
```

rather than:

```text
value = "+65 1234 5678"
```

The raw value is unnecessary for the redaction decision and therefore should not cross system boundaries unless explicitly required.

---

## 6. Face Embeddings

Creator face embeddings are biometric-derived data.

They must be treated as highly sensitive.

### 6.1 Storage

A creator embedding may only be stored when the creator explicitly enrolls.

The system must not persist face embeddings automatically as a side effect of detection.

The embedding store must:

* restrict access to the minimum required service/component;
* protect stored embeddings against unauthorized access;
* avoid exposing embeddings through normal APIs;
* avoid writing embeddings to logs;
* associate each embedding with an explicit enrollment record.

### 6.2 Purpose limitation

Creator embeddings may only be used for the documented creator-whitelisting function.

They must not be reused for:

* arbitrary person identification;
* surveillance;
* unrelated analytics;
* training unrelated models;
* identifying viewers or third parties.

### 6.3 Deletion

When creator enrollment is revoked, the corresponding embedding must be deleted.

Deletion must remove all persisted copies managed by the application, including applicable caches or derived storage.

After deletion, the creator must be treated as an unknown face.

### 6.4 No enrollment by inference

The system must never create a creator embedding merely because a face appears repeatedly.

Enrollment requires an explicit user action and consent.

---

## 7. Creator Consent

Creator face enrollment must be opt-in.

The enrollment flow must clearly communicate:

* that a face-derived biometric representation is being created;
* why it is needed;
* how it is used;
* that enrollment is optional;
* how the creator can revoke enrollment.

No third-party face should be enrolled as the creator without an explicit supported consent flow.

If consent is absent, creator-whitelisting must not occur.

---

## 8. Logging Requirements

Ordinary application logs must not contain raw PII.

The following must not be logged:

* phone numbers;
* email addresses;
* addresses;
* government/identity numbers;
* license plate strings;
* transcripts;
* OCR text;
* face embeddings;
* raw media;
* raw detector payloads containing PII.

Safe diagnostic metadata may include:

```text
category=phone_number
confidence_bucket=high
detector_id=phone-detector-v2
status=detected
```

where exposing the metadata does not reveal the underlying PII.

Exact confidence values may be omitted or bucketed where unnecessary.

---

## 9. UI Data Minimization

The UI should receive only metadata required to communicate the privacy state.

For example:

```text
category: face
status: protected
```

is preferable to exposing the underlying recognition result.

The UI must not receive raw:

* transcripts;
* OCR strings;
* identity numbers;
* phone numbers;
* email addresses;
* face embeddings.

Debug interfaces, where necessary, must require appropriate authorization and must not become a backdoor for exposing raw PII.

---

## 10. Detector Contract Security

All detectors use the shared privacy taxonomy and output contract.

### 10.1 PII taxonomy

The MVP taxonomy is:

```text
face
face_bystander
license_plate
phone_number
email
postal_address
government_id
payment_identifier
custom_sensitive_text
```

Detector-specific categories are not allowed unless the shared taxonomy is updated.

### 10.2 VideoRegion

The normalized video detector output is conceptually:

```text
VideoRegion {
    frame_id
    timestamp
    geometry
    category
    confidence
    detector_id
    expires_at
    tracking_id
}
```

### 10.3 AudioInterval

The normalized audio detector output is conceptually:

```text
AudioInterval {
    start_timestamp
    end_timestamp
    category
    confidence
    detector_id
}
```

The contract must contain metadata required for redaction but should not contain raw PII values unless explicitly required by a future feature.

---

## 11. Confidence and Uncertainty

A confidence score is not itself a privacy guarantee.

Each protection defines a configured minimum confidence threshold.

If a detector produces a result below the threshold, the result must be treated as uncertain.

The system must not interpret uncertainty as absence.

For example:

```text
detector result:
phone_number
confidence: 0.42

threshold:
0.80
```

must result in:

```text
status = uncertain
```

rather than:

```text
status = no_phone_number
```

---

## 12. Detector Failure and Fail-Closed Policy

Every configured protection must have an explicit failure policy.

### Required protection

If a required detector:

* crashes;
* becomes unavailable;
* times out beyond its configured limit;
* produces invalid output;
* cannot satisfy its confidence/readiness requirements;

the privacy pipeline must enter:

```text
UNSAFE
```

The compositor/streaming layer must fail closed and must not expose unredacted output.

### Optional protection

If an optional detector fails, the system may continue operating.

The system must report:

```text
DEGRADED
```

and must not represent that optional protection as guaranteed.

### Face-specific rule

Unknown or uncertain faces are protected.

If creator enrollment is missing, all detected faces are protected.

This prevents the absence of a trusted identity result from accidentally exposing a face.

---

## 13. Invalid Detector Output

Detector output must be validated before it reaches the compositor.

Invalid output includes:

* unknown PII category;
* confidence outside `[0, 1]`;
* invalid timestamps;
* negative duration;
* malformed geometry;
* missing required fields;
* invalid detector identifier;
* expired regions presented as active.

Invalid output from a required detector must cause an unsafe state.

Invalid output from an optional detector must cause a degraded state.

The compositor must never blindly trust detector output.

---

## 14. Redaction Safety

### 14.1 Video

Video redaction must cover the detected region sufficiently to prevent the underlying PII from being readable.

Supported modes:

```text
blur
pixelate
cover
```

Where temporal tracking is used, the redaction must remain active until the detection expires.

A tracking failure must not immediately expose a previously protected region if the detector's protection policy requires continued protection.

### 14.2 Audio

Audio redaction supports:

```text
mute
beep
silence
```

The protected interval should include an appropriate safety margin where detector timing uncertainty could otherwise expose the beginning or end of a PII utterance.

---

## 15. Retention Policy

### Default

The default retention policy is:

```text
raw frames       → discard after processing
raw audio        → discard after processing
transcripts      → discard after processing
OCR output       → discard after processing
detected PII     → do not persist
detector regions → ephemeral
embeddings       → persist only while explicitly enrolled
configuration    → persist
benchmark data   → explicit retention policy
```

### Bounded buffers

Processing buffers must have explicit bounds for:

* maximum duration;
* maximum number of frames/chunks;
* maximum memory usage where practical.

A detector must not create an unbounded media cache.

---

## 16. Benchmark and Evaluation Artifacts

Benchmark artifacts are separate from production media.

If benchmark datasets contain faces, voices, license plates, or other PII, they must be treated as sensitive data.

Benchmark storage must explicitly document:

* dataset source;
* permitted use;
* access controls;
* retention period;
* deletion procedure;
* whether data is synthetic, consented, or otherwise authorized.

Benchmark logs must not accidentally contain raw PII.

Aggregate metrics such as:

```text
precision
recall
accuracy
false-positive rate
false-negative rate
latency
```

may be retained when they do not contain underlying PII.

---

## 17. Security Boundaries

The following components should have clearly defined boundaries:

```text
Raw media
    ↓
Detector processing
    ↓
Normalized privacy contract
    ↓
Policy evaluation
    ↓
Redaction/compositor
    ↓
Output media
```

Raw media and detector internals should not be unnecessarily exposed to:

* UI clients;
* unrelated application services;
* analytics systems;
* ordinary logging infrastructure.

---

## 18. Configuration Security

Protection configuration must be centralized.

Configuration should define, at minimum:

```text
category
enabled
required / optional
confidence threshold
redaction mode
detector identifier
```

Changes to required/optional protection settings should be auditable.

A configuration that disables a required protection must not silently leave the system reporting that protection as active.

---

## 19. Threat Model — MVP

The MVP primarily protects against accidental exposure of PII through supported media-processing paths.

It does not guarantee protection against:

* compromised host operating systems;
* compromised model runtimes;
* malicious administrators with unrestricted storage access;
* malicious modification of detector models;
* sophisticated adversarial examples;
* PII that cannot be reliably detected;
* external databases used to infer identity;
* screenshots or recordings made after protected output leaves the system.

The security model assumes the application runtime and trusted infrastructure are appropriately secured.

---

## 20. Security Non-Goals

The first version is not a general-purpose anonymity or identity-protection system.

It does not guarantee:

* perfect PII detection;
* perfect face recognition;
* perfect speaker identification;
* complete anonymization;
* irreversible anonymization;
* protection from contextual re-identification;
* detection of all sensitive information;
* protection against all adversarial attacks.

The product must not make claims stronger than the configured detector capabilities.

---

## 21. Security Review Requirements

Before a new detector is enabled in production, it should be reviewed for:

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

A detector is not production-ready merely because its model achieves an acceptable benchmark score.

---

## 22. Core Security Rule

The central security rule is:

> Failure to detect PII is not equivalent to proof that PII is absent.

Therefore:

> Required protection must fail closed whenever the system cannot establish that the configured protection is functioning.

This rule applies across video, audio, transcript, OCR, and biometric-derived protection components.
