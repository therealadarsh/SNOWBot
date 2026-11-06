"""Per-run and study dollar caps. No provider is contacted."""

from __future__ import annotations

from dataclasses import dataclass

from research.errors import BudgetError


@dataclass(slots=True)
class RunBudget:
    total_usd: float
    per_run_usd: float
    run_spent: float = 0.0
    cell_spent: float = 0.0

    def begin_cell(self) -> None:
        self.cell_spent = 0.0

    def authorize(self, amount_usd: float) -> None:
        if amount_usd < 0:
            raise BudgetError("cost must be non-negative")
        if self.cell_spent + amount_usd > self.per_run_usd + 1e-9:
            raise BudgetError(
                f"per-run cap {self.per_run_usd:.2f} USD would be exceeded "
                f"({self.cell_spent + amount_usd:.4f})"
            )
        if self.run_spent + amount_usd > self.total_usd + 1e-9:
            raise BudgetError(
                f"study cap {self.total_usd:.2f} USD would be exceeded "
                f"({self.run_spent + amount_usd:.4f})"
            )
        self.cell_spent += amount_usd
        self.run_spent += amount_usd


def nominal_cost(cell_count: int, per_run_usd: float) -> float:
    return cell_count * per_run_usd


def budget_allows(cell_count: int, per_run_usd: float, total_usd: float) -> bool:
    if cell_count < 0 or per_run_usd < 0 or total_usd < 0:
        return False
    if per_run_usd > total_usd + 1e-9 and cell_count > 0:
        return False
    return nominal_cost(cell_count, per_run_usd) <= total_usd + 1e-9
