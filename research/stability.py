"""Decide whether a research version meets the stability criterion.

Inputs are recorded by the caller. This module does not hit the network, does
not open a pull request, and does not edit ``STATUS.json``. Oracle kappa and
error targets are not built in: until the pre-registration supplies them, that
check is ``not_evaluated`` and the version is not stable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from research.errors import ConfigError
from research.yamlio import as_list, as_mapping, as_str

_PIN_FIELDS = (
    "oracle_config_sha256",
    "task_suite_sha256",
    "scanner_commit",
    "conditions_sha256",
    "pins_sha256",
)


@dataclass(frozen=True, slots=True)
class StabilityReport:
    stable: bool
    version: str | None
    checks: dict[str, str]
    draft_pr_body: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "stable": self.stable,
            "version": self.version,
            "checks": self.checks,
            "draft_pr_body": self.draft_pr_body,
            "opened_pr": False,
            "status_edited": False,
            "proposed_status": {
                "schedule": "paused",
                "version_state": "stable",
                "kill": False,
            }
            if self.stable
            else None,
        }


def evaluate_stability(payload: Mapping[str, object]) -> StabilityReport:
    runs = _runs(payload.get("runs"))
    checks = {
        "consecutive_runs": _consecutive(runs),
        "pins_unchanged": _pins(runs),
        "aa_noise": _noise(payload),
        "drift_and_ci": _drift_and_ci(payload),
        "oracle_accuracy": _oracle_accuracy(payload),
    }
    raw_version = runs[0]["version"] if runs else None
    version = raw_version if isinstance(raw_version, str) else None
    stable = all(value == "pass" or value.startswith("pass:") for value in checks.values())
    body = render_stable_body(version, checks) if stable and version is not None else None
    return StabilityReport(stable=stable, version=version, checks=checks, draft_pr_body=body)


def cohen_kappa(pairs: Sequence[tuple[str, str]]) -> tuple[float, float]:
    """Cohen's kappa and the disagreement rate for paired labels."""
    if not pairs:
        raise ConfigError("label sample is empty")
    count = len(pairs)
    agreed = sum(1 for left, right in pairs if left == right)
    observed = agreed / count
    lefts = [left for left, _right in pairs]
    rights = [right for _left, right in pairs]
    expected = 0.0
    for category in set(lefts) | set(rights):
        expected += (lefts.count(category) / count) * (rights.count(category) / count)
    if expected == 1.0:
        kappa = 1.0 if observed == 1.0 else 0.0
    else:
        kappa = (observed - expected) / (1.0 - expected)
    return kappa, (count - agreed) / count


def render_stable_body(version: str, checks: Mapping[str, str]) -> str:
    lines = [
        f"# Declare research version {version} stable",
        "",
        "This draft would set:",
        "",
        "- `schedule`: `paused`",
        "- `version_state`: `stable`",
        "- `kill`: `false`",
        "",
        "This command did not open a pull request and did not edit STATUS.json.",
        "",
        "## Checks",
        "",
    ]
    for name, result in checks.items():
        lines.append(f"- {name}: {result}")
    lines.append("")
    return "\n".join(lines)


def _runs(value: object) -> list[dict[str, object]]:
    parsed: list[dict[str, object]] = []
    for index, item in enumerate(as_list(value, label="runs")):
        body = as_mapping(item, label=f"runs[{index}]")
        scheduled = body.get("scheduled")
        failure = body.get("infrastructure_failure")
        if not isinstance(scheduled, bool):
            raise ConfigError(f"runs[{index}].scheduled must be a boolean")
        if not isinstance(failure, bool):
            raise ConfigError(f"runs[{index}].infrastructure_failure must be a boolean")
        record: dict[str, object] = {
            "version": as_str(body.get("version"), label=f"runs[{index}].version"),
            "scheduled": scheduled,
            "infrastructure_failure": failure,
        }
        for key in _PIN_FIELDS:
            record[key] = as_str(body.get(key), label=f"runs[{index}].{key}")
        parsed.append(record)
    return parsed


def _consecutive(runs: Sequence[Mapping[str, object]]) -> str:
    if len(runs) < 3:
        return "fail: fewer than 3 scheduled runs"
    if any(run["scheduled"] is not True for run in runs):
        return "fail: a run in the window was not scheduled"
    if any(run["infrastructure_failure"] is True for run in runs):
        return "fail: an infrastructure failure is in the window"
    versions = {str(run["version"]) for run in runs}
    if len(versions) != 1:
        return "fail: runs are not on the same version"
    return "pass"


def _pins(runs: Sequence[Mapping[str, object]]) -> str:
    if len(runs) < 3:
        return "fail: fewer than 3 runs"
    fingerprints = [tuple(str(run[key]) for key in _PIN_FIELDS) for run in runs]
    if len(set(fingerprints)) != 1:
        return "fail: oracle, task, scanner, pin, or condition changed between runs"
    return "pass"


def _noise(payload: Mapping[str, object]) -> str:
    difference = payload.get("aa_difference")
    tolerance = payload.get("aa_tolerance")
    if difference is None or tolerance is None:
        return "fail: A/A difference and tolerance are required"
    left = _number(difference, "aa_difference")
    right = _number(tolerance, "aa_tolerance")
    if right < 0:
        raise ConfigError("aa_tolerance must be non-negative")
    if abs(left) <= right:
        return "pass"
    return f"fail: A/A difference {left} is outside tolerance {right}"


def _drift_and_ci(payload: Mapping[str, object]) -> str:
    outdated = payload.get("drift_outdated")
    unchecked = payload.get("drift_unchecked")
    ci_green = payload.get("ci_green")
    if not isinstance(outdated, bool) or not isinstance(ci_green, bool):
        return "fail: drift_outdated and ci_green must be input flags"
    if unchecked is not False:
        return "fail: drift still has unchecked pins or the flag was omitted"
    if outdated:
        return "fail: drift-check reported outdated pins"
    if not ci_green:
        return "fail: CI / architect-gate was not green"
    return "pass"


def _oracle_accuracy(payload: Mapping[str, object]) -> str:
    kappa_target = payload.get("kappa_target")
    error_target = payload.get("error_target")
    if kappa_target is None or error_target is None:
        return "not_evaluated"
    target_kappa = _number(kappa_target, "kappa_target")
    target_error = _number(error_target, "error_target")
    labels = payload.get("labels")
    if not isinstance(labels, list):
        return "fail: kappa and error targets were set but no label sample was provided"
    pairs = _pairs(labels)
    kappa, error = cohen_kappa(pairs)
    if kappa + 1e-12 >= target_kappa and error <= target_error + 1e-12:
        return f"pass: kappa {kappa:.4f} >= {target_kappa} and error {error:.4f} <= {target_error}"
    return f"fail: kappa {kappa:.4f} vs {target_kappa} and error {error:.4f} vs {target_error}"


def _pairs(labels: list[object]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for index, item in enumerate(labels):
        body = as_mapping(item, label=f"labels[{index}]")
        pairs.append(
            (
                as_str(body.get("oracle"), label=f"labels[{index}].oracle"),
                as_str(body.get("human"), label=f"labels[{index}].human"),
            )
        )
    return pairs


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{label} must be a number")
    return float(value)
