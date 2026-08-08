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
| Standalone visual privacy demo | `apps/api/scripts/vision_demo.py` | Processes a local image or short video with plate and OCR/PII adapters when optional dependencies and local weights are supplied. | Implemented | Unverified |
| Standalone spoken-PII demo | `python -m privastream_api.pipeline.spoken_pii` | Accepts a bounded PCM16 WAV and writes a copy with detected phone-number and email intervals muted. | Implemented | Unverified |

The HTTP product surface does not accept media. The standalone demos process
local image/video or PCM16 audio inputs, run their local detectors, and render
local protected copies. They do not store or transport media.

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

Authentication, creator enrollment, product-surface media upload, live
transport, face detection integration, cross-modal synchronization, shared
redaction compositing, persistence, and production deployment are not
implemented here. The standalone plate/OCR and spoken-PII demos are
intentionally not user-facing or real-time product capabilities; they do not
claim complete privacy coverage, model accuracy, latency, or future delivery
outcomes. Each next capability requires an approved contract and its owning
documentation.
