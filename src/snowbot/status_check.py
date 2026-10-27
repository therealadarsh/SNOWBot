"""``snowbot status --check`` memory freshness and structure validation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from snowbot.lessons.digest import PLAYBOOK_MAX_LINES
from snowbot.memory.layout import MemoryLayout

STALE_AFTER = timedelta(hours=24)


@dataclass
class StatusIssue:
    code: str
    message: str
    severity: str = "error"


@dataclass
class StatusReport:
    issues: list[StatusIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.issues)


def run_status_check(layout: MemoryLayout) -> StatusReport:
    """Verify memory tree, INDEX/playbook freshness, and playbook line cap."""
    report = StatusReport()
    layout.ensure_structure()

    required_files = (
        layout.vision,
        layout.progress,
        layout.log,
        layout.risks,
        layout.state,
        layout.lessons_index,
    )
    for path in required_files:
        if not path.is_file():
            report.issues.append(
                StatusIssue("missing_file", f"Missing required memory file: {path}", "error")
            )

    state = _read_state(layout.state)
    index_mtime = _mtime(layout.lessons_index)
    playbook_mtime = _mtime(layout.playbook)

    index_updated = state.get("index_updated_at")
    playbook_generated = state.get("playbook_generated_at")

    if layout.playbook.is_file():
        lines = len(layout.playbook.read_text(encoding="utf-8").splitlines())
        if lines > PLAYBOOK_MAX_LINES:
            report.issues.append(
                StatusIssue(
                    "playbook_too_long",
                    f"PLAYBOOK.md has {lines} lines (max {PLAYBOOK_MAX_LINES})",
                    "error",
                )
            )

    if isinstance(index_updated, str) and isinstance(playbook_generated, str):
        if _parse_iso(playbook_generated) < _parse_iso(index_updated):
            report.issues.append(
                StatusIssue(
                    "stale_playbook",
                    "PLAYBOOK.md older than lessons INDEX update",
                    "error",
                )
            )
    elif index_mtime and playbook_mtime and playbook_mtime < index_mtime:
        report.issues.append(
            StatusIssue(
                "stale_playbook",
                "PLAYBOOK.md mtime older than INDEX.yaml",
                "error",
            )
        )

    if isinstance(index_updated, str) and _is_stale(_parse_iso(index_updated)):
        report.issues.append(
            StatusIssue(
                "stale_index",
                "lessons INDEX not updated recently",
                "warning",
            )
        )

    if not layout.lessons_index.read_text(encoding="utf-8").strip():
        report.issues.append(
            StatusIssue("empty_index", "lessons/INDEX.yaml is empty", "error"),
        )

    return report


def _read_state(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _mtime(path: Path) -> datetime | None:
    if not path.is_file():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _is_stale(moment: datetime) -> bool:
    return datetime.now(tz=UTC) - moment > STALE_AFTER
