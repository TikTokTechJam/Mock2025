# Observability

## Purpose

This document owns health, persistent status, structured logs, measurements,
freshness, redaction, and incident indicators.

## Health

The API GET /health endpoint reports only API process liveness. The Compose
healthchecks probe the web root, the API health endpoint, and PostgreSQL
pg_isready. None of these checks establishes product, database-schema,
provider, alert, or notification readiness.

## Logs

Use docker compose logs for local process output. The scaffold does not yet
define structured application logs, correlation identifiers, persistent status,
metrics, queue measurements, or incident automation.

The standalone spoken-PII CLI reports only the number of output redaction
intervals. It does not write raw transcript text, PII values, or source audio
to ordinary logs. Dependency/model logs are not currently normalized into the
application observability contract.

The timestamped audio pipeline keeps transcript words in its in-memory result
sink and exposes only sanitized status, queue depth, processing duration,
redaction-interval count, protected-chunk count, and release status to callers.
Successful results also expose a source-timeline release watermark and
processing lag. Timestamp discontinuity, VAD failure, queue overflow,
transcription failure, deadline lag, and unclassified speech are distinct unsafe
statuses and block release. VAD-positive windows with no usable transcript are
reported as `unsafe_unclassified`; raw audio, transcript text, PII values, and
model errors are not included in these statuses.

The standalone face CLI reports only processed-frame and protected-region
counts. It does not report embeddings, enrollment images, face geometry, or
model response payloads. Face-model and threshold behavior remain a local
operator concern until a product diagnostics contract is approved.

The production face integration exposes only sanitized enrollment lifecycle and
readiness codes through its protected control routes. The readiness tracker
records model-unavailable, detector-unavailable, detector-error, enrollment,
and safe-ready states for the future safety gate; it does not log images,
embeddings, geometry, or model payloads.

The reusable browser media client exposes session state, the latest source-clock
timestamp, the bounded pending-frame value, and processor or disconnect errors
in the page. It does not log camera frames, audio samples, or raw media
metadata. These are local UI signals only; no browser session status is sent to
the API or persisted.

The creator console exposes adapter-mapped session state, capability readiness,
enrollment status, safety state, permission presentation, and source/protected
handle availability. Browser adapter failures are reduced to sanitized UI
messages and do not become authorization, audit events, or persisted media
state. The console does not show raw enrollment samples, transcripts, PII
values, embeddings, or arbitrary API response bodies. Server-side media and
safety events are not yet observable because their routes remain absent.

The in-process `PrivacyGate` exposes sanitized readiness (`ready`, `degraded`, or
`unsafe`), process liveness, panic/recovery state, publication action, reason
code, processed watermark, and lag to its caller. It never logs media,
transcripts, PII values, detector payloads, or arbitrary failure text. The
`/health` route remains process liveness only and does not report privacy
readiness.

The shared video engine exposes aggregate per-stage detector calls, success,
skip, timeout, failure, duration, queue wait, pending-frame, and processing
measurements through `VideoMetrics.snapshot()`. These metrics contain no frame
payloads, coordinates, OCR text, plate values, or raw detector errors. The
production plate and OCR/PII adapters use the same sanitized success and failure
statuses; they do not add model-specific payload or matched-text logging.

The cross-modal synchronizer exposes only aggregate frame counts, protected and
no-sensitive-speech outcomes, unsafe outcomes, late audio-decision count,
buffer-overflow count, source-time buffer delay, and source-time decision lag
through `CrossModalMetrics.snapshot()`. It does not expose interval values,
transcript text, face geometry, track payloads, or model output. Late decisions,
timestamp discontinuities, unresolved face association, incomplete audio, and
buffer overflow remain explicit unsafe update/decision statuses.

`ProductionMediaIntegrationMetrics.snapshot()` exposes only aggregate window
outcomes: processed, protected, full-redact, blocked, video-failure,
audio-failure, and cross-modal-failure counts. The integration emits sanitized
publication decisions and statuses to its caller; it does not log source
payloads, transcript text, PII values, or raw processor exceptions.

## Verification

The API health, browser session, and creator-console signals are Unverified; no
runtime verification pass was run.
