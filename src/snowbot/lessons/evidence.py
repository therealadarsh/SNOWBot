"""Resolve lesson evidence refs against files, pull requests, and stop events.

A ref resolves when it is an existing file inside the project root, a pull
request number that appears in this repository's git history, or the id of a
stop event stored under the memory stops directory.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from snowbot.lessons.models import Lesson
from snowbot.memory.layout import MemoryLayout

_PR_REF = re.compile(
    r"^(?:https?://github\.com/[\w.-]+/[\w.-]+/pull/(\d+)|#(\d+)|(?:pull|pr)/(\d+)|(\d+))/?$",
    re.IGNORECASE,
)


def unresolved_evidence_refs(layout: MemoryLayout, lesson: Lesson) -> list[str]:
    """Return evidence refs that are not a file, pull request, or stop event."""
    return [item.ref for item in lesson.evidence if not evidence_ref_resolves(layout, item.ref)]


def evidence_ref_resolves(layout: MemoryLayout, ref: str) -> bool:
    """Return True when ``ref`` names a file, an existing PR, or a stop event."""
    text = ref.strip()
    if not text:
        return False
    if _file_exists(layout.root, text):
        return True
    if _stop_event_exists(layout, text):
        return True
    number = _pr_number(text)
    return number is not None and _pr_exists(layout.root, number)


def _file_exists(root: Path, ref: str) -> bool:
    if "://" in ref or ref.startswith("#"):
        return False
    candidate = Path(ref)
    if candidate.is_absolute():
        return False
    root_resolved = root.resolve()
    try:
        resolved = (root_resolved / candidate).resolve()
    except OSError:
        return False
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        return False
    return resolved.is_file()


def _stop_event_exists(layout: MemoryLayout, ref: str) -> bool:
    stops = layout.stops_dir
    if not stops.is_dir():
        return False
    for path in stops.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("id") == ref:
            return True
    return False


def _pr_number(ref: str) -> int | None:
    match = _PR_REF.fullmatch(ref.strip())
    if match is None:
        return None
    raw = next(group for group in match.groups() if group is not None)
    return int(raw)


def _pr_exists(root: Path, number: int) -> bool:
    if not (root / ".git").exists():
        return False
    proc = subprocess.run(
        ["git", "-C", str(root), "log", "--all", "--format=%s%n%b"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False
    return re.search(rf"#({number})(?!\d)", proc.stdout) is not None
