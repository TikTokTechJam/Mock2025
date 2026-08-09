"""Tracking, EMA stabilization, and hold-over emission.

Two jobs (`PROJECT_OVERVIEW.md` §3.5):

* **Visual stability** — raw per-frame boxes jitter, which makes the redacted
  region shimmer and draws attention to it. An EMA smooths the emitted box.
* **Coverage continuity** — a track carries protection through frames where
  detection flickers. A tracking failure must not immediately expose a region
  that was protected in the previous frame (`SECURITY.md` §14.1).

Because the output contract has no ``expires_at``, continued protection is
expressed as continued emission: a lost track keeps producing its last
stabilized box for the hold-over window, then stops
(`INTEGRATION_GUIDE.md` §3.5). Emitting past that window would be presenting an
expired region as active, which is invalid output.

Boxes here are stabilized but **not** padded. Padding is applied at emission so
live and held-over regions get the same margin.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .classification import FaceClassification
from .config import FaceBlurConfig
from .geometry import NormalizedBox


@dataclass(frozen=True, slots=True)
class FaceObservation:
    """One classified face in the current frame."""

    box: NormalizedBox
    classification: FaceClassification
    confidence: float


@dataclass(frozen=True, slots=True)
class EmittedRegion:
    """A stabilized region the detector must emit for the current frame."""

    track_id: str
    box: NormalizedBox
    confidence: float
    held_over: bool
    """Whether this frame's region comes from hold-over rather than a live
    detection. It is a protection decision either way, not a weakened guess, and
    carries the same confidence semantics (`INTEGRATION_GUIDE.md` §3.5)."""


@dataclass(slots=True)
class _Track:
    track_id: str
    box: NormalizedBox
    confidence: float
    last_seen_ms: int
    protected: bool


class FaceTracker:
    """Associates faces across frames and owns the temporal protection decision."""

    def __init__(self, config: FaceBlurConfig | None = None) -> None:
        self._config = config or FaceBlurConfig()
        self._tracks: dict[str, _Track] = {}
        self._issued = 0

    def __repr__(self) -> str:
        return f"{type(self).__name__}(tracks={len(self._tracks)})"

    @property
    def track_count(self) -> int:
        return len(self._tracks)

    def reset(self) -> None:
        """Forget every track. Track ids are still never reused afterwards."""

        self._tracks.clear()

    def update(
        self, observations: Sequence[FaceObservation], timestamp_ms: int
    ) -> tuple[EmittedRegion, ...]:
        """Advance every track to ``timestamp_ms`` and return what to emit."""

        assignments = self._assign(observations)
        seen: set[str] = set()
        for index, observation in enumerate(observations):
            track_id = assignments.get(index)
            if track_id is None:
                track_id = self._new_track(observation, timestamp_ms)
            else:
                self._advance(self._tracks[track_id], observation, timestamp_ms)
            seen.add(track_id)

        emitted: list[EmittedRegion] = []
        expired: list[str] = []
        for track_id, track in self._tracks.items():
            if track_id in seen:
                if track.protected:
                    emitted.append(
                        EmittedRegion(
                            track_id=track_id,
                            box=track.box,
                            confidence=track.confidence,
                            held_over=False,
                        )
                    )
                continue
            # A frame may arrive out of order; treat that as no elapsed time
            # rather than as an aged-out track, because ending protection early
            # is the failure that matters.
            elapsed_ms = max(0, timestamp_ms - track.last_seen_ms)
            if elapsed_ms > self._config.hold_over_ms:
                expired.append(track_id)
                continue
            if track.protected:
                emitted.append(
                    EmittedRegion(
                        track_id=track_id,
                        box=track.box,
                        confidence=track.confidence,
                        held_over=True,
                    )
                )
        for track_id in expired:
            del self._tracks[track_id]
        self._enforce_capacity()
        return tuple(emitted)

    def _assign(self, observations: Sequence[FaceObservation]) -> dict[int, str]:
        """Match observations to tracks greedily, strongest overlap first."""

        candidates: list[tuple[float, int, str]] = []
        for index, observation in enumerate(observations):
            for track_id, track in self._tracks.items():
                overlap = observation.box.iou(track.box)
                if overlap >= self._config.track_match_iou:
                    candidates.append((overlap, index, track_id))
        # Ties resolve by observation order then track id, so the same input
        # always produces the same association.
        candidates.sort(key=lambda candidate: (-candidate[0], candidate[1], candidate[2]))
        assignments: dict[int, str] = {}
        taken: set[str] = set()
        for _, index, track_id in candidates:
            if index in assignments or track_id in taken:
                continue
            assignments[index] = track_id
            taken.add(track_id)
        return assignments

    def _new_track(self, observation: FaceObservation, timestamp_ms: int) -> str:
        self._issued += 1
        track_id = f"face-{self._issued:08d}"
        self._tracks[track_id] = _Track(
            track_id=track_id,
            box=observation.box,
            confidence=observation.confidence,
            last_seen_ms=timestamp_ms,
            protected=observation.classification.requires_redaction,
        )
        return track_id

    def _advance(
        self, track: _Track, observation: FaceObservation, timestamp_ms: int
    ) -> None:
        track.box = observation.box.smoothed(track.box, self._config.ema_alpha)
        track.confidence = observation.confidence
        track.last_seen_ms = timestamp_ms
        track.protected = observation.classification.requires_redaction

    def _enforce_capacity(self) -> None:
        """Keep tracker state bounded, dropping the least protective tracks first.

        Unprotected tracks go before protected ones, and older before newer, so
        the capacity bound costs coverage only after every whitelisted and every
        more recently seen track has already been released.
        """

        excess = len(self._tracks) - self._config.max_tracked_faces
        if excess <= 0:
            return
        ordered = sorted(
            self._tracks.values(), key=lambda track: (track.protected, track.last_seen_ms)
        )
        for track in ordered[:excess]:
            del self._tracks[track.track_id]
