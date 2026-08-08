# US-0006 — Protect spoken PII

## Actor
Creator

## Story
As a creator, I want sensitive information spoken in my media to be detected and muted so that private information is not exposed through audio.

## Value
Spoken phone numbers, email addresses, identifiers, and other supported sensitive information can leak even when the video is visually protected.

## Acceptance Criteria
- Speech is detected without continuously transcribing silence.
- Timestamped transcription remains anchored to source-media time.
- Supported spoken PII such as phone numbers and email-like phrases can produce privacy intervals.
- Sensitive intervals are padded/merged deterministically and muted in protected output.
- Benign numbers or unrelated speech are not automatically treated as sensitive solely because they contain digits.
- Raw audio, transcripts, and matched PII are not persisted/logged by default.
- Transcription/classification lag, queue overflow, or model failure makes the affected window unsafe rather than silently passing raw speech.

## Scope
- PCM/stream adaptation, VAD/transcription integration, speech-specific normalization, shared text-PII recognition, interval mapping, and audio redaction.

## Out of Scope
- General-purpose transcript storage/search.
- Perfect transcription of every language/accent.
- Voice identity recognition.

## Decisions
- Use source-media timestamps from ingestion through redaction.
- Silence/mute is the MVP redaction action.
- Modality-independent text-PII recognition is shared with visual PII through issue #32; speech-specific normalization and timestamp mapping remain in the spoken path.

## Concerns
- Transcription latency directly affects how long audio must be buffered.
- Accents, noise, hesitations, and spoken separators can reduce accuracy.

## Status Boundary
A standalone local spoken-PII slice exists, but the complete user story remains Planned until integrated with the real protected-media session and verified end-to-end.

## Touched By
Issues #3, #8, #9, #10, #11, #13, #14, #15, #17, #20, #32.