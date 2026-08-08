# Operations

## Purpose

This document owns commands, settings, process profiles, maintenance, recovery,
deployment boundaries, and safe local or hosted operation.

## Local configuration

Copy .env.example to the ignored .env file before starting Compose. The
template contains local web, API, and PostgreSQL ports plus local PostgreSQL
initialization values. It contains no provider credentials.

## Processes

| Process | Entry point | Health signal |
| --- | --- | --- |
| web | pnpm --filter @freecoinalert/web dev --hostname 0.0.0.0 | GET / |
| api | uv run fastapi dev src/freecoinalert_api/main.py | GET /health |
| db | postgres:18.4-bookworm | pg_isready |

Compose mounts source code for development and keeps dependency/database data
in named volumes. No migrations, workers, scheduled jobs, or provider processes
exist in this scaffold.

## Commands

From the repository root:

~~~bash
pnpm install
pnpm dev
pnpm dev:detached
pnpm dev:status
pnpm dev:logs
pnpm dev:down
pnpm dev:reset
~~~

pnpm dev:reset removes the local PostgreSQL and dependency volumes and is
destructive. The other shutdown path preserves volumes.

## Availability and verification

The local scaffold topology is Planned until merged and Unverified. No
tests, builds, migrations, services, providers, linting, formatting checks, or
type checks were run.
