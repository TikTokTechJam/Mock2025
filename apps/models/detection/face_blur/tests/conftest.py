"""Make ``face_blur`` importable when the tests run from anywhere in the repo."""

from __future__ import annotations

import sys
from pathlib import Path

_DETECTION_ROOT = Path(__file__).resolve().parents[2]
if str(_DETECTION_ROOT) not in sys.path:
    sys.path.insert(0, str(_DETECTION_ROOT))
