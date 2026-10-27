"""Run phase validation from checklist.yaml."""

from __future__ import annotations

import os
from importlib import resources
from typing import Any

import yaml

from snowbot.memory.layout import MemoryLayout
from snowbot.memory.stops import StopKind, capture_stop_event
from snowbot.models.phases import normalize_phase_id
from snowbot.validator.checks import CheckOutcome, parse_check, run_check
from snowbot.validator.context import CheckContext
from snowbot.validator.report import write_validation_report
from snowbot.validator.types import ValidationResult

BASE_REF_ENV = "SNOWBOT_VALIDATE_BASE"


def _load_checklist() -> dict[str, Any]:
    checklist_path = resources.files("snowbot.validator").joinpath("checklist.yaml")
    data = checklist_path.read_text(encoding="utf-8")
    payload = yaml.safe_load(data)
    if not isinstance(payload, dict):
        msg = "checklist.yaml root must be a mapping"
        raise ValueError(msg)
    return payload


def _phase_map(raw: dict[Any, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in raw.items()}


def run_phase_validation(
    layout: MemoryLayout,
    phase: str,
    *,
    pr_url: str | None = None,
    dry_run: bool = False,
    base_ref: str | None = None,
    diff_override: str | None = None,
) -> ValidationResult:
    """Execute checklist checks for *phase* and persist a report under memory/validation/."""
    phase_id = normalize_phase_id(phase)
    checklist = _load_checklist()
    phases_raw = checklist.get("phases", {})
    if not isinstance(phases_raw, dict):
        msg = "checklist phases must be a mapping"
        raise ValueError(msg)

    phases = _phase_map(phases_raw)
    phase_doc = phases.get(phase_id)
    if phase_doc is None:
        msg = f"No checklist defined for phase {phase_id!r}"
        raise ValueError(msg)

    title = str(phase_doc.get("title", f"Phase {phase_id}"))
    raw_checks = phase_doc.get("checks", [])
    specs = [parse_check(item) for item in raw_checks if isinstance(item, dict)]

    resolved_base = base_ref or os.environ.get(BASE_REF_ENV)
    context = CheckContext(base_ref=resolved_base, diff_override=diff_override)

    outcomes: list[CheckOutcome] = []
    for spec in specs:
        if dry_run and spec.kind == "anti_gaming_diff":
            outcomes.append(
                CheckOutcome(spec, True, "Anti-gaming diff skipped in dry-run mode"),
            )
            continue
        outcomes.append(run_check(layout.root, spec, context=context))
    result = ValidationResult(phase=phase_id, title=title, outcomes=outcomes, pr_url=pr_url)

    if not dry_run:
        write_validation_report(layout, result)
        if not result.passed:
            capture_stop_event(
                layout,
                StopKind.VALIDATOR_FAIL,
                phase=phase_id,
                detail=f"Phase {phase_id} validation failed",
                metadata={"failed_checks": [o.spec.id for o in outcomes if not o.passed]},
            )

    return result
