# Applications

This directory contains the runnable PrivaStream applications only:

- `web/` — Next.js browser and creator application.
- `api/` — FastAPI backend and current in-process privacy/media processing
  runtime.

Model metadata, offline ML tooling, dataset metadata, and authoritative project
documentation live at the repository root in `models/`, `ml/`, `datasets/`, and
`docs/`. There is no `apps/models` application or separate model service.

The web app currently exposes the browser-local media demo. The API currently
exposes only an unauthenticated process-health endpoint, while the standalone
visual-privacy and spoken-PII modules can be invoked through local demos.
Product-surface media processing, creator controls, and server-side real-time
transport remain planned.
