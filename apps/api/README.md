# PrivaStream API

The API is the Python and FastAPI control-plane foundation for PrivaStream. It
currently exposes only an unauthenticated process-health endpoint. A standalone
visual-privacy module is available under `src/privastream_api/privacy/vision` and
can process local images or short videos through `scripts/vision_demo.py`. Product
surface media ingestion, redaction integration, persistence, creator controls,
and real-time transport are planned and are not implemented.

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
defines the normalized detector interfaces used by the standalone adapters.
`src/privastream_api/privacy/vision` contains independent plate and OCR/PII
adapters that emit those normalized regions. The only current HTTP route is
`GET /health`.

## Environment rules

Keep component-specific variables in `.env` files that are not committed. Use
`.env.example` only for safe, consumed variable names and comments. This foundation has
no runtime configuration, so it defines no environment variables.

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

## Standalone visual privacy demo

The optional vision dependencies and demo are documented in
`docs/PRIVACY_VISION.md`. From `apps/api`, run the demo with a local plate weight
file:

```bash
uv sync --extra vision
uv run python scripts/vision_demo.py --input demo.mp4 --output protected.mp4 --plate --plate-weights weights/license_plate.pt --ocr-pii
```
