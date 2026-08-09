# US-0008 — Inspect protected live preview and readiness

## Actor
Creator

## Story
As a creator, I want to see the protected output and the readiness of each enabled privacy capability so that I know whether the stream is safe before relying on it.

## Value
Privacy controls are only trustworthy when the creator can distinguish source media from processed output and can see when required protections are unavailable.

## Acceptance Criteria
- The creator can see a clearly labeled protected-output preview.
- Any local raw preview is clearly labeled as unprotected and is never used as protected fallback.
- Capability states come from backend readiness, not from UI toggle state alone.
- Required unavailable capabilities prevent the UI from claiming the session is protected.
- Connecting, processing, protected, degraded, blocked, panic, and stopped states are distinguishable.
- Sanitized failure reasons can be shown without exposing transcripts, PII values, or embeddings.
- Camera/microphone permission and source-selection failures are represented clearly.

## Scope
- Creator console, device controls, protected media client, readiness/status panel, capability controls, and session-state UX.

## Out of Scope
- General analytics dashboard.
- Account/admin management.
- Raw PII diagnostics.

## Decisions
- Backend readiness is authoritative.
- The protected preview accepts only the protected stream returned by the real-time transport.
- Privacy capability availability controls what the UI may present as enabled.

## Concerns
- UI state can become misleading if transport and readiness events are not synchronized.
- Raw local preview must be visually distinct to avoid accidental interpretation as protected output.

## Status Boundary
The #12 client adapter and #11 in-process gate-to-protected-output integration
boundary are Implemented but Unverified. The protected preview attaches only a
returned protected stream, while unavailable readiness/safety/media boundaries
remain blocked. This product story remains Planned until real-time protected
transport and readiness/safety APIs are integrated and verified.

## Touched By
Issues #2, #3, #5, #11, #12, #13, #17, #21, #22.
