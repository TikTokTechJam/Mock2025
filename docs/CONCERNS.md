# Current Concerns

## Purpose

Record only unresolved current risks, limitations, assumptions, verification gaps, and decisions that affect safe operation or accurate understanding.

## Concern Entry

For each concern, record:

- Statement of the unresolved issue.
- Affected boundary or owner.
- Impact and likelihood when known.
- Current mitigation or constraint.
- Evidence and verification state.
- Decision or next action.
- Owner and review condition.

## Boundaries

Do not use this document as a backlog, completion diary, issue mirror, speculative roadmap, or duplicate domain contract. Remove a concern when it is resolved, or replace it with the new current rule in the owning document.

## Status

A concern may explain why a capability remains Planned, Unresolved, or Unverified. It must not change the meaning of the independent availability and verification vocabulary.

## Current concerns

- The timestamped spoken-PII pipeline has no runtime verification yet. Model
  accuracy, source-timeline quality across resampling, CPU/memory cost, queue
  lag, and behavior on accents, noise, overlap, and non-English speech remain
  Unverified. The current mitigation is explicit model/VAD configuration,
  bounded normalization and transcription queues, sanitized unsafe statuses,
  no transcript logging, source-chunk muting across interval boundaries, and a
  dependency-free energy-VAD baseline. Shared-recognizer integration,
  segment-only timestamp fallback, release watermark/lag, and chunk-boundary
  protection still require an explicit runtime pass.

- The shared text-PII recognizer has deterministic email/phone coverage and
  explicitly configured identity/payment formats, but postal-address and other
  contextual categories have only a replaceable classifier boundary. No
  contextual classifier is bundled by default, so language coverage and
  contextual accuracy remain Unverified. A successful empty result must not be
  used as evidence that unsupported contextual PII is absent.
- The local demo has no fail-closed delivery boundary or creator review step.
  A muted output must not be treated as proof of complete privacy coverage.
- The browser media loopback has not received a browser verification pass.
  Permission behavior, WebRTC support, audio autoplay, device disconnect, and
  processor failure handling remain Unverified. The current mitigation is a
  local-only boundary, explicit session error state, bounded video scheduling,
  and no raw-output fallback.
- The creator console production adapters are not runtime verified. The default
  API denies face control authorization, and the browser-to-transport bridge for
  #13 safety events is not connected, so the console remains blocked on that
  boundary. The current mitigation is fail-closed state mapping, explicit
  consent gating, no raw diagnostics, protected-stream-only preview attachment,
  and a separate unprotected source preview.
- The web-to-API deployment origin and credential/CORS boundary is not defined.
  `NEXT_PUBLIC_API_BASE_URL` is configurable for local routing, but it does not
  supply authorization or make cross-origin requests trusted. The current
  mitigation is deny-by-default API authorization and blocked client state.

- The shared video engine has not received a runtime verification pass. Detector
  deadline behavior, queue backpressure, temporal association/expiry, and
  raster compositor output remain Unverified. The current mitigation is
  dependency-free deterministic mock-detector and raster-fixture coverage,
  explicit sanitized failure states, bounded concurrency, and no automatic
  full-frame fallback decision.
- The centralized privacy gate has not received a runtime or protected-output
  integration pass. Required/optional policy evaluation, source watermark and
  lag coverage, liveness transitions, panic recovery hysteresis, and consumer
  behavior remain Unverified. The current mitigation is deterministic unit
  coverage, sanitized reason codes, fail-closed fallback/block decisions, and
  the #11 adapter's gate-before-sink ordering; no server transport can bypass
  the gate because that sink is not wired yet.
- The production plate adapter has not received a runtime model or integration
  pass. Its source-image provider, local weight configuration, and interaction
  with the safety gate/model artifact resolver remain environment and
  follow-up concerns. The current mitigation is a thin normalized adapter,
  exactly-once shared padding, explicit scheduler failures, and deterministic
  mocked integration coverage.
- The production OCR/visual-PII adapter has not received a runtime OCR-model or
  integration pass. OCR image-provider compatibility, block-level mapping,
  contextual-recognizer availability, and interaction with the future safety
  gate remain Unverified. The current mitigation is reuse of the shared
  recognizer, conservative whole-block mapping, exactly-once shared padding,
  explicit scheduler failures, and deterministic mocked integration coverage.
- The standalone face module has not received a real-model verification pass.
  InsightFace model-pack availability, ArcFace threshold calibration, pose and
  lighting robustness, and local blur quality remain Unverified. The current
  mitigation is explicit local-model configuration, deterministic model doubles,
  conservative unknown/ambiguous protection, bounded enrollment samples, and no
  embedding or raw-image logging.
- The production face adapter and control routes have not received an integration
  or runtime verification pass. The process-local repository, injected creator
  authorization, model-pack availability, readiness handoff to #13, and shared
  scheduler behavior remain Unverified. The current mitigation is a thin
  adapter over #18, default-deny route authorization, sanitized status/error
  codes, and deterministic integration fixtures.
- The cross-modal synchronizer has no dedicated runtime or end-to-end
  verification pass. Source-clock alignment, active-speaker hints, face-box
  lower-face precision, bounded lookahead under real transcription latency, and
  integration with the #13 publication gate remain Unverified. The current
  mitigation is a dependency-free bounded source-time coordinator, conservative
  all-face fallback for ambiguous scenes, explicit unsafe late/overflow/
  discontinuity outcomes, sanitized aggregate metrics, and no transport path
  that can bypass final safety policy.
- The production media integration adapter has no runtime or protected-output
  verification pass. Its processor failure handling, source timestamp
  continuity, optional cross-modal handoff, fallback silence/full-cover output,
  and sink ordering remain Unverified. The current mitigation is a narrow
  injected-sink contract, deterministic integration fixtures, no raw-media
  fallback, and an explicit boundary that leaves server transport Planned.
