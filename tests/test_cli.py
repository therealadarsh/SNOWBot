"""CLI smoke tests."""

from __future__ import annotations

from typer.testing import CliRunner

from snowbot.cli import app

runner = CliRunner()


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("doctor", "init", "run", "update"):
        assert name in result.stdout


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_doctor_without_config() -> None:
    result = runner.invoke(app, ["doctor"], env={"SNOWBOT_CONFIG": "/nonexistent/snowbot.yaml"})
    assert result.exit_code == 0
    assert "optional until init" in result.stdout.lower() or "No config" in result.stdout


def test_init_stub_exits() -> None:
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 2
    assert "Phase 1" in result.stdout
