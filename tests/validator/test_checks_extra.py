"""Extra validator check branches."""

from __future__ import annotations

from pathlib import Path

from snowbot.validator.checks import CheckSpec, run_check


def test_unknown_kind(tmp_path: Path) -> None:
    spec = CheckSpec(id="x", description="d", kind="unknown")
    assert not run_check(tmp_path, spec).passed


def test_playbook_missing_skips(tmp_path: Path) -> None:
    spec = CheckSpec(id="p", description="d", kind="playbook_line_cap", path="missing.md")
    assert run_check(tmp_path, spec).passed
