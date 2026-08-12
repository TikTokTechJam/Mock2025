# Testing

## Purpose

This document defines the verification boundary, test levels, isolation requirements, deterministic fixtures, and evidence vocabulary.

## Verification Boundary

A test or check is verification only when it is explicitly requested or part of an approved verification pass. Static inspection, compilation, and a dry run do not prove external safety or complete runtime correctness.

## Test Levels

Define the purpose and boundary of unit, integration, interface, worker, browser, end-to-end, performance, and recovery checks. Keep each level deterministic and avoid duplicating another level's contract.

The spoken-PII unit boundary should cover source-time mapping, silence gating,
spoken phone/email normalization, padding and merging, and PCM16 muting with
synthetic in-memory fixtures. Model inference requires a separate local fixture
or explicitly controlled model pass; it must not use real personal audio.

The timestamped audio-ingestion boundary should use deterministic chunks and
mock VAD/transcriber implementations to cover exact sample-derived end times,
mono normalization and resampling, sequence/timestamp discontinuity, pre/post
roll, bounded long-speech splitting, queue count/duration limits, transcription
deadlines, explicit VAD/transcription failures, and sanitized outcomes. It must
not load Faster-Whisper, Silero, real provider data, or personal audio. The
production integration boundary should additionally cover injection of the
shared text recognizer, segment-only transcript timestamp fallback, source-time
interval mapping, muting across chunk boundaries for supported PCM formats, and
safe/blocked release watermark decisions, including `unsafe_unclassified` when
VAD-positive speech has no usable transcript timestamps.

The privacy-gate unit boundary should use deterministic capability observations
to cover required versus optional failures, missing or pending source
watermarks, configured lag limits, separate process liveness, immediate panic,
explicit exit, consecutive healthy recovery, sanitized reason codes, and
`publish_protected`/`full_redact`/`block` decisions. It must not load media,
detectors, models, transport, or browser clients.

The production media-integration boundary should use the real normalized
`VideoOrchestrator`, `AudioPipeline`, optional `CrossModalSynchronizerAdapter`,
and `PrivacyGate` contracts with deterministic detector/VAD/transcriber doubles.
It should cover source timestamp preservation, protected video/audio delivery,
cross-modal augmentation when enabled, required processor failure, full-redact
silent/full-frame fallback, block behavior, gate ordering, and an injected
`ProtectedMediaSink` that can never receive raw source media. It must not create
a second WebRTC/mediasoup stack or require browser capture, provider data, ML
weights, or a live transport.

The browser media boundary should cover permission denial, successful local
offer/answer and ICE exchange, camera/microphone track return, visible fixed
video redaction, deterministic audio muting, source-clock updates, bounded
frame scheduling, device disconnect, and processor failure without raw-output
fallback. Browser checks require a permission-controlled local browser session;
they are not represented by the API health check.

The creator-console boundary should cover responsive layout, keyboard and label
accessibility, browser permission states, consent-gated enrollment
capture/replace/delete, capability enablement versus server readiness,
connecting/processing/protected/degraded/blocked/panic/stopped/error states,
protected-output stream separation, fail-closed API errors, and sanitized
diagnostics. Adapter tests should inject deterministic fetch and media clients;
browser E2E checks should separately cover controlled camera/microphone
permission and the protected stream. No test should use the unprotected source
as a protected-output fallback or expose raw enrollment/API diagnostics.

The shared video-engine unit boundary should use deterministic mock detectors and
raster fixtures to cover cadence skips, per-detector deadlines, bounded
concurrency, ordered release, explicit timeout/unavailable/invalid/error states,
TTL persistence and expiry, coordinate padding/clamping, overlap merging, and
blur/pixelate/cover/full-frame cover primitives. It must not load face, plate,
OCR, or transport implementations.

The production plate-adapter boundary should use a mocked #19 model and a
deterministic source-image provider to cover source-frame geometry, registration
with `VideoOrchestrator`, exactly-once production padding, successful zero
detections, and propagation of unavailable or execution failures. It must not
require downloaded weights or real media.

The production OCR/visual-PII adapter boundary should use mocked #19 OCR blocks,
the shared #32 recognizer, and a deterministic source-image provider to cover
OCR normalization, sensitive-span-to-block mapping, benign text, registration
with `VideoOrchestrator`, exactly-once production padding, successful zero
detections, and propagation of OCR or recognizer failures. It must not require
downloaded OCR models or real media.

The model-artifact boundary should use temporary local handoff files, archives,
and manifests to cover registration, logical-ID resolution, versioned cache
paths, checksum success, checksum mismatch, missing source, unsupported source
scheme, runtime metadata, safe archive extraction, traversal/link rejection,
extraction limits, and path-safe metadata. It must not download a production
weight or contact an external model provider during ordinary unit coverage.

The standalone face unit boundary should use deterministic model doubles to
cover explicit consent, zero-face and multi-face enrollment rejection,
normalization and aggregate replacement, deletion, creator matches, unknown or
ambiguous matches, low-quality and failed embeddings, coordinate clamping, and
explicit model errors. It must not require InsightFace weights or retain raw
face images.

The offline benchmark boundary should use normalized synthetic or authorized
labels and predictions to cover IoU matching, confidence-threshold precision
and recall, privacy-critical misses, 101-point AP at the standard IoU profile,
deterministic latency percentiles, FPS, cold-start separation, provenance, and
JSON/Markdown report output. It must not load models, contact providers, or
persist raw media or unnecessary PII.

The deployment-packaging boundary should use a clean checkout and controlled
Docker/Compose environments to cover CPU image builds, health-gated startup,
model-cache persistence across API restarts, API-origin build configuration,
loopback port binding, and the NVIDIA device reservation override when a
compatible host is available. It must not treat process health as privacy
readiness, require a server WebRTC implementation owned by #21, or publish
credentials and model weights in images or logs.

The production face-integration boundary should use the real #18 public
interfaces with deterministic model doubles to cover #4 registration, canonical
`face_bystander` regions, creator suppression, process-local create/replace/
delete lifecycle, readiness transitions, detector-unavailable/error propagation,
bounded multipart enrollment, safe response fields, and default-deny route
authorization. It must not duplicate face matching or require model weights,
real media, raw images, or an external database.

The cross-modal synchronization unit boundary should use deterministic
source-timestamped frames, audio intervals, and normalized face geometry to
cover interval indexing and de-duplication, pre/post padding, bounded lookahead,
single-face mouth/lower-face derivation, unique active-speaker selection,
ambiguous multi-face full-face fallback, missing-face unsafe results, buffer
overflow, timestamp discontinuity, late audio decisions, flush behavior, and
sanitized buffer-delay/decision-lag metrics. It must not load detectors,
transcribers, models, transport, compositor payloads, or real media.

## Isolation

Use dedicated data, resources, credentials, and controlled dependencies for tests that can mutate state or contact external systems. Reset safely and prevent accidental actions outside the test boundary.

## Fixtures

Keep fixtures minimal, deterministic, versioned, ownership-aware, and free of secrets or unnecessary personal data. Mock or simulate external behavior when the test does not require a real provider.

## Evidence

Record the command or pass, scope, environment, result, artifacts, limitations, and unverified areas. Do not call behavior Verified without evidence from the requested pass.
