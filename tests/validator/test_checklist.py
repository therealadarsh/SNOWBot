"""checklist.yaml covers every planned phase with known check kinds."""

from __future__ import annotations

from importlib import resources
from typing import Any

import pytest
import yaml

from snowbot.validator.checks import _CHECK_RUNNERS

PLANNED_PHASES = ("1", "1b", "2b", "2", "4", "3", "5", "5b", "7", "8", "2c", "6", "9")


def _phases() -> dict[str, Any]:
    text = resources.files("snowbot.validator").joinpath("checklist.yaml").read_text("utf-8")
    payload = yaml.safe_load(text)
    return {str(key): value for key, value in payload["phases"].items()}


def test_checklist_keys_are_strings_in_source() -> None:
    raw = yaml.safe_load(
        resources.files("snowbot.validator").joinpath("checklist.yaml").read_text("utf-8")
    )
    assert all(isinstance(key, str) for key in raw["phases"])


@pytest.mark.parametrize("phase", PLANNED_PHASES)
def test_planned_phase_has_checklist(phase: str) -> None:
    doc = _phases()[phase]
    kinds = [check["kind"] for check in doc["checks"]]
    assert "anti_gaming_diff" in kinds
    assert set(kinds) <= set(_CHECK_RUNNERS)


@pytest.mark.parametrize("phase", PLANNED_PHASES)
def test_check_ids_unique_within_phase(phase: str) -> None:
    ids = [check["id"] for check in _phases()[phase]["checks"]]
    assert len(ids) == len(set(ids))
