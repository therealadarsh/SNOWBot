"""Tests for snowbot.models.spec."""

from __future__ import annotations

from pathlib import Path

import pytest

from snowbot.errors import ConfigError
from snowbot.models.spec import PipelineSpec, load_pipeline_spec


def test_pipeline_spec_counts() -> None:
    spec = PipelineSpec(
        name="Test",
        phases=[
            {
                "id": "p1",
                "title": "One",
                "steps": [{"id": "s1", "title": "Step"}],
            }
        ],
    )
    assert spec.step_count() == 1
    assert spec.phase_ids() == ["p1"]


def test_load_pipeline_spec(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text(
        "schema_version: 1\nname: Loaded\nphases: []\n",
        encoding="utf-8",
    )
    spec = load_pipeline_spec(path)
    assert spec.name == "Loaded"


def test_load_pipeline_spec_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_pipeline_spec(tmp_path / "nope.yaml")
