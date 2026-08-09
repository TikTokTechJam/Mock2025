"""Re-export of the authoritative pipeline contracts.

`apps/api/src/privastream_api/pipeline/contracts.py` **is** the contract
(`INTEGRATION_GUIDE.md` §3.1). This module is the single place that imports it,
so the detector never carries a copy of the types and cannot drift from them.

When ``privastream_api`` is not already importable — a plain ``python`` run from
the repository rather than ``uv run --project apps/api`` — the sibling source
tree is added to ``sys.path`` first. Nothing else in this package touches
``sys.path``.
"""

from __future__ import annotations

import sys
from importlib.util import find_spec
from pathlib import Path

if find_spec("privastream_api") is None:  # pragma: no cover - environment dependent
    _API_SOURCE = Path(__file__).resolve().parents[3] / "api" / "src"
    if _API_SOURCE.is_dir():
        sys.path.insert(0, str(_API_SOURCE))

from privastream_api.pipeline.contracts import (  # noqa: E402 - needs the path bootstrap above
    FaceDetector,
    VideoDetectionKind,
    VideoFrame,
    VideoRegionDetection,
)

__all__ = [
    "FaceDetector",
    "VideoDetectionKind",
    "VideoFrame",
    "VideoRegionDetection",
]
