"""The model boundary: detect every face in an image and embed each one.

`PROJECT_OVERVIEW.md` §3.3 requires detection and embedding to happen together.
Embedding extraction is never skipped for a detected face — a detected but
unclassified face is an unclassified face, and is protected — so both live
behind one call.

:class:`InsightFaceAnalyzer` is the InsightFace/ArcFace adapter named in the
design. It is an optional dependency, imported lazily, in the same shape as the
optional audio adapters in ``privastream_api.pipeline.spoken_pii``. The rest of
this package depends only on the :class:`FaceAnalyzer` protocol, so a different
model can be substituted without touching detection, tracking, or output.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Any, Protocol

from .embeddings import Embedding, as_embedding
from .errors import FaceDetectorUnavailable


@dataclass(frozen=True, slots=True)
class DetectedFace:
    """One face found in a frame or reference image.

    Coordinates are normalized to the analyzed image and follow the output
    convention (`INTEGRATION_GUIDE.md` §3.3): top-left origin, ordered
    ``x, y, width, height``. A face partly outside the image keeps its
    out-of-range values — clamping happens once, after padding, at emission.

    ``embedding`` is ``None`` when the model detected a face but could not embed
    it. That face is still classified, and being unclassifiable makes it
    UNCERTAIN, which means protected.
    """

    x: float
    y: float
    width: float
    height: float
    score: float
    embedding: Embedding | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("x", self.x),
            ("y", self.y),
            ("width", self.width),
            ("height", self.height),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("detected face dimensions must be positive")
        # A model that reports a score slightly outside [0, 1] is a scaling
        # quirk, not a reason to fail the whole frame; clamp it instead.
        score = self.score if isfinite(self.score) else 0.0
        object.__setattr__(self, "score", min(max(score, 0.0), 1.0))


class FaceAnalyzer(Protocol):
    """Detect and embed every face in one image."""

    def analyze(self, pixels: Any) -> Sequence[DetectedFace]:
        """Return every detected face, each with its embedding when available.

        Implementations raise on model or runtime failure. Returning an empty
        sequence means "no faces in this image" and nothing else
        (`SECURITY.md` §22).
        """


class InsightFaceAnalyzer:
    """Lazy InsightFace detection plus ArcFace embeddings.

    ``pixels`` is a BGR image array as InsightFace expects it. The model is
    loaded on first use so importing this package never pulls in the optional
    dependency or a model file.
    """

    def __init__(
        self,
        model_name: str = "buffalo_l",
        providers: Sequence[str] = ("CPUExecutionProvider",),
        det_size: tuple[int, int] = (640, 640),
        ctx_id: int = 0,
    ) -> None:
        if not model_name.strip():
            raise ValueError("model_name must not be empty")
        if det_size[0] <= 0 or det_size[1] <= 0:
            raise ValueError("det_size must be positive")
        self.model_name = model_name
        self.providers = tuple(providers)
        self.det_size = det_size
        self.ctx_id = ctx_id
        self._app: Any | None = None

    def _get_app(self) -> Any:
        if self._app is None:
            try:
                from insightface.app import FaceAnalysis  # type: ignore[import-not-found]
            except ImportError as error:
                raise FaceDetectorUnavailable(
                    "InsightFace is an optional dependency and is not installed"
                ) from error
            app = FaceAnalysis(name=self.model_name, providers=list(self.providers))
            app.prepare(ctx_id=self.ctx_id, det_size=self.det_size)
            self._app = app
        return self._app

    def analyze(self, pixels: Any) -> tuple[DetectedFace, ...]:
        app = self._get_app()
        shape = getattr(pixels, "shape", None)
        if shape is None or len(shape) < 2:
            raise FaceDetectorUnavailable("frame pixels have no spatial dimensions")
        height, width = int(shape[0]), int(shape[1])
        if width <= 0 or height <= 0:
            raise FaceDetectorUnavailable("frame pixels have no spatial dimensions")
        faces: list[DetectedFace] = []
        for face in app.get(pixels):
            left, top, right, bottom = (float(value) for value in face.bbox)
            faces.append(
                DetectedFace(
                    x=left / width,
                    y=top / height,
                    width=(right - left) / width,
                    height=(bottom - top) / height,
                    score=float(getattr(face, "det_score", 1.0)),
                    embedding=_optional_embedding(face),
                )
            )
        return tuple(faces)


def _optional_embedding(face: Any) -> Embedding | None:
    """Read an ArcFace embedding, or ``None`` when it is missing or unusable.

    An unusable embedding must not fail the frame: it makes that one face
    unclassifiable, and unclassifiable means protected.
    """

    values = getattr(face, "normed_embedding", None)
    if values is None:
        values = getattr(face, "embedding", None)
    if values is None:
        return None
    try:
        return as_embedding(values)
    except (TypeError, ValueError):
        return None
