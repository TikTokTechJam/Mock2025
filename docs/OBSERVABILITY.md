# Observability

## Purpose

This document owns health, persistent status, structured logs, measurements,
freshness, redaction, and incident indicators.

## Health

The API GET /health endpoint reports only API process liveness. The Compose
healthchecks probe the web root, the API health endpoint, and PostgreSQL
pg_isready. None of these checks establishes product, database-schema,
provider, alert, or notification readiness.

## Logs

Use docker compose logs for local process output. The scaffold does not yet
define structured application logs, correlation identifiers, persistent status,
metrics, queue measurements, or incident automation.

The standalone spoken-PII CLI reports only the number of output redaction
intervals. It does not write raw transcript text, PII values, or source audio
to ordinary logs. Dependency/model logs are not currently normalized into the
application observability contract.

The browser media demo exposes session state, the latest source-clock
timestamp, the bounded pending-frame value, and processor or disconnect errors
in the page. It does not log camera frames, audio samples, or raw media
metadata. These are local UI signals only; no browser session status is sent to
the API or persisted.

The shared video engine exposes aggregate per-stage detector calls, success,
skip, timeout, failure, duration, queue wait, pending-frame, and processing
measurements through `VideoMetrics.snapshot()`. These metrics contain no frame
payloads, coordinates, OCR text, plate values, or raw detector errors. The
production plate adapter uses the same sanitized success and failure statuses;
it does not add model-specific payload logging.

## Verification

The API health and browser session signals are Unverified; no runtime
verification pass was run.
