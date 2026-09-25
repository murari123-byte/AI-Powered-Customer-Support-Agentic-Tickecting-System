"""Remove secrets from text before it is sent to a language model.

Customers sometimes paste passwords, tokens or card numbers into tickets. The model never
needs them, and logs or prompts must never contain them. AIService runs every outgoing
message through `redact()`.

This is a safety net based on patterns, not a guarantee: it catches the common shapes.
"""

import re
from dataclasses import dataclass, field


@dataclass
class RedactionResult:
    text: str
    # Kinds of secret that were found, for example ["jwt", "password"]. Never the values.
    found: list[str] = field(default_factory=list)


# (kind, pattern, replacement). Order matters: specific patterns run before general ones.
_RULES: list[tuple[str, re.Pattern[str], str]] = [
    # JSON Web Tokens: three base64url parts, the first always starts with "eyJ".
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b"),
        "[REDACTED_JWT]",
    ),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [REDACTED_TOKEN]"),
    ("api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[REDACTED_API_KEY]"),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_API_KEY]"),
    # "password: hunter2", "pwd=hunter2", "api_key = abc", "secret: xyz"
    (
        "password",
        re.compile(
            r"(?i)\b(password|passwd|pwd|passcode|api[_-]?key|secret|access[_-]?token)"
            r"(\s*[:=]\s*)\S+"
        ),
        r"\1\2[REDACTED]",
    ),
    # "my password is hunter2"
    ("password", re.compile(r"(?i)\b(password|passcode)(\s+is\s+)\S+"), r"\1\2[REDACTED]"),
    # "OTP 482913", "pin is 1234", "cvv: 123". Digits only, so "the charging pin is bent" is kept.
    (
        "pin_or_otp",
        re.compile(r"(?i)\b(pin|otp|cvv)(\s*(?:is\s+|[:=]\s*)?)\d{3,8}\b"),
        r"\1\2[REDACTED]",
    ),
]

# 13-19 digits, optionally separated by single spaces or dashes.
_CARD_CANDIDATE = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")


def _passes_luhn(digits: str) -> bool:
    """Card numbers satisfy the Luhn checksum. Order or phone numbers usually don't."""
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def redact(text: str) -> RedactionResult:
    found: list[str] = []

    for kind, pattern, replacement in _RULES:
        text, count = pattern.subn(replacement, text)
        if count:
            found.append(kind)

    def _replace_card(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group())
        if _passes_luhn(digits):
            found.append("card_number")
            return "[REDACTED_CARD]"
        return match.group()

    text = _CARD_CANDIDATE.sub(_replace_card, text)

    # Keep each kind once, in first-seen order.
    return RedactionResult(text=text, found=list(dict.fromkeys(found)))
