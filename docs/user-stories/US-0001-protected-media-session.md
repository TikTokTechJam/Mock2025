# US-0001 — Start a protected media session

## Actor
Creator

## Story
As a creator, I want to start a media session with selected privacy protections so that my outgoing video/audio is processed before it becomes publishable output.

## Value
This is the entry point for the PrivaStream experience. It connects source media, privacy policy, processing, safety readiness, and protected delivery into one user-visible action.

## Acceptance Criteria
- The creator can select camera/microphone or an approved media source.
- The creator can select or accept a privacy policy before starting.
- Required privacy capabilities must report ready before normal protected output is released.
- Video/audio entering the session passes through the configured processing boundary.
- A required processing failure cannot fall back to publishing raw media.
- The creator can stop the session and associated media resources are released.

## Scope
- Session lifecycle and privacy policy selection.
- Source-media timestamps and processing boundaries.
- Integration with protected real-time transport and safety readiness.

## Out of Scope
- User accounts or billing.
- Large-scale multi-viewer distribution.
- Recording/history management unless separately approved.

## Decisions
- Backend privacy readiness is authoritative.
- Raw source media is not a protected-output fallback.
- Media processing and transport remain separate concerns.

## Concerns
- Processing latency can delay session readiness/output.
- WebRTC/browser permissions and network setup may affect startup.
- Required capability selection must remain consistent with fail-closed behavior.

## Status Boundary
The #12 browser client adapter and the in-process #11 production media
integration boundary are Implemented but Unverified. The full protected
session remains Planned until the #13 safety events are bridged through a real
#21/#11 transport sink and an end-to-end protected session is verified.

## Touched By
Issues #2, #3, #4, #11, #12, #13, #17, #21, #22.
