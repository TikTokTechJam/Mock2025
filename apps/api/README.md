# FreeCoinAlert API

The API is the Python and FastAPI foundation for FreeCoinAlert. It currently exposes
only an unauthenticated process-health endpoint; authentication, persistence, alerts,
market data, Telegram delivery, and background work are not implemented.

## Prerequisites

- CPython 3.14
- [uv](https://docs.astral.sh/uv/)

The required Python version is recorded in `.python-version`. uv manages the Python
environment, dependencies, and lockfile for this component.

## Setup and local startup

From `apps/api`:

```bash
uv sync
uv run fastapi dev src/freecoinalert_api/main.py --host 0.0.0.0 --port 8000
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

`src/freecoinalert_api/main.py` owns the application factory and ASGI application.
`src/freecoinalert_api/api/router.py` composes routes, keeping future feature routes
outside the application entry point. The only current route is `GET /health`.

## Environment rules

Keep component-specific variables in `.env` files that are not committed. Use
`.env.example` only for safe, consumed variable names and comments. This foundation has
no runtime configuration, so it defines no environment variables.

## Health endpoint

`GET /health` returns:

```json
{
  "status": "ok",
  "service": "freecoinalert-api"
}
```

It reports only that the API process is running. It does not indicate readiness for a
database, market-data ingestion, alert evaluation, or Telegram delivery.
