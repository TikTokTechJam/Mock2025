"""Production privacy-pipeline orchestration at the protected media boundary.

This module owns the integration layer described by issue #11. It connects the
normalized video, audio, optional cross-modal, and privacy-gate contracts, then
hands only protected output or an explicit block decision to an injected sink.
It deliberately does not implement WebRTC, mediasoup, signaling, capture, or
transport lifecycle.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from privastream_api.pipeline.audio import (
    AudioPipeline,
    AudioProcessingResult,
    AudioProcessingStatus,
)
from privastream_api.pipeline.contracts import AudioChunk, VideoFrame
from privastream_api.pipeline.cross_modal import (
    CrossModalDecision,
    CrossModalSynchronizer,
    FaceGeometry,
)
from privastream_api.pipeline.safety import (
    CapabilityObservation,
    MediaWindow,
    PrivacyGate,
    PublicationDecision,
)
from privastream_api.pipeline.video import (
    ProtectedVideoFrame,
    RasterFrame,
    VideoCompositor,
    VideoCompositionError,
    VideoOrchestrator,
    VideoPrivacyRegion,
)


AugmentationStatus = Literal["ready", "processing", "failed"]


class ProtectedMediaSink(Protocol):
    """Consumer boundary for protected output owned by a transport adapter."""

    def publish_decision(self, decision: PublicationDecision) -> None:
        """Receive the gate decision before any protected media is published."""

    def publish_video(self, timestamp_ms: int, payload: RasterFrame) -> None:
        """Publish one protected video payload with its source timestamp."""

    def publish_audio(self, chunk: AudioChunk) -> None:
        """Publish one protected, source-timestamped audio chunk."""

    def publish_blocked(self, decision: PublicationDecision) -> None:
        """Signal that no media may be published for this source window."""


class CrossModalAugmentor(Protocol):
    """Optional A/V augmentation adapter supplied by the integration caller."""

    def augment(
        self,
        frame: VideoFrame,
        video: ProtectedVideoFrame | None,
        audio: AudioProcessingResult | None,
    ) -> VideoAugmentation:
        """Return visual regions and source-time readiness for one media window."""


@dataclass(frozen=True, slots=True)
class VideoAugmentation:
    """Sanitized visual augmentation returned by an optional A/V adapter."""

    status: AugmentationStatus
    regions: tuple[VideoPrivacyRegion, ...] = ()
    watermark_ms: int | None = None
    lag_ms: int | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"ready", "processing", "failed"}:
            raise ValueError("unsupported augmentation status")
        if self.watermark_ms is not None and self.watermark_ms < 0:
            raise ValueError("augmentation watermark must be non-negative")
        if self.lag_ms is not None and self.lag_ms < 0:
            raise ValueError("augmentation lag must be non-negative")
        if self.reason_code is not None and (
            not self.reason_code
            or len(self.reason_code) > 64
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
                for character in self.reason_code
            )
        ):
            raise ValueError("augmentation reason_code must be sanitized")


@dataclass(frozen=True, slots=True)
class MediaIntegrationConfig:
    """Capability IDs and timing policy shared with the privacy gate."""

    frame_duration_ms: int = 33
    video_capability_id: str = "video"
    audio_capability_id: str = "spoken_pii"
    cross_modal_capability_id: str = "cross_modal"

    def __post_init__(self) -> None:
        if self.frame_duration_ms <= 0:
            raise ValueError("frame_duration_ms must be positive")
        for name, value in (
            ("video_capability_id", self.video_capability_id),
            ("audio_capability_id", self.audio_capability_id),
            ("cross_modal_capability_id", self.cross_modal_capability_id),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")


@dataclass(slots=True)
class MediaIntegrationMetrics:
    """Aggregate integration outcomes without media, transcript, or PII values."""

    windows_processed: int = 0
    protected_windows: int = 0
    fallback_windows: int = 0
    blocked_windows: int = 0
    video_failures: int = 0
    audio_failures: int = 0
    cross_modal_failures: int = 0

    def record(
        self,
        decision: PublicationDecision,
        *,
        video_status: str,
        audio_status: AudioProcessingStatus,
        cross_modal_status: AugmentationStatus | None,
    ) -> None:
        self.windows_processed += 1
        if decision.action == "publish_protected":
            self.protected_windows += 1
        elif decision.action == "full_redact":
            self.fallback_windows += 1
        else:
            self.blocked_windows += 1
        if video_status != "ready":
            self.video_failures += 1
        if audio_status not in {"ok", "no_speech"}:
            self.audio_failures += 1
        if cross_modal_status == "failed":
            self.cross_modal_failures += 1

    def snapshot(self) -> dict[str, int]:
        """Return safe aggregate counters for status or operational metrics."""

        return {
            "windows_processed": self.windows_processed,
            "protected_windows": self.protected_windows,
            "fallback_windows": self.fallback_windows,
            "blocked_windows": self.blocked_windows,
            "video_failures": self.video_failures,
            "audio_failures": self.audio_failures,
            "cross_modal_failures": self.cross_modal_failures,
        }


@dataclass(frozen=True, slots=True)
class ProtectedMediaWindow:
    """Gate decision and protected payloads for one source-time window.

    The window intentionally contains no source ``VideoFrame``. A caller can
    inspect status and timestamps, but cannot accidentally pass raw video to a
    protected-output sink through this result.
    """

    video_timestamp_ms: int
    source_frame_id: str | None
    video_payload: RasterFrame | None
    audio_chunks: tuple[AudioChunk, ...]
    publication: PublicationDecision
    video_status: str
    audio_status: AudioProcessingStatus
    cross_modal_status: AugmentationStatus | None = None


class CrossModalSynchronizerAdapter:
    """Adapt #10's stateful synchronizer to the #11 augmentation contract."""

    def __init__(
        self,
        synchronizer: CrossModalSynchronizer,
        *,
        face_provider: "FaceGeometryProvider" | None = None,
    ) -> None:
        self.synchronizer = synchronizer
        self.face_provider = face_provider

    def augment(
        self,
        frame: VideoFrame,
        video: ProtectedVideoFrame | None,
        audio: AudioProcessingResult | None,
    ) -> VideoAugmentation:
        if (
            audio is None
            or not audio.safe_to_release
            or audio.release_watermark_ms is None
        ):
            return VideoAugmentation(
                status="failed",
                reason_code="cross_modal_audio_unavailable",
            )

        try:
            faces = self._faces(frame, video)
            submitted = self.synchronizer.submit_frame(frame, faces)
            ingested = self.synchronizer.ingest_audio(
                audio.redaction_intervals,
                watermark_ms=audio.release_watermark_ms,
            )
        except (TypeError, ValueError):
            return VideoAugmentation(status="failed", reason_code="cross_modal_input")

        if submitted.status == "unsafe" or ingested.status == "unsafe":
            reason = (
                ingested.reason_code
                or submitted.reason_code
                or "cross_modal_unsafe"
            )
            return VideoAugmentation(status="failed", reason_code=reason)

        decisions = (*submitted.decisions, *ingested.decisions)
        decision = next(
            (
                candidate
                for candidate in reversed(decisions)
                if candidate.frame_timestamp_ms == frame.timestamp_ms
            ),
            None,
        )
        if decision is None:
            return VideoAugmentation(
                status="processing",
                watermark_ms=self.synchronizer.audio_watermark_ms,
                reason_code="cross_modal_pending",
            )
        return self._augmentation_for_decision(decision)

    def _faces(
        self, frame: VideoFrame, video: ProtectedVideoFrame | None
    ) -> tuple[FaceGeometry, ...]:
        if self.face_provider is not None:
            return tuple(self.face_provider(frame, video))
        if video is None:
            return ()
        return tuple(
            FaceGeometry.from_region(region)
            for region in video.regions
            if region.kind in {"face", "face_bystander"}
        )

    @staticmethod
    def _augmentation_for_decision(decision: CrossModalDecision) -> VideoAugmentation:
        if decision.status in {"protected", "no_sensitive_speech"}:
            return VideoAugmentation(
                status="ready",
                regions=decision.regions,
                watermark_ms=decision.audio_watermark_ms,
                lag_ms=decision.decision_lag_ms,
            )
        return VideoAugmentation(
            status="failed",
            watermark_ms=decision.audio_watermark_ms,
            lag_ms=decision.decision_lag_ms,
            reason_code=decision.reason_code or "cross_modal_unsafe",
        )


class FaceGeometryProvider(Protocol):
    """Optional source of normalized face geometry for cross-modal association."""

    def __call__(
        self, frame: VideoFrame, video: ProtectedVideoFrame | None
    ) -> Sequence[FaceGeometry]:
        """Return face geometry without running another detector."""


class ProductionMediaIntegration:
    """Coordinate production processors and gate protected output."""

    def __init__(
        self,
        video: VideoOrchestrator,
        audio: AudioPipeline,
        gate: PrivacyGate,
        *,
        augmentor: CrossModalAugmentor | None = None,
        compositor: VideoCompositor | None = None,
        config: MediaIntegrationConfig | None = None,
        metrics: MediaIntegrationMetrics | None = None,
    ) -> None:
        self.video = video
        self.audio = audio
        self.gate = gate
        self.augmentor = augmentor
        self.compositor = compositor or video.compositor
        self.config = config or MediaIntegrationConfig()
        self.metrics = metrics or MediaIntegrationMetrics()
        policy_ids = {policy.capability_id for policy in gate.policies}
        required_ids = {
            self.config.video_capability_id,
            self.config.audio_capability_id,
        }
        if not required_ids.issubset(policy_ids):
            raise ValueError("privacy gate must own video and audio integration capabilities")
        if (
            augmentor is not None
            and self.config.cross_modal_capability_id not in policy_ids
        ):
            raise ValueError("cross-modal augmentation requires a configured gate capability")

    async def process_window(
        self,
        frame: VideoFrame,
        audio_chunks: Sequence[AudioChunk],
    ) -> ProtectedMediaWindow:
        """Process one source window and apply the centralized gate decision."""

        source_audio = tuple(audio_chunks)
        video_result: ProtectedVideoFrame | None
        try:
            video_result = await self.video.process_frame(frame)
        except Exception:
            video_result = None

        audio_result: AudioProcessingResult | None
        try:
            audio_result = self.audio.process(source_audio)
        except Exception:
            audio_result = None

        augmentation: VideoAugmentation | None = None
        if self.augmentor is not None:
            try:
                augmentation = self.augmentor.augment(frame, video_result, audio_result)
            except Exception:
                augmentation = VideoAugmentation(
                    status="failed", reason_code="cross_modal_failure"
                )

        video_payload, video_status = self._protected_video(
            frame, video_result, augmentation
        )
        audio_status: AudioProcessingStatus = (
            audio_result.status if audio_result is not None else "unsafe_input"
        )
        observations = [
            self._video_observation(video_result, video_payload),
            self._audio_observation(audio_result),
        ]
        if self.config.cross_modal_capability_id in {
            policy.capability_id for policy in self.gate.policies
        }:
            observations.append(self._cross_modal_observation(augmentation))

        window = MediaWindow(
            start_ms=frame.timestamp_ms,
            end_ms=frame.timestamp_ms + self.config.frame_duration_ms,
        )
        publication = self.gate.evaluate(window, tuple(observations))
        if publication.action == "publish_protected":
            output_video = video_payload
            output_audio = (
                audio_result.protected_chunks
                if audio_result is not None and audio_result.safe_to_release
                else ()
            )
        elif publication.action == "full_redact":
            output_video = self._full_redact(frame)
            output_audio = self._silence_chunks(source_audio)
        else:
            output_video = None
            output_audio = ()

        self.metrics.record(
            publication,
            video_status=video_status,
            audio_status=audio_status,
            cross_modal_status=augmentation.status if augmentation else None,
        )
        return ProtectedMediaWindow(
            video_timestamp_ms=frame.timestamp_ms,
            source_frame_id=frame.frame_id,
            video_payload=output_video,
            audio_chunks=output_audio,
            publication=publication,
            video_status=video_status,
            audio_status=audio_status,
            cross_modal_status=augmentation.status if augmentation else None,
        )

    @staticmethod
    def publish(result: ProtectedMediaWindow, sink: ProtectedMediaSink) -> None:
        """Deliver only the selected protected output through an injected sink."""

        sink.publish_decision(result.publication)
        if result.publication.blocked:
            sink.publish_blocked(result.publication)
            return
        if result.video_payload is not None:
            sink.publish_video(result.video_timestamp_ms, result.video_payload)
        for chunk in result.audio_chunks:
            sink.publish_audio(chunk)

    def _protected_video(
        self,
        frame: VideoFrame,
        video: ProtectedVideoFrame | None,
        augmentation: VideoAugmentation | None,
    ) -> tuple[RasterFrame | None, str]:
        if video is None:
            return None, "video_processor_failure"
        if video.detector_failures:
            return None, "video_detector_failure"
        if video.render_status != "rendered" or video.payload is None:
            return None, "video_render_failure"
        if augmentation is None or augmentation.status != "ready":
            return video.payload, "ready"
        try:
            regions = (*video.regions, *augmentation.regions)
            return self.compositor.compose(frame, regions), "ready"
        except VideoCompositionError:
            return None, "video_render_failure"

    def _video_observation(
        self, video: ProtectedVideoFrame | None, payload: RasterFrame | None
    ) -> CapabilityObservation:
        if video is None:
            return CapabilityObservation(
                self.config.video_capability_id,
                state="failed",
                reason_code="video_processor_failure",
            )
        if video.detector_failures:
            reason = "video_detector_failure"
        elif video.render_status != "rendered" or payload is None:
            reason = "video_render_failure"
        else:
            return CapabilityObservation(
                self.config.video_capability_id,
                state="ready",
                watermark_ms=video.source.timestamp_ms + self.config.frame_duration_ms,
                lag_ms=0,
            )
        return CapabilityObservation(
            self.config.video_capability_id,
            state="failed",
            reason_code=reason,
        )

    def _audio_observation(
        self, audio: AudioProcessingResult | None
    ) -> CapabilityObservation:
        if (
            audio is not None
            and audio.safe_to_release
            and audio.release_watermark_ms is not None
        ):
            return CapabilityObservation(
                self.config.audio_capability_id,
                state="ready",
                watermark_ms=audio.release_watermark_ms,
                lag_ms=audio.release_lag_ms or 0,
            )
        reason = audio.status if audio is not None else "audio_processor_failure"
        return CapabilityObservation(
            self.config.audio_capability_id,
            state="failed",
            reason_code=reason,
        )

    def _cross_modal_observation(
        self, augmentation: VideoAugmentation | None
    ) -> CapabilityObservation:
        if augmentation is None:
            return CapabilityObservation(
                self.config.cross_modal_capability_id,
                state="unavailable",
                reason_code="cross_modal_unavailable",
            )
        if augmentation.status == "ready":
            return CapabilityObservation(
                self.config.cross_modal_capability_id,
                state="ready",
                watermark_ms=augmentation.watermark_ms,
                lag_ms=augmentation.lag_ms or 0,
            )
        return CapabilityObservation(
            self.config.cross_modal_capability_id,
            state=augmentation.status,
            watermark_ms=augmentation.watermark_ms,
            lag_ms=augmentation.lag_ms,
            reason_code=augmentation.reason_code or "cross_modal_unavailable",
        )

    def _full_redact(self, frame: VideoFrame) -> RasterFrame | None:
        try:
            return self.compositor.full_frame_safe_cover(frame)
        except VideoCompositionError:
            return None

    @staticmethod
    def _silence_chunks(chunks: Sequence[AudioChunk]) -> tuple[AudioChunk, ...]:
        silenced: list[AudioChunk] = []
        for chunk in chunks:
            if isinstance(chunk.samples, bytes):
                samples: bytes | tuple[float, ...] = b"\x00" * len(chunk.samples)
            else:
                samples = tuple(0.0 for _ in chunk.samples)
            silenced.append(replace(chunk, samples=samples))
        return tuple(silenced)


__all__ = [
    "AugmentationStatus",
    "CrossModalAugmentor",
    "CrossModalSynchronizerAdapter",
    "FaceGeometryProvider",
    "MediaIntegrationConfig",
    "MediaIntegrationMetrics",
    "ProductionMediaIntegration",
    "ProtectedMediaSink",
    "ProtectedMediaWindow",
    "VideoAugmentation",
]
