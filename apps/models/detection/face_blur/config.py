"""Detector-local configuration.

Protection configuration — enabled, required/optional, redaction mode, the
policy confidence threshold — is centralized and owned elsewhere
(`SECURITY.md` §18). This dataclass holds only the parameters the detection
pipeline itself needs (`INTEGRATION_GUIDE.md` §4).

Every parameter has a safe direction, recorded beside it. When a value is
uncertain, choose the one that protects more faces.

The defaults are conservative placeholders, not benchmarked values. Concrete
match and uncertainty thresholds are an open item (`PROJECT_OVERVIEW.md` §8) and
must be set from benchmark data before production use.
"""

from __future__ import annotations

from dataclasses import dataclass


def _require_unit_interval(name: str, value: float, *, allow_zero: bool = True) -> None:
    """Reject NaN, infinities, and values outside the unit interval.

    The comparisons are written so that NaN fails the lower bound rather than
    passing silently, which is why there is no separate finiteness check.
    """

    above_lower_bound = value >= 0 if allow_zero else value > 0
    if not above_lower_bound or value > 1:
        interval = "[0, 1]" if allow_zero else "(0, 1]"
        raise ValueError(f"{name} must be a finite value in {interval}")


@dataclass(frozen=True, slots=True)
class FaceBlurConfig:
    """Parameters for detection, recognition, stabilization, and hold-over."""

    detector: str = "face-detector-v1"
    """Detector identifier and version, emitted on every region."""

    match_threshold: float = 0.55
    """Similarity at or above which a face is WHITELISTED. Higher = fewer
    strangers whitelisted."""

    uncertainty_margin: float = 0.10
    """Width of the band below ``match_threshold`` treated as UNCERTAIN, and
    therefore protected. Wider = more faces protected."""

    top_k: int = 3
    """References averaged by the comparison (`PROJECT_OVERVIEW.md` §3.2)."""

    min_face_size: float = 0.045
    """Smallest normalized width or height that can be classified reliably.
    Below it a face is UNCERTAIN — protected, never skipped."""

    min_reliable_score: float = 0.60
    """Detection score below which recognition is not trusted, so the face is
    UNCERTAIN rather than WHITELISTED."""

    ema_alpha: float = 0.55
    """Weight of the new observation in the smoothed box. Lower = more
    smoothing = more lag = needs more padding."""

    padding: float = 0.15
    """Margin added on each side, as a fraction of the box's own size, before
    clamping. Larger = safer coverage."""

    hold_over_ms: int = 500
    """How long a lost track keeps being emitted, in source-media time.
    Longer = safer."""

    track_match_iou: float = 0.30
    """Minimum IoU for an observation to continue an existing track."""

    max_tracked_faces: int = 64
    """Bound on concurrently tracked faces, so tracker state cannot grow
    without limit."""

    min_redaction_confidence: float = 0.85
    """Floor for the confidence of a redaction decision. Identity uncertainty
    never pushes a region below it (`INTEGRATION_GUIDE.md` §3.4)."""

    def __post_init__(self) -> None:
        if not self.detector.strip():
            raise ValueError("detector must not be empty")
        _require_unit_interval("match_threshold", self.match_threshold, allow_zero=False)
        _require_unit_interval("uncertainty_margin", self.uncertainty_margin)
        _require_unit_interval("min_face_size", self.min_face_size, allow_zero=False)
        _require_unit_interval("min_reliable_score", self.min_reliable_score)
        _require_unit_interval("ema_alpha", self.ema_alpha, allow_zero=False)
        _require_unit_interval("track_match_iou", self.track_match_iou)
        _require_unit_interval("min_redaction_confidence", self.min_redaction_confidence)
        _require_unit_interval("padding", self.padding)
        if self.top_k < 1:
            raise ValueError("top_k must be at least 1")
        if self.hold_over_ms < 0:
            raise ValueError("hold_over_ms must be non-negative")
        if self.max_tracked_faces < 1:
            raise ValueError("max_tracked_faces must be at least 1")

    @property
    def uncertainty_threshold(self) -> float:
        """Similarity at or above which a non-match is UNCERTAIN, not a
        confident non-match. Below ``match_threshold`` by the configured band."""

        return self.match_threshold - self.uncertainty_margin
