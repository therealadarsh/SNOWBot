"""Paths and bootstrap for the shared lessons / validation memory tree."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_MEMORY_DIR = Path(".snowbot/memory")

VISION_STUB = """# Project vision

Describe the long-term outcome this repo is building toward.
Agents update PROGRESS.md; humans own VISION.md.
"""

PROGRESS_STUB = """# Progress

Track phase completion and notable milestones here.
"""

LOG_STUB = """# Session log

Append dated notes from pipeline runs (high level only; secrets are redacted in tooling).
"""

RISKS_STUB = """# Risks

Track open risks, mitigations, and owners.
"""


@dataclass(frozen=True)
class MemoryLayout:
    """Resolved paths for memory artifacts relative to the consumer repo root."""

    root: Path
    memory_dir: Path = DEFAULT_MEMORY_DIR

    @property
    def vision(self) -> Path:
        return self.memory_dir / "VISION.md"

    @property
    def state(self) -> Path:
        return self.memory_dir / "state.json"

    @property
    def progress(self) -> Path:
        return self.memory_dir / "PROGRESS.md"

    @property
    def log(self) -> Path:
        return self.memory_dir / "LOG.md"

    @property
    def risks(self) -> Path:
        return self.memory_dir / "RISKS.md"

    @property
    def playbook(self) -> Path:
        return self.memory_dir / "PLAYBOOK.md"

    @property
    def lessons_dir(self) -> Path:
        return self.memory_dir / "lessons"

    @property
    def lessons_index(self) -> Path:
        return self.lessons_dir / "INDEX.yaml"

    @property
    def lessons_proposed(self) -> Path:
        return self.lessons_dir / "proposed"

    @property
    def lessons_accepted(self) -> Path:
        return self.lessons_dir / "accepted"

    @property
    def validation_dir(self) -> Path:
        return self.memory_dir / "validation"

    @property
    def stops_dir(self) -> Path:
        return self.memory_dir / "stops"

    def ensure_structure(self) -> None:
        """Create memory directories and stub files if missing."""
        for directory in (
            self.memory_dir,
            self.lessons_dir,
            self.lessons_proposed,
            self.lessons_accepted,
            self.validation_dir,
            self.stops_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        stubs: tuple[tuple[Path, str], ...] = (
            (self.vision, VISION_STUB),
            (self.progress, PROGRESS_STUB),
            (self.log, LOG_STUB),
            (self.risks, RISKS_STUB),
        )
        for path, content in stubs:
            if not path.is_file():
                path.write_text(content, encoding="utf-8")

        if not self.lessons_index.is_file():
            self.lessons_index.write_text("schema_version: 1\nlessons: []\n", encoding="utf-8")

        if not self.state.is_file():
            self.write_state({"schema_version": 1, "current_phase": "1"})

    def write_state(self, payload: dict[str, Any]) -> None:
        self.state.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def read_state(self) -> dict[str, Any]:
        if not self.state.is_file():
            return {}
        try:
            data = json.loads(self.state.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def touch_playbook_generated(self) -> None:
        state = self.read_state()
        state["playbook_generated_at"] = datetime.now(tz=UTC).isoformat()
        self.write_state(state)

    def touch_index_updated(self) -> None:
        state = self.read_state()
        state["index_updated_at"] = datetime.now(tz=UTC).isoformat()
        self.write_state(state)

    @classmethod
    def from_project_root(cls, root: Path, memory_dir: Path | None = None) -> MemoryLayout:
        base = root.resolve()
        mem = memory_dir if memory_dir is not None else DEFAULT_MEMORY_DIR
        if not mem.is_absolute():
            mem = base / mem
        return cls(root=base, memory_dir=mem)
