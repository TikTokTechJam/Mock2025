# US-0004 — Protect visible license plates

## Actor
Creator

## Story
As a creator, I want visible vehicle license plates in my media to be automatically obscured so that identifying vehicle information is not exposed.

## Value
License plates are common privacy-sensitive visual identifiers in outdoor and street content.

## Acceptance Criteria
- Representative visible plates produce privacy regions in source-frame coordinates.
- Multiple plates in one frame can be protected.
- Detection coordinates map correctly after model resize/letterboxing.
- Configurable confidence and padding are applied consistently.
- Short missed detections remain protected through temporal smoothing.
- Detector failure is distinguishable from a successful frame containing no plates.
- Required plate protection fails closed when the detector is unavailable.

## Scope
- Plate detection, geometry mapping, normalized region output, temporal integration, and compositor redaction.

## Out of Scope
- Reading/storing plate numbers.
- Vehicle ownership lookup.
- Guaranteed coverage for every geography without benchmark evidence.

## Decisions
- Use a replaceable real-time detector behind the common visual-detector interface.
- Rendering and temporal smoothing remain shared pipeline responsibilities.

## Concerns
- Small, angled, low-light, occluded, or region-specific plates may reduce recall.
- Model licensing/provenance must be recorded.

## Status Boundary
Planned product story until integrated and benchmarked on representative fixtures.

## Touched By
Issues #3, #4, #6, #13, #14, #15, #17, #19.