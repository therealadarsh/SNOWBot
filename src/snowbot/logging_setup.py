"""Logging configuration with secret redaction."""

from __future__ import annotations

import logging
import re
from typing import Final

REDACTED: Final = "[REDACTED]"

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"x-access-token:[^\s@]+@[^\s]+"),
)


def redact_secrets(text: str) -> str:
    """Replace likely secrets in *text* with a stable placeholder."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(lambda m: _redact_match(m.group(0)), redacted)
    return redacted


def _redact_match(original: str) -> str:
    if ":" in original or "=" in original:
        sep = ":" if ":" in original else "="
        prefix = original.split(sep, 1)[0] + sep
        return prefix + REDACTED
    return REDACTED


class SecretRedactingFilter(logging.Filter):
    """Logging filter that redacts secrets from log messages and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_secrets(str(record.msg))
        if record.args:
            record.args = tuple(
                redact_secrets(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        return True


def configure_logging(level: int | str = logging.INFO) -> None:
    """Configure root logging for CLI use with secret redaction."""
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.addFilter(SecretRedactingFilter())
    handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s: %(message)s"),
    )
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a module logger (call :func:`configure_logging` once at startup)."""
    return logging.getLogger(name)
