"""Validator failure captures stop events."""

from __future__ import annotations

from pathlib import Path

from snowbot.memory.layout import MemoryLayout
from snowbot.validator.runner import run_phase_validation


def test_failed_validation_stop(tmp_path: Path) -> None:
    layout = MemoryLayout.from_project_root(tmp_path)
    layout.ensure_structure()
    result = run_phase_validation(layout, "1")
    assert not result.passed
    assert list(layout.stops_dir.glob("*.json"))
