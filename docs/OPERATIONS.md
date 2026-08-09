# Operations

## Purpose

This document owns commands, settings, process profiles, maintenance, recovery,
deployment boundaries, and safe local or hosted operation.

## Local configuration

Copy `.env.example` to the ignored `.env` file before starting Compose. The
template contains local web, API, and PostgreSQL ports plus local PostgreSQL
initialization values for the `privastream` database and user. It contains no
provider credentials.

## Offline benchmark reports

The dependency-free Issue #15 runner uses normalized labels and predictions
from an approved detector or pipeline evaluation workflow. From the repository
root, run the documented synthetic example with explicit model, checksum,
dataset, profile, hardware, and code-commit provenance:

~~~bash
python ml/evaluation/benchmark.py run \
  --input ml/evaluation/fixtures/plate-example.json \
  --output reports/plate-example.json \
  --model plate-detector:v1 \
  --model-checksum 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --dataset plate-fixture \
  --profile plate-default-640 \
  --hardware "Apple Silicon / CPU" \
  --commit 0000000000000000000000000000000000000000
~~~

The runner writes JSON and Markdown reports, including precision, recall,
privacy-critical miss rate, mAP@0.5, mAP@0.5:0.95, steady-state p50/p95/p99,
inference FPS, optional video/audio measurements, cold-start time, and supplied
resource samples. The checked-in fixture is synthetic and is not a production
quality claim.

## Runtime model artifacts

Model artifacts are described by JSON manifests under `models/manifests/` and
cached under `.cache/models/`. After the ML team provides a real artifact and
manifest metadata, fetch it from the repository root with:

~~~bash
uv run --project apps/api python -m privastream_api.model_artifacts fetch --model plate-detector
~~~

The resolver validates the SHA-256 checksum before returning a local path.
Missing manifests, unavailable sources, and mismatches are errors; detector
code must not silently load an unverified or developer-specific path.

## Processes

| Process | Entry point | Health signal |
| --- | --- | --- |
| web | `pnpm --filter @privastream/web dev --hostname 0.0.0.0` | `GET /` |
| api | `uv run fastapi dev src/privastream_api/main.py` | `GET /health`; protected face readiness is a capability signal |
| db | `postgres:18.4-bookworm` | `pg_isready` |

The web process serves the creator privacy console at `/`. Its source,
permission, enrollment, readiness, safety, and media-session controls use the
production client adapters. Browser permission is requested locally, face
control calls use `NEXT_PUBLIC_API_BASE_URL` (defaulting to
`http://localhost:8000`), and unavailable API boundaries remain blocked. The
reusable browser media loopback remains a separate client module. The API
process serves liveness and the protected face control boundary, while the
standalone spoken-PII demo runs as a separate local CLI
invocation. The database is provisioned for future approved configuration and
lifecycle state but is not accessed by the API, console, browser loopback, or
audio demo.

Compose mounts source code for development and keeps dependency/database data
in named volumes. The browser media baseline uses same-page WebRTC and does not
require a signaling port; set `NEXT_PUBLIC_API_BASE_URL` for the web-to-API
origin when the default is not suitable. No server-side media transport,
migrations, external/background worker processes, scheduled jobs, or provider
processes exist in this foundation. The in-process production media integration
has no separate process, port, command, or environment setting; it hands output
to a future transport sink.
The shared video engine, production plate, OCR/PII, and face adapters, and
bounded transcription workers are in-process API libraries; the visual-privacy
and spoken-PII demos remain local
standalone commands rather than Compose services.

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

Once the ML handoff manifest exists, pass `--plate-model plate-detector` to
resolve and verify the artifact through the shared model cache.

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
media consumers. `ProductionMediaIntegration` applies those decisions to
protected video/audio output or a fail-closed fallback before calling an
injected sink. Neither is an HTTP route or an active server transport;
`/health` continues to report liveness only.

## Availability and verification

The PrivaStream web/API/Compose foundation, creator-console adapter path,
normalized detector contracts, browser-local mock media path, shared video
engine, cross-modal synchronizer, production plate, OCR/PII, and face adapters,
process-local face enrollment repository/readiness routes, standalone face and
plate/OCR modules, standalone spoken-PII module, in-process privacy gate, and
production media integration adapter are Implemented in source. Authorization-
provider wiring, durable persistence, server-side live media processing and
transport, and production deployment are Planned. Runtime
verification is Unverified: no browser session,
audio or visual demo, model inference, orchestration tests, builds, migrations,
services, providers, linting, formatting checks, or type checks were run.
