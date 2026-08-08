"""Media pipeline contracts, video orchestration, and spoken-PII processing."""

from privastream_api.pipeline.video import (
    DetectorRun,
    RasterFrame,
    ProtectedVideoFrame,
    TemporalRegionStore,
    VideoCompositor,
    VideoDetectorRegistration,
    VideoMetrics,
    VideoOrchestrator,
    VideoOrchestrationConfig,
    VideoPrivacyRegion,
    merge_overlapping_regions,
    normalize_regions,
)

__all__ = [
    "DetectorRun",
    "ProtectedVideoFrame",
    "RasterFrame",
    "TemporalRegionStore",
    "VideoCompositor",
    "VideoDetectorRegistration",
    "VideoMetrics",
    "VideoOrchestrator",
    "VideoOrchestrationConfig",
    "VideoPrivacyRegion",
    "merge_overlapping_regions",
    "normalize_regions",
]
