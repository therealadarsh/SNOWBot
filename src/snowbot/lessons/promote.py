"""Promote proposed lessons to accepted and refresh playbook."""

from __future__ import annotations

from snowbot.lessons.digest import generate_playbook
from snowbot.lessons.models import Lesson
from snowbot.lessons.store import LessonStore
from snowbot.memory.layout import MemoryLayout


def promote_lesson(
    layout: MemoryLayout,
    lesson_id: str,
    *,
    dry_run: bool = False,
    refresh_playbook: bool = True,
) -> Lesson:
    """Accept a proposed lesson and optionally regenerate PLAYBOOK.md."""
    store = LessonStore(layout)
    lesson = store.accept(lesson_id, dry_run=dry_run)
    if refresh_playbook and not dry_run:
        generate_playbook(layout)
    return lesson
