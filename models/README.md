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

Each manifest records `model_id`, `version`, `type`, `filename`, a `source` object
containing `url` and `sha256`, `license`, and optional runtime metadata. `type`
is `file` for one model file or `archive` for a pack that the resolver must
extract. The source may be a public HTTP(S) URL or a local handoff path. A
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

For an InsightFace pack, register the archive and its adapter metadata:

```bash
uv run --project apps/api python -m privastream_api.model_artifacts register \
  --model face-buffalo-l \
  --version v1 \
  --type archive \
  --filename buffalo_l.zip \
  --source https://example.invalid/buffalo_l.zip \
  --license "Record the handed-off model license" \
  --artifact /path/to/buffalo_l.zip \
  --runtime-format insightface-pack \
  --runtime-model-name buffalo_l \
  --runtime-provider CPUExecutionProvider \
  --output models/manifests/face-buffalo-l.json
```

Runtime code can then fetch and verify the artifact with one command:

```bash
uv run --project apps/api python -m privastream_api.model_artifacts fetch \
  --model plate-detector
```

The repository currently has no production model handoff, so no production
manifest or weight is committed. The resolver rejects missing, corrupt, or
checksum-mismatched artifacts before a detector can load them, and extracts
archives only after verification with path, link, member-count, and expanded-size
safety checks.
