from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Literal

from privastream_api.pipeline.audio import AudioPipeline, AudioProcessingResult
from privastream_api.pipeline.contracts import (
    AudioChunk,
    AudioSegment,
    VideoFrame,
    VideoRegionDetection,
)
from privastream_api.pipeline.cross_modal import CrossModalConfig, CrossModalSynchronizer
from privastream_api.pipeline.media_integration import (
    CrossModalSynchronizerAdapter,
    MediaIntegrationConfig,
    ProductionMediaIntegration,
    VideoAugmentation,
)
from privastream_api.pipeline.safety import (
    CapabilityPolicy,
    PrivacyGate,
    PrivacyGateConfig,
)
from privastream_api.pipeline.spoken_pii import SpeechWindow
from privastream_api.pipeline.video import (
    ProtectedVideoFrame,
    RasterFrame,
    VideoCompositor,
    VideoOrchestrator,
    VideoPrivacyRegion,
)


class SilentVad:
    def detect(self, segment: AudioSegment) -> Sequence[SpeechWindow]:
        return ()


class FailingVad:
    def detect(self, segment: AudioSegment) -> Sequence[SpeechWindow]:
        raise RuntimeError("test VAD failure")


class UnusedTranscriber:
    def transcribe(
        self, segment: AudioSegment, windows: Sequence[SpeechWindow]
    ) -> Sequence[object]:
        return ()


class RecordingSink:
    def __init__(self) -> None:
        self.decisions = []
        self.video = []
        self.audio = []
        self.blocked = []

    def publish_decision(self, decision: object) -> None:
        self.decisions.append(decision)

    def publish_video(self, timestamp_ms: int, payload: RasterFrame) -> None:
        self.video.append((timestamp_ms, payload))

    def publish_audio(self, chunk: AudioChunk) -> None:
        self.audio.append(chunk)

    def publish_blocked(self, decision: object) -> None:
        self.blocked.append(decision)


def _frame() -> VideoFrame:
    return VideoFrame(
        width=10,
        height=10,
        timestamp_ms=0,
        frame_id="frame-0",
        payload=RasterFrame.solid(10, 10, (20, 30, 40)),
    )


def _chunk() -> AudioChunk:
    return AudioChunk(
        start_timestamp_ms=0,
        sample_rate_hz=16_000,
        channels=1,
        pcm_format="float32",
        samples=(0.0,) * 640,
        sequence_id=0,
    )


def _audio(vad: object) -> AudioPipeline:
    return AudioPipeline(vad=vad, transcriber=UnusedTranscriber())


def _integration(
    audio: AudioPipeline,
    *,
    fallback: Literal["full_redact", "block"] = "full_redact",
    augmentor=None,
    cross_modal_required: bool = False,
) -> ProductionMediaIntegration:
    policies = [
        CapabilityPolicy("video", required=True),
        CapabilityPolicy("spoken_pii", required=True),
    ]
    if augmentor is not None or cross_modal_required:
        policies.append(CapabilityPolicy("cross_modal", required=cross_modal_required))
    return ProductionMediaIntegration(
        VideoOrchestrator(compositor=VideoCompositor(mode="cover")),
        audio,
        PrivacyGate(
            policies,
            PrivacyGateConfig(fallback_action=fallback),
        ),
        augmentor=augmentor,
        config=MediaIntegrationConfig(frame_duration_ms=33),
    )


def test_real_processors_publish_only_protected_timestamped_output() -> None:
    integration = _integration(_audio(SilentVad()))

    result = asyncio.run(integration.process_window(_frame(), (_chunk(),)))
    sink = RecordingSink()
    integration.publish(result, sink)

    assert result.publication.action == "publish_protected"
    assert result.video_payload is not None
    assert result.audio_chunks[0].start_timestamp_ms == 0
    assert result.audio_chunks[0].sequence_id == 0
    assert sink.decisions == [result.publication]
    assert sink.video[0][0] == 0
    assert sink.audio == list(result.audio_chunks)
    assert not sink.blocked


def test_processor_failure_uses_full_redaction_without_raw_audio_fallback() -> None:
    integration = _integration(_audio(FailingVad()))

    result = asyncio.run(integration.process_window(_frame(), (_chunk(),)))

    assert result.publication.action == "full_redact"
    assert result.video_payload is not None
    assert result.video_payload.pixel(0, 0) == (0, 0, 0)
    assert result.audio_chunks[0].samples == (0.0,) * 640


def test_block_decision_does_not_send_any_media_to_sink() -> None:
    integration = _integration(_audio(FailingVad()), fallback="block")

    result = asyncio.run(integration.process_window(_frame(), (_chunk(),)))
    sink = RecordingSink()
    integration.publish(result, sink)

    assert result.publication.action == "block"
    assert not sink.video
    assert not sink.audio
    assert sink.blocked == [result.publication]


def test_cross_modal_adapter_is_optional_but_can_be_required_by_the_gate() -> None:
    augmentor = CrossModalSynchronizerAdapter(
        CrossModalSynchronizer(
            CrossModalConfig(frame_duration_ms=33, pre_padding_ms=0, post_padding_ms=0)
        )
    )
    integration = _integration(
        _audio(SilentVad()), augmentor=augmentor, cross_modal_required=True
    )

    result = asyncio.run(integration.process_window(_frame(), (_chunk(),)))

    assert result.publication.action == "publish_protected"
    assert result.cross_modal_status == "ready"


class FixedAugmentor:
    def augment(
        self,
        frame: VideoFrame,
        video: ProtectedVideoFrame | None,
        audio: AudioProcessingResult | None,
    ) -> VideoAugmentation:
        detection = VideoRegionDetection(
            kind="spoken_pii",
            x=0,
            y=0,
            width=0.5,
            height=0.5,
            confidence=1,
            timestamp_ms=frame.timestamp_ms,
            detector="test-cross-modal",
        )
        return VideoAugmentation(
            status="ready",
            regions=(
                VideoPrivacyRegion.from_detection(
                    detection, expires_at_ms=frame.timestamp_ms + 33
                ),
            ),
            watermark_ms=40,
            lag_ms=0,
        )


def test_ready_augmentation_is_composed_before_protected_publication() -> None:
    integration = _integration(
        _audio(SilentVad()), augmentor=FixedAugmentor(), cross_modal_required=True
    )

    result = asyncio.run(integration.process_window(_frame(), (_chunk(),)))

    assert result.publication.action == "publish_protected"
    assert result.video_payload is not None
    assert result.video_payload.pixel(0, 0) == (0, 0, 0)
