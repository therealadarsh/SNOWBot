"""Stop event capture."""

from __future__ import annotations

from pathlib import Path

from snowbot.memory.layout import MemoryLayout
from snowbot.memory.stops import StopKind, capture_stop_event


def test_stop_redaction(tmp_path: Path) -> None:
    root = tmp_path
    layout = MemoryLayout.from_project_root(root)
    path = capture_stop_event(
        layout,
        StopKind.CI_FAILURE,
        detail="token=abc123",
    )
    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert "abc123" not in text
    assert "[REDACTED]" in text


def test_dry_run_no_file(tmp_path: Path) -> None:
    root = tmp_path
    layout = MemoryLayout.from_project_root(root)
    assert capture_stop_event(layout, StopKind.GATE_REJECTED, dry_run=True) is None
