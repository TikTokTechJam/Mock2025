"""Non-whitelisted face detection for PrivaStream.

Returns the regions that must be redacted before media reaches any downstream
consumer. Recognition is a negative filter only: it decides which faces may be
left alone. Every face not positively established as whitelisted is a redaction
target, and this component never modifies media.

Design: ``apps/models/detection/PROJECT_OVERVIEW.md``.
Wiring: ``apps/models/detection/INTEGRATION_GUIDE.md``.
Output contract: ``apps/api/src/privastream_api/pipeline/contracts.py``.
"""

from __future__ import annotations

from .backends import DetectedFace, FaceAnalyzer, InsightFaceAnalyzer
from .classification import FaceClassification, most_protective, redaction_confidence
from .config import FaceBlurConfig
from .detector import FaceBlurDetector
from .diagnostics import (
    ConfidenceBucket,
    DetectionStatus,
    confidence_bucket,
    detection_log_fields,
    protection_state,
)
from .embeddings import Embedding
from .errors import (
    EnrollmentError,
    FaceDetectorError,
    FaceDetectorUnavailable,
    FrameUnavailable,
    WhitelistStorageError,
)
from .frames import BoundedFrameBuffer, FrameSource
from .geometry import NormalizedBox, pad_and_clamp
from .tracking import EmittedRegion, FaceObservation, FaceTracker
from .whitelist import (
    EnrollmentConsent,
    EnrollmentResult,
    ReferenceRejection,
    WhitelistStore,
    enroll_identity,
)

__all__ = [
    "BoundedFrameBuffer",
    "ConfidenceBucket",
    "DetectedFace",
    "DetectionStatus",
    "Embedding",
    "EmittedRegion",
    "EnrollmentConsent",
    "EnrollmentError",
    "EnrollmentResult",
    "FaceAnalyzer",
    "FaceBlurConfig",
    "FaceBlurDetector",
    "FaceClassification",
    "FaceDetectorError",
    "FaceDetectorUnavailable",
    "FaceObservation",
    "FaceTracker",
    "FrameSource",
    "FrameUnavailable",
    "InsightFaceAnalyzer",
    "NormalizedBox",
    "ReferenceRejection",
    "WhitelistStorageError",
    "WhitelistStore",
    "confidence_bucket",
    "detection_log_fields",
    "enroll_identity",
    "most_protective",
    "pad_and_clamp",
    "protection_state",
    "redaction_confidence",
]
