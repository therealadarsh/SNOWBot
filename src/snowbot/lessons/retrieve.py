"""Lesson retrieval with precedence: AGENTS.md safety > accepted > proposed."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from snowbot.lessons.models import Lesson, LessonEvidence, LessonStatus
from snowbot.lessons.store import LessonStore
from snowbot.memory.layout import MemoryLayout


class Precedence(IntEnum):
    AGENTS_SAFETY = 3
    ACCEPTED = 2
    PROPOSED = 1


@dataclass(frozen=True)
class RankedLesson:
    lesson: Lesson
    precedence: Precedence


def load_agents_safety_rules(agents_path: Path) -> list[str]:
    """Extract bullet lines tagged as safety-critical from AGENTS.md."""
    if not agents_path.is_file():
        return []
    rules: list[str] = []
    for line in agents_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("-") and "secret" in stripped.lower():
            rules.append(stripped.lstrip("- ").strip())
        if "never commit" in stripped.lower():
            rules.append(stripped.lstrip("-# ").strip())
    return rules


def retrieve_lessons(
    layout: MemoryLayout,
    *,
    agents_file: Path | None = None,
    include_proposed: bool = True,
) -> list[RankedLesson]:
    """Return lessons sorted by precedence (highest first)."""
    store = LessonStore(layout)
    ranked: list[RankedLesson] = []
    for lesson in store.list_lessons():
        if lesson.status == LessonStatus.ACCEPTED:
            ranked.append(RankedLesson(lesson, Precedence.ACCEPTED))
        elif include_proposed and lesson.status == LessonStatus.PROPOSED:
            ranked.append(RankedLesson(lesson, Precedence.PROPOSED))

    agents = agents_file or (layout.root / "AGENTS.md")
    for rule in load_agents_safety_rules(agents):
        pseudo = Lesson(
            id="agents-safety",
            title="AGENTS.md safety",
            body=rule,
            status=LessonStatus.ACCEPTED,
            evidence=[
                LessonEvidence(kind="file", ref=str(agents), summary="safety rule"),
            ],
        )
        ranked.append(RankedLesson(pseudo, Precedence.AGENTS_SAFETY))

    ranked.sort(key=lambda item: (-int(item.precedence), item.lesson.created_at))
    return ranked
