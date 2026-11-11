"""Per-stage diff policy: what an agent may change in its worktree."""

from __future__ import annotations

from snowbot.validator.antigaming import GOVERNANCE_PATH_PREFIXES

LOCKS_DIR = ".snowbot/locks"
_TESTS = "tests/"
_PROJECT_CONFIG = ("pyproject.toml", "snowbot.yaml")


def stage1_violations(changes: list[tuple[str, str]]) -> list[str]:
    """Stage 1 (write tests) may only add or change files under tests/."""
    return [
        f"{status} {path}: stage 1 may only add or change tests/"
        for status, path in changes
        if not (status in ("A", "M") and path.startswith(_TESTS))
    ]


def _stage2_reason(status: str, path: str, locked: set[str]) -> str | None:
    if path in locked:
        return "locked test"
    if path.startswith(LOCKS_DIR + "/"):
        return "lock manifest"
    if path.startswith(".github/"):
        return "CI config"
    if path in _PROJECT_CONFIG:
        return "project config"
    if any(path == p or path.startswith(p) for p in GOVERNANCE_PATH_PREFIXES):
        return "governance path"
    if path.startswith(_TESTS) and status == "M":
        return "existing test modified"
    if path.startswith(_TESTS) and status == "D":
        return "existing test deleted"
    return None


def stage2_violations(changes: list[tuple[str, str]], locked: set[str]) -> list[str]:
    """Stage 2 (write code) may not touch locks, governance, CI or old tests."""
    out: list[str] = []
    for status, path in changes:
        reason = _stage2_reason(status, path, locked)
        if reason:
            out.append(f"{status} {path}: {reason}")
    return out
