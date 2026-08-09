FROM node:24.18.0-bookworm-slim AS base

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:${PATH} \
    PNPM_STORE_PATH=/pnpm/store

RUN corepack enable \
    && corepack prepare pnpm@11.4.0 --activate

WORKDIR /workspace

FROM base AS dependencies

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile

FROM dependencies AS builder

ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_TELEMETRY_DISABLED=1

COPY apps/web apps/web
RUN pnpm --filter @privastream/web build

FROM base AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=dependencies --chown=node:node /workspace/package.json ./package.json
COPY --from=dependencies --chown=node:node /workspace/pnpm-workspace.yaml ./pnpm-workspace.yaml
COPY --from=dependencies --chown=node:node /workspace/node_modules ./node_modules
COPY --from=dependencies --chown=node:node /workspace/apps/web/node_modules ./apps/web/node_modules
COPY --from=builder --chown=node:node /workspace/apps/web/package.json ./apps/web/package.json
COPY --from=builder --chown=node:node /workspace/apps/web/.next ./apps/web/.next

USER node

WORKDIR /workspace
EXPOSE 3000

CMD ["pnpm", "--filter", "@privastream/web", "start", "--hostname", "0.0.0.0"]
