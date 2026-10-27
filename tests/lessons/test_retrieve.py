"""Precedence retrieval tests."""

from __future__ import annotations

from pathlib import Path

from snowbot.lessons.models import Lesson, LessonEvidence
from snowbot.lessons.retrieve import Precedence, retrieve_lessons
from snowbot.lessons.store import LessonStore
from snowbot.memory.layout import MemoryLayout


def test_precedence_order(tmp_path: Path) -> None:
    root = tmp_path
    layout = MemoryLayout.from_project_root(root)
    (root / "AGENTS.md").write_text("- Never commit secrets\n", encoding="utf-8")
    store = LessonStore(layout)
    proposed = Lesson(
        id="p1",
        title="Proposed",
        body="p",
        evidence=[LessonEvidence(ref="r")],
    )
    store.add_proposed(proposed)
    accepted = Lesson(
        id="a1",
        title="Accepted",
        body="a",
        evidence=[LessonEvidence(ref="r")],
    )
    store.add_proposed(accepted)
    store.accept("a1")
    ranked = retrieve_lessons(layout)
    assert ranked[0].precedence == Precedence.AGENTS_SAFETY
