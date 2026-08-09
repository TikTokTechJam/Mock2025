# US-0007 — Synchronize sensitive speech with visual protection

## Actor
Creator

## Story
As a creator, I want sensitive spoken information to trigger synchronized visual protection so that lip movement or the associated face does not reveal information that the audio path has muted.

## Value
Audio-only muting can still leave visual cues. Coordinated A/V protection strengthens privacy for sensitive speech.

## Acceptance Criteria
- Audio and video are mapped to one documented source-media timeline.
- Sensitive audio intervals deterministically map to overlapping video frames.
- Protected video waits for the necessary audio decision within a bounded delay budget.
- A reliable speaker/face association may redact only the mouth/lower-face region.
- Ambiguous speaker association uses a more conservative face/broader fallback.
- Buffer overflow, timestamp discontinuity, or classification arriving too late creates an unsafe state rather than knowingly releasing an unprotected sensitive-speech frame.
- Added latency and fallback counts are observable without exposing PII values.

## Scope
- Shared media clock, audio-interval index, protected-video delay buffer, mouth/lower-face region generation, and conservative fallback behavior.

## Out of Scope
- Full speaker diarization research.
- Sophisticated audiovisual identity recognition unless later required.

## Decisions
- Privacy becomes more conservative as speaker-association confidence decreases.
- Wall-clock processing time is not used for A/V overlap decisions.
- Bounded buffering is an explicit privacy/latency trade-off.

## Concerns
- Transcription delay can materially increase video latency.
- Active speaker association is difficult in multi-person scenes.

## Status Boundary
The cross-modal synchronization primitive is Implemented but Unverified. The
full story remains Planned at the product boundary until detector, transport,
and publication-safety integration is implemented and explicitly verified.

## Touched By
Issues #4, #9, #10, #13, #15, #17.
