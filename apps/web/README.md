# PrivaStream Web

The web application is the creator-console foundation for PrivaStream. It uses
Next.js, TypeScript, the App Router, Tailwind CSS, production client adapters,
and a reusable browser media client.

## Prerequisites

- Node.js `24.18.0`
- pnpm `11.4.0`

Install workspace dependencies from the repository root:

```bash
pnpm install
```

## Local Commands

Run these commands from the repository root:

```bash
pnpm dev:web
pnpm build:web
pnpm lint:web
pnpm typecheck:web
```

`pnpm dev:web` starts the local development server on [http://localhost:3000](http://localhost:3000).
`pnpm build:web` produces a production build, and `pnpm --filter @privastream/web start` serves that build.

## Directory Purpose

- `src/app/` contains App Router routes, the root layout, and global styles.
- `public/` holds static assets when a future approved feature requires them.

## Environment Rules

- Browser-exposed variables require the `NEXT_PUBLIC_` prefix.
- Secrets must never use `NEXT_PUBLIC_`.
- Add variables only when they are consumed by implemented code.
- Shared variables belong in the repository root `.env.example`; web-only variables belong in `.env.example` here.

Set `NEXT_PUBLIC_API_BASE_URL` when the browser cannot reach the API at its
default `http://localhost:8000` origin. The value is an origin only; do not put
credentials or tokens in browser-exposed configuration.

## Creator privacy console

Open [http://localhost:3000](http://localhost:3000) to use the creator console.
The page uses `src/lib/production-clients.ts` for browser media, face
enrollment, capability readiness, and safety control boundaries. It requests
real browser device permission, attaches the source and protected `MediaStream`
to separate previews, and maps only sanitized API state into the UI. A
production adapter failure leaves publication blocked; it does not fall back to
the unprotected source.

The reusable issue-21 browser media client remains in
`src/lib/browser-media-session.ts`. Its unprotected source and protected output
are separate handles. The adapter is intentionally at the client boundary so a
future server-side #21/#11 transport can replace the browser baseline without
redesigning the console.

## Current Limitations

The current API exposes only authorization-protected face enrollment/readiness
routes; server-side media transport and #13 safety status/event routes are not
available yet. Detector integrations, production redaction, deployment
configuration, and a reusable design system remain planned. The console and
browser loopback are Unverified until explicit UI/browser verification passes
are run.
