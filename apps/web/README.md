# FreeCoinAlert Web

The web application is the browser foundation for FreeCoinAlert. It uses Next.js,
TypeScript, the App Router, Tailwind CSS, and Server Components by default.

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
`pnpm build:web` produces a production build, and `pnpm --filter @freecoinalert/web start` serves that build.

## Directory Purpose

- `src/app/` contains App Router routes, the root layout, and global styles.
- `public/` holds static assets when a future approved feature requires them.

## Environment Rules

- Browser-exposed variables require the `NEXT_PUBLIC_` prefix.
- Secrets must never use `NEXT_PUBLIC_`.
- Add variables only when they are consumed by implemented code.
- Shared variables belong in the repository root `.env.example`; web-only variables belong in `.env.example` here.

## Current Limitations

Authentication, Telegram linking, alert management, market charts, API integration,
deployment configuration, and a reusable design system are not implemented yet.
