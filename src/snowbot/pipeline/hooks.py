"""Orchestrator integration hooks for onboard packs and validator gates."""

from __future__ import annotations

from dataclasses import dataclass

from snowbot.memory.layout import MemoryLayout
from snowbot.memory.stops import StopKind, capture_stop_event
from snowbot.pipeline.onboard import render_onboard_pack
from snowbot.validator.runner import run_phase_validation
from snowbot.validator.types import ValidationResult


@dataclass
class StageHooks:
    """Lightweight hooks consumed by future orchestrator stages."""

    layout: MemoryLayout

    def at_stage_start(self, stage: str, *, task: str | None = None, dry_run: bool = False) -> str:
        """Emit onboard pack markdown at the beginning of a pipeline stage."""
        return render_onboard_pack(self.layout, stage=stage, task=task, dry_run=dry_run)

    def validator_gate(
        self,
        phase: int,
        *,
        pr_url: str | None = None,
        dry_run: bool = False,
    ) -> ValidationResult:
        """Run phase validation; capture stop event when checks fail."""
        return run_phase_validation(self.layout, phase, pr_url=pr_url, dry_run=dry_run)

    def gate_rejected(self, detail: str, *, dry_run: bool = False) -> None:
        capture_stop_event(
            self.layout,
            StopKind.GATE_REJECTED,
            detail=detail,
            dry_run=dry_run,
        )

    def retry_exhausted(self, detail: str, *, dry_run: bool = False) -> None:
        capture_stop_event(
            self.layout,
            StopKind.RETRY_EXHAUSTED,
            detail=detail,
            dry_run=dry_run,
        )

    def ci_failure(self, detail: str, *, dry_run: bool = False) -> None:
        capture_stop_event(
            self.layout,
            StopKind.CI_FAILURE,
            detail=detail,
            dry_run=dry_run,
        )
