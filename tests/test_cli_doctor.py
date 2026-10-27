"""Additional CLI tests for doctor and main()."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from snowbot.cli import app

runner = CliRunner()


def test_doctor_with_valid_config(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "snowbot.yaml"
    cfg.write_text("schema_version: 1\ndisplay_name: OK\n", encoding="utf-8")
    result = runner.invoke(app, ["doctor", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "OK" in result.stdout


def test_run_and_update_stubs() -> None:
    for cmd in ("run", "update"):
        result = runner.invoke(app, [cmd])
        assert result.exit_code == 2
        assert "Phase 1" in result.stdout


def test_main_invokes_app() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0


def test_doctor_config_error(tmp_path: Path) -> None:
    cfg = tmp_path / "bad.yaml"
    cfg.write_text("not: [valid", encoding="utf-8")
    result = runner.invoke(app, ["doctor", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "Config error" in result.stdout
