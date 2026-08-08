from privastream_api.privacy.vision.pii_classifier import classify_pii, normalize_ocr_text


def test_email_and_phone_are_classified() -> None:
    matches = classify_pii("Email: Owner@Example.com or call +65 8123 4567")

    assert [match.kind for match in matches] == ["email", "phone"]


def test_benign_ocr_text_is_not_classified() -> None:
    assert classify_pii("Welcome to the neighborhood market") == ()


def test_matching_normalizes_unicode_and_whitespace() -> None:
    assert normalize_ocr_text("  Caf\u00e9\u00a0Owner  ") == "caf\u00e9 owner"
