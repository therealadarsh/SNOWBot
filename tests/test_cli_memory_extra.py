"""Additional CLI coverage for lessons and promote."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from snowbot.cli import app

runner = CliRunner()


def test_lesson_lifecycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    add = runner.invoke(
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
        ],
    )
    assert add.exit_code == 0
    lesson_id = add.stdout.split()[1].strip(".")
    assert runner.invoke(app, ["lesson", "list"]).exit_code == 0
    assert runner.invoke(app, ["lesson", "show", lesson_id]).exit_code == 0
    assert runner.invoke(app, ["lesson", "promote", lesson_id]).exit_code == 0
    playbook = tmp_path / ".snowbot" / "memory" / "PLAYBOOK.md"
    assert playbook.is_file()


def test_playbook_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["playbook"]).exit_code == 0
