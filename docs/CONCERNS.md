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

- The spoken-PII module has no runtime verification yet. Model accuracy,
  timestamp quality, CPU/memory cost, and behavior on accents, noise, overlap,
  and non-English speech remain Unverified. The current mitigation is explicit
  model/VAD configuration, bounded input, no transcript logging, and a
  dependency-free energy-VAD baseline.
- The local demo has no fail-closed delivery boundary or creator review step.
  A muted output must not be treated as proof of complete privacy coverage.
- The browser media loopback has not received a browser verification pass.
  Permission behavior, WebRTC support, audio autoplay, device disconnect, and
  processor failure handling remain Unverified. The current mitigation is a
  local-only boundary, explicit session error state, bounded video scheduling,
  and no raw-output fallback.
- The shared video engine has not received a runtime verification pass. Detector
  deadline behavior, queue backpressure, temporal association/expiry, and
  raster compositor output remain Unverified. The current mitigation is
  dependency-free deterministic mock-detector and raster-fixture coverage,
  explicit sanitized failure states, bounded concurrency, and no automatic
  full-frame fallback decision.
