# US-0003 — Protect non-creator faces

## Actor
Creator

## Story
As a creator, I want non-whitelisted faces in my media to be automatically obscured so that bystanders are not exposed in the protected output.

## Value
This is a primary privacy guarantee of PrivaStream and the main use of creator face enrollment.

## Acceptance Criteria
- With no valid creator enrollment, every detected face is treated as private.
- A confidently matched enrolled creator may remain visible.
- Bystander, unknown, low-confidence, or ambiguous faces are redacted.
- Face regions remain protected across short missed detections/skipped inference frames.
- Region padding covers the complete face sufficiently for the selected redaction style.
- Face-model failure or unsafe matching cannot produce a false-safe result.

## Scope
- Face detection, creator matching, region generation, short temporal stability, and rendering through the common compositor.

## Out of Scope
- Identifying who a bystander is.
- Persisting bystander embeddings.
- General face recognition/search.

## Decisions
- Privacy transitions are asymmetric: becoming private is faster than becoming whitelisted.
- Face detectors return normalized privacy regions; they do not own rendering.
- Unknown faces are protected by default.

## Concerns
- False creator matches are privacy-critical.
- Fast motion, occlusion, masks, and extreme pose can reduce detection/matching quality.

## Status Boundary
Planned product story until integrated through the protected media path and verified with representative fixtures.

## Touched By
Issues #3, #4, #5, #13, #15, #17, #18.