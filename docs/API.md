# API Contract

## Purpose

This document owns the public interface contract between trusted services,
clients, and integrations.

## Current interface

The scaffold exposes one unauthenticated process-health endpoint:

GET /health

Response:

~~~json
{
  "status": "ok",
  "service": "privastream-api"
}
~~~

The response is served by the FastAPI process and does not check PostgreSQL,
media ingestion, detector execution, redaction, real-time transport, or any other
dependency. No media or creator-control endpoint exists yet.

The standalone spoken-PII module is intentionally not an HTTP endpoint. Its
local command accepts bounded PCM16 WAV input and writes a muted WAV result; the
module's detailed input, interval, and renderer contract belongs to
`ARCHITECTURE.md` until an approved API operation is defined.

## Errors and ownership

No authenticated or owner-scoped API operation exists yet. No feature request
or mutation contract is defined. Future endpoints must validate input and
enforce authorization server-side before being added to this document.

## Availability

The health contract is Implemented in the merged foundation. Runtime
verification is Unverified.
