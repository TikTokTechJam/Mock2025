# API Contract

## Purpose

This document owns the public interface contract between trusted services,
clients, and integrations.

## Current interface

The API exposes one unauthenticated process-health endpoint:

GET /health

Response:

~~~json
{
  "status": "ok",
  "service": "privastream-api"
}
~~~

The response is served by the FastAPI process and does not check PostgreSQL,
media ingestion, detector execution, redaction, real-time transport, or any
other dependency. The current
browser media loopback and creator-console façades are entirely local to the web
page and do not add an HTTP signaling or media route. The protected production
face control surface is documented below.

The production face control surface is available at:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/privacy/face/enrollment` | Return safe lifecycle and enrollment metadata. |
| `POST` | `/privacy/face/enrollment` | Create one bounded, explicitly consented enrollment. |
| `PUT` | `/privacy/face/enrollment` | Replace the existing enrollment atomically through #18. |
| `DELETE` | `/privacy/face/enrollment` | Delete the active enrollment and return to `not_enrolled`. |
| `GET` | `/privacy/face/readiness` | Return the sanitized capability input for #13. |

All face routes require an injected server-side creator authorizer. The default
application uses a deny-by-default dependency and returns `503` until a trusted
host supplies that boundary. This is intentional: an explicit multipart
`consent=true` field is required in addition to authorization, but is not a
replacement for authorization.

Create and replace accept `multipart/form-data` with repeated `images` files and
the `consent=true` form field. Samples are bounded by the #18 enrollment limits
and the API byte limit. Responses contain only lifecycle state, enrollment ID,
sample count, embedding dimension, timestamps, sanitized rejection reasons, and
readiness codes; they never contain images or embedding values.

The current repository is process-local. Durable database persistence and the
production authorization provider remain separate follow-up boundaries. Detector
or model failures return a sanitized error and are recorded as not-ready rather
than being represented as zero faces.

The standalone spoken-PII module is intentionally not an HTTP endpoint. Its
local command accepts bounded PCM16 WAV input and writes a muted WAV result; the
module's detailed input, interval, and renderer contract belongs to
`ARCHITECTURE.md` until an approved API operation is defined.

## Errors and ownership

The face control routes validate bounded input, require explicit consent, and
enforce the injected creator authorization dependency. They return `400` for
missing consent, `404` for replacing a missing enrollment, `409` for duplicate
create, `413` for oversized/bounded input, `422` for rejected samples, and `503`
for unavailable model or detector failure. The route does not decide whether a
protected media frame may be published; that remains #13's responsibility.

## Availability

The health contract, production face adapter, process-local enrollment lifecycle,
and protected control routes are Implemented in source. Durable persistence,
authorization-provider wiring, #13 publication decisions, and runtime
verification are Unverified or Planned at their respective boundaries.
