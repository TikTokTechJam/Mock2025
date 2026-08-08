# PrivaStream API

The API is the Python and FastAPI control-plane foundation for PrivaStream. It
exposes an unauthenticated process-health endpoint and contains a standalone
spoken-PII demo module. The demo is local-only: it is not an API route, does not
persist raw audio or transcript text, and does not implement live transport,
creator controls, or durable processing.

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
defines normalized detector interfaces and source-timestamped PCM segments.
`src/privastream_api/pipeline/spoken_pii.py` contains the bounded VAD,
transcription, PII interval, and PCM16 renderer path. The only current HTTP
route is `GET /health`.

Run the local demo from the repository root:

```bash
uv run --project apps/api python -m privastream_api.pipeline.spoken_pii input.wav output.wav
```

The default VAD is the dependency-free energy baseline. Use `--vad silero` for
the optional Silero adapter. The Faster-Whisper model, language, device,
compute type, padding, and merge gap are configurable through CLI flags.

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
database, media ingestion, detector execution, redaction, or transport readiness.
