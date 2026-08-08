# Product

## Current implementation status

PrivaStream is a privacy-first media processing platform foundation. The
planned outcome is protected video and audio in which configured privacy-
sensitive content is redacted before delivery.

| Capability | Entry point | Current result | Availability | Verification |
| --- | --- | --- | --- | --- |
| Browser media loopback demo | `GET /` on the web app | Uses a local WebRTC loopback and deterministic mock video/audio processing, then attaches only processed tracks to the protected preview. | Implemented | Unverified |
| API process health | `GET /health` | Returns `{ "status": "ok", "service": "privastream-api" }`. | Implemented | Unverified |
| Standalone visual privacy demo | `apps/api/scripts/vision_demo.py` | Processes a local image or short video with plate and OCR/PII adapters when optional dependencies and local weights are supplied. | Implemented | Unverified |
| Standalone spoken-PII demo | `python -m privastream_api.pipeline.spoken_pii` | Accepts a bounded PCM16 WAV and writes a copy with detected phone-number and email intervals muted. | Implemented | Unverified |

The HTTP product surface does not accept media. The browser demo does not
upload media to the API or provide server-side live transport. The standalone
demos process local inputs and render local protected copies; they do not store
or transport media as product state.

## Planned creator journey

1. A creator selects a live or recorded media source and a privacy policy.
2. PrivaStream runs the configured face, license-plate, OCR, and spoken-PII
   detectors independently.
3. Normalized detector results are coordinated across time and passed to a
   redaction compositor.
4. The creator inspects and controls the protected preview or output.

The local capture and protected-preview portion is Implemented through the
browser demo. Policy selection, real detectors, temporal coordination, and
protected delivery beyond that local preview are Planned.

## Privacy and safety boundaries

- Required detector failure must not be represented as a safe result.
- Raw media and biometric data must not be retained unless a later approved
  contract requires it.
- Model-specific outputs are not a product contract; detectors return
  normalized video regions or audio intervals.
- The current scaffold makes no claim about complete privacy coverage, latency,
  accuracy, delivery, or end-to-end protection.

## Current non-goals

Authentication, creator enrollment, product-surface media upload, server-side
or production live transport, face detection integration, cross-modal
synchronization, shared redaction compositing, persistence, and production
deployment are not implemented here. The browser loopback and standalone demos
are local or best-effort paths, not production delivery capabilities.

## Detailed privacy protection specification

## 1. Purpose

This document defines the privacy protections provided by the first version of the privacy/redaction system.

The system detects configured personally identifiable information (PII) in video and audio streams and applies the configured protection policy before the media is exposed to downstream consumers.

All detectors use a shared privacy contract. Individual detectors must not define their own incompatible output formats or PII taxonomies.

The MVP prioritizes predictable privacy behavior over broad or speculative PII detection.

---

## 2. MVP Privacy Guarantees

The MVP provides protection for the following supported PII categories:

| Category          | Media                                 | MVP support                                               |
| ----------------- | ------------------------------------- | --------------------------------------------------------- |
| `face`            | Video                                 | Supported                                                 |
| `license_plate`   | Video                                 | Supported                                                 |
| `phone_number`    | Audio / transcript / OCR-derived text | Supported                                                 |
| `email`           | Audio / transcript / OCR-derived text | Supported                                                 |
| `address`         | Audio / transcript / OCR-derived text | Supported when reliably identifiable                      |
| `identity_number` | Audio / transcript / OCR-derived text | Supported when matched by configured patterns/classifiers |

The system does **not** claim to detect every occurrence of PII. Protection is limited to the configured detectors, models, patterns, and confidence thresholds.

### 2.1 Face protection

Faces of people who are not explicitly whitelisted are protected by default.

If creator face enrollment is enabled:

* the enrolled creator face may be treated as whitelisted;
* all other detected faces remain protected;
* an uncertain identity match must not cause a face to become unprotected.

If creator enrollment is unavailable or no creator has been explicitly enrolled, **all detected faces are protected**.

This is intentionally conservative.

### 2.2 License plates

Detected vehicle license plates are protected using the configured video redaction mode.

The system does not attempt to infer ownership or identify the vehicle owner.

### 2.3 Phone numbers

Phone numbers are protected when detected by a configured speech/transcript/OCR detector and when the detector confidence satisfies the configured threshold.

The system does not guarantee detection of:

* non-standard spoken phone numbers;
* deliberately obfuscated phone numbers;
* numbers spoken with insufficient audio quality;
* phone numbers that cannot be reliably distinguished from unrelated numeric sequences.

### 2.4 Email addresses

Email addresses are protected when reliably detected by a configured detector.

The detector may use transcript, OCR, or another approved text extraction mechanism.

The system does not guarantee detection of arbitrary or heavily obfuscated email addresses.

### 2.5 Addresses

Addresses are protected only when they can be reliably identified as addresses by the configured classifier or detector.

Arbitrary geographic references, landmarks, place names, or incomplete location descriptions are not automatically considered PII.

### 2.6 Government and identity numbers

Government/identity numbers are protected only when they match configured patterns and/or approved classifiers.

Examples may include configured national identification, passport, driver's-license, or other government-issued identifier formats.

The system must not assume that every numeric string is an identity number.

---

## 3. Protection Modes

Each PII protection can be configured as either:

* `required`
* `optional`

### Required protection

A required protection is necessary for the system to declare the media safe for release.

If its detector cannot operate or cannot satisfy its configured confidence/readiness requirements, the system enters an unsafe readiness state and the downstream compositor/streaming layer must fail closed.

### Optional protection

An optional protection is best-effort.

If its detector is unavailable or fails, the system may continue operating, but the UI and system status must accurately indicate that the protection is unavailable.

Optional protection must never be presented as guaranteed protection.

---

## 4. Redaction Policy

### 4.1 Video

Supported video redaction modes are:

* `blur`
* `pixelate`
* `cover`

The default mode should be configured centrally rather than independently by each detector.

The redaction region must cover the detected PII region with sufficient margin to avoid exposing the protected content due to small localization errors.

For tracked regions, redaction must remain active until the region expires according to the detector/tracker metadata.

### 4.2 Audio

Supported audio redaction modes are:

* `mute`
* `beep`
* `silence`

The selected audio mode must cover the entire protected interval.

When timing uncertainty exists, the compositor may apply a configured safety margin before and after the detected interval.

---

## 5. Shared Detector Contract

All privacy detectors must emit normalized objects using the shared privacy contract.

### 5.1 PII taxonomy

The stable MVP taxonomy is:

```text
face
license_plate
phone_number
email
identity_number
address
```

New categories must be explicitly added to the shared taxonomy before detector implementations use them.

Arbitrary detector-specific category strings are not permitted.

---

## 6. VideoRegion

A video detector produces one or more `VideoRegion` objects.

Conceptually:

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

### Required fields

| Field         | Description                                                       |
| ------------- | ----------------------------------------------------------------- |
| `frame_id`    | Source frame identifier when available                            |
| `timestamp`   | Source-media timestamp                                            |
| `geometry`    | Bounding geometry of the detected PII                             |
| `category`    | Value from the shared `PiiCategory` taxonomy                      |
| `confidence`  | Detector confidence in the range `[0, 1]`                         |
| `detector_id` | Identifier/version of the detector                                |
| `expires_at`  | Time at which the detection should no longer be considered active |

`tracking_id` is used when temporal tracking is available.

### Geometry

Geometry must have a documented coordinate convention.

Implementations should prefer normalized coordinates when regions cross different resolutions or processing stages.

The API documentation must specify:

* coordinate origin;
* coordinate ordering;
* normalization range;
* whether coordinates refer to the original or processed frame.

---

## 7. AudioInterval

An audio detector produces one or more `AudioInterval` objects.

Conceptually:

```text
AudioInterval {
    start_timestamp
    end_timestamp
    category
    confidence
    detector_id
}
```

### Required fields

| Field             | Description                                  |
| ----------------- | -------------------------------------------- |
| `start_timestamp` | Start of protected source-media interval     |
| `end_timestamp`   | End of protected source-media interval       |
| `category`        | Value from the shared `PiiCategory` taxonomy |
| `confidence`      | Detector confidence in `[0, 1]`              |
| `detector_id`     | Identifier/version of the detector           |

---

## 8. Detection Uncertainty

The system must behave conservatively when a detector is uncertain.

A detector must not silently convert an uncertain result into an unprotected result.

Each detector has a configured confidence threshold.

If:

```text
confidence < configured_threshold
```

the detection is considered uncertain.

For required protections, unresolved uncertainty must result in an unsafe readiness state when the protected content could otherwise be exposed.

For optional protections, the system may continue operating but must report the protection as degraded/unavailable.

For faces specifically, an uncertain creator/non-creator identity match must result in protection.

---

## 9. Detector Failure

Every configured protection has an explicit failure policy.

| Protection      | Default policy                              |
| --------------- | ------------------------------------------- |
| Face            | Fail closed                                 |
| License plate   | Required → fail closed; optional → degraded |
| Phone number    | Required → fail closed; optional → degraded |
| Email           | Required → fail closed; optional → degraded |
| Address         | Required → fail closed; optional → degraded |
| Identity number | Required → fail closed; optional → degraded |

The `required`/`optional` configuration determines the final readiness behavior.

A detector failure must never be interpreted as "no PII detected."

It means:

```text
PII detection status = unavailable
```

not:

```text
PII detection status = none
```

---

## 10. Creator Consent and Face Enrollment

Creator face enrollment is an explicit opt-in operation.

The creator must knowingly provide an enrollment image or approved enrollment sequence.

Enrollment is used only to determine whether a detected face corresponds to the enrolled creator.

The system must not:

* automatically enroll a creator;
* infer consent from the presence of a face;
* enroll other people without an explicit supported consent mechanism;
* use the embedding for unrelated recognition purposes.

If no creator is enrolled, all faces are protected.

If enrollment is revoked or deleted, the associated creator embedding must be deleted and subsequent frames must treat the creator as an unknown face.

---

## 11. MVP Non-Goals

The first version does **not** guarantee protection against:

* arbitrary sensitive text;
* arbitrary names;
* arbitrary personally identifying descriptions;
* every possible address representation;
* every possible government identifier;
* every possible phone-number representation;
* every possible email obfuscation;
* biometric identification of arbitrary people;
* identifying relationships between people;
* inferring a person's identity from contextual information;
* deanonymizing people using external databases;
* protection of PII that the configured detectors cannot reliably detect;
* semantic interpretation of all natural-language content;
* protection against malicious adversarial inputs specifically designed to evade detectors.

General text/entity detection is out of scope unless a contextual model is explicitly introduced and added to the supported taxonomy.

---

## 12. Data Exposure Guarantees

The application UI exposes only the minimum metadata needed to communicate protection status.

The UI should expose information such as:

```text
Protected: face
Confidence: high
Status: active
```

It should not expose:

* detected phone numbers;
* email addresses;
* identity numbers;
* raw transcripts;
* OCR text;
* face embeddings;
* raw detector payloads containing PII.

Detector identifiers and technical metadata may be exposed to authorized diagnostics interfaces when necessary.

---

## 13. Product Status Semantics

The privacy pipeline should expose an explicit readiness state.

At minimum:

```text
READY
DEGRADED
UNSAFE
```

### READY

All required protections are available and operating within their configured requirements.

### DEGRADED

One or more optional protections are unavailable or below their configured requirements.

### UNSAFE

One or more required protections cannot guarantee their configured protection.

The streaming/compositor layer must not expose unprotected output while the system is `UNSAFE`.

---

## 14. Product Principle

The primary design principle is:

> When the system cannot establish that required PII protection is working, it must not claim that the media is safe.

The MVP therefore favors conservative protection over maximum media availability.
