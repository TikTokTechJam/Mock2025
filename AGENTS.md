# AGENTS.md

## Project Overview

This repository contains a software product whose behavior is defined by merged implementation and authoritative documentation. Work must preserve user safety, data ownership, confidentiality, reliable state transitions, reproducible calculations, and clear separation between an event and any later delivery.

Keep product facts, runtime details, and current status in the appropriate repository documents. Keep this file focused on reusable engineering and documentation policy.

## Repository and Runtime Structure

- The docs directory contains the documentation guide, authoritative domain documents, continuity, concerns, and planning templates.
- Source, package, service, and infrastructure paths are current only when they exist and contain the described implementation.
- Planned structure must be approved before it is presented as current.
- Do not create folders, services, packages, or runtime boundaries merely because they may be useful later.

## Mandatory Working Rules

- Read this file and the documentation guide before editing.
- Read the relevant requirements, approved solution, current-state documents, and implementation before changing behavior.
- Make the smallest correct change within the requested scope.
- Keep implementation, interfaces, configuration, and current-state documentation synchronized.
- Enforce ownership and authorization on the server or trusted boundary.
- Protect credentials, personal data, provider data, and internal details from exposure.
- Preserve exact values, ordering, versioning, idempotency, and lifecycle semantics where the domain requires them.
- Treat static inspection as inspection, not proof that runtime behavior was verified.

## Current-State Documentation Rules

### Source of Truth

Merged implementation and authoritative domain documents describe current behavior. Requirements, design discussions, issues, pull requests, and user stories preserve scope and history; they do not replace the current-state contract.

Before changing a domain, read the documentation guide and every document that owns an affected contract.

### Same-Change and Replacement Rules

When behavior or a contract changes, update every affected owner in the same change. Review related entry points, examples, configuration, operations, and continuity when they could become inaccurate.

Replace stale statements with the current rule. Remove obsolete pending text, duplicate contracts, contradictory examples, and completion diaries. Do not append history where a current explanation belongs.

### Status Vocabulary

Use independent status dimensions:

| Dimension    | Allowed terms                                   |
| ------------ | ----------------------------------------------- |
| Availability | Implemented, Planned, Not supported, Unresolved |
| Verification | Verified, Unverified, Not applicable            |

Implemented means present in merged code. Verified requires an explicit verification pass. Planned is absent from the implementation. Do not use vague status words when one of these dimensions is intended.

### README, Continuity, and Concerns

README files are entry points: purpose, actual entry points, minimal setup, commands, configuration location, a concise surface summary, and links to owners.

Continuity contains only the current snapshot, active work, blockers, verification status, next actions, and handoff constraints. Remove completed work from Active Work rather than keeping a completion diary.

Concerns contains only unresolved current risks, limitations, assumptions, verification gaps, and decisions. It is not a backlog or implementation diary.

## Documentation Ownership

Review the owning document when a change affects its contract.

| Concern                                                                     | Owning document                |
| --------------------------------------------------------------------------- | ------------------------------ |
| User-visible behavior, limits, and non-goals                                | PRODUCT.md                     |
| Components, processes, dependencies, and data flow                          | ARCHITECTURE.md                |
| Requests, responses, errors, authentication, pagination, and limits         | API.md                         |
| Tables, relationships, constraints, transactions, retention, and migrations | DATABASE.md                    |
| Trust boundaries, authorization, secrets, abuse, privacy, and redaction     | SECURITY.md                    |
| External data, streams, time series, freshness, repair, and retention       | MARKET_DATA.md                 |
| Conditions, events, crossing, invalidation, and deduplication               | ALERTS.md                      |
| Rules, formulas, versions, inputs, warm-up, and outcomes                    | STRATEGIES.md                  |
| Messaging, destinations, outbox, retries, and delivery state                | TELEGRAM.md                    |
| Commands, settings, processes, maintenance, and recovery                    | OPERATIONS.md                  |
| Health, logs, measurements, freshness, and incident signals                 | OBSERVABILITY.md               |
| Historical analysis availability and semantic requirements                  | BACKTESTING.md                 |
| Test boundaries and isolated end-to-end coverage                            | TESTING.md and E2E_COVERAGE.md |
| Unresolved risk or decision                                                 | CONCERNS.md                    |
| Current handoff state                                                       | CONTINUITY.md                  |
| Approved requirements and planning templates                                | docs/user-stories/             |

## Implementation Workflow

### Before Editing

1. Read this file and docs/README.md.
2. Read the relevant requirement and approved solution when one exists.
3. Read all authoritative documents for affected domains.
4. Inspect the current implementation and current documentation.
5. Identify the owners of every changed contract.

### During Editing

1. Make the smallest approved change.
2. Update affected owners in the same change.
3. Replace stale statements instead of appending history.
4. Add only genuinely unresolved concerns.
5. Keep entry points, continuity, and planning documents within their defined boundaries.

### Before Completion

Perform a manual static consistency review:

1. Compare changed behavior, routes, schemas, models, settings, commands, statuses, logs, and consumers with the authoritative documents.
2. Search for old values, stale pending language, duplicate contracts, and completion wording.
3. Confirm Planned work is not described as Implemented.
4. Confirm implementation is not described as Verified without an explicit pass.
5. Confirm continuity contains current work only.
6. Record documentation impact and verification scope in the handoff or pull request.

## Minimal Change Rule

Do not refactor unrelated code, rename unrelated files, add dependencies, infrastructure, distributed services, or new runtime boundaries unless the approved scope requires them. Follow established local patterns and prefer simple, reversible changes.

## Security and Sensitive Data

Never commit or expose credentials, tokens, private keys, connection strings, unnecessary personal data, or sensitive provider responses. Require server-side authorization, rate-limit sensitive and expensive actions, audit important changes, and use redacted structured logs.

Do not claim guarantees about delivery, outcomes, prediction, or future performance. Clearly distinguish current behavior, planned behavior, and unverified behavior.

## Verification Execution Rule

Do not run tests, builds, migrations, databases, services, providers, browser interaction, linting, formatting checks, type checks, generators, link checkers, or other verification commands unless a dedicated verification pass is explicitly requested.

Static code and documentation inspection is allowed. Never claim a verification result that was not produced. State exactly what was and was not run.

## Pull Request Completion Rule

Before opening a pull request, complete the manual consistency review, state which authoritative documents changed, state what verification was performed, and explain why any affected document did not change.

Do not add automated documentation enforcement unless it is explicitly approved. Clear policy and an accurate pull-request summary are the default enforcement mechanism.
