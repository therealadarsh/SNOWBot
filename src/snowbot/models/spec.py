"""Pipeline specification model (``docs/pipeline-spec.yaml``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from snowbot.errors import ConfigError, FileOperationError


class PipelineStep(BaseModel):
    """Single unit of work within a pipeline phase."""

    id: str
    title: str
    description: str | None = None
    optional: bool = False

    @field_validator("id", "title")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            msg = "id and title must be non-empty"
            raise ValueError(msg)
        return value.strip()


class PipelinePhase(BaseModel):
    """Grouped steps executed in order during pipeline setup."""

    id: str
    title: str
    steps: list[PipelineStep] = Field(default_factory=list)

    @field_validator("id", "title")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            msg = "id and title must be non-empty"
            raise ValueError(msg)
        return value.strip()


class PipelineSpec(BaseModel):
    """Declarative description of the SNOWBot install pipeline."""

    schema_version: Literal[1] = 1
    name: str
    phases: list[PipelinePhase] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _non_empty_name(cls, value: str) -> str:
        if not value.strip():
            msg = "name must be non-empty"
            raise ValueError(msg)
        return value.strip()

    def phase_ids(self) -> list[str]:
        """Return ordered phase identifiers."""
        return [phase.id for phase in self.phases]

    def step_count(self) -> int:
        """Return total number of steps across all phases."""
        return sum(len(phase.steps) for phase in self.phases)


def load_pipeline_spec(path: Path) -> PipelineSpec:
    """Load a pipeline spec YAML file."""
    if not path.is_file():
        msg = f"Pipeline spec not found: {path}"
        raise ConfigError(msg, code="spec_not_found", details={"path": str(path)})

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"Unable to read pipeline spec: {path}"
        raise FileOperationError(msg, details={"path": str(path)}) from exc

    try:
        payload: Any = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML in pipeline spec: {path}"
        raise ConfigError(msg, details={"path": str(path)}) from exc

    if not isinstance(payload, dict):
        msg = f"Pipeline spec root must be a mapping: {path}"
        raise ConfigError(msg, details={"path": str(path)})

    try:
        return PipelineSpec.model_validate(payload)
    except Exception as exc:
        msg = f"Pipeline spec validation failed for {path}"
        raise ConfigError(msg, details={"path": str(path)}) from exc
