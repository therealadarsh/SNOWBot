"""Tests for snowbot.models.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from snowbot.errors import ConfigError
from snowbot.models.config import (
    BackendKind,
    SnowbotConfig,
    load_config,
    resolve_config_path,
)


def test_resolve_config_path_default() -> None:
    assert resolve_config_path() == Path("snowbot.yaml")


def test_resolve_config_path_explicit() -> None:
    assert resolve_config_path(Path("/tmp/custom.yaml")) == Path("/tmp/custom.yaml")


def test_resolve_config_path_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNOWBOT_CONFIG", "/env/snowbot.yaml")
    assert resolve_config_path() == Path("/env/snowbot.yaml")


def test_load_config_success(tmp_path: Path) -> None:
    cfg_file = tmp_path / "snowbot.yaml"
    cfg_file.write_text(
        "schema_version: 1\ndisplay_name: Demo\n",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.display_name == "Demo"
    assert cfg.pipeline.setup_branch == "chore/snowbot-setup"


def test_load_config_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yaml")


def test_load_config_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(":\n  - broken", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_config(path)


def test_effective_backend_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNOWBOT_BACKEND", "cursor")
    cfg = SnowbotConfig(display_name="x")
    assert cfg.effective_backend_kind() == BackendKind.CURSOR


def test_effective_backend_invalid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNOWBOT_BACKEND", "unknown-backend")
    cfg = SnowbotConfig(display_name="x")
    with pytest.raises(ConfigError):
        cfg.effective_backend_kind()


def test_model_dump_yaml_roundtrip() -> None:
    cfg = SnowbotConfig(display_name="Roundtrip")
    dumped = cfg.model_dump_yaml()
    assert "display_name: Roundtrip" in dumped
