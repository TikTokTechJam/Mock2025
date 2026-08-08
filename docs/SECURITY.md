# Security

## Purpose

This document owns trust boundaries, authentication, authorization, secrets, privacy, abuse controls, auditability, logging, and exposure rules.

## Trust Boundaries

Identify clients, servers, workers, databases, external providers, administrators, and untrusted input. State what each boundary may trust and what must be validated again.

## Identity and Authorization

Define authentication, session or token handling, ownership checks, role checks, administrative authorization, expiration, revocation, and cross-tenant isolation. Never rely on a client-only check.

## Secrets and Privacy

Keep credentials, tokens, private keys, connection strings, and unnecessary personal data out of code, logs, examples, artifacts, and errors. Define storage, rotation, redaction, and access rules.

The standalone spoken-PII demo keeps PCM samples and transcript words in
process memory for one bounded invocation. The module does not log transcript
text, detected PII, or raw samples, and the renderer writes only the explicitly
requested muted audio output. Model caches and output files remain local
operator-controlled artifacts and are outside the current product retention
contract.

## Abuse Controls

Bound expensive operations, input size, rule complexity, retries, concurrency, and externally visible actions. Rate-limit sensitive actions and make important changes auditable.

## Integrations

Validate provider responses, isolate provider failures, avoid exposing raw provider errors, and document webhook or callback authenticity when applicable.

## Claims

Do not claim guarantees about delivery, prediction, financial outcomes, availability, or historical performance. Mark uncertainty and verification boundaries clearly.

Spoken-PII detection is best-effort model and pattern matching. A detected
interval is not proof that all sensitive speech was found; the current demo has
no fail-closed delivery boundary or creator review workflow.
