"""Structured errors for SNOWBot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SnowbotError(Exception):
    """Base error for recoverable SNOWBot failures."""

    message: str
    code: str = "snowbot_error"
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


class ConfigError(SnowbotError):
    """Invalid or missing configuration."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "config_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, details=details)


class ValidationError(SnowbotError):
    """Domain validation failure (not Pydantic)."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "validation_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, details=details)


class FileOperationError(SnowbotError):
    """Filesystem read/write failures."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "file_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, details=details)
