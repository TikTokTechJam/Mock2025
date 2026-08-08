# Mock2025

This repository contains the FreeCoinAlert application scaffold.

## Local development

The scaffold includes a Next.js frontend, a FastAPI backend with a health endpoint, and a PostgreSQL-backed Docker Compose development stack.

```bash
pnpm install
pnpm dev
```

The web app is served at `http://localhost:3000`; the API is served at `http://localhost:8000`, with health at `/health`.

Product features, persistence, provider integrations, background workers, and E2E infrastructure are intentionally not included in this scaffold.
