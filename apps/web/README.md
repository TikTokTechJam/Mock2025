# PrivaStream Web

The web application is the browser media foundation for PrivaStream. It uses
Next.js, TypeScript, the App Router, Tailwind CSS, and client-side browser media
APIs for the local loopback demo.

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

## Browser media demo

Open [http://localhost:3000](http://localhost:3000), select **Start session**,
and grant camera and microphone permission. The page performs a same-browser
WebRTC offer/answer exchange, applies a fixed video redaction and deterministic
audio mute transform, and attaches only those processed tracks to the protected
preview. No API signaling endpoint or extra environment variable is required.

The local capture preview is for device feedback and is not the published
output. A disconnect or processor error stops the output rather than falling
back to raw media.

## Current Limitations

Server-side media upload and live transport, detector integrations, production
redaction, API integration, deployment configuration, and a reusable design
system are planned and are not implemented yet. The browser loopback is a local
mock path and is Unverified until an explicit browser verification pass is run.
