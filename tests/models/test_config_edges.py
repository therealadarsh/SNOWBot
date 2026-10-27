"""Edge-case coverage for config loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from snowbot.errors import ConfigError
from snowbot.models.config import BackendConfig, ProjectConfig, load_config


def test_load_config_not_a_mapping(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- item\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(path)


def test_load_config_validation_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("schema_version: 2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="validation failed"):
        load_config(path)


def test_backend_config_empty_env() -> None:
    with pytest.raises(ValueError):
        BackendConfig(api_key_env="  ")


def test_project_config_coerces_strings() -> None:
    project = ProjectConfig.model_validate({"root": "src", "agents_file": "AGENTS.md"})
    assert project.root == Path("src")
