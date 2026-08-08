# End-to-End Coverage

## Purpose

Map complete user and system journeys across the real boundaries that the isolated environment is intended to exercise.

## Coverage Map

For each journey, record the starting state, actions, expected visible results, API or worker effects, ownership checks, error paths, recovery path, and current verification status.

The standalone spoken-PII demo journey is Implemented but Unverified: bounded
PCM16 input → source-timestamped `AudioChunk` → mono/model-rate normalization →
bounded VAD ring buffer and speech segments → local word-timestamp transcription
→ phone/email interval normalization → padded/merged intervals → muted PCM16
output.
The coverage target includes silence-only input, a representative phone number,
a representative email address, source timestamps offset from zero, invalid
audio, timestamp discontinuity, queue overflow, deadline lag, and a
model/dependency failure without logging transcript text.

The browser media loopback journey is Implemented but Unverified: local camera /
microphone permission → WebRTC offer/answer and ICE exchange → returned remote
tracks → canvas video redaction and Web Audio mute transform → processed
protected preview. The coverage target includes permission denial, successful
session startup, source timestamp updates, visible fixed-region redaction,
deterministic audio transformation, device disconnect, and processor failure
without raw-preview fallback.

The creator-console journey is Implemented but Unverified: local `/` route →
mock source and permission presentation → consent-gated enrollment shell →
capability toggles and mock readiness → session state and safety controls →
separate unprotected source and protected-output handles. The coverage target
includes required-readiness blocking, degraded optional protection, panic stop,
stopped/reset recovery, and absence of raw PII or embedding diagnostics.

## Environment

The end-to-end environment must be isolated from normal development data and external side effects. Define deterministic fixtures, controlled dependencies, reset behavior, startup gates, teardown, and resource names without exposing credentials.

## Scenarios

Cover successful, empty, disabled, unauthorized, invalid, duplicate, timeout, dependency-failure, restart, replay, and recovery paths where the product semantics require them.

## Artifacts

Keep logs, screenshots, traces, reports, and accessibility results bounded, redacted, attributable to a scenario, and safe to retain. Do not store secrets or unnecessary personal data.

## Verification Boundary

A listed scenario is not Verified until an explicit pass exercises it. Keep the coverage map current when routes, contracts, workflows, or fixtures change.
