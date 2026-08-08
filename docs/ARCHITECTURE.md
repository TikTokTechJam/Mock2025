# Architecture

## Purpose

This document owns the current repository topology, component responsibilities,
process boundaries, dependencies, and data flows.

## Current scaffold topology

- apps/web is a Next.js App Router frontend with TypeScript and Tailwind CSS.
- apps/api is a FastAPI backend using a src/freecoinalert_api package.
- compose.yaml defines the local development topology:
  - web serves the Next.js development server on port 3000;
  - api serves FastAPI on port 8000; and
  - db runs PostgreSQL on port 5432.
- apps/api/Dockerfile.dev and apps/web/Dockerfile.dev provide development
  images with mounted source trees and persistent dependency volumes.

No feature service, worker, provider integration, migration layer, or E2E
runtime boundary exists in this scaffold.

## Boundaries

The browser frontend and API are separate processes. The API currently owns
only the process-health route and has no persistence or domain services. The
PostgreSQL container is provisioned for the future application but is not
currently accessed by the API.

## Data flow

The current scaffold has no user or provider data flow. The browser serves a
static foundation page, and GET /health reports API process liveness.

## Dependencies and failure boundaries

The frontend depends on Node.js and pnpm. The API depends on CPython 3.14 and
uv. Docker Compose supplies the local process and PostgreSQL boundaries.
Compose healthchecks cover the web process, API health route, and PostgreSQL
process; they do not prove feature readiness.

## Availability

The scaffold is present in this working tree and remains Planned until merged.
Runtime verification is Unverified; no Compose startup or application
verification was requested or run.
