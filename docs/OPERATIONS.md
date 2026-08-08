# Operations

## Purpose

This document owns commands, settings, process profiles, maintenance, recovery,
deployment boundaries, and safe local or hosted operation.

## Local configuration

Copy `.env.example` to the ignored `.env` file before starting Compose. The
template contains local web, API, and PostgreSQL ports plus local PostgreSQL
initialization values for the `privastream` database and user. It contains no
provider credentials.

## Processes

| Process | Entry point | Health signal |
| --- | --- | --- |
| web | `pnpm --filter @privastream/web dev --hostname 0.0.0.0` | `GET /` |
| api | `uv run fastapi dev src/privastream_api/main.py` | `GET /health` |
| db | `postgres:18.4-bookworm` | `pg_isready` |

The web process currently serves the foundation page. The API process currently
serves only liveness. The database is provisioned for future approved
configuration and lifecycle state but is not accessed by the API.

Compose mounts source code for development and keeps dependency/database data
in named volumes. No migrations, workers, scheduled jobs, media transport,
shared compositor, or provider processes exist in this foundation. The visual
privacy module is a local standalone command rather than a Compose service.

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

`pnpm dev:reset` removes the local PostgreSQL and dependency volumes and is
destructive. The other shutdown path preserves volumes.

## Standalone visual demo

From `apps/api`, install the optional vision dependencies and run the local
image/video redaction demo:

~~~bash
uv sync --extra vision
uv run python scripts/vision_demo.py --input demo.mp4 --output protected.mp4 --plate --plate-weights weights/license_plate.pt --ocr-pii
~~~

The command requires a local YOLO-family plate weight file. It does not download
weights during processing and does not require WebRTC or other services. See
`docs/PRIVACY_VISION.md` for thresholds, languages, limitations, and failure
behavior.

## Availability and verification

The PrivaStream web/API/Compose foundation, normalized detector contracts, and
standalone plate/OCR module are Implemented in source. Product-surface redaction,
transport, persistence, and production deployment are Planned. Runtime
verification is Unverified: no tests, builds, migrations, services, providers,
linting, formatting checks, or type checks were run.
