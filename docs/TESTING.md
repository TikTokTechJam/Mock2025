# Testing

## Purpose

This document defines the verification boundary, test levels, isolation requirements, deterministic fixtures, and evidence vocabulary.

## Verification Boundary

A test or check is verification only when it is explicitly requested or part of an approved verification pass. Static inspection, compilation, and a dry run do not prove external safety or complete runtime correctness.

## Test Levels

Define the purpose and boundary of unit, integration, interface, worker, browser, end-to-end, performance, and recovery checks. Keep each level deterministic and avoid duplicating another level's contract.

The spoken-PII unit boundary should cover source-time mapping, silence gating,
spoken phone/email normalization, padding and merging, and PCM16 muting with
synthetic in-memory fixtures. Model inference requires a separate local fixture
or explicitly controlled model pass; it must not use real personal audio.

The browser media boundary should cover permission denial, successful local
offer/answer and ICE exchange, camera/microphone track return, visible fixed
video redaction, deterministic audio muting, source-clock updates, bounded
frame scheduling, device disconnect, and processor failure without raw-output
fallback. Browser checks require a permission-controlled local browser session;
they are not represented by the API health check.

The creator-console boundary should cover responsive layout, keyboard and label
accessibility, mock source selection and permission states, consent-gated
enrollment capture/replace/delete, capability enablement versus readiness,
connecting/processing/protected/degraded/blocked/panic/stopped/error states,
protected-output type separation, and sanitized diagnostics. These checks must
use deterministic mock clients and must not require real camera, microphone,
backend, ML, or biometric fixtures.

The shared video-engine unit boundary should use deterministic mock detectors and
raster fixtures to cover cadence skips, per-detector deadlines, bounded
concurrency, ordered release, explicit timeout/unavailable/invalid/error states,
TTL persistence and expiry, coordinate padding/clamping, overlap merging, and
blur/pixelate/cover/full-frame cover primitives. It must not load face, plate,
OCR, or transport implementations.

The production plate-adapter boundary should use a mocked #19 model and a
deterministic source-image provider to cover source-frame geometry, registration
with `VideoOrchestrator`, exactly-once production padding, successful zero
detections, and propagation of unavailable or execution failures. It must not
require downloaded weights or real media.

## Isolation

Use dedicated data, resources, credentials, and controlled dependencies for tests that can mutate state or contact external systems. Reset safely and prevent accidental actions outside the test boundary.

## Fixtures

Keep fixtures minimal, deterministic, versioned, ownership-aware, and free of secrets or unnecessary personal data. Mock or simulate external behavior when the test does not require a real provider.

## Evidence

Record the command or pass, scope, environment, result, artifacts, limitations, and unverified areas. Do not call behavior Verified without evidence from the requested pass.
