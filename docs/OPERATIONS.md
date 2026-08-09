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

The web process serves the creator privacy console at `/`. Its current source,
permission, enrollment, readiness, safety, and media-session controls use local
typed mocks and do not require device permission or an API call. The reusable
browser media loopback remains a separate client module. The API process serves
liveness, while the standalone spoken-PII demo runs as a separate local CLI
invocation. The database is provisioned for future approved configuration and
lifecycle state but is not accessed by the API, console, browser loopback, or
audio demo.

Compose mounts source code for development and keeps dependency/database data
in named volumes. The browser demo uses same-page WebRTC and does not require a
signaling port or extra environment variable. No server-side media transport,
migrations, external/background worker processes, scheduled jobs, cross-modal
policy, or provider processes exist in this foundation. The shared video engine,
production plate adapter, and bounded transcription workers are in-process API
libraries; the visual-privacy and spoken-PII demos remain local standalone
commands rather than Compose services.

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

## Standalone face demo

From `apps/api`, install the optional face dependencies and provide a local
InsightFace model pack:

~~~bash
uv sync --extra face
uv run python scripts/face_demo.py --input demo.mp4 --output protected.mp4 --model-root models/insightface
~~~

Creator enrollment is opt-in. Repeat `--enrollment` for local sample images and
add `--consent`; without enrollment, every detected face is protected. No model
weights are downloaded by the face adapter during processing. See
`docs/PRIVACY_FACE.md` for thresholds, data lifecycle, and limitations.

## Standalone audio demo

For the standalone audio demo:

~~~bash
uv sync --project apps/api --extra audio
uv run --project apps/api python -m privastream_api.pipeline.spoken_pii input.wav output.wav
~~~

Input must be an uncompressed PCM16 WAV no longer than the configured in-memory
limit. The runner feeds the same timestamped `AudioChunk` and bounded
`AudioPipeline` interfaces used by the future transport path. The default model
is Faster-Whisper `small` on CPU with `int8` compute, the default VAD is the
energy baseline, and the default safety padding is 250 milliseconds. Use
`--help` to review the explicit model, VAD, language, device, padding, and merge
settings. The first model-backed run may download model artifacts to the local
model cache.

The pipeline applies canonical spoken-PII intervals to the original source
chunks before returning protected chunks. A safe release watermark and lag are
available only after this step; blocked or unsafe results must not be published
as protected output by a future transport boundary.

The audio pipeline fails closed with explicit local statuses for timestamp
discontinuity, invalid input, VAD failure, queue overflow, unclassified speech,
transcription failure, or processing deadline lag. None is represented as an
empty successful redaction result.

The in-process `PrivacyGate` is the single source of publication decisions for
future media consumers. It reports separate process liveness and privacy
readiness, applies required/optional capability policy, and requires explicit
panic recovery with consecutive healthy evaluations. It is not an HTTP route or
an active transport integration; `/health` continues to report liveness only.

## Availability and verification

The PrivaStream web/API/Compose foundation, creator-console mock shell,
normalized detector contracts, browser-local mock media path, shared video
engine, production plate adapter, standalone face and plate/OCR modules,
standalone spoken-PII module, and in-process privacy gate are Implemented in
source. Cross-modal policy, backend readiness/enrollment/safety integration,
server-side live media processing and transport, persistence, and production
deployment are Planned. Runtime
verification is Unverified: no browser session,
audio or visual demo, model inference, orchestration tests, builds, migrations,
services, providers, linting, formatting checks, or type checks were run.
