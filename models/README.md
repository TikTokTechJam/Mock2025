# Runtime model metadata

This directory contains metadata and configuration for model artifacts used by
the in-process `apps/api` runtime. It is not an application or model server.

- `manifests/` is reserved for logical model manifests and is owned by the
  model bootstrap/resolver work in Issue #14.
- Downloaded weights must remain outside Git, for example in the configured
  `.cache/models/` directory.
- Runtime detector code belongs in `apps/api`; this boundary must not acquire a
  separate inference process without an approved isolation requirement.
