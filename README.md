# PrivaStream

PrivaStream is a privacy-first media processing platform foundation. Its planned
pipeline accepts live or recorded media, detects privacy-sensitive content, and
produces a protected output with faces, plates, on-screen text, and sensitive
speech redacted as configured.

The current repository contains the web and API foundation, a browser-local
WebRTC media loopback with deterministic mock processing, normalized detector
contracts, standalone license-plate/OCR visual-privacy and spoken-PII
detector/renderer modules, and a local PostgreSQL-backed Docker Compose
topology. HTTP media ingestion, server-side or production transport,
cross-modal redaction compositing, persistence, and creator controls are planned
and are not implemented yet.

## Local development

```bash
pnpm install
pnpm dev
```

The web app is served at `http://localhost:3000`; the API is served at
`http://localhost:8000`, with process health at `/health`.

The web app at `http://localhost:3000` includes a browser media demo. Select
**Start session**, grant camera and microphone permission, and use the
processed protected preview. The signaling and processing path stays in the
browser; no extra port or environment variable is required.

The API also contains a standalone local spoken-PII demo. It is not exposed as
an API route and requires the optional audio dependencies:

```bash
uv sync --project apps/api --extra audio
uv run --project apps/api python -m privastream_api.pipeline.spoken_pii input.wav output.wav
```

The demo accepts a bounded PCM16 WAV, detects speech, transcribes locally, and
writes a copy with detected phone-number and email intervals muted. It does not
persist raw audio or transcript text. Server-side transport, persistence,
background workers, creator controls, and E2E infrastructure remain
unimplemented.

See [Product](docs/PRODUCT.md), [Architecture](docs/ARCHITECTURE.md), and
[Operations](docs/OPERATIONS.md) for current boundaries, planned behavior, and
local commands. See [Visual Privacy](docs/PRIVACY_VISION.md) for the standalone
plate/OCR module.
