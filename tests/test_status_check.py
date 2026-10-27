"""Status --check stale detection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from snowbot.memory.layout import MemoryLayout
from snowbot.status_check import run_status_check


def test_stale_playbook_detected(tmp_path: Path) -> None:
    root = tmp_path
    layout = MemoryLayout.from_project_root(root)
    layout.ensure_structure()
    layout.touch_index_updated()
    layout.playbook.write_text("# old\n", encoding="utf-8")
    old = datetime.now(tz=UTC) - timedelta(hours=1)
    layout.write_state(
        {
            "schema_version": 1,
            "index_updated_at": datetime.now(tz=UTC).isoformat(),
            "playbook_generated_at": old.isoformat(),
        }
    )
    report = run_status_check(layout)
    assert any(issue.code == "stale_playbook" for issue in report.issues)


def test_status_ok_after_playbook(tmp_path: Path) -> None:
    root = tmp_path
    layout = MemoryLayout.from_project_root(root)
    layout.ensure_structure()
    layout.lessons_index.write_text("schema_version: 1\nlessons: []\n", encoding="utf-8")
    layout.touch_index_updated()
    layout.playbook.write_text("# playbook\n", encoding="utf-8")
    layout.touch_playbook_generated()
    report = run_status_check(layout)
    assert report.ok
