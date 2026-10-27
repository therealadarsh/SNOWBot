"""Edge-case coverage for backlog loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from snowbot.errors import ConfigError
from snowbot.models.backlog import BacklogItem, load_backlog


def test_backlog_item_empty_title() -> None:
    with pytest.raises(ValueError):
        BacklogItem(id="x", title="  ")


def test_load_backlog_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "backlog.yaml"
    path.write_text("items: [", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_backlog(path)


def test_load_backlog_not_mapping(tmp_path: Path) -> None:
    path = tmp_path / "backlog.yaml"
    path.write_text("plain string\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        load_backlog(path)
