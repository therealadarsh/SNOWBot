"""Generate PLAYBOOK.md from accepted lessons with a hard line cap."""

from __future__ import annotations

from snowbot.lessons.models import LessonStatus
from snowbot.lessons.store import LessonStore
from snowbot.memory.layout import MemoryLayout

PLAYBOOK_MAX_LINES = 150


def generate_playbook(layout: MemoryLayout, *, dry_run: bool = False) -> str:
    """Build playbook markdown from accepted lessons (non-executable guidance)."""
    store = LessonStore(layout)
    accepted = [lesson for lesson in store.list_lessons() if lesson.status == LessonStatus.ACCEPTED]
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
