FROM ghcr.io/astral-sh/uv:0.11.32 AS uv

FROM python:3.14.6-slim-bookworm

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_CACHE_DIR=/home/privastream/.cache/uv \
    PRIVASTREAM_MODEL_CACHE_DIR=/var/cache/privastream/models

RUN useradd --create-home --uid 10001 privastream \
    && mkdir -p /app/.venv /app/models/manifests ${UV_CACHE_DIR} ${PRIVASTREAM_MODEL_CACHE_DIR} \
    && chown -R privastream:privastream /app /home/privastream /var/cache/privastream

WORKDIR /app

COPY --chown=privastream:privastream apps/api/pyproject.toml apps/api/uv.lock ./
COPY --chown=privastream:privastream apps/api/src ./src
COPY --chown=privastream:privastream models/manifests ./models/manifests
COPY --chown=privastream:privastream apps/api/docker-entrypoint.sh /usr/local/bin/privastream-api-entrypoint

# InsightFace 0.7.x is source-distributed for the pinned Python runtime.
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*

USER privastream

RUN uv sync --frozen --no-dev --extra face --extra vision --extra audio

EXPOSE 8000

ENTRYPOINT ["sh", "/usr/local/bin/privastream-api-entrypoint"]
CMD ["uv", "run", "--no-sync", "fastapi", "run", "src/privastream_api/main.py", "--host", "0.0.0.0", "--port", "8000"]
