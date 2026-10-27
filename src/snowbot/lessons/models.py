"""Pydantic models for proposed / accepted lessons (data only — not executable)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from snowbot.logging_setup import redact_secrets

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class LessonStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    RETIRED = "retired"


class LessonEvidence(BaseModel):
    """Pointer to supporting material (paths, URLs, PRs)."""

    kind: str = "note"
    ref: str
    summary: str = ""

    @field_validator("ref", "summary")
    @classmethod
    def _redact(cls, value: str) -> str:
        return redact_secrets(value)


class Lesson(BaseModel):
    """A single lesson record stored as YAML on disk."""

    id: str
    title: str
    body: str
    status: LessonStatus = LessonStatus.PROPOSED
    evidence: list[LessonEvidence] = Field(default_factory=list)
    dedupe_key: str = ""
    supersedes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(tz=UTC).isoformat())
    updated_at: str | None = None

    @field_validator("title", "body")
    @classmethod
    def _redact_text(cls, value: str) -> str:
        return redact_secrets(value)

    @field_validator("evidence")
    @classmethod
    def _require_evidence(cls, value: list[LessonEvidence]) -> list[LessonEvidence]:
        if not value:
            msg = "At least one evidence item is required for every lesson"
            raise ValueError(msg)
        return value

    def effective_dedupe_key(self) -> str:
        if self.dedupe_key.strip():
            return self.dedupe_key.strip().lower()
        slug = _SLUG_RE.sub("-", self.title.strip().lower()).strip("-")
        return slug or self.id

    def model_dump_yaml_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class LessonIndexEntry(BaseModel):
    id: str
    status: LessonStatus
    dedupe_key: str
    path: str


class LessonIndex(BaseModel):
    schema_version: int = 1
    lessons: list[LessonIndexEntry] = Field(default_factory=list)
