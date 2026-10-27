"""Run phase validation from checklist.yaml."""

from __future__ import annotations

from importlib import resources
from typing import Any

import yaml

from snowbot.memory.layout import MemoryLayout
from snowbot.memory.stops import StopKind, capture_stop_event
from snowbot.validator.checks import parse_check, run_check
from snowbot.validator.report import write_validation_report
from snowbot.validator.types import ValidationResult


def _load_checklist() -> dict[str, Any]:
    checklist_path = resources.files("snowbot.validator").joinpath("checklist.yaml")
    data = checklist_path.read_text(encoding="utf-8")
    payload = yaml.safe_load(data)
    if not isinstance(payload, dict):
        msg = "checklist.yaml root must be a mapping"
        raise ValueError(msg)
    return payload


def run_phase_validation(
    layout: MemoryLayout,
    phase: int,
    *,
    pr_url: str | None = None,
    dry_run: bool = False,
) -> ValidationResult:
    """Execute checklist checks for *phase* and persist a report under memory/validation/."""
    checklist = _load_checklist()
    phases = checklist.get("phases", {})
    if not isinstance(phases, dict):
        msg = "checklist phases must be a mapping"
        raise ValueError(msg)

    key = str(phase)
    phase_doc = phases.get(key)
    if phase_doc is None:
        phase_doc = phases.get(phase)
    if phase_doc is None:
        msg = f"No checklist defined for phase {phase}"
        raise ValueError(msg)

    title = str(phase_doc.get("title", f"Phase {key}"))
    raw_checks = phase_doc.get("checks", [])
    specs = [parse_check(item) for item in raw_checks if isinstance(item, dict)]

    outcomes = [run_check(layout.root, spec) for spec in specs]
    result = ValidationResult(phase=key, title=title, outcomes=outcomes, pr_url=pr_url)

    if not dry_run:
        write_validation_report(layout, result)
        if not result.passed:
            capture_stop_event(
                layout,
                StopKind.VALIDATOR_FAIL,
                phase=phase,
                detail=f"Phase {key} validation failed",
                metadata={"failed_checks": [o.spec.id for o in outcomes if not o.passed]},
            )

    return result
