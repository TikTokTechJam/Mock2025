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
  "service": "freecoinalert-api"
}
~~~

The response is served by the FastAPI process and does not check PostgreSQL,
market data, authentication, notifications, or any other dependency.

## Errors and ownership

No authenticated or owner-scoped API operation exists yet. No feature request
or mutation contract is defined. Future endpoints must validate input and
enforce authorization server-side before being added to this document.

## Availability

The health contract is present in the working-tree scaffold and is Planned
until merged. Runtime verification is Unverified.
