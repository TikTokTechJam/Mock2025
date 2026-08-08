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
- The creator console uses deterministic local façades rather than backend
  enrollment, readiness, safety, or authorization clients. Its state transitions,
  accessibility behavior, protected-handle separation, and responsive layout
  remain Unverified. The current mitigation is explicit mock labeling, consent
  gating, no raw diagnostics, required-readiness blocking, and a separate
unprotected source preview.

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
  no transport integration that could bypass the gate.
- The production plate adapter has not received a runtime model or integration
  pass. Its source-image provider, local weight configuration, and interaction
  with the safety gate/model manifest resolver remain environment and
  follow-up concerns. The current mitigation is a thin normalized adapter,
  exactly-once shared padding, explicit scheduler failures, and deterministic
mocked integration coverage.
- The standalone face module has not received a real-model verification pass.
  InsightFace model-pack availability, ArcFace threshold calibration, pose and
  lighting robustness, and local blur quality remain Unverified. The current
  mitigation is explicit local-model configuration, deterministic model doubles,
  conservative unknown/ambiguous protection, bounded enrollment samples, and no
  embedding or raw-image logging.
