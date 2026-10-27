"""Edge-case coverage for pipeline spec loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from snowbot.errors import ConfigError
from snowbot.models.spec import PipelineStep, load_pipeline_spec


def test_pipeline_step_empty_id() -> None:
    with pytest.raises(ValueError):
        PipelineStep(id="  ", title="x")


def test_load_spec_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text("name: [broken", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_pipeline_spec(path)


def test_load_spec_not_mapping(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        load_pipeline_spec(path)


def test_load_spec_validation(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text("schema_version: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="validation failed"):
        load_pipeline_spec(path)
