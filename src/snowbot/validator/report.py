"""Write human-readable phase validation reports."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from snowbot.memory.layout import MemoryLayout
from snowbot.validator.types import ValidationResult


def write_validation_report(layout: MemoryLayout, result: ValidationResult) -> Path:
    layout.ensure_structure()
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"phase-{result.phase}-{timestamp}.md"
    path = layout.validation_dir / filename

    lines = [
        f"# Phase {result.phase} validation — {result.title}",
        "",
        f"- recorded_at: {datetime.now(tz=UTC).isoformat()}",
        f"- result: {'PASS' if result.passed else 'FAIL'}",
    ]
    if result.pr_url:
        lines.append(f"- pr: {result.pr_url}")
    lines.extend(["", "## Checks", ""])

    for outcome in result.outcomes:
        mark = "pass" if outcome.passed else "FAIL"
        lines.append(f"- [{mark}] **{outcome.spec.id}**: {outcome.message}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    latest = layout.validation_dir / f"phase-{result.phase}-latest.md"
    latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path
