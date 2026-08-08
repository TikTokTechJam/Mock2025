"""Compatibility helpers for the shared text-PII recognizer.

OCR normalization remains visual-owned. Recognition itself is implemented by
``privastream_api.privacy.text_pii.TextPiiRecognizer`` so spoken and visual
paths cannot drift apart.
"""

from __future__ import annotations

import unicodedata

from privastream_api.privacy.text_pii import PiiSpan, TextPiiRecognizer

PiiMatch = PiiSpan


def normalize_ocr_text(text: str) -> str:
    """Return a matching copy without mutating or logging the source text."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("…", "...")
    return " ".join(normalized.split()).strip(" |~")


def classify_pii(text: str) -> tuple[PiiMatch, ...]:
    """Recognize normalized OCR text through the shared production service."""

    return TextPiiRecognizer().recognize(normalize_ocr_text(text))


__all__ = ["PiiMatch", "PiiSpan", "classify_pii", "normalize_ocr_text"]
