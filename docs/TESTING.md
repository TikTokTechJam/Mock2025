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

## Isolation

Use dedicated data, resources, credentials, and controlled dependencies for tests that can mutate state or contact external systems. Reset safely and prevent accidental actions outside the test boundary.

## Fixtures

Keep fixtures minimal, deterministic, versioned, ownership-aware, and free of secrets or unnecessary personal data. Mock or simulate external behavior when the test does not require a real provider.

## Evidence

Record the command or pass, scope, environment, result, artifacts, limitations, and unverified areas. Do not call behavior Verified without evidence from the requested pass.
