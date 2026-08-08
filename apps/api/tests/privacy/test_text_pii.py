from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from privastream_api.privacy.text_pii import (
    ConfiguredTextPiiPattern,
    PiiSpan,
    TextPiiRecognizer,
    TextPiiRecognizerConfig,
    TextPiiRecognizerUnavailable,
)


def test_shared_recognizer_returns_canonical_email_and_phone_spans() -> None:
    text = "Contact owner@example.com or call +65 8123 4567"

    spans = TextPiiRecognizer().recognize(text)

    assert [(span.category, text[span.start : span.end]) for span in spans] == [
        ("email", "owner@example.com"),
        ("phone_number", "+65 8123 4567"),
    ]
    assert all(span.source.startswith("text-") for span in spans)


def test_dates_prices_and_short_random_numbers_are_not_phone_matches() -> None:
    text = "Report date 2025-01-31, price 123456.78, build 1234567"

    assert TextPiiRecognizer().recognize(text) == ()


def test_structured_recognizers_can_be_disabled_by_configuration() -> None:
    recognizer = TextPiiRecognizer(
        TextPiiRecognizerConfig(email_enabled=False, phone_enabled=False)
    )

    assert recognizer.recognize("owner@example.com +65 8123 4567") == ()


def test_configured_identity_and_payment_formats_are_supported() -> None:
    recognizer = TextPiiRecognizer(
        TextPiiRecognizerConfig(
            configured_patterns=(
                ConfiguredTextPiiPattern(
                    category="government_id",
                    pattern=r"\bSG\d{7}[A-Z]\b",
                    source="configured-sg-id",
                ),
                ConfiguredTextPiiPattern(
                    category="payment_identifier",
                    pattern=r"\bPAY-\d{8}\b",
                    source="configured-payment-id",
                ),
            )
        )
    )

    spans = recognizer.recognize("SG1234567A and PAY-12345678")

    assert [span.category for span in spans] == ["government_id", "payment_identifier"]
    assert [span.source for span in spans] == ["configured-sg-id", "configured-payment-id"]


class FixedContextualClassifier:
    source = "contextual-test"

    def recognize(
        self, text: str, context: Mapping[str, str] | None = None
    ) -> Sequence[PiiSpan]:
        assert context == {"locale": "en"}
        return (PiiSpan("postal_address", 0.8, 0, 7, self.source),)


def test_contextual_classifier_is_replaceable_and_uses_canonical_spans() -> None:
    recognizer = TextPiiRecognizer(contextual_classifier=FixedContextualClassifier())

    spans = recognizer.recognize("address", {"locale": "en"})

    assert spans == (PiiSpan("postal_address", 0.8, 0, 7, "contextual-test"),)


class UnavailableContextualClassifier:
    source = "contextual-unavailable"

    def recognize(
        self, text: str, context: Mapping[str, str] | None = None
    ) -> Sequence[PiiSpan]:
        raise TextPiiRecognizerUnavailable("classifier unavailable")


def test_contextual_failure_is_not_reported_as_zero_pii() -> None:
    assert TextPiiRecognizer().recognize("ordinary text") == ()

    recognizer = TextPiiRecognizer(contextual_classifier=UnavailableContextualClassifier())
    with pytest.raises(TextPiiRecognizerUnavailable):
        recognizer.recognize("ordinary text")
