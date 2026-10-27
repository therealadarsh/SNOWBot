"""``snowbot.yaml`` configuration model and loader."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from snowbot.errors import ConfigError, FileOperationError

DEFAULT_CONFIG_FILENAME = "snowbot.yaml"
CONFIG_ENV_VAR = "SNOWBOT_CONFIG"
BACKEND_ENV_VAR = "SNOWBOT_BACKEND"


class BackendKind(StrEnum):
    """Supported agent backends (adapters implemented in later phases)."""

    CURSOR = "cursor"


class BackendConfig(BaseModel):
    """Backend connection settings."""

    kind: BackendKind = BackendKind.CURSOR
    api_key_env: str = "CURSOR_API_KEY"

    @field_validator("api_key_env")
    @classmethod
    def _non_empty_env(cls, value: str) -> str:
        if not value.strip():
            msg = "api_key_env must be a non-empty environment variable name"
            raise ValueError(msg)
        return value


class ProjectConfig(BaseModel):
    """Target repository layout."""

    root: Path = Field(default_factory=Path.cwd)
    agents_file: Path = Path("AGENTS.md")
    context_dir: Path = Path(".cursor")
    memory_dir: Path = Path(".snowbot/memory")

    @field_validator("root", "agents_file", "context_dir", "memory_dir", mode="before")
    @classmethod
    def _coerce_path(cls, value: Any) -> Path:
        return Path(value) if not isinstance(value, Path) else value


class PipelineConfig(BaseModel):
    """Pipeline artifact locations and VCS conventions."""

    setup_branch: str = "chore/snowbot-setup"
    spec_path: Path = Path("docs/pipeline-spec.yaml")
    backlog_path: Path = Path("docs/backlog.yaml")

    @field_validator("spec_path", "backlog_path", mode="before")
    @classmethod
    def _coerce_path(cls, value: Any) -> Path:
        return Path(value) if not isinstance(value, Path) else value


class SnowbotConfig(BaseModel):
    """Root configuration document persisted as ``snowbot.yaml``."""

    schema_version: Literal[1] = 1
    display_name: str = "SNOWBot Project"
    backend: BackendConfig = Field(default_factory=BackendConfig)
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)

    def effective_backend_kind(self) -> BackendKind:
        """Return backend kind, honoring ``SNOWBOT_BACKEND`` when set."""
        override = os.environ.get(BACKEND_ENV_VAR)
        if override:
            try:
                return BackendKind(override.strip().lower())
            except ValueError as exc:
                msg = f"Invalid {BACKEND_ENV_VAR}={override!r}"
                raise ConfigError(msg, details={"env": BACKEND_ENV_VAR}) from exc
        return self.backend.kind

    def model_dump_yaml(self) -> str:
        """Serialize config to YAML for templates and tests."""
        data = self.model_dump(mode="json")
        return yaml.safe_dump(data, sort_keys=False)


def resolve_config_path(explicit: Path | None = None) -> Path:
    """Resolve config file path from explicit arg, env, or default filename."""
    if explicit is not None:
        return explicit.expanduser()
    env_path = os.environ.get(CONFIG_ENV_VAR)
    if env_path:
        return Path(env_path).expanduser()
    return Path(DEFAULT_CONFIG_FILENAME)


def load_config(path: Path | None = None) -> SnowbotConfig:
    """Load and validate ``snowbot.yaml`` (or path from ``SNOWBOT_CONFIG``)."""
    config_path = resolve_config_path(path)
    if not config_path.is_file():
        msg = f"Configuration file not found: {config_path}"
        raise ConfigError(msg, code="config_not_found", details={"path": str(config_path)})

    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"Unable to read configuration: {config_path}"
        raise FileOperationError(msg, details={"path": str(config_path)}) from exc

    try:
        payload = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML in {config_path}"
        raise ConfigError(msg, details={"path": str(config_path)}) from exc

    if not isinstance(payload, dict):
        msg = f"Configuration root must be a mapping: {config_path}"
        raise ConfigError(msg, details={"path": str(config_path)})

    try:
        return SnowbotConfig.model_validate(payload)
    except Exception as exc:
        msg = f"Configuration validation failed for {config_path}"
        raise ConfigError(msg, details={"path": str(config_path)}) from exc
