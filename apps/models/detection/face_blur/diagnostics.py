"""Safe diagnostic metadata for logs and the UI.

Ordinary logs may carry category, detector id, status, and a bucketed
confidence. They must not carry embeddings, frames, crops, similarity scores, or
raw detector payloads (`INTEGRATION_GUIDE.md` §8, `PROJECT_OVERVIEW.md` §4.5).

Nothing here accepts an embedding or a similarity score, so the safe fields are
the only fields there is a helper to produce.
"""

from __future__ import annotations

from math import isfinite
from typing import Literal

ConfidenceBucket = Literal["low", "medium", "high"]

DetectionStatus = Literal["detected", "none", "unavailable"]
"""``none`` means the detector ran and found nothing to redact. A detector
failure is ``unavailable`` and never ``none`` — failure to detect is not proof of
absence (`SECURITY.md` §22)."""


def confidence_bucket(confidence: float) -> ConfidenceBucket:
    """Bucket a confidence value so exact scores stay out of logs."""

    if not isfinite(confidence):
        raise ValueError("confidence must be finite")
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def detection_log_fields(
    detector: str,
    status: DetectionStatus,
    *,
    region_count: int | None = None,
    confidence: float | None = None,
) -> dict[str, str]:
    """Build the log fields for one detect call.

    ``region_count`` is how many regions were emitted, which says nothing about
    who was in the frame. ``confidence`` is bucketed, never recorded exactly.
    """

    fields = {"category": "face", "detector_id": detector, "status": status}
    if region_count is not None:
        fields["region_count"] = str(region_count)
    if confidence is not None:
        fields["confidence_bucket"] = confidence_bucket(confidence)
    return fields


def protection_state(region_count: int, available: bool) -> dict[str, str]:
    """Build the protection state shown to the UI.

    The UI receives protection state only — never a recognition result, a
    similarity score, or a detector payload. An unavailable detector is reported
    as unavailable, never as protected.
    """

    if not available:
        return {"category": "face", "status": "unavailable"}
    return {"category": "face", "status": "active" if region_count else "no_regions"}
