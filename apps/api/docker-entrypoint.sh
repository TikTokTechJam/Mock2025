#!/bin/sh
set -eu

if [ -n "${PRIVASTREAM_MODEL_ID:-}" ]; then
    uv run --no-sync python -m privastream_api.model_artifacts fetch \
        --model "${PRIVASTREAM_MODEL_ID}" \
        --manifest-dir /app/models/manifests \
        --cache-dir "${PRIVASTREAM_MODEL_CACHE_DIR:-/var/cache/privastream/models}"
fi

exec "$@"
