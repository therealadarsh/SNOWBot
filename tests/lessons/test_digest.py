"""Playbook generation and line cap."""

from __future__ import annotations

from pathlib import Path

from snowbot.lessons.digest import PLAYBOOK_MAX_LINES, generate_playbook
from snowbot.lessons.models import Lesson, LessonEvidence
from snowbot.lessons.store import LessonStore
from snowbot.memory.layout import MemoryLayout


def test_playbook_cap(tmp_path: Path) -> None:
    root = tmp_path
    layout = MemoryLayout.from_project_root(root)
    store = LessonStore(layout)
    body = "\n".join(f"line {i}" for i in range(200))
    lesson = Lesson(
        id="big",
        title="Big",
        body=body,
        evidence=[LessonEvidence(ref="r")],
    )
    store.add_proposed(lesson)
    store.accept("big")
    content = generate_playbook(layout)
    assert len(content.splitlines()) <= PLAYBOOK_MAX_LINES
    assert "truncated" in content
