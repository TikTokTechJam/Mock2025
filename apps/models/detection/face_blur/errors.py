"""Failure types for the face detection pipeline.

Face protection fails closed (`PRODUCT.md` §9, `INTEGRATION_GUIDE.md` §6). A
detector failure must reach the caller as a raised error so policy can map it to
`UNSAFE` (required) or `DEGRADED` (optional). It must never be flattened into an
empty region list, which is indistinguishable from "no faces present" — the
confusion `SECURITY.md` §22 forbids.

Error messages carry no frames, crops, embeddings, similarity scores, or raw
detector payloads.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager


class FaceDetectorError(RuntimeError):
    """Base class for every failure raised by this package."""


class FaceDetectorUnavailable(FaceDetectorError):
    """The detector cannot guarantee its configured protection for a frame.

    Raised for a missing model, a backend crash, or invalid detector output.
    Callers translate this to `status = unavailable`, never to `no faces
    detected`.
    """


class FrameUnavailable(FaceDetectorUnavailable):
    """Pixel data for the requested frame is not in the bounded buffer."""


class EnrollmentError(FaceDetectorError):
    """An enrollment request is not backed by an explicit consent record."""


class WhitelistStorageError(FaceDetectorError):
    """The whitelist database could not be read or written.

    Raised rather than absorbed: a whitelist that silently loaded half its
    identities would blur an enrolled creator, and one that silently failed to
    write a revocation would keep a withdrawn identity whitelisted.
    """


@contextmanager
def fail_closed(message: str) -> Generator[None]:
    """Turn any unexpected error inside the block into detector unavailability.

    Every stage of a detect call runs inside one of these, so a failure anywhere
    — model, geometry, contract construction — surfaces as the same fail-closed
    signal instead of leaking an implementation-specific exception that a caller
    might handle as "nothing found".

    ``message`` describes the stage only. The original error stays as the
    chained cause, for diagnostics rather than ordinary logs; a backend is
    responsible for keeping frames, crops, and embeddings out of its own error
    messages.
    """

    try:
        yield
    except FaceDetectorUnavailable:
        raise
    except Exception as error:
        raise FaceDetectorUnavailable(message) from error
