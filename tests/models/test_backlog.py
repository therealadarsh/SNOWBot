"""Tests for snowbot.models.backlog."""

from __future__ import annotations

from pathlib import Path

import pytest

from snowbot.errors import ConfigError, ValidationError
from snowbot.models.backlog import Backlog, BacklogItemStatus, load_backlog


def test_backlog_by_status() -> None:
    backlog = Backlog.model_validate(
        {
            "items": [
                {"id": "a", "title": "A", "status": "pending"},
                {"id": "b", "title": "B", "status": "done"},
            ]
        }
    )
    assert len(backlog.by_status(BacklogItemStatus.PENDING)) == 1
    assert backlog.find("b") is not None
    assert backlog.find("z") is None


def test_validate_unique_ids_raises() -> None:
    backlog = Backlog.model_validate(
        {
            "items": [
                {"id": "dup", "title": "One"},
                {"id": "dup", "title": "Two"},
            ]
        }
    )
    with pytest.raises(ValidationError, match="Duplicate"):
        backlog.validate_unique_ids()


def test_load_backlog(tmp_path: Path) -> None:
    path = tmp_path / "backlog.yaml"
    path.write_text(
        "schema_version: 1\nitems:\n  - id: x\n    title: Item\n",
        encoding="utf-8",
    )
    backlog = load_backlog(path)
    assert backlog.items[0].id == "x"


def test_load_backlog_duplicate(tmp_path: Path) -> None:
    path = tmp_path / "backlog.yaml"
    path.write_text(
        "schema_version: 1\nitems:\n  - {id: a, title: A}\n  - {id: a, title: B}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_backlog(path)


def test_load_backlog_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_backlog(tmp_path / "missing.yaml")
