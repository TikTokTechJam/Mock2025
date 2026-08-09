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
enrollment, capability readiness, and the #13 safety event boundary. It
requests real browser device permission, attaches the source and protected
`MediaStream` to separate previews, and maps only sanitized API state into the
UI. The safety adapter consumes an injected #13/#11 event transport; until that
host transport is connected, publication remains blocked. A production adapter
failure never falls back to the unprotected source.

The reusable issue-21 browser media client remains in
`src/lib/browser-media-session.ts`. Its unprotected source and protected output
are separate handles. The adapter is intentionally at the client boundary so a
future server-side #21/#11 transport can replace the browser baseline without
redesigning the console.

## Current Limitations

The current API exposes only authorization-protected face enrollment/readiness
routes to the browser. The #13 gate is implemented in the API, but its
decision/event bridge into the browser transport is not connected here; server-
side media transport remains a separate boundary. Detector integrations,
production redaction, deployment configuration, and a reusable design system
remain planned. The console and browser loopback are Unverified until explicit
UI/browser verification passes are run.
