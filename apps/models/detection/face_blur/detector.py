"""The face detector: frame in, redaction regions out.

Implements the ``FaceDetector`` protocol from the authoritative contract. Per
frame (`PROJECT_OVERVIEW.md` §3.3):

    frame → detect every face → embed each one → compare against the whitelist
    → WHITELISTED / NON_WHITELISTED / UNCERTAIN → track and stabilize
    → pad and clamp → emit

Every face that is not positively established as whitelisted is emitted as a
redaction target, and so is every track inside its hold-over window. This
component never blurs, pixelates, covers, or encodes media — redaction belongs
to the compositor.

Failure is raised, never returned. A crash, a missing model, an unavailable
frame, or invalid geometry raises :class:`FaceDetectorUnavailable` so policy can
move the pipeline to ``UNSAFE`` (required) or ``DEGRADED`` (optional). An empty
tuple from :meth:`FaceBlurDetector.detect` means one thing only: no face in this
frame needs redaction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from .backends import DetectedFace, FaceAnalyzer
from .classification import FaceClassification, most_protective, redaction_confidence
from .config import FaceBlurConfig
from .contracts import VideoFrame, VideoRegionDetection
from .errors import fail_closed
from .frames import FrameSource
from .geometry import NormalizedBox, pad_and_clamp
from .tracking import EmittedRegion, FaceObservation, FaceTracker
from .whitelist import WhitelistStore


class FaceBlurDetector:
    """Detect faces that must be redacted before media reaches a consumer."""

    kind: Literal["face"] = "face"
    """The only value this detector emits. Extending ``VideoDetectionKind``
    means editing the ``Literal`` in ``contracts.py``, not inventing a string."""

    def __init__(
        self,
        analyzer: FaceAnalyzer,
        frames: FrameSource,
        whitelist: WhitelistStore | None = None,
        config: FaceBlurConfig | None = None,
        tracker: FaceTracker | None = None,
    ) -> None:
        self._config = config or FaceBlurConfig()
        self._analyzer = analyzer
        self._frames = frames
        # No whitelist is a valid configuration and the safest one: with nothing
        # enrolled, every detected face is protected.
        self._whitelist = (
            whitelist if whitelist is not None else WhitelistStore(config=self._config)
        )
        self._tracker = tracker if tracker is not None else FaceTracker(self._config)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(detector={self._config.detector!r})"

    @property
    def detector_id(self) -> str:
        """The identifier emitted on every region and safe to log."""

        return self._config.detector

    @property
    def config(self) -> FaceBlurConfig:
        return self._config

    def reset(self) -> None:
        """Drop tracking state, e.g. between two unrelated media sources."""

        self._tracker.reset()

    def detect(self, frame: VideoFrame) -> tuple[VideoRegionDetection, ...]:
        """Return the regions that must be redacted in ``frame``.

        Raises :class:`FaceDetectorUnavailable` on any failure. The frame's
        pixels are released before returning, on both the success and the
        failure path, so nothing about the media outlives the call.
        """

        try:
            detected = self._analyze(frame)
        finally:
            self._frames.release(frame)
        with fail_closed("face detection failed for this frame"):
            observations = tuple(self._observe(face) for face in detected)
            regions = self._tracker.update(observations, frame.timestamp_ms)
            return tuple(self._emit(region, frame) for region in regions)

    def _analyze(self, frame: VideoFrame) -> Sequence[DetectedFace]:
        """Run the model on the frame's pixels."""

        with fail_closed("face analysis failed for this frame"):
            return self._analyzer.analyze(self._frames.pixels(frame))

    def _observe(self, face: DetectedFace) -> FaceObservation:
        """Classify one detected face and score the resulting decision."""

        classification = self._whitelist.classify(face.embedding)
        if not self._is_reliable(face):
            # Too small or too weakly detected to trust the comparison. This can
            # only downgrade WHITELISTED to UNCERTAIN — the face is still
            # classified and still emitted, never skipped.
            classification = most_protective(classification, FaceClassification.UNCERTAIN)
        confidence = (
            redaction_confidence(classification, face.score, self._config)
            if classification.requires_redaction
            else 0.0
        )
        return FaceObservation(
            box=self._box(face), classification=classification, confidence=confidence
        )

    def _is_reliable(self, face: DetectedFace) -> bool:
        return (
            min(face.width, face.height) >= self._config.min_face_size
            and face.score >= self._config.min_reliable_score
        )

    def _box(self, face: DetectedFace) -> NormalizedBox:
        with fail_closed("face analyzer returned an invalid region"):
            return NormalizedBox(x=face.x, y=face.y, width=face.width, height=face.height)

    def _emit(self, region: EmittedRegion, frame: VideoFrame) -> VideoRegionDetection:
        """Pad, clamp, and convert one stabilized region to the output contract.

        Construction failure is detector failure, so an invalid region raises
        rather than being dropped: emitting nothing is indistinguishable from
        "no faces present" (`INTEGRATION_GUIDE.md` §5).
        """

        box = pad_and_clamp(region.box, self._config.padding)
        with fail_closed("detector produced an invalid region"):
            return VideoRegionDetection(
                kind=self.kind,
                x=box.x,
                y=box.y,
                width=box.width,
                height=box.height,
                confidence=region.confidence,
                timestamp_ms=frame.timestamp_ms,
                detector=self._config.detector,
                track_id=region.track_id,
            )
