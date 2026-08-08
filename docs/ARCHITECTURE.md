# Architecture

## Purpose

This document owns the current repository topology, component responsibilities,
process boundaries, dependencies, and data flows.

## Current repository topology

- `apps/web` is the Next.js App Router browser and creator UI. Its current page
  contains the browser-local media loopback and mock processing path.
- `apps/api` is the FastAPI control-plane foundation. It exposes `GET /health`
  and contains normalized media contracts, standalone visual-privacy adapters
  under `src/privastream_api/privacy/vision`, the model-agnostic video
  orchestrator/compositor under `src/privastream_api/pipeline/video.py`, and the
  in-process spoken-PII demo under `src/privastream_api/pipeline/`.
- `models/` contains runtime model metadata and the future manifest boundary;
  it is not a model server and must not contain downloaded weights.
- `ml/` contains offline training, fine-tuning, and evaluation tooling. Runtime
  API code must not import training-only dependencies by default.
- `datasets/` contains safe dataset manifests, schemas, split metadata, and
  provenance; raw or private datasets are not part of the repository.
- `docs/` contains the authoritative product, architecture, security,
  operations, and current-state documentation.
- `compose.yaml` defines the local development topology:
  - `web` serves the Next.js development server on port 3000;
  - `api` serves FastAPI on port 8000; and
  - `db` runs PostgreSQL on port 5432.
- `apps/api/Dockerfile.dev` and `apps/web/Dockerfile.dev` provide development
  images with mounted source trees and persistent dependency volumes.

The standalone plate/OCR module, shared video orchestrator/compositor, spoken-
PII detector, and local PCM16 renderer are implemented inside the API package
but are not exposed through the HTTP product surface. The browser-local loopback
is implemented without an API dependency. No cross-modal redaction policy,
server-side real-time media transport, persistence layer, worker, provider
integration, or E2E runtime boundary exists yet. `apps/` contains only runnable
application boundaries; there is no separate model/inference service.

## Runtime boundaries

| Boundary | Responsibility | Availability |
| --- | --- | --- |
| Browser/creator UI | Request local camera/microphone access, manage the demo session, and show source plus protected-preview tracks. | Implemented browser demo; broader creator controls Planned |
| API/control plane | Own future sessions, privacy policies, pipeline lifecycle, and authorization. The current route only reports process liveness. | Implemented foundation; product operations Planned |
| Media processing/inference | Run normalized detector adapters, temporal region coordination, and generic video composition in-process with the API until GPU/runtime isolation requires a separate process. Cross-modal policy and product publication remain outside this boundary. | Implemented video engine and adapters; product pipeline Planned |
| Real-time media transport | Move live media and protected output without coupling transport to a detector implementation. The current browser baseline uses a same-page WebRTC loopback; server-side and production transport remain absent. | Implemented browser baseline; broader transport Planned |
| Persistence/configuration | Store only the configuration and lifecycle state later approved for persistence. PostgreSQL is provisioned locally but unused. | Planned |

The design starts in-process. A separate service or worker requires a concrete
runtime or GPU dependency; conceptual separation alone is not a reason to add
one.

## Processing flow

```mermaid
flowchart LR
    A[Live or recorded media] --> B[Transport adapter]
    B --> C[Pipeline orchestrator]
    C --> D[Face detector]
    C --> E[License-plate detector]
    C --> F[OCR detector]
    C --> G[Audio PII detector]
    D --> H[Normalized detections]
    E --> H
    F --> H
    G --> H
    H --> I[Privacy policy and temporal coordination]
    I --> J[Redaction compositor]
    J --> K[Protected output]
```

The intended flow is:

1. A future browser or transport adapter supplies live or recorded media.
2. The in-process orchestrator sends video frames and audio segments to
   independent detector modules.
3. Detectors return model-neutral results defined by the API contract module.
4. A future policy layer applies whitelist, redaction, temporal-stability, and
   fail-closed rules.
5. The shared video compositor creates a `ProtectedVideoFrame`; a future
   transport and publication-safety layer decide how protected output is
   delivered.

### Current shared video engine

The implemented model-agnostic video path is:

```mermaid
flowchart LR
    A[VideoFrame] --> B[VideoOrchestrator]
    B --> C[Registered detector adapters]
    C --> D[Validated VideoPrivacyRegion values]
    D --> E[Temporal TTL and spatial association]
    E --> F[Padding, clamping, and conservative merge]
    F --> G[VideoCompositor]
    G --> H[ProtectedVideoFrame]
```

The orchestrator schedules detectors at configured cadence, applies per-detector
deadlines and concurrency limits, preserves temporal masks across skipped or
failed detector frames until TTL expiry, and releases completed frames in input
order. Detector failures remain explicit in the output metadata. The compositor
provides blur, pixelate, solid cover, and full-frame safe-cover primitives; the
central safety gate still owns whether a frame may be published.

### Current browser loopback path

The current browser demo provides the smallest transport-independent media path:

```mermaid
flowchart LR
    A[getUserMedia camera and microphone] --> B[Local WebRTC sender]
    B --> C[Local WebRTC receiver]
    C --> D[Remote media tracks]
    D --> E[Canvas mock video redaction]
    D --> F[Web Audio deterministic mute transform]
    E --> G[Processed video track]
    F --> H[Processed audio track]
    G --> I[Protected preview MediaStream]
    H --> I
```

The sender and receiver are separate `RTCPeerConnection` objects in the same
browser page, with offer/answer and ICE candidate exchange performed locally.
The incoming tracks are the processing boundary: video is rendered through a
canvas with a fixed center redaction region, and audio passes through a gain
node that mutes a fixed 500 ms interval every 2 seconds. The output preview is
created only after both processed tracks exist; capture tracks are never used as
the output preview source.

The browser controller exposes each processed video frame's source timestamp
from the media callback when available, with a monotonic capture-clock fallback,
for later detector and A/V integration. Its single-frame scheduling loop has at
most one pending frame, so a slow draw cannot build an unbounded queue. A device
disconnect, transport failure, or processor failure stops the session and leaves
the output detached instead of falling back to raw media.

The browser foundation, browser-local loopback, API process-health route, local
Compose topology, and standalone plate/OCR and spoken-PII audio paths are
present. Shared orchestration, cross-modal policy, redaction output, server-side
live transport, compositor, and protected delivery beyond the local preview
remain Planned.

## Detector and redaction contracts

`privastream_api.pipeline.contracts` is the shared boundary for independent
detector work:

- `VideoRegionDetection` represents a face, license-plate, OCR, email, or phone result with
  normalized `x`, `y`, `width`, and `height` coordinates in the inclusive
  `[0, 1]` frame space, a confidence, a frame timestamp, and an optional track
  identity.
- `VideoFrame` is the canonical source-frame envelope. Its optional payload is
  kept opaque to detector adapters; the dependency-free compositor accepts its
  `RasterFrame` adapter surface.
- `VideoPrivacyRegion` is the validated, padded, clamped, TTL-bearing region
  retained by the shared video engine. `ProtectedVideoFrame` carries ordered
  output, active regions, sanitized detector runs, and render status without
  claiming publication safety.
- `AudioRedactionInterval` represents a time-based spoken-PII redaction with
  millisecond start and end offsets, confidence, detector identity, and an
  optional reason.
- `FaceDetector`, `LicensePlateDetector`, and `OcrDetector` each accept a
  `VideoFrame` and return normalized `VideoRegionDetection` values.
- `AudioPiiDetector` accepts an `AudioSegment` and returns normalized
  `AudioRedactionInterval` values.
- `SpokenPiiDetector` implements the audio detector boundary by composing a
  bounded VAD, a local word-timestamp transcriber, structured phone/email
  matching, configurable safety padding, and adjacent-interval merging.
- `EnergyVoiceActivityDetector` is the dependency-free baseline; the optional
  `SileroVoiceActivityDetector` uses the Silero adapter without changing the
  normalized contract. `FasterWhisperTranscriber` is loaded lazily so the API
  health process does not load an ML model.
- The local renderer accepts PCM16 WAV input and mutes only normalized source
  time intervals. It does not expose model-specific transcript output.

The standalone plate/OCR adapters use a `FrameContext` containing source image
data and `VideoFrame` metadata, then emit the same normalized result type.

Detector implementations must not expose model-specific boxes, timestamps, or
labels beyond these contracts. The compositor consumes normalized values; it
does not import a detector implementation. A timeout, unavailable detector,
invalid result, or execution error is recorded explicitly and is never converted
to a successful empty detection.

## Failure boundaries and privacy invariant

The target processing pipeline fails closed: if a detector required by the
active privacy policy cannot make a safe decision, the protected output is held
or redacted rather than released as if it were safe. The standalone adapters
surface detector failures, but the shared fail-closed output policy is Planned
and is not implemented by the current HTTP scaffold.

## Dependencies and verification

The frontend depends on Node.js and pnpm. The API depends on CPython 3.14 and
uv. Docker Compose supplies the local process and PostgreSQL boundaries.
Compose healthchecks cover process liveness only; they do not prove product
readiness, detector accuracy, redaction correctness, or transport readiness.

The foundation, normalized contracts, shared video engine, standalone
visual-privacy adapters, spoken-PII detector baseline, local renderer, and
browser-local loopback are Implemented in source. Runtime verification is
Unverified; the orchestration tests, browser path, audio and visual demos,
real-model inference, and application verification have not been exercised.
