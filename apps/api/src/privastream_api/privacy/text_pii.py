"""Shared modality-neutral text-PII recognition contracts and recognizers.

Callers own modality-specific normalization.  This module receives normalized
text and returns safe metadata only; it never stores or logs a matched value.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Literal, Protocol

TextPiiCategory = Literal[
    "email",
    "phone_number",
    "postal_address",
    "government_id",
    "payment_identifier",
    "custom_sensitive_text",
]
ConfiguredTextPiiCategory = Literal["government_id", "payment_identifier"]

_TEXT_PII_CATEGORIES = frozenset(
    {
        "email",
        "phone_number",
        "postal_address",
        "government_id",
        "payment_identifier",
        "custom_sensitive_text",
    }
)
_CONFIGURED_CATEGORIES = frozenset({"government_id", "payment_identifier"})

_EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[a-z0-9.!#$%&'*+/=?^_`{|}~-]+\s*@\s*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\s*\.\s*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(r"(?<!\w)\+?\d[\d\s().-]*\d(?!\w)")
_DATE_PATTERN = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}$")
_DECIMAL_PATTERN = re.compile(r"^\d+\.\d{1,2}$")


class TextPiiRecognitionError(RuntimeError):
    """Base error for a text recognizer that could not produce a result."""


class TextPiiRecognizerUnavailable(TextPiiRecognitionError):
    """A configured contextual recognizer is unavailable."""


class TextPiiRecognizerExecutionError(TextPiiRecognitionError):
    """A contextual recognizer failed while processing text."""


@dataclass(frozen=True, slots=True)
class PiiSpan:
    """A safe category, confidence, and character span in normalized text."""

    category: TextPiiCategory
    confidence: float
    start: int
    end: int
    source: str
    unit: Literal["character"] = "character"

    def __post_init__(self) -> None:
        if self.category not in _TEXT_PII_CATEGORIES:
            raise ValueError("unsupported text PII category")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("PII confidence must be between 0 and 1")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("PII span must be non-empty and non-negative")
        if self.unit != "character":
            raise ValueError("text PII spans use character offsets")
        if not self.source.strip():
            raise ValueError("PII source must not be empty")

    @property
    def kind(self) -> TextPiiCategory:
        """Compatibility alias for the former visual classifier result."""

        return self.category


@dataclass(frozen=True, slots=True)
class ConfiguredTextPiiPattern:
    """An explicitly configured deterministic identity/payment format."""

    category: ConfiguredTextPiiCategory
    pattern: str
    source: str
    confidence: float = 0.9

    def __post_init__(self) -> None:
        if self.category not in _CONFIGURED_CATEGORIES:
            raise ValueError("configured patterns must identify government or payment PII")
        if not self.pattern.strip():
            raise ValueError("configured PII pattern must not be empty")
        if not self.source.strip():
            raise ValueError("configured PII source must not be empty")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("configured PII confidence must be between 0 and 1")
        try:
            re.compile(self.pattern, re.IGNORECASE)
        except re.error as exc:
            raise ValueError("configured PII pattern must be valid") from exc


@dataclass(frozen=True, slots=True)
class TextPiiRecognizerConfig:
    """Deterministic recognizer thresholds and optional configured formats."""

    email_enabled: bool = True
    phone_enabled: bool = True
    email_confidence: float = 0.99
    phone_confidence: float = 0.95
    phone_min_digits: int = 8
    phone_max_digits: int = 15
    configured_patterns: tuple[ConfiguredTextPiiPattern, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (
            ("email_confidence", self.email_confidence),
            ("phone_confidence", self.phone_confidence),
        ):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.phone_min_digits <= 0 or self.phone_max_digits < self.phone_min_digits:
            raise ValueError("phone digit bounds are invalid")


class ContextualTextPiiClassifier(Protocol):
    """Replaceable NER/classifier boundary for context-dependent categories."""

    source: str

    def recognize(
        self, text: str, context: Mapping[str, str] | None = None
    ) -> Sequence[PiiSpan]:
        """Return canonical spans without exposing matched values."""


def _phone_candidate_is_plausible(value: str, *, min_digits: int, max_digits: int) -> bool:
    digits = re.sub(r"\D", "", value)
    if not min_digits <= len(digits) <= max_digits:
        return False
    compact = value.strip()
    if _DATE_PATTERN.fullmatch(compact):
        return False
    if _DECIMAL_PATTERN.fullmatch(compact) and not compact.startswith("+"):
        return False
    return True


def _overlaps(left: PiiSpan, right: PiiSpan) -> bool:
    return left.start < right.end and right.start < left.end


class TextPiiRecognizer:
    """Recognize structured text PII and optionally delegate contextual PII."""

    def __init__(
        self,
        config: TextPiiRecognizerConfig | None = None,
        contextual_classifier: ContextualTextPiiClassifier | None = None,
    ) -> None:
        self.config = config or TextPiiRecognizerConfig()
        self.contextual_classifier = contextual_classifier

    def recognize(
        self, text: str, context: Mapping[str, str] | None = None
    ) -> tuple[PiiSpan, ...]:
        """Return canonical spans; a failure is never represented as an empty result."""

        if not isinstance(text, str):
            raise TypeError("text PII recognition requires a string")
        if not text:
            return ()

        candidates: list[PiiSpan] = []
        if self.config.email_enabled:
            candidates.extend(self._recognize_email(text))
        if self.config.phone_enabled:
            candidates.extend(self._recognize_phone(text))
        candidates.extend(self._recognize_configured(text))
        if self.contextual_classifier is not None:
            try:
                contextual = self.contextual_classifier.recognize(text, context)
            except TextPiiRecognitionError:
                raise
            except Exception:
                raise TextPiiRecognizerExecutionError(
                    "contextual text PII classifier failed"
                ) from None
            if contextual is None:
                raise TextPiiRecognizerExecutionError(
                    "contextual text PII classifier returned no result"
                )
            for span in contextual:
                if not isinstance(span, PiiSpan):
                    raise TextPiiRecognizerExecutionError(
                        "contextual text PII classifier returned an invalid span"
                    )
                if span.end > len(text):
                    raise TextPiiRecognizerExecutionError(
                        "contextual text PII classifier returned an out-of-range span"
                    )
                candidates.append(span)

        selected: list[PiiSpan] = []
        for span in sorted(
            candidates,
            key=lambda candidate: (
                candidate.start,
                -(candidate.end - candidate.start),
                candidate.category,
                candidate.source,
            ),
        ):
            if any(_overlaps(span, existing) for existing in selected):
                continue
            selected.append(span)
        return tuple(sorted(selected, key=lambda span: (span.start, span.end, span.category)))

    def _recognize_email(self, text: str) -> tuple[PiiSpan, ...]:
        return tuple(
            PiiSpan(
                category="email",
                confidence=self.config.email_confidence,
                start=match.start(),
                end=match.end(),
                source="text-email-regex",
            )
            for match in _EMAIL_PATTERN.finditer(text)
        )

    def _recognize_phone(self, text: str) -> tuple[PiiSpan, ...]:
        spans: list[PiiSpan] = []
        for match in _PHONE_PATTERN.finditer(text):
            if not _phone_candidate_is_plausible(
                match.group(),
                min_digits=self.config.phone_min_digits,
                max_digits=self.config.phone_max_digits,
            ):
                continue
            spans.append(
                PiiSpan(
                    category="phone_number",
                    confidence=self.config.phone_confidence,
                    start=match.start(),
                    end=match.end(),
                    source="text-phone-regex",
                )
            )
        return tuple(spans)

    def _recognize_configured(self, text: str) -> tuple[PiiSpan, ...]:
        spans: list[PiiSpan] = []
        for configured in self.config.configured_patterns:
            pattern = re.compile(configured.pattern, re.IGNORECASE)
            spans.extend(
                PiiSpan(
                    category=configured.category,
                    confidence=configured.confidence,
                    start=match.start(),
                    end=match.end(),
                    source=configured.source,
                )
                for match in pattern.finditer(text)
            )
        return tuple(spans)


__all__ = [
    "ConfiguredTextPiiPattern",
    "ContextualTextPiiClassifier",
    "PiiSpan",
    "TextPiiCategory",
    "TextPiiRecognitionError",
    "TextPiiRecognizer",
    "TextPiiRecognizerConfig",
    "TextPiiRecognizerExecutionError",
    "TextPiiRecognizerUnavailable",
]
