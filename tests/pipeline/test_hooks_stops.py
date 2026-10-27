"""Stop hooks on pipeline."""

from __future__ import annotations

from pathlib import Path

from snowbot.memory.layout import MemoryLayout
from snowbot.pipeline.hooks import StageHooks


def test_stop_hooks(tmp_path: Path) -> None:
    layout = MemoryLayout.from_project_root(tmp_path)
    hooks = StageHooks(layout)
    hooks.gate_rejected("no")
    hooks.retry_exhausted("retries")
    hooks.ci_failure("ci")
    assert len(list(layout.stops_dir.glob("*.json"))) == 3
