# Product

## Purpose

PrivaStream is a privacy-first media processing platform for creators. Its
planned outcome is a protected video and audio stream or recording in which
configured privacy-sensitive content is redacted before delivery.

## Current capabilities

| Capability | Entry point | Current result | Availability | Verification |
| --- | --- | --- | --- | --- |
| Browser media loopback demo | `GET /` on the web app | Requests camera/microphone access, sends the capture through a local WebRTC loopback, applies deterministic mock video/audio processing, and attaches only the processed tracks to the protected preview. | Implemented | Unverified |
| API process health | `GET /health` | Returns `{ "status": "ok", "service": "privastream-api" }`. | Implemented | Unverified |
| Standalone spoken-PII demo | `python -m privastream_api.pipeline.spoken_pii` | Accepts a bounded PCM16 WAV and writes a copy with detected phone-number and email intervals muted. | Implemented | Unverified |

The HTTP product surface does not accept media. The browser demo captures media
locally and uses browser APIs for its loopback; it does not upload media to the
API or provide a server-side live transport. The standalone demo accepts local
PCM16 audio in memory, runs local speech detection and transcription, and
renders a local muted copy. Neither path stores media as product state.

## Planned creator journey

1. A creator selects a live or recorded media source and a privacy policy.
2. PrivaStream runs the configured face, license-plate, OCR, and spoken-PII
   detectors independently.
3. Normalized detector results are coordinated across time and passed to a
   redaction compositor.
4. The creator inspects and controls the protected preview or output.

The local capture and protected-preview portion is Implemented through the
browser media loopback demo. Policy selection, real detectors, temporal
coordination, and protected delivery beyond that local preview are Planned.

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

Authentication, creator enrollment, HTTP media upload, server-side or
production live transport, face and license-plate detection, OCR, cross-modal
synchronization, persistence, and production deployment are not implemented
here. The browser loopback and spoken-PII demo use deterministic/local mock or
best-effort processing; neither claims complete privacy coverage, model
accuracy, latency, or future delivery outcomes.
