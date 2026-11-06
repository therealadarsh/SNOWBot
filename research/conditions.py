"""Load experimental arms and the crossed condition cells."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from research.errors import ConfigError
from research.paths import path_matches
from research.yamlio import (
    as_bool,
    as_list,
    as_mapping,
    as_str,
    as_str_list,
    load_yaml,
    optional_str,
)

_FEEDBACK = frozenset({"shown", "hidden"})


@dataclass(frozen=True, slots=True)
class Arm:
    id: str
    label: str
    gates_editable: bool
    prompt_rule: str | None
    path_lock: bool
    posthoc_scanner: bool
    governance_split: bool


@dataclass(frozen=True, slots=True)
class Condition:
    id: str
    arm: Arm
    escalation: bool
    scanner_feedback: str

    @property
    def feedback_shown(self) -> bool:
        return self.scanner_feedback == "shown"


@dataclass(frozen=True, slots=True)
class TreatmentScanner:
    blocked_path_globs: tuple[str, ...]
    blocked_substrings: tuple[str, ...]

    def matches(self, path: str, diff: str) -> str | None:
        if path_matches(path, self.blocked_path_globs):
            return f"path:{path}"
        for snippet in self.blocked_substrings:
            if snippet in diff:
                return f"substring:{snippet}"
        return None


@dataclass(frozen=True, slots=True)
class ConditionSet:
    record_attempts_before_block: bool
    arms: tuple[Arm, ...]
    conditions: tuple[Condition, ...]
    gate_paths: tuple[str, ...]
    treatment: TreatmentScanner
    escalation_crossed_with: tuple[str, ...]
    scanner_feedback_crossed_with: tuple[str, ...]

    def by_id(self, condition_id: str) -> Condition:
        for condition in self.conditions:
            if condition.id == condition_id:
                return condition
        raise ConfigError(f"unknown condition {condition_id}")

    def arm(self, arm_id: str) -> Arm:
        for arm in self.arms:
            if arm.id == arm_id:
                return arm
        raise ConfigError(f"unknown arm {arm_id}")


def default_conditions_path() -> Path:
    return Path(__file__).resolve().parents[1] / "research" / "conditions.yaml"


def load_conditions(path: Path | None = None) -> ConditionSet:
    source = path or default_conditions_path()
    raw = as_mapping(load_yaml(source), label=str(source))
    recorded = as_bool(
        raw.get("record_attempts_before_block"),
        label="record_attempts_before_block",
    )
    if recorded is not True:
        raise ConfigError("record_attempts_before_block must be true")
    arms = _load_arms(raw.get("arms"))
    arms_by_id = {arm.id: arm for arm in arms}
    escalation = as_str_list(raw.get("escalation_crossed_with"), label="escalation_crossed_with")
    feedback = as_str_list(
        raw.get("scanner_feedback_crossed_with"), label="scanner_feedback_crossed_with"
    )
    for arm_id in (*escalation, *feedback):
        if arm_id not in arms_by_id:
            raise ConfigError(f"cross references unknown arm {arm_id}")
    conditions = _load_conditions(raw.get("conditions"), arms_by_id, escalation, feedback)
    _require_cross(conditions, escalation, feedback, arms_by_id)
    treatment_raw = as_mapping(raw.get("treatment_scanner"), label="treatment_scanner")
    treatment = TreatmentScanner(
        blocked_path_globs=as_str_list(
            treatment_raw.get("blocked_path_globs"), label="treatment_scanner.blocked_path_globs"
        ),
        blocked_substrings=as_str_list(
            treatment_raw.get("blocked_substrings"), label="treatment_scanner.blocked_substrings"
        ),
    )
    return ConditionSet(
        record_attempts_before_block=True,
        arms=arms,
        conditions=conditions,
        gate_paths=as_str_list(raw.get("gate_paths"), label="gate_paths"),
        treatment=treatment,
        escalation_crossed_with=escalation,
        scanner_feedback_crossed_with=feedback,
    )


def _load_arms(value: object) -> tuple[Arm, ...]:
    raw = as_mapping(value, label="arms")
    arms: list[Arm] = []
    for arm_id, item in raw.items():
        body = as_mapping(item, label=f"arms.{arm_id}")
        arms.append(
            Arm(
                id=arm_id,
                label=as_str(body.get("label"), label=f"arms.{arm_id}.label"),
                gates_editable=as_bool(
                    body.get("gates_editable"), label=f"arms.{arm_id}.gates_editable"
                ),
                prompt_rule=optional_str(
                    body.get("prompt_rule"), label=f"arms.{arm_id}.prompt_rule"
                ),
                path_lock=as_bool(body.get("path_lock"), label=f"arms.{arm_id}.path_lock"),
                posthoc_scanner=as_bool(
                    body.get("posthoc_scanner"), label=f"arms.{arm_id}.posthoc_scanner"
                ),
                governance_split=as_bool(
                    body.get("governance_split"), label=f"arms.{arm_id}.governance_split"
                ),
            )
        )
    if not arms:
        raise ConfigError("arms must not be empty")
    return tuple(arms)


def _load_conditions(
    value: object,
    arms_by_id: dict[str, Arm],
    escalation_arms: tuple[str, ...],
    feedback_arms: tuple[str, ...],
) -> tuple[Condition, ...]:
    raw_items = value
    conditions: list[Condition] = []
    seen: set[str] = set()
    for index, item in enumerate(as_list(raw_items, label="conditions")):
        body = as_mapping(item, label=f"conditions[{index}]")
        condition_id = as_str(body.get("id"), label=f"conditions[{index}].id")
        if condition_id in seen:
            raise ConfigError(f"duplicate condition id {condition_id}")
        seen.add(condition_id)
        arm_id = as_str(body.get("arm"), label=f"conditions[{index}].arm")
        if arm_id not in arms_by_id:
            raise ConfigError(f"condition {condition_id} references unknown arm {arm_id}")
        escalation = as_bool(body.get("escalation"), label=f"conditions[{index}].escalation")
        feedback = as_str(
            body.get("scanner_feedback"),
            label=f"conditions[{index}].scanner_feedback",
        )
        if feedback not in _FEEDBACK:
            raise ConfigError(f"condition {condition_id} has unknown scanner_feedback")
        if escalation and arm_id not in escalation_arms:
            raise ConfigError(f"escalation is not crossed with arm {arm_id}")
        arm = arms_by_id[arm_id]
        if feedback == "shown" and not arm.posthoc_scanner:
            raise ConfigError(f"scanner feedback is only crossed with scanner arms, not {arm_id}")
        if arm_id not in feedback_arms and feedback != "hidden":
            raise ConfigError(f"scanner feedback is not crossed with arm {arm_id}")
        conditions.append(
            Condition(
                id=condition_id,
                arm=arm,
                escalation=escalation,
                scanner_feedback=feedback,
            )
        )
    if not conditions:
        raise ConfigError("conditions must not be empty")
    return tuple(conditions)


def _require_cross(
    conditions: tuple[Condition, ...],
    escalation_arms: tuple[str, ...],
    feedback_arms: tuple[str, ...],
    arms_by_id: dict[str, Arm],
) -> None:
    for arm_id in escalation_arms:
        flags = {item.escalation for item in conditions if item.arm.id == arm_id}
        if flags != {True, False}:
            raise ConfigError(f"arm {arm_id} must include escalation on and off")
    for arm_id in feedback_arms:
        if not arms_by_id[arm_id].posthoc_scanner:
            raise ConfigError(
                f"scanner feedback cross requires a posthoc scanner arm, got {arm_id}"
            )
        feedback_flags = {item.scanner_feedback for item in conditions if item.arm.id == arm_id}
        if feedback_flags != {"shown", "hidden"}:
            raise ConfigError(f"arm {arm_id} must include scanner feedback shown and hidden")
