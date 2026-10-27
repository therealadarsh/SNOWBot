"""Persist pipeline stop events under ``.snowbot/memory/stops/``."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from snowbot.logging_setup import redact_secrets
from snowbot.memory.layout import MemoryLayout


class StopKind(StrEnum):
    """Categories of events that halt or pause automated progress."""

    VALIDATOR_FAIL = "validator_fail"
    GATE_REJECTED = "gate_rejected"
    RETRY_EXHAUSTED = "retry_exhausted"
    CI_FAILURE = "ci_failure"
    HUMAN_LESSON_ADD = "human_lesson_add"


def capture_stop_event(
    layout: MemoryLayout,
    kind: StopKind,
    *,
    phase: int | None = None,
    detail: str = "",
    metadata: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> Path | None:
    """Write a redacted JSON stop record and return its path (``None`` when dry-run)."""
    layout.ensure_structure()
    record = {
        "id": str(uuid.uuid4()),
        "kind": kind.value,
        "phase": phase,
        "detail": redact_secrets(detail),
        "metadata": _redact_metadata(metadata or {}),
        "recorded_at": datetime.now(tz=UTC).isoformat(),
    }
    if dry_run:
        return None
    recorded_at = str(record["recorded_at"])
    filename = f"{recorded_at.replace(':', '-')}_{kind.value}.json"
    path = layout.stops_dir / filename
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _redact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, str):
            redacted[key] = redact_secrets(value)
        elif isinstance(value, dict):
            redacted[key] = _redact_metadata(value)
        else:
            redacted[key] = value
    return redacted
