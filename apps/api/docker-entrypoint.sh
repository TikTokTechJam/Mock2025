#!/bin/sh
set -eu

last_model_id=""
for model_id in "${PRIVASTREAM_MODEL_ID:-}" "${PRIVASTREAM_FACE_MODEL_ID:-}"; do
    if [ -n "$model_id" ] && [ "$model_id" != "$last_model_id" ]; then
        uv run --no-sync python -m privastream_api.model_artifacts fetch \
            --model "$model_id" \
            --manifest-dir /app/models/manifests \
            --cache-dir "${PRIVASTREAM_MODEL_CACHE_DIR:-/var/cache/privastream/models}"
        last_model_id="$model_id"
    fi
done

exec "$@"
