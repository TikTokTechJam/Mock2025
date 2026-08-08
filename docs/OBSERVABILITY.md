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

## Verification

The health signals are Unverified; no runtime verification pass was run.
