# Documentation Guide

## Purpose

This directory contains the semantic documentation for the product: current behavior, domain contracts, unresolved concerns, continuity, testing boundaries, and approved planning requirements.

## Current-State Rule

Current behavior is derived from merged implementation and the authoritative domain documents. Read the relevant owners before changing a domain and update their current-state contracts in the same change.

A document may provide brief context and a relative link to another owner. It must not reproduce another document's detailed contract.

## Status Vocabulary

Use availability and verification as independent dimensions.

| Dimension | Term | Meaning |
| --- | --- | --- |
| Availability | Implemented | Present in merged implementation. |
| Availability | Planned | Approved or discussed, but absent from merged implementation. |
| Availability | Not supported | Deliberately unavailable. |
| Availability | Unresolved | A decision or risk remains open. |
| Verification | Verified | An explicit verification pass exercised the behavior. |
| Verification | Unverified | Implementation exists, but no such pass exercised it. |
| Verification | Not applicable | There is no runtime behavior to exercise. |

Do not use vague words such as done, ready, complete, or working when a status dimension is intended.

## Reading Paths

- New contributor: product → architecture → relevant domain → concerns → continuity → AGENTS.md.
- API or backend change: architecture → API → database and security → affected runtime domain → concerns → AGENTS.md.
- Frontend change: product → API → security → relevant feature domain → AGENTS.md.
- Operations or incident work: operations → observability → affected runtime domain → concerns → continuity.
- End-to-end work: testing → E2E coverage → operations → affected domain → security → concerns.
- Planning: product → user story template → requirement and approved solution.

## Authoritative Ownership

| Document | Sole detailed owner |
| --- | --- |
| PRODUCT.md | User-visible capabilities, journeys, limits, and non-goals. |
| ARCHITECTURE.md | Repository topology, components, processes, dependencies, and data flows. |
| PRIVACY_VISION.md | Standalone license-plate, OCR, and visual-PII detector contract and limitations. |
| PRIVACY_FACE.md | Standalone face detection, creator enrollment, matching, region output, and local runner contract. |
| API.md | Interface methods, paths, authentication, inputs, outputs, errors, caching, pagination, and limits. |
| DATABASE.md | Tables, relationships, constraints, lifecycle storage, transactions, retention, and migrations. |
| SECURITY.md | Trust boundaries, authentication, authorization, secrets, privacy, abuse controls, and redaction. |
| MARKET_DATA.md | External data, streams, time series, aggregation, repair, freshness, and retention. |
| ALERTS.md | Conditions, crossing, events, invalidation, lifecycle, and deduplication. |
| STRATEGIES.md | Rules, formulas, versions, inputs, warm-up, outcomes, and compatibility. |
| TELEGRAM.md | Messaging, destinations, processing, durable delivery, retries, and provider status. |
| OPERATIONS.md | Commands, settings, processes, profiles, maintenance, recovery, and deployment gaps. |
| OBSERVABILITY.md | Health, persistent states, logs, measurements, freshness, redaction, and incident indicators. |
| BACKTESTING.md | Historical-analysis availability and semantic requirements. |
| TESTING.md | Verification boundary and isolated test environment contract. |
| E2E_COVERAGE.md | End-to-end scenarios, route/action coverage, fixtures, artifacts, and gaps. |
| CONCERNS.md | Unresolved current risks, assumptions, limitations, and decisions. |
| CONTINUITY.md | Current snapshot, active work, blockers, verification, next actions, and handoff constraints. |
| docs/user-stories/*.md | Approved requirements and planning templates, not current implementation truth. |

## History and Planning Boundary

Issues, pull requests, and design discussions preserve history and decisions. User stories preserve requirements. The authoritative domain documents describe current availability. Do not create completed-work diaries under docs.

## Update Rule

Replace stale, incomplete, superseded, or contradictory statements. Review related entry points, examples, configuration, operations, and continuity whenever a change could make them inaccurate.
