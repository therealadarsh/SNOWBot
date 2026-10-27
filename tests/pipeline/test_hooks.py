"""Pipeline hook smoke tests."""

from __future__ import annotations

from pathlib import Path

from snowbot.memory.layout import MemoryLayout
from snowbot.pipeline.hooks import StageHooks


def test_onboard_and_gate(tmp_path: Path) -> None:
    root = tmp_path
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / "STATUS.md").write_text("# STATUS\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text("## [Unreleased]\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "OPEN_QUESTIONS.md").write_text("q", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "snowbot").mkdir(parents=True)
    (root / "src" / "snowbot" / "cli.py").write_text("# cli", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_cli.py").write_text("# t", encoding="utf-8")
    layout = MemoryLayout.from_project_root(root)
    hooks = StageHooks(layout)
    pack = hooks.at_stage_start("scaffold", dry_run=True)
    assert "Validator role" in pack
    result = hooks.validator_gate("1", dry_run=True)
    assert result.passed
