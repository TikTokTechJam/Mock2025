# Continuity

## Current Snapshot

The working tree contains the PrivaStream web and API foundation, normalized
video/audio detector contracts, the shared text-PII recognizer, standalone
plate/OCR visual-privacy and spoken-PII detector/renderer modules, production
plate and OCR/visual-PII adapters, a timestamped audio ingestion/transcription
pipeline, standalone face enrollment/matching, production face integration and
protected enrollment/readiness routes, and a FastAPI process-health route, a
browser-local WebRTC loopback with mock video/audio
processors, and a local PostgreSQL-backed Compose topology. The model-agnostic
shared video orchestrator and compositor are implemented as an internal API
pipeline, the cross-modal synchronization primitive and centralized privacy
readiness/publication gate are present, and the creator-console mock shell is
present. The production privacy-media integration adapter now coordinates the
processors and gate through a protected-output sink contract. Product-surface
media ingestion, UI wiring, backend creator operations beyond protected face
controls, server-side transport, durable persistence, and E2E infrastructure
remain absent.

## Active Work

- Review the creator-console mock contract and prepare an explicit UI/browser
  verification pass.
- Wire the authorized #12 client to the protected face enrollment/readiness
  routes after the authentication and safety boundaries are available.
- Review the centralized privacy gate and timestamped audio, face, shared
  text-PII, and cross-modal paths and prepare explicit focused verification
  passes.
- Review the production media integration adapter with a dedicated protected-
  output verification pass before wiring a real transport sink.

## Current Blockers

- The creator console, browser media path, and local audio path have not received
  dedicated runtime verification passes; UI/device support is therefore
  Unverified.
- The shared video engine has not received a dedicated orchestration or raster
  compositor verification pass.
- The centralized privacy gate has not received a dedicated state-transition or
  protected-output integration verification pass, and no transport consumes its
  decisions yet.
- The timestamped audio pipeline has not received a dedicated streaming,
  model, or failure-injection verification pass. Shared-recognizer integration,
  source-chunk muting, and release watermark behavior are also Unverified.
- The standalone face module has not received a real-model or local-runner
  verification pass.
- The production face adapter, control routes, authorization injection, and
  readiness handoff to #13 have not received a runtime integration pass.
- The cross-modal synchronizer has not received a dedicated source-timeline or
  integration verification pass. The #11 adapter consumes its decisions
  in-process, but no server transport uses them.
- The production media integration adapter has not received a runtime or
  protected-output verification pass. The server-side transport sink remains
  absent, so no live media path consumes its output.

## Verification Status

| Area | Availability | Verification | Note |
| --- | --- | --- | --- |
| Creator privacy console shell and mock façades | Implemented | Unverified | Responsive UI with mock media, enrollment, readiness, and safety clients; no UI/browser pass run. |
| Browser media loopback and mock processors | Implemented | Unverified | Local WebRTC path with canvas/gain processing; no browser pass run. |
| Backend foundation and `/health` | Implemented | Unverified | FastAPI process-health route; no runtime pass run. |
| Normalized media contracts | Implemented | Not applicable | Dependency-free detector protocols and result types used by the standalone visual module. |
| Shared video orchestration and compositor | Implemented | Unverified | Cadence, deadlines, bounded concurrency, temporal TTL, normalized composition, and deterministic unit fixtures; no verification pass run. |
| Centralized privacy readiness/publication gate | Implemented | Unverified | Required/optional policy, watermark/lag coverage, liveness, panic, conservative recovery, sanitized decisions; no integration pass run. |
| Production privacy-media integration adapter | Implemented | Unverified | Coordinates video/audio, optional cross-modal augmentation, gate decisions, fail-closed fallback, and protected sink ordering; no runtime or transport pass run. |
| Shared text-PII recognizer | Implemented | Unverified | Deterministic email/phone matching, configured identity/payment formats, contextual classifier boundary, and modality integrations; no verification pass run. |
| Standalone face enrollment and matching | Implemented | Unverified | Explicit consent, in-memory aggregate enrollment, conservative matching, normalized bystander regions, and deterministic model doubles; no real-model pass run. |
| Standalone plate/OCR module | Implemented | Unverified | Optional-model adapters, deterministic recognizers, and local demo; no real-model pass run. |
| Production plate adapter | Implemented | Unverified | Reuses source-frame plate inference and registers with the shared scheduler; no model or integration pass run. |
| Production OCR/visual-PII adapter | Implemented | Unverified | Reuses OCR blocks and the shared text-PII recognizer, then registers source-frame regions; no model or integration pass run. |
| Timestamped audio pipeline and spoken-PII renderer | Implemented | Unverified | Bounded chunk normalization, VAD segmentation, transcription queue, interval mapping, and PCM16 muting; no streaming or model pass run. |
| Timestamped audio pipeline and spoken-PII renderer | Implemented | Unverified | Bounded chunk normalization, VAD segmentation, shared text-PII interval mapping, source-chunk muting, and release watermark/lag; no streaming or model pass run. |
| Production face adapter, enrollment repository, and readiness routes | Implemented | Unverified | Delegates to #18, supports process-local create/replace/delete, preserves scheduler failures, and defaults API authorization to deny; no integration pass run. |
| Spoken-PII detector and PCM16 renderer | Implemented | Unverified | Local VAD/transcription/pattern/interval/muting path; no model or audio pass run. |
| Cross-modal spoken-PII visual synchronizer | Implemented | Unverified | Bounded source-time lookahead, interval indexing, padding, face association/fallback, unsafe late/overflow/discontinuity outcomes, and sanitized metrics; no dedicated pass or transport integration run. |
| Local Compose topology | Implemented | Unverified | `web`, `api`, and PostgreSQL services; Compose was not started. |

## Next Actions

1. Request a dedicated creator-console UI/browser verification pass with
   keyboard, responsive, mock-state, and protected-handle scenarios.
2. Request a dedicated privacy-gate verification pass with deterministic
   capability observations, liveness, panic, watermark, lag, and recovery
   scenarios.
3. Request a dedicated video-engine verification pass with deterministic mock
   detectors, timeout/failure injection, and raster fixtures.
4. Request a dedicated timestamped-audio verification pass with deterministic
   chunks, mock VAD/transcription, shared-recognizer integration,
   chunk-boundary muting, release watermark, queue overflow, deadline, and
   failure cases.
5. Request a dedicated browser media verification pass with controlled camera
   and microphone permissions, including disconnect and failure scenarios.
6. Request a dedicated face, visual, and audio verification pass with controlled
   local fixtures and models when runtime checks are wanted.
7. Provide the approved authorization provider, durable repository contract, and
   #21 server transport sink before wiring the face control surface or protected
   media integration into the creator UI or live media transport.
8. Add the next approved privacy/media lifecycle contract before exposing the
   remaining standalone detectors through server transport or creator controls.

## Handoff Constraints

- Keep backend creator operations, server-side transport, persistence, provider
  integrations, workers, and E2E boundaries outside the console mock, browser-
  local demo, and standalone detector modules.
- Preserve the documented verification boundary and do not claim runtime
  verification without an explicit pass.
- Keep detector modules behind normalized contracts and keep media transport
  independent from detector implementations.
