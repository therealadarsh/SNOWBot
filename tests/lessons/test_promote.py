"""Promote helper."""

from __future__ import annotations

from pathlib import Path

from snowbot.lessons.models import Lesson, LessonEvidence
from snowbot.lessons.promote import promote_lesson
from snowbot.lessons.store import LessonStore
from snowbot.memory.layout import MemoryLayout


def test_promote_refreshes_playbook(tmp_path: Path) -> None:
    layout = MemoryLayout.from_project_root(tmp_path)
    store = LessonStore(layout)
    store.add_proposed(
        Lesson(id="p", title="P", body="text", evidence=[LessonEvidence(ref="r")]),
    )
    (tmp_path / "r").write_text("evidence\n", encoding="utf-8")
    promote_lesson(layout, "p")
    assert layout.playbook.is_file()
