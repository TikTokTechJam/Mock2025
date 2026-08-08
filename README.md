# PrivaStream

PrivaStream is a privacy-first media processing platform foundation. Its planned
pipeline accepts live or recorded media, detects privacy-sensitive content, and
produces a protected output with faces, plates, on-screen text, and sensitive
speech redacted as configured.

The current repository contains the web and API foundation, normalized detector
contracts, standalone license-plate/OCR visual-privacy and spoken-PII
detector/renderer modules, and a local PostgreSQL-backed Docker Compose
topology. HTTP media ingestion, cross-modal redaction compositing, real-time
transport, persistence, and creator controls are planned and are not implemented
yet.

## Local development

```bash
pnpm install
pnpm dev
```

The web app is served at `http://localhost:3000`; the API is served at
`http://localhost:8000`, with process health at `/health`.

The API also contains a standalone local spoken-PII demo. It is not exposed as
an API route and requires the optional audio dependencies:

```bash
uv sync --project apps/api --extra audio
uv run --project apps/api python -m privastream_api.pipeline.spoken_pii input.wav output.wav
```

The demo accepts a bounded PCM16 WAV, detects speech, transcribes locally, and
writes a copy with detected phone-number and email intervals muted. It does not
persist raw audio or transcript text. Live transport, persistence, background
workers, creator controls, and E2E infrastructure remain unimplemented.

See [Product](docs/PRODUCT.md), [Architecture](docs/ARCHITECTURE.md), and
[Operations](docs/OPERATIONS.md) for current boundaries, planned behavior, and
local commands. See [Visual Privacy](docs/PRIVACY_VISION.md) for the standalone
plate/OCR module.
