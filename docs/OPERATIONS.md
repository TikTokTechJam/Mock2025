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

The web process serves the browser media loopback at `/`; a browser must grant
camera and microphone permission. The API process serves liveness, while the
standalone spoken-PII demo runs as a separate local CLI invocation. The database
is provisioned for future approved configuration and lifecycle state but is not
accessed by the API, browser demo, or audio demo.

Compose mounts source code for development and keeps dependency/database data
in named volumes. The browser demo uses same-page WebRTC and does not require a
signaling port or extra environment variable. No server-side media transport,
migrations, workers, scheduled jobs, cross-modal compositor, or provider
processes exist in this foundation; the standalone spoken-PII module runs
outside Compose.

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

For the standalone audio demo:

~~~bash
uv sync --project apps/api --extra audio
uv run --project apps/api python -m privastream_api.pipeline.spoken_pii input.wav output.wav
~~~

Input must be an uncompressed PCM16 WAV no longer than the configured in-memory
limit. The default model is Faster-Whisper `small` on CPU with `int8` compute,
the default VAD is the energy baseline, and the default safety padding is 250
milliseconds. Use `--help` to review the explicit model, VAD, language, device,
padding, and merge settings. The first model-backed run may download model
artifacts to the local model cache.

## Availability and verification

The PrivaStream web/API/Compose foundation, browser-local mock media path,
normalized detector contracts, and standalone spoken-PII module are Implemented
in source. Server-side live media processing, cross-modal redaction, transport,
persistence, and production deployment are Planned. Runtime verification is
Unverified: no browser session, audio demo, model inference, tests, builds,
migrations, services, providers, linting, formatting checks, or type checks were
run.
