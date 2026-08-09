# Shared Text-PII Recognizer

## Purpose

This document owns the current modality-neutral text-PII recognition contract.
The recognizer accepts normalized text from a visual OCR path, a spoken
transcript path, or another approved text adapter and returns safe metadata for
the caller to map back to media.

It does not own OCR normalization, speech token normalization, media geometry,
source timestamps, redaction rendering, transport, persistence, or the final
publication-safety decision.

## Availability and verification

The deterministic recognizer, configured identity/payment formats, contextual
classifier boundary, OCR integration, spoken-PII integration, and deterministic
fixtures are Implemented in source. Runtime, model, language-coverage, and
protected-output verification are Unverified because no verification pass was
run for this change.

## Ownership and data flow

```text
modality-specific extraction
        |
        v
modality-specific normalization
        |
        v
TextPiiRecognizer.recognize()
        |
        v
safe PiiSpan metadata only
        |
        +--> OCR block -> normalized video privacy region
        |
        +--> transcript words -> source-timestamped audio interval
```

The shared service is implemented at
`apps/api/src/privastream_api/privacy/text_pii.py` and is re-exported from
`privastream_api.privacy`. Visual behavior is owned by
`privacy/vision/ocr_detector.py`; spoken behavior is owned by
`pipeline/spoken_pii.py`.

## Recognition taxonomy

The canonical categories are:

| Category | Default behavior | Meaning |
| --- | --- | --- |
| `email` | Enabled deterministic matcher | Email-shaped text. |
| `phone_number` | Enabled deterministic matcher | A candidate containing 8 to 15 digits, with common separators and an optional leading `+`. |
| `government_id` | Explicit configuration only | A government or identity format supplied by an approved pattern. |
| `payment_identifier` | Explicit configuration only | A payment or account identifier supplied by an approved pattern. |
| `postal_address` | Contextual classifier only | An address-like span returned by an injected contextual classifier. No default classifier is bundled. |
| `custom_sensitive_text` | Contextual or downstream composite category | A custom sensitive span supplied by an injected classifier, or a visual block containing multiple categories. |

The default recognizer does not classify arbitrary natural-language text as
sensitive. In particular, date-shaped values, ordinary decimal prices, and
short or random numeric strings are not phone matches merely because they
contain digits.

## Canonical output

Each match is a frozen `PiiSpan` containing only:

| Field | Contract |
| --- | --- |
| `category` | One of the canonical categories above. |
| `confidence` | Finite numeric value in the inclusive range `[0, 1]`. |
| `start`, `end` | Non-empty character offsets into the normalized input text; `end` is exclusive. |
| `source` | A non-empty, non-sensitive recognizer identifier such as a configured pattern name. |
| `unit` | Always `"character"`. |

The span does not contain the matched text. Callers must use the offsets only
while the in-memory normalized input is available and must not persist or log
the corresponding value.

The service returns a tuple sorted by character position. Candidate matches are
ordered deterministically by start position, longer span first, category, and
source. Overlapping candidates are resolved by keeping the first candidate in
that order. This keeps output stable when a configured pattern overlaps a
structured match or a contextual classifier result.

## Deterministic configuration

`TextPiiRecognizerConfig` controls the structured matchers:

| Setting | Default | Behavior |
| --- | --- | --- |
| `email_enabled` | `True` | Enables the email matcher. |
| `phone_enabled` | `True` | Enables the phone matcher. |
| `email_confidence` | `0.99` | Confidence assigned to email matches. |
| `phone_confidence` | `0.95` | Confidence assigned to phone matches. |
| `phone_min_digits` | `8` | Minimum digit count after separators are removed. |
| `phone_max_digits` | `15` | Maximum digit count after separators are removed. |
| `configured_patterns` | Empty | Explicit `government_id` or `payment_identifier` regex patterns. |

Configured patterns use `ConfiguredTextPiiPattern` and must declare a canonical
category, a valid case-insensitive regular expression, a non-sensitive source
identifier, and a confidence value. For example, an approved country-specific
format can be configured without placing any actual identifier value in the
configuration:

```python
ConfiguredTextPiiPattern(
    category="government_id",
    pattern=r"\bSG\d{7}[A-Z]\b",
    source="configured-country-id",
)
```

Pattern selection, approval, versioning, and operational rollout remain
configuration responsibilities. The recognizer does not infer that every
numeric string is an identity or payment identifier.

## Contextual classifier boundary

`ContextualTextPiiClassifier` is a replaceable protocol for categories that
cannot be safely recognized from structure alone. An implementation receives
normalized text and optional non-sensitive context, then returns validated
`PiiSpan` values. It exposes a source identifier but does not expose matched
text through the result contract.

The shared service does not select a model family, download model assets, or
provide a default address/entity model. A contextual classifier is therefore
an explicit dependency and must be treated as unavailable when it cannot run.

## Failure semantics

An empty result and a recognizer failure have different meanings:

| Situation | Result | Required interpretation |
| --- | --- | --- |
| Input is empty or contains no supported match | `()` | Recognition completed and found no supported span. |
| Contextual classifier is unavailable | `TextPiiRecognizerUnavailable` | The configured contextual capability could not run. |
| Contextual classifier raises, returns `None`, returns an invalid span, or returns an out-of-range span | `TextPiiRecognizerExecutionError` | Recognition failed; it is not evidence that the text is safe. |
| Caller receives a recognizer failure | Modality-specific unavailable or execution error | Preserve the explicit failure and let the required-protection policy fail closed. |

The recognizer never converts a contextual failure into `()`.

## Modality handoff

### Visual OCR

`OcrPiiDetector` owns OCR confidence filtering, Unicode/whitespace
normalization, polygon handling, cadence, and short region-TTL reuse. It sends
the normalized OCR block to the shared recognizer. A match causes the OCR block
to become a normalized video privacy region; the current visual path uses the
whole block when character-to-sub-box mapping is unavailable. Multiple
categories in one block are emitted as `custom_sensitive_text` so the caller
does not claim false character-level precision. The production
`OcrVideoDetector` reuses this path without standalone cadence, TTL, or padding
and registers it with the shared video scheduler, which owns those policies.

OCR engine failures remain detector failures. Shared recognizer unavailability
is mapped to `DetectorUnavailableError`; recognizer execution failures are
mapped to `DetectorExecutionError`.

### Spoken transcript

`pipeline/spoken_pii.py` owns spoken-token normalization, source-media word
timestamps, interval padding, clamping, sorting, and merge behavior. It joins
normalized transcript words while retaining character-to-word offsets, sends
the joined text to the shared recognizer, and maps each returned span back to
the covered source-time words. The resulting intervals use
`kind="spoken_pii"` and retain the matched category as the safe `reason` field.
`pipeline/audio.py` injects this same recognizer into the production-shaped
audio pipeline and applies the resulting intervals to source chunks; it does
not maintain a second structured phone, email, identity, or payment pattern
set.

Speech/VAD/transcription failures remain audio-path failures. A recognizer
failure must not be treated as a successful transcript with no sensitive
intervals.

### Cross-modal visual augmentation

`pipeline/cross_modal.py` consumes only the resulting source-timestamped
`AudioRedactionInterval` values. It applies its own bounded source-time
lookahead and configured pre/post synchronization padding, then returns a
visual `spoken_pii` region for an associated face or an explicit unsafe result
when no conservative association is possible. It does not recognize text,
mutate audio, expose matched values, or decide publication safety.

## Data handling and limits

- Raw OCR text, transcript text, and matched values remain in memory only for
  the active recognition call and are not returned by the recognizer.
- The recognizer does not log or persist input text, matched values, or
  classifier payloads. Downstream diagnostics may expose only safe category,
  confidence, source, and detector-status metadata.
- The recognizer is not a general document-understanding or language-detection
  system and does not guarantee coverage for languages, scripts, obfuscation,
  OCR errors, accents, or ambiguous context outside configured support.
- Contextual categories remain unavailable by default until an approved
  classifier is injected and its behavior is separately verified.
- A local demo or standalone detector result is not proof that a protected
  output is safe; the platform safety boundary still owns required-protection
  and publication decisions.

## Source and tests

- Implementation: `apps/api/src/privastream_api/privacy/text_pii.py`
- Public exports: `apps/api/src/privastream_api/privacy/__init__.py`
- OCR adapter: `apps/api/src/privastream_api/privacy/vision/ocr_detector.py`
- Production OCR adapter: `OcrVideoDetector` and `register_ocr_detector` in the same module
- Spoken adapter: `apps/api/src/privastream_api/pipeline/spoken_pii.py`
- Shared recognizer fixtures: `apps/api/tests/privacy/test_text_pii.py`
- OCR integration fixtures: `apps/api/tests/privacy/vision/test_ocr_detector.py`

The deterministic fixtures document intended behavior. No runtime verification
pass has exercised the shared recognizer, OCR model, production OCR adapter,
protected output, services, or browser path; verification therefore remains
Unverified.
