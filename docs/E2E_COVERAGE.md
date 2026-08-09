# End-to-End Coverage

## Purpose

Map complete user and system journeys across the real boundaries that the isolated environment is intended to exercise.

## Coverage Map

For each journey, record the starting state, actions, expected visible results, API or worker effects, ownership checks, error paths, recovery path, and current verification status.

The standalone spoken-PII demo journey is Implemented but Unverified: bounded
PCM16 input → source-timestamped `AudioChunk` → mono/model-rate normalization →
bounded VAD ring buffer and speech segments → local word-timestamp transcription
→ shared text-PII recognition and source-timestamp mapping → padded/merged
intervals → protected source chunks, including chunk-boundary muting → safe
release watermark/lag.
The coverage target includes silence-only input, a representative phone number,
a representative email address, source timestamps offset from zero, invalid
audio, timestamp discontinuity, queue overflow, deadline lag, and a
model/dependency failure without logging transcript text. Segment-only ASR
timestamps, PCM format preservation, and blocked release for unsafe outcomes
are also part of this integration boundary, including `unsafe_unclassified`
when VAD-positive speech has no usable transcript timestamps.

The centralized privacy-gate boundary is Implemented but Unverified:
sanitized capability observations and source windows → readiness/liveness
evaluation → `publish_protected`, `full_redact`, or `block` decision. Coverage
targets required and optional capability failure, watermark/lag gaps, processor
disconnect, panic entry, explicit recovery, and conservative recovery
hysteresis. The production integration adapter consumes these decisions through
an injected protected-output sink, but no server transport or real protected
delivery path consumes the sink yet.

The production privacy-media integration boundary is Implemented but Unverified:
normalized video/audio processing → optional cross-modal augmentation →
centralized gate decision → protected video/audio, full-redact fallback, or
block through an injected sink. Coverage targets source timestamp continuity,
processor failure without raw fallback, sink ordering, silent/full-frame
fallback, and blocked publication. No browser, server transport, or model-backed
end-to-end pass has exercised this boundary.

The cross-modal synchronization boundary is Implemented but Unverified:
source-timestamped video frames and existing face geometry → bounded audio
watermark lookahead → deterministic spoken-PII interval overlap → mouth or
conservative full-face regions → explicit unsafe/late-decision result. Coverage
targets pre/post padding, one-face association, unique active-speaker hints,
ambiguous multi-face fallback, no-face failure, buffer overflow, timestamp
discontinuity, and sanitized synchronization metrics. No transport, detector,
compositor, or server transport uses this boundary yet; the #11 adapter is the
only current in-process publication consumer.

The browser media loopback journey is Implemented but Unverified: local camera /
microphone permission → WebRTC offer/answer and ICE exchange → returned remote
tracks → canvas video redaction and Web Audio mute transform → processed
protected preview. The coverage target includes permission denial, successful
session startup, source timestamp updates, visible fixed-region redaction,
deterministic audio transformation, device disconnect, and processor failure
without raw-preview fallback.

The creator-console adapter journey is Implemented but Unverified: local `/`
route → browser permission and local media adapter → protected face
enrollment/readiness calls → sanitized capability and safety state → separate
unprotected source and protected-output streams. The coverage target includes
authorization/readiness failure, enrollment error and deletion, required-
readiness blocking, degraded optional protection, panic stop, reconnect,
stopped/reset recovery, protected-stream-only rendering, and absence of raw PII,
embedding, or response diagnostics. The current API lacks server media and
safety event routes, so a complete production E2E scenario remains Planned.

## Environment

The end-to-end environment must be isolated from normal development data and external side effects. Define deterministic fixtures, controlled dependencies, reset behavior, startup gates, teardown, and resource names without exposing credentials.

## Scenarios

Cover successful, empty, disabled, unauthorized, invalid, duplicate, timeout, dependency-failure, restart, replay, and recovery paths where the product semantics require them.

## Artifacts

Keep logs, screenshots, traces, reports, and accessibility results bounded, redacted, attributable to a scenario, and safe to retain. Do not store secrets or unnecessary personal data.

## Verification Boundary

A listed scenario is not Verified until an explicit pass exercises it. Keep the coverage map current when routes, contracts, workflows, or fixtures change.
