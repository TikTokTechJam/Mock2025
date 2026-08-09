# PrivaStream API

The API is the Python and FastAPI control-plane foundation for PrivaStream. It
exposes an unauthenticated process-health endpoint plus protected face
enrollment/readiness control routes and contains
the model-agnostic shared video orchestration path under
`src/privastream_api/pipeline/video.py`, plus local-only visual-privacy,
spoken-audio, and face-detector paths. Visual privacy is under
`src/privastream_api/privacy/vision`, with image/video processing through
`scripts/vision_demo.py`. The completed plate detector also has a thin
`PlateVideoDetector` registration path for the shared scheduler; it returns
source-frame geometry without applying standalone padding or cadence. The OCR
detector has the corresponding `OcrVideoDetector` and `register_ocr_detector`
path, which consumes the shared text-PII recognizer and maps sensitive spans to
source OCR blocks without applying standalone padding or cadence. Spoken PII is
under
`src/privastream_api/pipeline/spoken_pii.py`, with bounded PCM16 WAV processing.
Cross-modal spoken-PII visual augmentation is under
`src/privastream_api/pipeline/cross_modal.py`; it correlates source-time audio
intervals with existing normalized face geometry without owning detectors,
composition, transport, or publication safety.
The face-specific path under `src/privastream_api/privacy/face` provides
standalone InsightFace/ArcFace detection, consented creator enrollment, and
conservative creator-vs-bystander matching through `scripts/face_demo.py`.
These detector paths do not persist raw media or model output. The production
face adapter delegates detection and matching to the standalone module, while
its process-local enrollment repository and readiness surface are separate
integration boundaries. Product-surface media ingestion, durable enrollment
persistence, creator UI wiring, and real-time transport are planned and are not
implemented.

## Prerequisites

- CPython 3.14
- [uv](https://docs.astral.sh/uv/)

The required Python version is recorded in `.python-version`. uv manages the Python
environment, dependencies, and lockfile for this component.

## Setup and local startup

From `apps/api`:

```bash
uv sync
uv run fastapi dev src/privastream_api/main.py --host 0.0.0.0 --port 8000
```

Install the optional local audio dependencies for the spoken-PII demo:

```bash
uv sync --extra audio
```

The API listens on `http://localhost:8000`. FastAPI's standard documentation remains
available at `/docs`, `/redoc`, and `/openapi.json`.

## Component commands

```bash
uv run ruff check .
uv run ruff format .
uv run ruff format --check .
uv run mypy src
```

## Source layout

`src/privastream_api/main.py` owns the application factory and ASGI application.
`src/privastream_api/api/router.py` composes routes, keeping future feature routes
outside the application entry point. `src/privastream_api/pipeline/contracts.py`
defines normalized detector interfaces, source-timestamped PCM segments, and
model-neutral detection results. `src/privastream_api/pipeline/video.py`
validates, schedules, temporally retains, and composes normalized video regions
without importing detector implementations. `src/privastream_api/privacy/vision`
contains independent plate and OCR/PII adapters that emit normalized regions.
`PlateVideoDetector` and `register_plate_detector` bridge the plate
implementation into the shared video scheduler without importing model-specific
code into the orchestrator. `OcrVideoDetector` and `register_ocr_detector` do
the same for the OCR/visual-PII path while keeping text recognition in
`privastream_api.privacy.text_pii`. `src/privastream_api/privacy/face` contains the
independent face model adapter, creator enrollment store, matcher, and
bystander-region detector. It does not apply production padding or temporal
composition.
`src/privastream_api/pipeline/audio.py` contains the timestamped chunk
normalizer, bounded ring-buffer segmenter, transcription queue, explicit unsafe
outcomes, in-memory timestamped transcript sink, shared text-PII recognizer
bridge, source-chunk muting, and safe-release watermark. It composes the VAD
and transcriber interfaces from `spoken_pii.py`; the only current HTTP route is
`GET /health`.
`src/privastream_api/pipeline/safety.py` contains the centralized privacy gate
for required/optional readiness, source-time coverage, liveness, panic,
conservative recovery, and sanitized publication decisions. It does not inspect
media or expose an HTTP route; transport integration remains outside the
current API surface.
`src/privastream_api/pipeline/media_integration.py` contains the production
privacy-media adapter. It coordinates the video, audio, optional cross-modal,
and gate decisions, then exposes only protected output through an injected
`ProtectedMediaSink`; it does not implement signaling or transport.
`src/privastream_api/pipeline/spoken_pii.py` contains the bounded VAD,
transcription, PII interval, and PCM16 renderer path. The current HTTP surface
includes `GET /health` and the authorization-protected face routes documented in
`docs/API.md`.
`src/privastream_api/pipeline/cross_modal.py` contains the bounded source-time
lookahead, spoken-PII interval index, face association/fallback, visual-region
derivation, and explicit unsafe/late-decision results for cross-modal consumers.

Run the spoken-PII local demo from the repository root:

```bash
uv run --project apps/api python -m privastream_api.pipeline.spoken_pii input.wav output.wav
```

The runner feeds the same `AudioChunk` and `AudioPipeline` interfaces used by
the bounded processing path. The default VAD is the dependency-free energy
baseline; use `--vad silero` for the optional Silero adapter. The Faster-Whisper
model, language, device, compute type, padding, and merge gap are configurable
through CLI flags. Timestamp discontinuity, VAD failure, queue overflow,
transcription failure, and deadline lag fail closed with explicit local status;
they are not converted to an empty redaction result.

## Environment rules

Keep component-specific variables in `.env` files that are not committed. Use
`.env.example` only for safe, consumed variable names and comments. The
foundation has no environment configuration; audio demo settings are explicit
CLI arguments so a run is attributable and does not silently change policy.

## Health endpoint

`GET /health` returns:

```json
{
  "status": "ok",
  "service": "privastream-api"
}
```

It reports only that the API process is running. It does not indicate readiness for a
database, product-surface media ingestion, redaction, or transport readiness.

## Production face control surface

The production face integration registers the standalone `CreatorFaceDetector`
with the shared `VideoOrchestrator`, preserves detector failures for the future
privacy gate, and exposes safe enrollment lifecycle and readiness metadata:

- `GET /privacy/face/enrollment`
- `POST /privacy/face/enrollment` to create consented enrollment
- `PUT /privacy/face/enrollment` to replace it
- `DELETE /privacy/face/enrollment` to revoke it
- `GET /privacy/face/readiness`

The mutation endpoints accept bounded multipart image samples and an explicit
`consent=true` field. All routes require an injected server-side creator
authorizer; the default application returns `503` until that boundary is
configured. The current repository is process-local because durable database
storage is outside this issue. See `docs/API.md` and `docs/PRIVACY_FACE.md`.

## Standalone visual privacy demo

The optional vision dependencies and demo are documented in
`docs/PRIVACY_VISION.md`. From `apps/api`, run the demo with a local plate weight
file:

```bash
uv sync --extra vision
uv run python scripts/vision_demo.py --input demo.mp4 --output protected.mp4 --plate --plate-weights weights/license_plate.pt --ocr-pii
```

## Standalone face demo

Install the optional local InsightFace/ArcFace path and run the image/video
runner:

```bash
uv sync --extra face
uv run python scripts/face_demo.py --input demo.mp4 --output protected.mp4 --model-root models/insightface
```

Add `--enrollment creator.jpg --consent` for explicit creator enrollment. See
`docs/PRIVACY_FACE.md` for the matching policy, lifecycle rules, local model
requirements, and limitations.
