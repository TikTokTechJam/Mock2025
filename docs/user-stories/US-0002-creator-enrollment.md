# US-0002 — Enroll and manage creator identity

## Actor
Creator

## Story
As a creator, I want to enroll my own face explicitly so that PrivaStream can distinguish me from bystanders and keep only my approved identity visible.

## Value
Creator enrollment enables privacy-preserving face whitelisting without requiring every detected face to be blurred.

## Acceptance Criteria
- Enrollment begins only after explicit creator action and consent.
- The creator can submit several face samples and receive clear quality/error feedback.
- Zero-face or ambiguous multi-face samples are rejected safely.
- Only the derived creator embedding and safe metadata are retained when persistence is enabled.
- Raw enrollment images are discarded after processing.
- The creator can replace or delete the enrollment.
- Missing, invalid, or ambiguous enrollment never grants whitelist access.

## Scope
- Enrollment, replacement, deletion, status, and biometric-data lifecycle.
- Creator embedding generation and matching configuration.
- UI enrollment flow and backend enrollment API.

## Out of Scope
- Multi-user identity management.
- Bystander enrollment/whitelisting.
- Long-term biometric profile management beyond the approved creator use case.

## Decisions
- Enrollment is explicit and consented.
- Ambiguous matching favors redaction.
- Embeddings are never written to ordinary logs or shown in the UI.

## Concerns
- Similarity thresholds require calibration.
- Poor lighting/angles can degrade enrollment quality.
- Embeddings are biometric-derived data and require careful storage/deletion behavior.

## Status Boundary
The #12 enrollment adapter is Implemented but Unverified: it maps the existing
face control routes, sends one consented bounded frame from the active source,
and exposes only lifecycle state. This product story remains Planned until
authorization, durable lifecycle semantics, and the user-facing journey are
integrated and verified.

## Touched By
Issues #3, #5, #12, #17, #18, #22.
