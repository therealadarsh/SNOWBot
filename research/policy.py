"""Treatment policy for one condition. This is not the outcome oracle."""

from __future__ import annotations

from dataclasses import dataclass

from research.conditions import Condition, ConditionSet
from research.paths import path_matches


@dataclass(frozen=True, slots=True)
class BlockDecision:
    block: bool
    rule: str
    route_governance: bool


class Policy:
    def __init__(self, condition: Condition, loaded: ConditionSet) -> None:
        self.condition = condition
        self._gates = loaded.gate_paths
        self._treatment = loaded.treatment

    def decide(self, rel: str, diff: str) -> BlockDecision:
        arm = self.condition.arm
        if arm.path_lock and path_matches(rel, self._gates):
            return BlockDecision(block=True, rule="path_lock", route_governance=False)
        if arm.governance_split and path_matches(rel, self._gates):
            return BlockDecision(block=True, rule="governance_channel", route_governance=True)
        if arm.posthoc_scanner:
            matched = self._treatment.matches(rel, diff)
            if matched is not None:
                return BlockDecision(block=True, rule=matched, route_governance=False)
        return BlockDecision(block=False, rule="", route_governance=False)

    def message(self, decision: BlockDecision) -> str:
        if not decision.block:
            return "applied"
        if self.condition.feedback_shown:
            return f"edit was not applied: {decision.rule}"
        return "edit was not applied"
