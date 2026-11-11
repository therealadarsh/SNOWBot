"""Per-stage diff policy: what an agent may change in its worktree."""

from __future__ import annotations

from fnmatch import fnmatchcase

from snowbot.validator.antigaming import GOVERNANCE_PATH_PREFIXES

LOCKS_DIR = ".snowbot/locks"
_TESTS = "tests/"
_PROJECT_CONFIG = ("pyproject.toml", "snowbot.yaml")
_AGENT_DIRS = {".claude", ".cursor", ".codex"}
_AGENT_FILES = {"claude.md", "claude.local.md", "agents.md", ".mcp.json", "conftest.py"}
_CONFIG_BASENAMES = (
    "requirements*.txt",
    "*.lock",
    "package-lock.json",
    "setup.cfg",
    "setup.py",
    "tox.ini",
    ".coveragerc",
    "pytest.ini",
)


def is_agent_config(path: str) -> bool:
    """True for agent instruction/config files and conftest.py at any depth."""
    parts = path.lower().split("/")
    return bool(_AGENT_DIRS.intersection(parts)) or parts[-1] in _AGENT_FILES


def stage1_violations(changes: list[tuple[str, str]]) -> list[str]:
    """Stage 1 (write tests) may only add or change files under tests/."""
    out: list[str] = []
    for status, path in changes:
        if is_agent_config(path):
            out.append(f"{status} {path}: agent config")
        elif not (status in ("A", "M") and path.startswith(_TESTS)):
            out.append(f"{status} {path}: stage 1 may only add or change tests/")
    return out


def _stage2_reason(status: str, path: str, locked: set[str]) -> str | None:
    base = path.lower().rsplit("/", 1)[-1]
    if is_agent_config(path):
        return "agent config"
    if path in locked:
        return "locked test"
    if path.startswith(LOCKS_DIR + "/"):
        return "lock manifest"
    if path.startswith(".snowbot/"):
        return "snowbot state"
    if path.lower().startswith(".github/"):
        return "CI config"
    if path in _PROJECT_CONFIG:
        return "project config"
    if path.startswith("scripts/"):
        return "scripts"
    if any(fnmatchcase(base, pat) for pat in _CONFIG_BASENAMES):
        return "build or tool config"
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
