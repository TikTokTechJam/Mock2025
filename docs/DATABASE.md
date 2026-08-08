# Database

## Purpose

This document owns the durable data model, relationships, constraints, indexes, lifecycle storage, transactions, retention, and migration inventory.

## Source of Truth

Identify which records are canonical, which are derived, and which are caches or projections. Define ownership and visibility for every user-scoped record.

## Identity and Versioning

Define stable identities for entities, events, intervals, revisions, and rule versions. Immutable facts must not be overwritten by later interpretations. Corrections should preserve the history needed to explain prior state.

## Constraints and Transactions

Document required fields, uniqueness, foreign keys, check constraints, indexes, transaction boundaries, concurrency rules, idempotency keys, and lifecycle transitions.

## Time and Data Quality

Use an explicit time standard, define interval boundaries, distinguish complete from incomplete data, and record correction or reconciliation semantics. Do not silently replace canonical state with partial state.

## Retention and Deletion

Document retention, archival, deletion, ownership transfer, privacy removal, backup, and restore behavior. State which records must remain immutable for audit or reproducibility.

## Migrations

Every schema change requires an idempotent migration plan, compatibility review, rollback or recovery considerations, and updates to affected API, application, and documentation contracts.
