"""CLI commands for validate, lesson, playbook, onboard, status."""

from __future__ import annotations

from typer.testing import CliRunner

from snowbot.cli import app

runner = CliRunner()


def test_help_lists_new_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("validate", "playbook", "onboard", "lesson", "status"):
        assert name in result.stdout


def test_status_requires_check_flag() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 2


def test_validate_dry_run() -> None:
    result = runner.invoke(app, ["validate", "--phase", "1b", "--dry-run"])
    assert result.exit_code == 0


def test_lesson_add_dry_run(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "lesson",
            "add",
            "--title",
            "T",
            "--body",
            "B",
            "--evidence-ref",
            "docs/x.md",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0


def test_onboard_dry_run(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["onboard", "--stage", "scaffold", "--dry-run"])
    assert result.exit_code == 0
    assert "Validator role" in result.stdout


def test_status_check_repo() -> None:
    runner.invoke(app, ["playbook"])
    result = runner.invoke(app, ["status", "--check"])
    assert result.exit_code == 0
