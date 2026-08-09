"""Enrollment, whitelist storage, and the classification of a query face.

An identity is whitelisted only through an explicit, opt-in enrollment action by
that person (`PROJECT_OVERVIEW.md` §4.1, `INTEGRATION_GUIDE.md` §7). That is
enforced structurally: :meth:`WhitelistStore.enroll` cannot be called without an
:class:`EnrollmentConsent` naming the consent record that authorizes it, so
there is no code path that enrolls a face by inference.

Embeddings live here and in the JSON database behind :mod:`.storage`, and
nowhere else. Nothing in this module returns, formats, or logs one, ``__repr__``
reports a count rather than contents, and similarity scores never leave
:meth:`WhitelistStore.classify` — the caller receives a class, not a number
(`INTEGRATION_GUIDE.md` §3.4).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .backends import DetectedFace, FaceAnalyzer
from .classification import FaceClassification
from .config import FaceBlurConfig
from .embeddings import Embedding, l2_normalize, top_k_mean_similarity
from .errors import EnrollmentError
from .storage import StoredIdentity, delete_whitelist, read_whitelist, write_whitelist

RejectionReason = Literal[
    "no_face_detected",
    "multiple_faces_detected",
    "face_too_small",
    "unusable_embedding",
]


@dataclass(frozen=True, slots=True)
class EnrollmentConsent:
    """Proof that an enrollment was explicitly authorized by its subject.

    ``consent_record_id`` points at the record held by the consent flow, which
    owns what was disclosed and when. This detector stores the reference only so
    revocation and audit can find the enrollment again; it never infers consent
    and never constructs this object on a subject's behalf.
    """

    identity_id: str
    consent_record_id: str

    def __post_init__(self) -> None:
        if not self.identity_id.strip():
            raise ValueError("identity_id must not be empty")
        if not self.consent_record_id.strip():
            raise ValueError("consent_record_id must not be empty")


@dataclass(frozen=True, slots=True)
class ReferenceRejection:
    """A reference image that could not be used, and why.

    Rejection is a normal outcome, not an error (`PROJECT_OVERVIEW.md` §3.1).
    ``index`` is the position in the submitted reference set, so the creator can
    be told which image to replace without the image or its embedding being
    carried anywhere.
    """

    index: int
    reason: RejectionReason


@dataclass(frozen=True, slots=True)
class EnrollmentResult:
    """Outcome of one enrollment call."""

    identity_id: str
    accepted: int
    rejections: tuple[ReferenceRejection, ...] = ()

    @property
    def is_usable(self) -> bool:
        """Whether the identity ended up with at least one validated reference."""

        return self.accepted > 0


class WhitelistStore:
    """Consented identities, their reference embeddings, and the match decision.

    ``path`` is the JSON database (see :mod:`.storage`). It is read once at
    construction and rewritten on every mutation, so an enrollment survives a
    restart and a revocation is durable before the call returns. Omitting the
    path gives an in-memory store that keeps nothing after the process exits.

    The in-memory copy is the only cache: there is no derived index that could
    outlive a revocation and keep someone whitelisted after they withdrew
    consent (`INTEGRATION_GUIDE.md` §7.3).
    """

    def __init__(
        self, path: Path | str | None = None, config: FaceBlurConfig | None = None
    ) -> None:
        self._config = config or FaceBlurConfig()
        self._path = Path(path) if path is not None else None
        self._identities: dict[str, StoredIdentity] = (
            read_whitelist(self._path) if self._path is not None else {}
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}(identities={len(self._identities)})"

    @property
    def path(self) -> Path | None:
        """The JSON database backing this store, if any."""

        return self._path

    @property
    def identity_count(self) -> int:
        return len(self._identities)

    @property
    def is_empty(self) -> bool:
        """Whether no identity is enrolled, in which case every face is protected."""

        return not self._identities

    def identity_ids(self) -> tuple[str, ...]:
        """Return enrolled identity ids. Never returns embeddings."""

        return tuple(self._identities)

    def reference_count(self, identity_id: str) -> int:
        """Return how many validated references an identity has."""

        identity = self._identities.get(identity_id)
        return len(identity.embeddings) if identity is not None else 0

    def consent_record_id(self, identity_id: str) -> str | None:
        """Return the consent record backing an enrollment, for audit."""

        identity = self._identities.get(identity_id)
        return identity.consent_record_id if identity is not None else None

    def enroll(
        self,
        consent: EnrollmentConsent,
        references: Sequence[Sequence[DetectedFace]],
    ) -> EnrollmentResult:
        """Validate a reference set and store the embeddings that survive.

        ``references`` holds one entry per reference image: the faces the
        analyzer found in that image. An image is rejected when it contains no
        face, more than one face (the intended subject is ambiguous), a face too
        small to embed reliably, or an unusable embedding. Rejecting these is
        what stops a mislabeled or ambiguous reference from silently widening
        the whitelist — the one enrollment failure that leaves a stranger
        unblurred at inference time.

        Accepted references are appended to any the identity already has, so an
        enrollment can be extended with better images without re-submitting the
        originals.
        """

        if not isinstance(consent, EnrollmentConsent):
            raise EnrollmentError("enrollment requires an explicit consent record")
        accepted: list[Embedding] = []
        rejections: list[ReferenceRejection] = []
        for index, faces in enumerate(references):
            outcome = self._validate_reference(index, faces)
            if isinstance(outcome, ReferenceRejection):
                rejections.append(outcome)
            else:
                accepted.append(outcome)
        if accepted:
            identity_id = consent.identity_id
            existing = self._identities.get(identity_id)
            self._identities[identity_id] = StoredIdentity(
                consent_record_id=consent.consent_record_id,
                embeddings=(existing.embeddings if existing is not None else ()) + tuple(accepted),
            )
            self._persist()
        return EnrollmentResult(
            identity_id=consent.identity_id,
            accepted=len(accepted),
            rejections=tuple(rejections),
        )

    def _validate_reference(
        self, index: int, faces: Sequence[DetectedFace]
    ) -> Embedding | ReferenceRejection:
        """Return a reference image's normalized embedding, or why it was rejected."""

        def rejected(reason: RejectionReason) -> ReferenceRejection:
            return ReferenceRejection(index=index, reason=reason)

        if not faces:
            return rejected("no_face_detected")
        if len(faces) > 1:
            return rejected("multiple_faces_detected")
        face = faces[0]
        if min(face.width, face.height) < self._config.min_face_size:
            return rejected("face_too_small")
        if face.embedding is None:
            return rejected("unusable_embedding")
        try:
            return l2_normalize(face.embedding)
        except ValueError:
            return rejected("unusable_embedding")

    def revoke(self, identity_id: str) -> bool:
        """Delete an enrollment and every embedding derived from it.

        Revocation takes effect on the processing path immediately rather than
        at a later refresh: the in-memory references and the database row are
        dropped in the same call, and that is what makes the next frame treat
        that person as an unknown — therefore protected — face
        (`INTEGRATION_GUIDE.md` §7.3).
        """

        removed = self._identities.pop(identity_id, None) is not None
        if removed:
            self._persist()
        return removed

    def clear(self) -> None:
        """Drop every enrollment, including the database file.

        Afterwards no identity is enrolled, so every detected face is protected.
        """

        self._identities.clear()
        if self._path is not None:
            delete_whitelist(self._path)

    def reload(self) -> None:
        """Re-read the database, discarding the in-memory copy.

        For a process that did not perform the mutation itself — an enrollment
        or revocation applied by another component writing the same file.
        """

        if self._path is not None:
            self._identities = read_whitelist(self._path)

    def _persist(self) -> None:
        if self._path is not None:
            write_whitelist(self._path, self._identities)

    def classify(self, embedding: Embedding | None) -> FaceClassification:
        """Classify one query face against the whole whitelist.

        Returns a class, never a score. The outcomes are those in
        `PROJECT_OVERVIEW.md` §3.4, and everything short of a confident match
        resolves toward protection:

        * no identity enrolled — NON_WHITELISTED, because with no enrollment
          every face is protected;
        * missing or unusable embedding, or a model whose dimension disagrees
          with the stored references — UNCERTAIN, because a face that cannot be
          compared has not been established as whitelisted;
        * similarity at or above the match threshold — WHITELISTED;
        * similarity inside the uncertainty band below it — UNCERTAIN;
        * anything lower — NON_WHITELISTED.
        """

        if self.is_empty:
            return FaceClassification.NON_WHITELISTED
        if embedding is None:
            return FaceClassification.UNCERTAIN
        try:
            query = l2_normalize(embedding)
            best = max(
                top_k_mean_similarity(query, identity.embeddings, self._config.top_k)
                for identity in self._identities.values()
            )
        except ValueError:
            return FaceClassification.UNCERTAIN
        if best >= self._config.match_threshold:
            return FaceClassification.WHITELISTED
        if best >= self._config.uncertainty_threshold:
            return FaceClassification.UNCERTAIN
        return FaceClassification.NON_WHITELISTED


def enroll_identity(
    store: WhitelistStore,
    analyzer: FaceAnalyzer,
    consent: EnrollmentConsent,
    images: Iterable[Any],
) -> EnrollmentResult:
    """Run the analyzer over reference images and enroll the faces that pass.

    A convenience over :meth:`WhitelistStore.enroll` for callers holding decoded
    images. The images are consumed here and never retained; only validated
    embeddings reach the store.

    The design target is roughly 30 references per identity, spanning varied
    poses, lighting, expressions, and distances (`PROJECT_OVERVIEW.md` §3.1). An
    identity enrolled from fewer references than ``top_k`` is compared by
    maximum similarity, the most permissive aggregation — prefer more
    references over fewer.
    """

    return store.enroll(consent, [tuple(analyzer.analyze(image)) for image in images])
