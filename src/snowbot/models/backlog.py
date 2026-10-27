"""Backlog model for phased delivery tracking."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from snowbot.errors import ConfigError, FileOperationError, ValidationError


class BacklogItemStatus(StrEnum):
    """Lifecycle states for backlog items."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELED = "canceled"


class BacklogItem(BaseModel):
    """One trackable unit of work (maps to a spec step or free-form task)."""

    id: str
    title: str
    phase: str | None = None
    status: BacklogItemStatus = BacklogItemStatus.PENDING

    @field_validator("id", "title")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            msg = "id and title must be non-empty"
            raise ValueError(msg)
        return value.strip()


class Backlog(BaseModel):
    """Collection of backlog items for STATUS and automation."""

    schema_version: Literal[1] = 1
    items: list[BacklogItem] = Field(default_factory=list)

    def by_status(self, status: BacklogItemStatus) -> list[BacklogItem]:
        """Filter items by status."""
        return [item for item in self.items if item.status == status]

    def find(self, item_id: str) -> BacklogItem | None:
        """Return item by id or ``None``."""
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def validate_unique_ids(self) -> None:
        """Ensure backlog ids are unique."""
        seen: set[str] = set()
        duplicates: list[str] = []
        for item in self.items:
            if item.id in seen:
                duplicates.append(item.id)
            seen.add(item.id)
        if duplicates:
            msg = f"Duplicate backlog ids: {', '.join(sorted(set(duplicates)))}"
            raise ValidationError(msg, details={"ids": duplicates})


def load_backlog(path: Path) -> Backlog:
    """Load backlog YAML and validate uniqueness."""
    if not path.is_file():
        msg = f"Backlog file not found: {path}"
        raise ConfigError(msg, code="backlog_not_found", details={"path": str(path)})

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"Unable to read backlog: {path}"
        raise FileOperationError(msg, details={"path": str(path)}) from exc

    try:
        payload: Any = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML in backlog: {path}"
        raise ConfigError(msg, details={"path": str(path)}) from exc

    if not isinstance(payload, dict):
        msg = f"Backlog root must be a mapping: {path}"
        raise ConfigError(msg, details={"path": str(path)})

    try:
        backlog = Backlog.model_validate(payload)
    except Exception as exc:
        msg = f"Backlog validation failed for {path}"
        raise ConfigError(msg, details={"path": str(path)}) from exc

    backlog.validate_unique_ids()
    return backlog
