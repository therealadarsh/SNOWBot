"""Tests for secret redaction logging."""

from __future__ import annotations

import logging

from snowbot.logging_setup import (
    SecretRedactingFilter,
    configure_logging,
    get_logger,
    redact_secrets,
)


def test_redact_api_key_assignment() -> None:
    text = "CURSOR_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456"
    assert "[REDACTED]" in redact_secrets(text)
    assert "sk-" not in redact_secrets(text)


def test_redact_bearer_token() -> None:
    text = "Authorization: Bearer abc.def.ghi"
    redacted = redact_secrets(text)
    assert "abc.def" not in redacted
    assert "[REDACTED]" in redacted


def test_secret_filter_on_log_record() -> None:
    configure_logging(logging.INFO)
    get_logger("test.redaction")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="token=supersecret",
        args=(),
        exc_info=None,
    )
    assert SecretRedactingFilter().filter(record) is True
    assert "[REDACTED]" in record.msg
