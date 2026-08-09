"""Face classification and the confidence attached to a redaction decision.

`PROJECT_OVERVIEW.md` §3.4 defines three classes and only one of them is left
alone. That rule lives in :attr:`FaceClassification.requires_redaction` and
nowhere else, so a caller cannot re-derive it and get it wrong.
"""

from __future__ import annotations

from enum import Enum
from math import isfinite

from .config import FaceBlurConfig


class FaceClassification(Enum):
    """Recognition outcome for one detected face."""

    WHITELISTED = "whitelisted"
    """Sufficiently similar to an enrolled identity. Not redacted."""

    NON_WHITELISTED = "non_whitelisted"
    """Does not match any enrolled identity. Redacted."""

    UNCERTAIN = "uncertain"
    """Ambiguous or insufficient-quality recognition result. Redacted, treated
    exactly like NON_WHITELISTED (`PRODUCT.md` §2.1, `SECURITY.md` §12)."""

    @property
    def requires_redaction(self) -> bool:
        """Whether a face in this class must be emitted as a redaction region."""

        return self is not FaceClassification.WHITELISTED


_PROTECTION_RANK = {
    FaceClassification.WHITELISTED: 0,
    FaceClassification.UNCERTAIN: 1,
    FaceClassification.NON_WHITELISTED: 2,
}


def most_protective(
    first: FaceClassification, second: FaceClassification
) -> FaceClassification:
    """Combine two signals about one face, keeping the protective outcome.

    Used to fold detection quality into a recognition result: a face too small
    or too weakly detected to classify reliably can only ever be downgraded from
    WHITELISTED to UNCERTAIN, never the other way.
    """

    return first if _PROTECTION_RANK[first] >= _PROTECTION_RANK[second] else second


def redaction_confidence(
    classification: FaceClassification, detection_score: float, config: FaceBlurConfig
) -> float:
    """Confidence in the decision to redact — not the face score, not similarity.

    Only detection quality moves this value. Identity uncertainty does not lower
    it: emitting a low confidence to express "we are not sure who this is" would
    invite policy to threshold the region away, inverting the rule that
    uncertain means protect (`INTEGRATION_GUIDE.md` §3.4, `PRODUCT.md` §8).
    Similarity never reaches this function, and so never leaves the detector.
    """

    if not classification.requires_redaction:
        raise ValueError("confidence is only defined for a redaction decision")
    quality = min(max(detection_score, 0.0), 1.0) if isfinite(detection_score) else 0.0
    decided = (quality + 1.0) / 2
    return min(max(decided, config.min_redaction_confidence), 1.0)
