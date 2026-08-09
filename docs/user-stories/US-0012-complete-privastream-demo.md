# US-0012 — Run the complete PrivaStream demonstration

## Actor
Creator / demo operator

## Story
As a creator or demo operator, I want one reproducible end-to-end demonstration of PrivaStream so that I can prove the core privacy experience works through the actual browser, transport, processing, safety, and protected-output path.

## Value
The individual detectors are not sufficient evidence that the product works. The final story validates the integrated experience and provides one canonical reproduction path for the project.

## Acceptance Criteria
- A documented clean-checkout path starts the implemented stack and waits for privacy readiness.
- The creator completes enrollment through the user-facing flow.
- Protected output is delivered through the actual real-time media path.
- A controlled scenario demonstrates creator visibility and bystander protection.
- A visible plate is protected.
- Visible synthetic email/phone PII is protected.
- Spoken synthetic email/phone PII is muted.
- Synchronized visual protection is demonstrated during sensitive speech when enabled.
- Panic mode fully protects video/audio.
- An induced required-processor failure demonstrates fail-closed behavior with no raw fallback.
- Recovery follows the central safety gate rules.
- The run records sanitized readiness/performance evidence and cleans session resources on stop.

## Scope
- Deterministic fixture mode, live camera/mic demo mode, browser automation/control, media-output assertions, failure injection, coverage documentation, and canonical README instructions.

## Out of Scope
- Production-scale traffic/load demonstration.
- Claiming all original PrivaStream performance/accuracy numbers have been reproduced unless compatible benchmarks prove it.

## Decisions
- E2E assertions must inspect protected media behavior, not only UI labels.
- Synthetic/test PII is used for deterministic fixtures.
- The demo follows the same privacy pipeline as ordinary live sessions.

## Concerns
- Browser/WebRTC automation and media capture can be environment-sensitive.
- Deterministic fixtures must remain licensed/safe and small enough to manage.

## Status Boundary
The #12 browser client and #11 in-process integration boundaries are Implemented
but Unverified. This final integration story remains Planned until the
documented end-to-end scenario passes through the real #13 safety and #21/#11
protected media paths.

## Touched By
Issues #1, #2, #5, #6, #7, #9, #10, #11, #12, #13, #15, #16, #17.
