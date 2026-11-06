"""Research schedule status.

The committed default keeps ``schedule`` paused. Nothing in this package sets
``schedule`` to ``active`` or ``version_state`` to ``stable``.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from research.errors import ConfigError
from research.jsonio import load_json_object
from research.versioning import parse_semver
from research.yamlio import as_str

SCHEDULES = frozenset({"active", "paused"})
VERSION_STATES = frozenset({"current", "outdated", "stable"})


def status_file(root: Path) -> Path:
    return root / "research" / "STATUS.json"


def load_status(path: Path) -> dict[str, object]:
    document = load_json_object(path)
    validate_status(document)
    return document


def validate_status(document: Mapping[str, object]) -> None:
    schedule = as_str(document.get("schedule"), label="schedule")
    if schedule not in SCHEDULES:
        raise ConfigError("schedule must be active or paused")
    state = as_str(document.get("version_state"), label="version_state")
    if state not in VERSION_STATES:
        raise ConfigError("version_state must be current, outdated, or stable")
    if not isinstance(document.get("kill"), bool):
        raise ConfigError("kill must be a boolean")
    as_str(document.get("reason"), label="reason")
    attempts = document.get("fix_attempts")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        raise ConfigError("fix_attempts must be a non-negative integer")
    signature = document.get("last_drift_signature")
    if signature is not None and not isinstance(signature, str):
        raise ConfigError("last_drift_signature must be a string or null")
    parse_semver(as_str(document.get("version"), label="status.version"))


def default_status(version: str) -> dict[str, object]:
    parse_semver(version)
    return {
        "schema_version": 1,
        "schedule": "paused",
        "version_state": "current",
        "kill": False,
        "reason": "paused until a human activates the schedule; no spend is authorized",
        "fix_attempts": 0,
        "last_drift_signature": None,
        "version": version,
    }
