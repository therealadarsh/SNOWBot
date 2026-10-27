"""Validator check unit tests."""

from __future__ import annotations

from pathlib import Path

from snowbot.validator.checks import CheckSpec, run_check


def test_file_exists_check(tmp_path: Path) -> None:
    root = tmp_path
    (root / "AGENTS.md").write_text("x", encoding="utf-8")
    spec = CheckSpec(id="a", description="d", kind="file_exists", path="AGENTS.md")
    outcome = run_check(root, spec)
    assert outcome.passed
