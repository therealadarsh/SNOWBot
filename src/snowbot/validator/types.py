"""Shared validator result types."""

from __future__ import annotations

from dataclasses import dataclass, field

from snowbot.validator.checks import CheckOutcome


@dataclass
class ValidationResult:
    phase: str
    title: str
    outcomes: list[CheckOutcome] = field(default_factory=list)
    pr_url: str | None = None

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.outcomes)
