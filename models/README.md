# Runtime model metadata

This directory contains metadata and configuration for model artifacts used by
the in-process `apps/api` runtime. It is not an application or model server.

- `manifests/` contains logical model manifests consumed by the Issue #14
  bootstrap/resolver.
- Downloaded weights must remain outside Git, for example in the configured
  `.cache/models/` directory.
- Runtime detector code belongs in `apps/api`; this boundary must not acquire a
  separate inference process without an approved isolation requirement.

## Model handoff

Each manifest records `model_id`, `version`, `filename`, `source`, `sha256`, and
`license`. The source may be a public HTTP(S) URL or a local handoff path. A
manifest is not a model file and must never contain credentials.

After the ML team supplies an artifact, register its metadata and checksum:

```bash
uv run --project apps/api python -m privastream_api.model_artifacts register \
  --model plate-detector \
  --version v1 \
  --filename plate-detector.pt \
  --source https://example.invalid/plate-detector.pt \
  --license "Record the handed-off model license" \
  --artifact /path/to/plate-detector.pt \
  --output models/manifests/plate-detector.json
```

Runtime code can then fetch and verify the artifact with one command:

```bash
uv run --project apps/api python -m privastream_api.model_artifacts fetch \
  --model plate-detector
```

The repository currently has no production model handoff, so no production
manifest or weight is committed. The resolver rejects missing, corrupt, or
checksum-mismatched artifacts before a detector can load them.
