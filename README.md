# PrivaStream

PrivaStream is a privacy-first media processing platform foundation. Its planned
pipeline accepts live or recorded media, detects privacy-sensitive content, and
produces a protected output with faces, plates, on-screen text, and sensitive
speech redacted as configured.

The current repository contains the web and API foundation, normalized detector
contracts, and a local PostgreSQL-backed Docker Compose topology. Media ingestion,
detectors, redaction, real-time transport, persistence, and creator controls are
planned and are not implemented yet.

## Local development

```bash
pnpm install
pnpm dev
```

The web app is served at `http://localhost:3000`; the API is served at
`http://localhost:8000`, with process health at `/health`.

See [Product](docs/PRODUCT.md), [Architecture](docs/ARCHITECTURE.md), and
[Operations](docs/OPERATIONS.md) for current boundaries, planned behavior, and
local commands.
