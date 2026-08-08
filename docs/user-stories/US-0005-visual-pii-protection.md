# US-0005 — Protect visual PII

## Actor
Creator

## Story
As a creator, I want sensitive text visible in my media to be detected and obscured so that information such as phone numbers, email addresses, and supported identifiers is not exposed.

## Value
Sensitive information frequently appears on screens, documents, signs, packages, and backgrounds even when the creator did not intend to publish it.

## Acceptance Criteria
- OCR detects text with a source region and confidence.
- Structured PII such as supported emails and phone numbers can be classified as sensitive.
- Benign OCR text is not automatically redacted merely because text exists.
- Sensitive spans map back to the correct visual region and are protected.
- Raw OCR text and detected PII values are not written to ordinary logs.
- OCR/classifier failure is distinct from successful processing with no sensitive text.
- Required visual-PII protection fails closed when processing is unsafe.

## Scope
- Scene-text OCR, OCR-specific normalization and visual-region mapping, shared text-PII recognition, and compositor integration.

## Out of Scope
- General document understanding.
- Persisting searchable OCR transcripts.
- Perfect character-level masking when block-level redaction is safer.

## Decisions
- Use a two-stage OCR then PII-classification design.
- The initial renderer protects the full OCR block/line containing sensitive information.
- Modality-independent text-PII recognition is shared with spoken PII through issue #32 rather than implemented separately in the OCR path.

## Concerns
- OCR quality, language coverage, rotation, low contrast, and false-positive-like numeric text.
- Contextual categories such as addresses can be harder to classify reliably.

## Status Boundary
Planned product story until the OCR/classification path is integrated and verified through protected output.

## Touched By
Issues #3, #4, #7, #13, #14, #15, #17, #19, #32.