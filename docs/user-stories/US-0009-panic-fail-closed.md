# US-0009 — Trigger panic mode and fail closed

## Actor
Creator

## Story
As a creator, I want PrivaStream to immediately hide/mute output when privacy protection becomes unsafe, and I want a panic control I can trigger manually, so that failures do not expose raw media.

## Value
Fail-closed behavior is the main safety invariant of a privacy-first media system.

## Acceptance Criteria
- The creator can enter panic mode immediately during an active session.
- Panic video becomes fully obscured/blocked without relying on ML detectors.
- Panic audio becomes silent/blocked without relying on transcription/classification.
- Required detector/model/queue/timestamp/processor failures prevent normal protected publication.
- A media window cannot be released before required processors have safely covered that window.
- Leaving panic mode requires explicit action and healthy required capabilities.
- Recovery uses deterministic hysteresis rather than immediately trusting one successful check.
- Process health and privacy readiness are exposed as different concepts.

## Scope
- Central privacy gate, capability readiness, publication decisions, panic controls, safe fallback rendering, recovery rules, and sanitized status events.

## Out of Scope
- Security incident response outside the media session.
- Manual restoration that bypasses required privacy policy.

## Decisions
- One centralized privacy gate owns publication decisions.
- Failure is never represented as an empty successful detection.
- Transition toward unsafe is immediate; recovery is conservative.

## Concerns
- Every processor must report accurate source-time watermarks and failure states.
- A hidden raw-media bypass would violate this story even if ordinary UI paths are safe.

## Status Boundary
The #12 safety adapter applies local emergency stop behavior and maps the
planned #13 server boundary fail-closed; the #11 integration applies the #13
decision in-process. These boundaries are Implemented but Unverified. This
safety story remains Planned until #13 panic events are bridged through the
real protected-output path and induced-failure scenarios are demonstrated.

## Touched By
Issues #3, #4, #8, #9, #10, #11, #12, #13, #16, #17, #21, #22.
