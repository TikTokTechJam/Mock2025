"""Embedding representation and the whitelist comparison strategy.

Embeddings are biometric-derived and highly sensitive (`SECURITY.md` §3, §6).
Nothing here logs, formats, or returns an embedding, and no error message
carries one.

The comparison strategy is top-k mean cosine similarity with a max-similarity
fallback, chosen in `PROJECT_OVERVIEW.md` §3.2.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from math import isfinite, sqrt

Embedding = tuple[float, ...]
"""A face embedding as plain floats, so the core carries no array dependency."""


def as_embedding(values: Iterable[float]) -> Embedding:
    """Convert model output to an :data:`Embedding`.

    Raises ``ValueError`` for an empty or non-finite vector. The message names
    no values.
    """

    embedding = tuple(float(value) for value in values)
    if not embedding:
        raise ValueError("embedding must not be empty")
    if any(not isfinite(value) for value in embedding):
        raise ValueError("embedding values must be finite")
    return embedding


def l2_normalize(embedding: Embedding) -> Embedding:
    """Return ``embedding`` scaled to unit length.

    ArcFace similarity is cosine similarity, so both stored references and
    per-frame queries are normalized once and compared with a plain dot product.
    """

    magnitude = sqrt(sum(value * value for value in embedding))
    if not isfinite(magnitude) or magnitude <= 0:
        raise ValueError("embedding must have a positive finite magnitude")
    return tuple(value / magnitude for value in embedding)


def cosine_similarity(query: Embedding, reference: Embedding) -> float:
    """Return cosine similarity of two L2-normalized embeddings, in ``[-1, 1]``."""

    if len(query) != len(reference):
        raise ValueError("embeddings must have the same dimension")
    dot = sum(left * right for left, right in zip(query, reference, strict=True))
    return max(-1.0, min(1.0, dot))


def top_k_mean_similarity(query: Embedding, references: Sequence[Embedding], top_k: int) -> float:
    """Aggregate ``query`` against one identity's whole reference set.

    Averaging the ``top_k`` highest similarities requires agreement from several
    references, so a single outlier or partially mislabeled reference cannot
    whitelist a stranger. Identities with fewer than ``top_k`` validated
    references fall back to maximum similarity, as specified in
    `PROJECT_OVERVIEW.md` §3.2 — averaging a short reference set would
    under-match the enrolled creator instead.
    """

    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if not references:
        raise ValueError("identity has no validated reference embeddings")
    similarities = sorted(
        (cosine_similarity(query, reference) for reference in references), reverse=True
    )
    if len(similarities) < top_k:
        return similarities[0]
    return sum(similarities[:top_k]) / top_k
