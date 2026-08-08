# PrivaStream Web

The web application is the creator-console foundation for PrivaStream. It uses
Next.js, TypeScript, the App Router, Tailwind CSS, typed local mock façades, and
a reusable browser media client.

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

## Creator privacy console

Open [http://localhost:3000](http://localhost:3000) to use the creator console.
The current page uses typed local mock clients for source selection, permission
presentation, enrollment consent/status, capability readiness, safety state,
and the protected-output boundary. It does not acquire real devices or call the
API, and no extra port or environment variable is required.

The reusable issue-21 browser media client remains in
`src/lib/browser-media-session.ts`. Its unprotected source and protected output
are separate handles; a future production client can replace the mock façade
without redesigning the console.

## Current Limitations

Backend enrollment/readiness/safety operations, server-side media upload and
live transport, detector integrations, production redaction, deployment
configuration, and a reusable design system are planned and are not implemented
yet. The console and browser loopback are Unverified until explicit UI/browser
verification passes are run.
