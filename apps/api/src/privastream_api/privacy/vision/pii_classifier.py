"""Deterministic visual PII recognizers for OCR text."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

PiiKind = Literal["email", "phone"]

_EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[A-Z0-9.!#$%&'*+/=?^_{}|~-]+@"
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(r"(?<!\w)\+?\d[\d\s().-]{6,}\d(?!\w)")


@dataclass(frozen=True, slots=True)
class PiiMatch:
    """A deterministic match in normalized OCR text."""

    kind: PiiKind
    start: int
    end: int


def normalize_ocr_text(text: str) -> str:
    """Return a matching copy without mutating or logging the source text."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("…", "...")
    return re.sub(r"\s+", " ", normalized).strip(" |~")


def classify_pii(text: str) -> tuple[PiiMatch, ...]:
    """Classify email and phone patterns without treating all OCR as sensitive."""

    normalized = normalize_ocr_text(text)
    matches = [
        PiiMatch(kind="email", start=match.start(), end=match.end())
        for match in _EMAIL_PATTERN.finditer(normalized)
    ]
    for match in _PHONE_PATTERN.finditer(normalized):
        digits = re.sub(r"\D", "", match.group())
        if 8 <= len(digits) <= 15:
            matches.append(PiiMatch(kind="phone", start=match.start(), end=match.end()))
    return tuple(sorted(matches, key=lambda match: (match.start, match.end, match.kind)))
