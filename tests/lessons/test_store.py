"""Lesson store CRUD and dedupe."""

from __future__ import annotations

from pathlib import Path

import pytest

from snowbot.lessons.models import Lesson, LessonEvidence, LessonStatus
from snowbot.lessons.store import LessonStore, LessonStoreError
from snowbot.memory.layout import MemoryLayout


def test_add_and_dedupe(tmp_path: Path) -> None:
    root = tmp_path
    layout = MemoryLayout.from_project_root(root)
    store = LessonStore(layout)
    lesson = Lesson(
        id="abc",
        title="One",
        body="body",
        evidence=[LessonEvidence(ref="docs/x.md")],
        dedupe_key="same",
    )
    store.add_proposed(lesson)
    dup = Lesson(
        id="def",
        title="Two",
        body="body",
        evidence=[LessonEvidence(ref="docs/y.md")],
        dedupe_key="same",
    )
    with pytest.raises(LessonStoreError, match="Duplicate"):
        store.add_proposed(dup)


def test_accept_moves_file(tmp_path: Path) -> None:
    root = tmp_path
    layout = MemoryLayout.from_project_root(root)
    store = LessonStore(layout)
    lesson = Lesson(
        id="move",
        title="Move",
        body="b",
        evidence=[LessonEvidence(ref="r")],
    )
    store.add_proposed(lesson)
    store.accept("move")
    assert (layout.lessons_accepted / "move.yaml").is_file()
    assert store.get("move").status == LessonStatus.ACCEPTED


def test_corrupted_lesson(tmp_path: Path) -> None:
    root = tmp_path
    layout = MemoryLayout.from_project_root(root)
    layout.ensure_structure()
    bad = layout.lessons_proposed / "bad.yaml"
    bad.write_text(": [", encoding="utf-8")
    store = LessonStore(layout)
    with pytest.raises(LessonStoreError):
        store.get("bad")
