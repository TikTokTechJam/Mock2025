"""Normalized box geometry, temporal smoothing, padding, and clamping.

Coordinates are normalized ``[0, 1]`` with a top-left origin, ordered
``x, y, width, height``, relative to the processed frame
(`INTEGRATION_GUIDE.md` §3.3).

A :class:`NormalizedBox` may extend outside the frame — a partially visible face
is reported that way by the analyzer, and discarding the outside part before
padding is exactly the mistake §3.3 warns about. Only :func:`pad_and_clamp`
brings a box inside the frame, and it pads first.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, nextafter

_MIN_SPAN = 1e-4
"""Smallest emittable normalized dimension.

The output contract rejects a zero-sized region, so a box that clamps away to
nothing at the frame edge is widened to this instead of being dropped: emitting
a sliver protects more than emitting nothing.
"""


@dataclass(frozen=True, slots=True)
class NormalizedBox:
    """An axis-aligned box in normalized frame coordinates."""

    x: float
    y: float
    width: float
    height: float

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
            raise ValueError("box dimensions must be positive")

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def shortest_side(self) -> float:
        return min(self.width, self.height)

    def iou(self, other: NormalizedBox) -> float:
        """Return intersection over union with ``other``."""

        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        if right <= left or bottom <= top:
            return 0.0
        intersection = (right - left) * (bottom - top)
        union = self.area + other.area - intersection
        if union <= 0:
            return 0.0
        return intersection / union

    def smoothed(self, previous: NormalizedBox, alpha: float) -> NormalizedBox:
        """Return this observation blended into ``previous`` by an EMA.

        ``alpha`` is the weight of the new observation: 1.0 is no smoothing,
        smaller values smooth more and lag more.
        """

        if not isfinite(alpha) or not 0 < alpha <= 1:
            raise ValueError("alpha must be a finite value in (0, 1]")
        retained = 1.0 - alpha
        return NormalizedBox(
            x=alpha * self.x + retained * previous.x,
            y=alpha * self.y + retained * previous.y,
            width=alpha * self.width + retained * previous.width,
            height=alpha * self.height + retained * previous.height,
        )


def pad_and_clamp(box: NormalizedBox, padding: float) -> NormalizedBox:
    """Grow ``box`` by ``padding`` on every side, then clamp it to the frame.

    The order is the point of this function. Clamping first silently shrinks the
    margin at the frame edge, which is where a partially visible face is most
    likely to leak (`INTEGRATION_GUIDE.md` §3.3), so padding and clamping are
    not separately callable.

    ``padding`` is a fraction of the box's own size, so a distant face gets a
    proportionally sized margin rather than a fixed one.
    """

    if not isfinite(padding) or padding < 0:
        raise ValueError("padding must be a finite non-negative value")
    margin_x = box.width * padding
    margin_y = box.height * padding
    x, width = _clamp_span(box.x - margin_x, box.width + 2 * margin_x)
    y, height = _clamp_span(box.y - margin_y, box.height + 2 * margin_y)
    return NormalizedBox(x=x, y=y, width=width, height=height)


def _clamp_span(start: float, length: float) -> tuple[float, float]:
    """Clamp one axis into ``[0, 1]``, keeping ``start + length <= 1``."""

    end = min(1.0, start + length)
    start = min(max(start, 0.0), 1.0)
    length = end - start
    if length < _MIN_SPAN:
        length = _MIN_SPAN
        start = min(start, 1.0 - length)
        if start < 0.0:
            start = 0.0
    # The contract compares x + width against 1 exactly, so shed any rounding
    # that pushed the sum past the edge rather than failing construction.
    while length > 0.0 and start + length > 1.0:
        length = nextafter(length, 0.0)
    return start, length
