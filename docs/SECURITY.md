# Security

## Purpose

This document owns trust boundaries, authentication, authorization, secrets, privacy, abuse controls, auditability, logging, and exposure rules.

## Trust Boundaries

Identify clients, servers, workers, databases, external providers, administrators, and untrusted input. State what each boundary may trust and what must be validated again.

## Identity and Authorization

Define authentication, session or token handling, ownership checks, role checks, administrative authorization, expiration, revocation, and cross-tenant isolation. Never rely on a client-only check.

## Secrets and Privacy

Keep credentials, tokens, private keys, connection strings, and unnecessary personal data out of code, logs, examples, artifacts, and errors. Define storage, rotation, redaction, and access rules.

## Abuse Controls

Bound expensive operations, input size, rule complexity, retries, concurrency, and externally visible actions. Rate-limit sensitive actions and make important changes auditable.

## Integrations

Validate provider responses, isolate provider failures, avoid exposing raw provider errors, and document webhook or callback authenticity when applicable.

## Claims

Do not claim guarantees about delivery, prediction, financial outcomes, availability, or historical performance. Mark uncertainty and verification boundaries clearly.
