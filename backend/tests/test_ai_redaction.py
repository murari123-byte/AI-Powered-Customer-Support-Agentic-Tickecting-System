import pytest

from app.ai.redaction import redact

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk"


@pytest.mark.parametrize(
    ("text", "secret", "kind"),
    [
        (f"my token {JWT} expired", JWT, "jwt"),
        ("Authorization: Bearer abcDEF123456.xyz", "abcDEF123456.xyz", "bearer_token"),
        ("key sk-proj1234567890abcdefXYZ leaked", "sk-proj1234567890abcdefXYZ", "api_key"),
        ("aws AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE", "aws_access_key"),
        ("password: hunter2", "hunter2", "password"),
        ("pwd=S3cret!", "S3cret!", "password"),
        ("My Password is hunter2 please help", "hunter2", "password"),
        ("api_key = abc123xyz", "abc123xyz", "password"),
        ("the OTP 482913 didn't work", "482913", "pin_or_otp"),
        ("my pin is 1234", "1234", "pin_or_otp"),
        ("card 4111 1111 1111 1111 was charged twice", "4111 1111 1111 1111", "card_number"),
        ("card 4111-1111-1111-1111", "4111-1111-1111-1111", "card_number"),
    ],
)
def test_secrets_are_removed(text: str, secret: str, kind: str) -> None:
    result = redact(text)

    assert secret not in result.text
    assert "REDACTED" in result.text
    assert kind in result.found


@pytest.mark.parametrize(
    "text",
    [
        "I can't reset my password, the link is broken",
        "The charging pin is bent",
        "Order 1234567890123 has not arrived",  # 13 digits, fails the Luhn check
        "Call me on 9876543210",
        "Ticket #42 is still open",
    ],
)
def test_normal_support_text_is_untouched(text: str) -> None:
    result = redact(text)

    assert result.text == text
    assert result.found == []


def test_each_kind_is_reported_once() -> None:
    result = redact("password: a1 and later password: b2")

    assert result.found == ["password"]
    assert "a1" not in result.text
    assert "b2" not in result.text
