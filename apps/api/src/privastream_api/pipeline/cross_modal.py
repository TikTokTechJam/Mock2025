"""Source-timeline synchronization between spoken PII and video regions.

This module owns only the cross-modal coordination boundary. It consumes
source-timestamped audio intervals and existing face geometry, then returns
sanitized visual augmentations or explicit unsafe results. Detector execution,
audio muting, video composition, transport, and final publication policy stay
with their owning modules.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Literal

from privastream_api.pipeline.contracts import (
    AudioRedactionInterval,
    VideoFrame,
    VideoRegionDetection,
)
from privastream_api.pipeline.video import VideoPrivacyRegion

CrossModalDecisionStatus = Literal[
    "no_sensitive_speech",
    "protected",
    "unsafe_buffer_overflow",
    "unsafe_audio_incomplete",
    "unsafe_no_face_association",
    "unsafe_speaker_association",
    "unsafe_timestamp_discontinuity",
]
CrossModalUpdateStatus = Literal["pending", "released", "unsafe"]
CrossModalAssociation = Literal["none", "mouth", "face_fallback", "unsafe"]


def _validate_box(
    x: float, y: float, width: float, height: float, *, name: str
) -> None:
    values = (x, y, width, height)
    if any(not isfinite(value) for value in values):
        raise ValueError(f"{name} coordinates must be finite")
    if min(values) < 0 or width <= 0 or height <= 0:
        raise ValueError(f"{name} must be a positive normalized region")
    if x + width > 1 or y + height > 1:
        raise ValueError(f"{name} must stay within normalized frame bounds")


@dataclass(frozen=True, slots=True)
class FaceGeometry:
    """Existing normalized face geometry supplied by a face pipeline.

    ``mouth_region`` is optional because the current face adapter exposes a
    normalized face box rather than landmarks. When absent, the synchronizer
    derives a conservative lower-face region from that box. The optional
    active-speaker score is a non-sensitive association hint supplied by a
    future face/landmark adapter; it is never inferred here.
    """

    x: float
    y: float
    width: float
    height: float
    confidence: float
    track_id: str | None = None
    mouth_region: tuple[float, float, float, float] | None = None
    active_speaker_score: float | None = None

    def __post_init__(self) -> None:
        _validate_box(self.x, self.y, self.width, self.height, name="face")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("face confidence must be between 0 and 1")
        if self.track_id is not None and not self.track_id.strip():
            object.__setattr__(self, "track_id", None)
        if self.mouth_region is not None:
            _validate_box(*self.mouth_region, name="mouth")
            mouth_x, mouth_y, mouth_width, mouth_height = self.mouth_region
            if (
                mouth_x < self.x
                or mouth_y < self.y
                or mouth_x + mouth_width > self.x + self.width
                or mouth_y + mouth_height > self.y + self.height
            ):
                raise ValueError("mouth region must stay inside its face region")
        if self.active_speaker_score is not None and (
            not isfinite(self.active_speaker_score)
            or not 0 <= self.active_speaker_score <= 1
        ):
            raise ValueError("active-speaker score must be between 0 and 1")

    @classmethod
    def from_region(
        cls, region: VideoRegionDetection | VideoPrivacyRegion
    ) -> "FaceGeometry":
        """Adapt an existing canonical face region without invoking a detector."""

        detection = region.to_detection() if isinstance(region, VideoPrivacyRegion) else region
        if detection.kind not in {"face", "face_bystander"}:
            raise ValueError("cross-modal face geometry must come from a face region")
        return cls(
            x=detection.x,
            y=detection.y,
            width=detection.width,
            height=detection.height,
            confidence=detection.confidence,
            track_id=detection.track_id,
        )

    def lower_face_region(self) -> tuple[float, float, float, float]:
        """Return explicit mouth geometry or a conservative lower-face estimate."""

        if self.mouth_region is not None:
            return self.mouth_region
        return (
            self.x + self.width * 0.15,
            self.y + self.height * 0.55,
            self.width * 0.70,
            self.height * 0.40,
        )


@dataclass(frozen=True, slots=True)
class CrossModalConfig:
    """Bounds and source-time policy for cross-modal synchronization."""

    frame_duration_ms: int = 33
    pre_padding_ms: int = 50
    post_padding_ms: int = 50
    max_pending_frames: int = 30
    max_buffer_ms: int = 1_000
    minimum_face_confidence: float = 0.5
    active_speaker_min_score: float = 0.7
    active_speaker_margin: float = 0.1
    detector_id: str = "cross-modal-spoken-pii"

    def __post_init__(self) -> None:
        if self.frame_duration_ms <= 0:
            raise ValueError("frame_duration_ms must be positive")
        if self.pre_padding_ms < 0 or self.post_padding_ms < 0:
            raise ValueError("synchronization padding must be non-negative")
        if self.max_pending_frames <= 0 or self.max_buffer_ms <= 0:
            raise ValueError("cross-modal buffer limits must be positive")
        for name, value in (
            ("minimum_face_confidence", self.minimum_face_confidence),
            ("active_speaker_min_score", self.active_speaker_min_score),
            ("active_speaker_margin", self.active_speaker_margin),
        ):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if not self.detector_id.strip():
            raise ValueError("detector_id must not be empty")


@dataclass(frozen=True, slots=True)
class CrossModalDecision:
    """One source-frame cross-modal result, separate from publication safety."""

    sequence: int
    frame_timestamp_ms: int
    status: CrossModalDecisionStatus
    regions: tuple[VideoPrivacyRegion, ...] = ()
    intervals: tuple[AudioRedactionInterval, ...] = ()
    association: CrossModalAssociation = "none"
    reason_code: str | None = None
    audio_watermark_ms: int | None = None
    required_audio_watermark_ms: int | None = None
    buffer_delay_ms: int | None = None
    decision_lag_ms: int | None = None

    @property
    def cross_modal_complete(self) -> bool:
        """Whether this layer completed a non-unsafe decision for the frame."""

        return not self.status.startswith("unsafe_")


@dataclass(frozen=True, slots=True)
class CrossModalUpdate:
    """Results emitted by one frame or audio update."""

    status: CrossModalUpdateStatus
    decisions: tuple[CrossModalDecision, ...] = ()
    late_intervals: tuple[AudioRedactionInterval, ...] = ()
    reason_code: str | None = None
    pending_frames: int = 0


@dataclass(slots=True)
class CrossModalMetrics:
    """Aggregate timing and failure measurements without media or PII values."""

    frames_submitted: int = 0
    frames_released: int = 0
    protected_frames: int = 0
    frames_without_sensitive_speech: int = 0
    unsafe_frames: int = 0
    late_audio_decisions: int = 0
    buffer_overflow_frames: int = 0
    total_buffer_delay_ms: int = 0
    max_buffer_delay_ms: int = 0
    max_decision_lag_ms: int = 0

    def record_decision(self, decision: CrossModalDecision) -> None:
        self.frames_released += 1
        if decision.status == "protected":
            self.protected_frames += 1
        elif decision.status == "no_sensitive_speech":
            self.frames_without_sensitive_speech += 1
        else:
            self.unsafe_frames += 1
        if decision.buffer_delay_ms is not None:
            self.total_buffer_delay_ms += decision.buffer_delay_ms
            self.max_buffer_delay_ms = max(
                self.max_buffer_delay_ms, decision.buffer_delay_ms
            )
        if decision.decision_lag_ms is not None:
            self.max_decision_lag_ms = max(
                self.max_decision_lag_ms, decision.decision_lag_ms
            )

    def snapshot(self) -> dict[str, int]:
        """Return sanitized aggregate metrics for logs or readiness consumers."""

        return {
            "frames_submitted": self.frames_submitted,
            "frames_released": self.frames_released,
            "protected_frames": self.protected_frames,
            "frames_without_sensitive_speech": self.frames_without_sensitive_speech,
            "unsafe_frames": self.unsafe_frames,
            "late_audio_decisions": self.late_audio_decisions,
            "buffer_overflow_frames": self.buffer_overflow_frames,
            "total_buffer_delay_ms": self.total_buffer_delay_ms,
            "max_buffer_delay_ms": self.max_buffer_delay_ms,
            "max_decision_lag_ms": self.max_decision_lag_ms,
        }


class AudioIntervalIndex:
    """Deterministic, de-duplicated source-time index for audio intervals."""

    def __init__(self) -> None:
        self._intervals: list[AudioRedactionInterval] = []
        self._known: set[AudioRedactionInterval] = set()

    def add(
        self, intervals: Sequence[AudioRedactionInterval]
    ) -> tuple[AudioRedactionInterval, ...]:
        added: list[AudioRedactionInterval] = []
        for interval in intervals:
            if not isinstance(interval, AudioRedactionInterval):
                raise TypeError("audio interval index accepts AudioRedactionInterval values")
            if interval in self._known:
                continue
            self._known.add(interval)
            self._intervals.append(interval)
            added.append(interval)
        if added:
            self._intervals.sort(
                key=lambda item: (
                    item.start_ms,
                    item.end_ms,
                    item.detector,
                    item.reason or "",
                )
            )
        return tuple(added)

    def query(
        self,
        frame_start_ms: int,
        frame_end_ms: int,
        *,
        pre_padding_ms: int,
        post_padding_ms: int,
    ) -> tuple[AudioRedactionInterval, ...]:
        """Return intervals whose padded source range overlaps one frame."""

        upper_start = frame_end_ms + pre_padding_ms
        upper_index = bisect_right(
            [interval.start_ms for interval in self._intervals], upper_start
        )
        matches = (
            interval
            for interval in self._intervals[:upper_index]
            if interval.end_ms + post_padding_ms > frame_start_ms
            and interval.start_ms - pre_padding_ms < frame_end_ms
        )
        return tuple(matches)


@dataclass(frozen=True, slots=True)
class _PendingFrame:
    sequence: int
    frame: VideoFrame
    faces: tuple[FaceGeometry, ...]


class CrossModalSynchronizer:
    """Bounded source-timeline coordinator for spoken-PII visual augmentation."""

    def __init__(
        self,
        config: CrossModalConfig | None = None,
        *,
        metrics: CrossModalMetrics | None = None,
    ) -> None:
        self.config = config or CrossModalConfig()
        self.metrics = metrics or CrossModalMetrics()
        self.interval_index = AudioIntervalIndex()
        self._pending: deque[_PendingFrame] = deque()
        self._audio_watermark_ms: int | None = None
        self._last_frame_timestamp_ms = -1
        self._next_sequence = 0

    @property
    def pending_frames(self) -> int:
        return len(self._pending)

    @property
    def audio_watermark_ms(self) -> int | None:
        return self._audio_watermark_ms

    def submit_frame(
        self, frame: VideoFrame, faces: Sequence[FaceGeometry]
    ) -> CrossModalUpdate:
        """Buffer one source frame and release it when audio coverage is known."""

        if frame.timestamp_ms < self._last_frame_timestamp_ms:
            return self._fail_pending("unsafe_timestamp_discontinuity")
        try:
            face_values = tuple(faces)
            if any(not isinstance(face, FaceGeometry) for face in face_values):
                raise TypeError("faces must contain FaceGeometry values")
        except (TypeError, ValueError):
            return self._fail_pending("unsafe_speaker_association")

        sequence = self._next_sequence
        self._next_sequence += 1
        self._last_frame_timestamp_ms = frame.timestamp_ms
        self.metrics.frames_submitted += 1
        self._pending.append(_PendingFrame(sequence, frame, face_values))

        decisions = list(self._release_ready())
        decisions.extend(self._release_overflowed())
        return self._update(decisions)

    def ingest_audio(
        self,
        intervals: Sequence[AudioRedactionInterval],
        *,
        watermark_ms: int,
    ) -> CrossModalUpdate:
        """Index audio decisions and release frames covered by the watermark."""

        if watermark_ms < 0:
            return self._fail_pending("unsafe_timestamp_discontinuity")
        previous_watermark = self._audio_watermark_ms
        if previous_watermark is not None and watermark_ms < previous_watermark:
            return self._fail_pending("unsafe_timestamp_discontinuity")
        try:
            interval_values = tuple(intervals)
            if any(
                not isinstance(interval, AudioRedactionInterval)
                or interval.end_ms > watermark_ms
                for interval in interval_values
            ):
                raise ValueError("audio interval exceeds its source watermark")
            new_intervals = self.interval_index.add(interval_values)
        except (TypeError, ValueError):
            return self._fail_pending("unsafe_timestamp_discontinuity")

        late_intervals = (
            tuple(
                interval
                for interval in new_intervals
                if previous_watermark is not None and interval.end_ms <= previous_watermark
            )
            if previous_watermark is not None
            else ()
        )
        self._audio_watermark_ms = watermark_ms
        decisions = list(self._release_ready())
        decisions.extend(self._release_overflowed())
        if late_intervals:
            self.metrics.late_audio_decisions += len(late_intervals)
        return self._update(decisions, late_intervals=late_intervals)

    def flush(self) -> CrossModalUpdate:
        """Resolve frames still waiting at an input boundary as unsafe."""

        return self._fail_pending("unsafe_audio_incomplete")

    def _release_ready(self) -> tuple[CrossModalDecision, ...]:
        if self._audio_watermark_ms is None:
            return ()
        released: list[CrossModalDecision] = []
        while self._pending:
            pending = self._pending[0]
            required_watermark = self._required_watermark(pending.frame)
            if self._audio_watermark_ms < required_watermark:
                break
            self._pending.popleft()
            decision = self._evaluate(pending, required_watermark)
            self.metrics.record_decision(decision)
            released.append(decision)
        return tuple(released)

    def _release_overflowed(self) -> tuple[CrossModalDecision, ...]:
        released: list[CrossModalDecision] = []
        while self._pending and self._buffer_exceeded():
            pending = self._pending.popleft()
            decision = self._unsafe_decision(
                pending,
                "unsafe_buffer_overflow",
                self._required_watermark(pending.frame),
            )
            self.metrics.buffer_overflow_frames += 1
            self.metrics.record_decision(decision)
            released.append(decision)
        return tuple(released)

    def _buffer_exceeded(self) -> bool:
        if len(self._pending) > self.config.max_pending_frames:
            return True
        if len(self._pending) < 2:
            return False
        return (
            self._pending[-1].frame.timestamp_ms
            - self._pending[0].frame.timestamp_ms
            > self.config.max_buffer_ms
        )

    def _evaluate(
        self, pending: _PendingFrame, required_watermark: int
    ) -> CrossModalDecision:
        frame_start = pending.frame.timestamp_ms
        frame_end = frame_start + self.config.frame_duration_ms
        intervals = self.interval_index.query(
            frame_start,
            frame_end,
            pre_padding_ms=self.config.pre_padding_ms,
            post_padding_ms=self.config.post_padding_ms,
        )
        delay = max(0, (self._audio_watermark_ms or 0) - frame_start)
        lag = max(0, (self._audio_watermark_ms or 0) - required_watermark)
        if not intervals:
            return CrossModalDecision(
                sequence=pending.sequence,
                frame_timestamp_ms=frame_start,
                status="no_sensitive_speech",
                audio_watermark_ms=self._audio_watermark_ms,
                required_audio_watermark_ms=required_watermark,
                buffer_delay_ms=delay,
                decision_lag_ms=lag,
            )

        association = self._associate(pending.faces)
        if association is None:
            return self._unsafe_decision(
                pending,
                "unsafe_no_face_association",
                required_watermark,
                intervals=intervals,
                delay=delay,
                lag=lag,
            )
        mode, faces = association
        confidence = min(
            interval.confidence for interval in intervals
        )
        regions = tuple(
            self._region_for_face(
                frame_timestamp_ms=frame_start,
                face=face,
                confidence=min(confidence, face.confidence),
                box=face.lower_face_region() if mode == "mouth" else None,
            )
            for face in faces
        )
        return CrossModalDecision(
            sequence=pending.sequence,
            frame_timestamp_ms=frame_start,
            status="protected",
            regions=regions,
            intervals=intervals,
            association=mode,
            audio_watermark_ms=self._audio_watermark_ms,
            required_audio_watermark_ms=required_watermark,
            buffer_delay_ms=delay,
            decision_lag_ms=lag,
        )

    def _associate(
        self, faces: tuple[FaceGeometry, ...]
    ) -> tuple[Literal["mouth", "face_fallback"], tuple[FaceGeometry, ...]] | None:
        if not faces:
            return None
        if len(faces) == 1:
            if faces[0].confidence < self.config.minimum_face_confidence:
                return None
            return "mouth", faces

        scored = sorted(
            (
                face
                for face in faces
                if face.active_speaker_score is not None
            ),
            key=lambda face: face.active_speaker_score or 0,
            reverse=True,
        )
        if scored:
            top = scored[0]
            second_score = scored[1].active_speaker_score if len(scored) > 1 else None
            is_unique = second_score is None or (
                (top.active_speaker_score or 0) - second_score
                >= self.config.active_speaker_margin
            )
            if (
                is_unique
                and (top.active_speaker_score or 0)
                >= self.config.active_speaker_min_score
                and top.confidence >= self.config.minimum_face_confidence
            ):
                return "mouth", (top,)
        return "face_fallback", faces

    def _region_for_face(
        self,
        *,
        frame_timestamp_ms: int,
        face: FaceGeometry,
        confidence: float,
        box: tuple[float, float, float, float] | None,
    ) -> VideoPrivacyRegion:
        x, y, width, height = box or (face.x, face.y, face.width, face.height)
        detection = VideoRegionDetection(
            kind="spoken_pii",
            x=x,
            y=y,
            width=width,
            height=height,
            confidence=confidence,
            timestamp_ms=frame_timestamp_ms,
            detector=self.config.detector_id,
            track_id=face.track_id,
        )
        return VideoPrivacyRegion.from_detection(
            detection,
            expires_at_ms=frame_timestamp_ms + self.config.frame_duration_ms,
        )

    def _required_watermark(self, frame: VideoFrame) -> int:
        return (
            frame.timestamp_ms
            + self.config.frame_duration_ms
            + self.config.pre_padding_ms
        )

    def _unsafe_decision(
        self,
        pending: _PendingFrame,
        reason_code: CrossModalDecisionStatus,
        required_watermark: int,
        *,
        intervals: tuple[AudioRedactionInterval, ...] = (),
        delay: int | None = None,
        lag: int | None = None,
    ) -> CrossModalDecision:
        return CrossModalDecision(
            sequence=pending.sequence,
            frame_timestamp_ms=pending.frame.timestamp_ms,
            status=reason_code,
            intervals=intervals,
            association="unsafe",
            reason_code=reason_code,
            audio_watermark_ms=self._audio_watermark_ms,
            required_audio_watermark_ms=required_watermark,
            buffer_delay_ms=delay,
            decision_lag_ms=lag,
        )

    def _fail_pending(self, reason_code: CrossModalDecisionStatus) -> CrossModalUpdate:
        decisions: list[CrossModalDecision] = []
        while self._pending:
            pending = self._pending.popleft()
            decision = self._unsafe_decision(
                pending,
                reason_code,
                self._required_watermark(pending.frame),
            )
            self.metrics.record_decision(decision)
            decisions.append(decision)
        return self._update(decisions, reason_code=reason_code)

    def _update(
        self,
        decisions: Sequence[CrossModalDecision],
        *,
        late_intervals: Sequence[AudioRedactionInterval] = (),
        reason_code: str | None = None,
    ) -> CrossModalUpdate:
        decision_values = tuple(decisions)
        late_values = tuple(late_intervals)
        unsafe_reason = reason_code
        if unsafe_reason is None and late_values:
            unsafe_reason = "unsafe_late_audio"
        if unsafe_reason is None:
            unsafe_reason = next(
                (
                    decision.reason_code
                    for decision in decision_values
                    if not decision.cross_modal_complete
                ),
                None,
            )
        status: CrossModalUpdateStatus
        if unsafe_reason is not None or late_values:
            status = "unsafe"
        elif decision_values:
            status = "released"
        else:
            status = "pending"
        return CrossModalUpdate(
            status=status,
            decisions=decision_values,
            late_intervals=late_values,
            reason_code=unsafe_reason,
            pending_frames=len(self._pending),
        )


__all__ = [
    "AudioIntervalIndex",
    "CrossModalAssociation",
    "CrossModalConfig",
    "CrossModalDecision",
    "CrossModalDecisionStatus",
    "CrossModalMetrics",
    "CrossModalSynchronizer",
    "CrossModalUpdate",
    "CrossModalUpdateStatus",
    "FaceGeometry",
]
