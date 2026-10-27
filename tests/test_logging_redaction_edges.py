"""Additional redaction coverage."""

from snowbot.logging_setup import _redact_match, redact_secrets


def test_redact_match_without_separator() -> None:
    assert _redact_match("sk-abcdefghijklmnopqrstuvwxyz") == "[REDACTED]"


def test_redact_access_token_url() -> None:
    text = "https://x-access-token:abc123@github.com/org/repo"
    assert "[REDACTED]" in redact_secrets(text)
