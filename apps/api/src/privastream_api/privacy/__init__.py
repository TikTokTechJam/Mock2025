"""Shared privacy contracts and detector adapters."""

from privastream_api.privacy.text_pii import (
    ConfiguredTextPiiPattern,
    ContextualTextPiiClassifier,
    PiiSpan,
    TextPiiRecognizer,
    TextPiiRecognizerConfig,
    TextPiiRecognizerExecutionError,
    TextPiiRecognizerUnavailable,
)

__all__ = [
    "ConfiguredTextPiiPattern",
    "ContextualTextPiiClassifier",
    "PiiSpan",
    "TextPiiRecognizer",
    "TextPiiRecognizerConfig",
    "TextPiiRecognizerExecutionError",
    "TextPiiRecognizerUnavailable",
]
