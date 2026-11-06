"""Generate PLAYBOOK.md from accepted lessons with a hard line cap."""

from __future__ import annotations

import re

from snowbot.lessons.models import Lesson
from snowbot.lessons.retrieve import Precedence, retrieve_lessons
from snowbot.memory.layout import MemoryLayout

PLAYBOOK_MAX_LINES = 150

_PROHIBITION = re.compile(
    r"\b(?:never|do not|don't|dont|must not)\b\s+([^.;\n]+)",
    re.IGNORECASE,
)
_NEGATION_BEFORE = re.compile(
    r"(?:never|do not|don't|dont|must not|mustn'?t|avoid)\s*$",
    re.IGNORECASE,
)


def generate_playbook(layout: MemoryLayout, *, dry_run: bool = False) -> str:
    """Build playbook markdown from accepted lessons that do not contradict AGENTS.md.

    Retrieval precedence is AGENTS.md safety, then accepted lessons. A lesson that
    recommends an action those safety rules forbid is omitted.
    """
    ranked = retrieve_lessons(layout, include_proposed=False)
    rules = [item.lesson.body for item in ranked if item.precedence == Precedence.AGENTS_SAFETY]
    accepted = [
        item.lesson
        for item in ranked
        if item.precedence == Precedence.ACCEPTED and not _conflicts_with_safety(item.lesson, rules)
    ]
    lines = [
        "# SNOWBot playbook",
        "",
        "Generated from **accepted** lessons. AGENTS.md safety rules always win.",
        "",
    ]
    for lesson in accepted:
        lines.append(f"## {lesson.title}")
        lines.append("")
        for part in lesson.body.strip().splitlines():
            lines.append(part)
        lines.append("")
        if lesson.evidence:
            lines.append("Evidence:")
            for ev in lesson.evidence:
                lines.append(f"- ({ev.kind}) {ev.ref}: {ev.summary}".rstrip())
            lines.append("")

    if len(lines) > PLAYBOOK_MAX_LINES:
        lines = lines[: PLAYBOOK_MAX_LINES - 3]
        lines.extend(["", "... (truncated to 150 lines)", ""])

    content = "\n".join(lines).rstrip() + "\n"
    if not dry_run:
        layout.playbook.write_text(content, encoding="utf-8")
        layout.touch_playbook_generated()
    return content


def _conflicts_with_safety(lesson: Lesson, rules: list[str]) -> bool:
    text = f"{lesson.title}\n{lesson.body}"
    for rule in rules:
        for action in _prohibited_actions(rule):
            if _recommends(text, action):
                return True
    return False


def _prohibited_actions(rule: str) -> list[str]:
    plain = rule.replace("`", "")
    return [
        match.group(1).strip() for match in _PROHIBITION.finditer(plain) if match.group(1).strip()
    ]


def _recommends(text: str, action: str) -> bool:
    haystack = text.replace("`", "").lower()
    needle = action.replace("`", "").lower()
    if not needle:
        return False
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return False
        prefix = haystack[max(0, index - 48) : index]
        if _NEGATION_BEFORE.search(prefix) is None:
            return True
        start = index + len(needle)
