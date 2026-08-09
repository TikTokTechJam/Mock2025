"""The media path: bounded, ephemeral access to a frame's pixels.

``VideoFrame`` carries metadata only, so pixels reach the detector through this
boundary (`INTEGRATION_GUIDE.md` §2). Frames arrive in a bounded buffer and are
discarded after processing — no unbounded cache, and no frame kept for debugging
convenience (`PROJECT_OVERVIEW.md` §4.3).

Frames are keyed by ``timestamp_ms``, which is also how regions correlate back
to frames: ``VideoRegionDetection`` has nowhere to echo ``frame_id``.
"""

from __future__ import annotations

from typing import Any, Protocol

from .contracts import VideoFrame
from .errors import FrameUnavailable


class FrameSource(Protocol):
    """Supplies and releases the pixel data behind a :class:`VideoFrame`."""

    def pixels(self, frame: VideoFrame) -> Any:
        """Return pixel data for ``frame``, or raise :class:`FrameUnavailable`.

        Raising is the correct behavior for a frame that is gone. Returning a
        blank image would be read as "no faces here."
        """

    def release(self, frame: VideoFrame) -> None:
        """Discard the pixel data for ``frame``. Called after every attempt."""


class BoundedFrameBuffer:
    """A small FIFO of in-flight frames, bounded by count and by source time.

    Both limits are enforced on submission. When a limit is reached the oldest
    frame is dropped, and a dropped frame is never processed — so the caller
    must not emit a frame it never received detections for. Bounding the buffer
    is required (`SECURITY.md` §15); deciding what happens to media the detector
    never saw belongs to the caller's fail-closed policy.
    """

    def __init__(self, max_frames: int = 8, max_duration_ms: int = 2_000) -> None:
        if max_frames < 1:
            raise ValueError("max_frames must be at least 1")
        if max_duration_ms < 0:
            raise ValueError("max_duration_ms must be non-negative")
        self.max_frames = max_frames
        self.max_duration_ms = max_duration_ms
        self._pixels: dict[int, Any] = {}

    def __len__(self) -> int:
        return len(self._pixels)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(frames={len(self._pixels)}/{self.max_frames})"

    def submit(self, frame: VideoFrame, pixels: Any) -> None:
        """Add a frame's pixels, evicting whatever no longer fits."""

        self._pixels[frame.timestamp_ms] = pixels
        horizon = frame.timestamp_ms - self.max_duration_ms
        for timestamp_ms in [key for key in self._pixels if key < horizon]:
            del self._pixels[timestamp_ms]
        while len(self._pixels) > self.max_frames:
            del self._pixels[next(iter(self._pixels))]

    def pixels(self, frame: VideoFrame) -> Any:
        pixels = self._pixels.get(frame.timestamp_ms)
        if pixels is None:
            raise FrameUnavailable("frame pixels are not in the bounded buffer")
        return pixels

    def release(self, frame: VideoFrame) -> None:
        self._pixels.pop(frame.timestamp_ms, None)

    def clear(self) -> None:
        """Discard every buffered frame."""

        self._pixels.clear()
