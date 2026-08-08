# End-to-End Coverage

## Purpose

Map complete user and system journeys across the real boundaries that the isolated environment is intended to exercise.

## Coverage Map

For each journey, record the starting state, actions, expected visible results, API or worker effects, ownership checks, error paths, recovery path, and current verification status.

The standalone spoken-PII demo journey is Implemented but Unverified: bounded
PCM16 input → VAD speech windows → local word-timestamp transcription → phone /
email interval normalization → padded/merged intervals → muted PCM16 output.
The coverage target includes silence-only input, a representative phone number,
a representative email address, source timestamps offset from zero, invalid
audio, and a model/dependency failure without logging transcript text.

## Environment

The end-to-end environment must be isolated from normal development data and external side effects. Define deterministic fixtures, controlled dependencies, reset behavior, startup gates, teardown, and resource names without exposing credentials.

## Scenarios

Cover successful, empty, disabled, unauthorized, invalid, duplicate, timeout, dependency-failure, restart, replay, and recovery paths where the product semantics require them.

## Artifacts

Keep logs, screenshots, traces, reports, and accessibility results bounded, redacted, attributable to a scenario, and safe to retain. Do not store secrets or unnecessary personal data.

## Verification Boundary

A listed scenario is not Verified until an explicit pass exercises it. Keep the coverage map current when routes, contracts, workflows, or fixtures change.
