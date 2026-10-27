"""Validator runner fixtures."""

from __future__ import annotations

from pathlib import Path

from snowbot.memory.layout import MemoryLayout
from snowbot.validator.runner import run_phase_validation


def test_phase1_validation_repo_root() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    layout = MemoryLayout.from_project_root(root)
    result = run_phase_validation(layout, "1", dry_run=True)
    assert result.phase == "1"
    assert result.passed


def test_dry_run_writes_no_report(tmp_path: Path) -> None:
    root = tmp_path
    (root / "AGENTS.md").write_text("a", encoding="utf-8")
    layout = MemoryLayout.from_project_root(root)
    run_phase_validation(layout, "1", dry_run=True)
    assert not list(layout.validation_dir.glob("*.md"))
