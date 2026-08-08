# Product

## Purpose

PrivaStream is a privacy-first media processing platform for creators. Its
planned outcome is a protected video and audio stream or recording in which
configured privacy-sensitive content is redacted before delivery.

## Current capabilities

| Capability | Entry point | Current result | Availability | Verification |
| --- | --- | --- | --- | --- |
| Foundation landing page | `GET /` on the web app | Identifies PrivaStream and explains that media controls are not available yet. | Implemented | Unverified |
| API process health | `GET /health` | Returns `{ "status": "ok", "service": "privastream-api" }`. | Implemented | Unverified |
| Standalone spoken-PII demo | `python -m privastream_api.pipeline.spoken_pii` | Accepts a bounded PCM16 WAV and writes a copy with detected phone-number and email intervals muted. | Implemented | Unverified |

The HTTP product surface does not accept media. The standalone demo accepts
local PCM16 audio in memory, runs local speech detection and transcription, and
renders a local muted copy. It does not store or transport media.

## Planned creator journey

1. A creator selects a live or recorded media source and a privacy policy.
2. PrivaStream runs the configured face, license-plate, OCR, and spoken-PII
   detectors independently.
3. Normalized detector results are coordinated across time and passed to a
   redaction compositor.
4. The creator inspects and controls the protected preview or output.

This journey is Planned. The current UI and API do not expose these actions.

## Privacy and safety boundaries

- The privacy policy is the primary invariant: a required detector failure must
  not be represented as a safe result.
- Raw media and biometric data must not be retained unless a later approved
  contract requires it.
- Model-specific outputs are not a product contract; detector modules return
  normalized video regions or audio intervals.
- The current scaffold makes no claim about privacy coverage, latency, accuracy,
  delivery, or end-to-end protection.

## Non-goals for this foundation

Authentication, creator enrollment, HTTP media upload, live transport, face and
license-plate detection, OCR, cross-modal synchronization, persistence, and
production deployment are not implemented here. The spoken-PII demo is a local
standalone capability; it does not claim complete privacy coverage, model
accuracy, latency, or future delivery outcomes.
