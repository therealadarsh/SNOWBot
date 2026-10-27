"""Validation report persistence."""

from __future__ import annotations

from pathlib import Path

from snowbot.memory.layout import MemoryLayout
from snowbot.validator.runner import run_phase_validation


def test_validation_writes_report(tmp_path: Path) -> None:
    root = tmp_path
    (root / "AGENTS.md").write_text("a", encoding="utf-8")
    (root / "STATUS.md").write_text("s", encoding="utf-8")
    (root / "CHANGELOG.md").write_text("## [Unreleased]\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("p", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "OPEN_QUESTIONS.md").write_text("q", encoding="utf-8")
    (root / "src" / "snowbot").mkdir(parents=True)
    (root / "src" / "snowbot" / "cli.py").write_text("c", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_cli.py").write_text("t", encoding="utf-8")
    layout = MemoryLayout.from_project_root(root)
    result = run_phase_validation(layout, 1, pr_url="https://example.com/pr/1")
    assert result.passed
    assert (layout.validation_dir / "phase-1-latest.md").is_file()
    assert list(layout.stops_dir.glob("*.json")) == []
