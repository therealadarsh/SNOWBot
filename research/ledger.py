"""Spend ledger and the status object a workflow would persist.

Defaults are a monthly cap of 50 USD and a per-run cap of 1.50 USD. A breach
returns ``schedule: paused`` and ``kill: true``. This module does not write
the repository status file and does not spend money.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from research.errors import ConfigError
from research.jsonio import load_json_object
from research.versioning import parse_semver
from research.yamlio import as_list, as_mapping, as_str

DEFAULT_MONTHLY_CAP_USD = 50.0
DEFAULT_PER_RUN_CAP_USD = 1.5
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True, slots=True)
class LedgerRun:
    run_id: str
    version: str
    spent_usd: float
    at: str
    infrastructure_failure: bool
    scheduled: bool


def load_ledger(path: Path) -> dict[str, object]:
    document = load_json_object(path)
    _money(document.get("monthly_cap_usd"), "monthly_cap_usd")
    _money(document.get("per_run_cap_usd"), "per_run_cap_usd")
    _runs(document.get("runs"))
    return document


def evaluate_caps(
    ledger: Mapping[str, object],
    *,
    version: str,
    today: date,
    proposed_usd: float | None = None,
    status: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return the status object a breach or a clean ledger would persist."""
    parse_semver(version)
    monthly = _money(ledger.get("monthly_cap_usd"), "monthly_cap_usd")
    per_run = _money(ledger.get("per_run_cap_usd"), "per_run_cap_usd")
    runs = _runs(ledger.get("runs"))
    month = f"{today.year:04d}-{today.month:02d}"
    spent = 0.0
    reasons: list[str] = []
    for run in runs:
        amount = run.spent_usd
        if amount > per_run + 1e-9:
            reasons.append(
                f"run {run.run_id} spent {amount:.2f} USD above the per-run cap {per_run:.2f}"
            )
        if run.at.startswith(month):
            spent += amount
    if proposed_usd is not None:
        if isinstance(proposed_usd, bool) or not isinstance(proposed_usd, int | float):
            raise ConfigError("proposed spend must be a number")
        if proposed_usd < 0:
            raise ConfigError("proposed spend must be non-negative")
        if proposed_usd > per_run + 1e-9:
            reasons.append(f"proposed {proposed_usd:.2f} USD exceeds the per-run cap {per_run:.2f}")
        if spent + proposed_usd > monthly + 1e-9:
            reasons.append(
                f"month {month} spend {spent + proposed_usd:.2f} USD exceeds "
                f"the monthly cap {monthly:.2f}"
            )
    elif spent > monthly + 1e-9:
        reasons.append(f"month {month} spend {spent:.2f} USD exceeds the monthly cap {monthly:.2f}")
    schedule, state, attempts, signature = _status_fields(status, version)
    if reasons:
        return _status(
            schedule="paused",
            version_state=state,
            kill=True,
            reason="; ".join(reasons),
            fix_attempts=attempts,
            signature=signature,
            version=version if status is None else str(status["version"]),
        )
    return _status(
        schedule=schedule,
        version_state=state,
        kill=False,
        reason="within monthly and per-run caps",
        fix_attempts=attempts,
        signature=signature,
        version=version if status is None else str(status["version"]),
    )


def infrastructure_failure(ledger: Mapping[str, object] | None) -> bool | None:
    """True when a recorded run failed for an infrastructure reason.

    ``None`` means the caller did not pass a ledger, so the check is not guessed.
    """
    if ledger is None:
        return None
    return any(run.infrastructure_failure for run in _runs(ledger.get("runs")))


def spend_allowed(status: Mapping[str, object], *, human_confirmed: bool) -> bool:
    """Spend only after a human activates the schedule and confirms the run."""
    if status.get("schedule") != "active":
        return False
    if status.get("kill") is not False:
        return False
    return human_confirmed is True


def _status_fields(
    status: Mapping[str, object] | None,
    version: str,
) -> tuple[str, str, int, str | None]:
    if status is None:
        return "paused", "current", 0, None
    from research.status import validate_status

    validate_status(status)
    signature = status.get("last_drift_signature")
    attempts = status["fix_attempts"]
    if isinstance(attempts, bool) or not isinstance(attempts, int):
        raise ConfigError("fix_attempts must be an integer")
    return (
        str(status["schedule"]),
        str(status["version_state"]),
        attempts,
        signature if isinstance(signature, str) else None,
    )


def _status(
    *,
    schedule: str,
    version_state: str,
    kill: bool,
    reason: str,
    fix_attempts: int,
    signature: str | None,
    version: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "schedule": schedule,
        "version_state": version_state,
        "kill": kill,
        "reason": reason,
        "fix_attempts": fix_attempts,
        "last_drift_signature": signature,
        "version": version,
    }


def _runs(value: object) -> list[LedgerRun]:
    parsed: list[LedgerRun] = []
    for index, item in enumerate(as_list(value, label="runs")):
        body = as_mapping(item, label=f"runs[{index}]")
        at = as_str(body.get("at"), label=f"runs[{index}].at")
        if _DAY.fullmatch(at) is None:
            raise ConfigError(f"runs[{index}].at must be YYYY-MM-DD")
        flag = body.get("infrastructure_failure")
        scheduled = body.get("scheduled")
        if not isinstance(flag, bool):
            raise ConfigError(f"runs[{index}].infrastructure_failure must be a boolean")
        if not isinstance(scheduled, bool):
            raise ConfigError(f"runs[{index}].scheduled must be a boolean")
        parsed.append(
            LedgerRun(
                run_id=as_str(body.get("run_id"), label=f"runs[{index}].run_id"),
                version=as_str(body.get("version"), label=f"runs[{index}].version"),
                spent_usd=_money(body.get("spent_usd"), f"runs[{index}].spent_usd"),
                at=at,
                infrastructure_failure=flag,
                scheduled=scheduled,
            )
        )
    return parsed


def _money(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{label} must be a number")
    if value < 0:
        raise ConfigError(f"{label} must be non-negative")
    return float(value)
