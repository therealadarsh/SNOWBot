"""Per-stage diff policy: what an agent may change in its worktree.

Stage 1 (write tests) may only add or modify files under ``tests/``. Stage 2 (write code) is an
allowlist (ruling R17): product code under ``src/snowbot/``, new tests, docs, examples and three
root files. Specific checks run first so the reason names what was hit. Every comparison is
case-insensitive, because a case-insensitive filesystem resolves ``Src/Snowbot`` to
``src/snowbot``.
"""

from __future__ import annotations

import sys
from fnmatch import fnmatchcase
from functools import cache
from importlib.metadata import packages_distributions

from snowbot.validator.antigaming import GOVERNANCE_PATH_PREFIXES

LOCKS_DIR = ".snowbot/locks"
PROJECT_PACKAGE = "snowbot"
_TESTS = "tests/"
_PROJECT_CONFIG = ("snowbot.yaml",)
_AGENT_DIRS = {".claude", ".cursor", ".codex"}
_AGENT_FILES = {"claude.md", "claude.local.md", "agents.md", ".mcp.json", "conftest.py"}
# Files that configure ruff, mypy, pytest, coverage or the interpreter itself, at any depth.
_TOOL_CONFIG_FILES = {
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "tox.ini",
    "pytest.ini",
    ".pytest.ini",
    "mypy.ini",
    ".mypy.ini",
    "ruff.toml",
    ".ruff.toml",
    ".coveragerc",
    "conftest.py",
    "sitecustomize.py",
    "usercustomize.py",
}
# Modules the interpreter imports at start-up, in any importable form (.py, .pyc, .so, ...).
_STARTUP_MODULES = {"sitecustomize", "usercustomize"}
_IMPORTABLE_SUFFIXES = (".py", ".pyc", ".pyo", ".pyd", ".so")
# Package metadata on sys.path registers entry points, including pytest plugins.
_METADATA_SUFFIXES = (".egg-info", ".dist-info", ".egg-link")
_CONFIG_BASENAMES = (
    "requirements*.txt",
    "*.lock",
    "package-lock.json",
)
_STAGE2_ALLOWED_PREFIXES = ("src/snowbot/", "tests/", "docs/", "examples/")
_STAGE2_ALLOWED_FILES = {"readme.md", "changelog.md", "status.md"}
_GOVERNANCE = tuple(p.lower() for p in GOVERNANCE_PATH_PREFIXES)


def _base(path: str) -> str:
    return path.lower().rsplit("/", 1)[-1]


def is_agent_config(path: str) -> bool:
    """True for agent instruction/config files and conftest.py at any depth."""
    parts = path.lower().split("/")
    return bool(_AGENT_DIRS.intersection(parts)) or parts[-1] in _AGENT_FILES


def is_tool_config(path: str) -> bool:
    """True for tool or interpreter configuration at any depth, by case-insensitive basename."""
    base = _base(path)
    if base in _TOOL_CONFIG_FILES or base.endswith(".pth"):
        return True
    return base.split(".", 1)[0] in _STARTUP_MODULES and base.endswith(_IMPORTABLE_SUFFIXES)


def is_package_metadata(path: str) -> bool:
    """True for anything inside (or named) ``*.egg-info``, ``*.dist-info`` or ``*.egg-link``."""
    return any(part.endswith(_METADATA_SUFFIXES) for part in path.lower().split("/"))


@cache
def _shadowable_names() -> frozenset[str]:
    """Top-level names a file under tests/ must not take: stdlib, installed, this project."""
    names = set(sys.stdlib_module_names) | set(packages_distributions()) | {PROJECT_PACKAGE}
    return frozenset(n.lower() for n in names)


def shadowed_module(path: str) -> str | None:
    """The module a path under ``tests/`` would shadow, if any.

    ``tests/`` has no ``__init__.py``, so pytest's prepend import mode puts test directories at
    the front of ``sys.path``. Any directory below ``tests/``, or importable file in one, then
    competes with real top-level modules: ``tests/snowbot/__init__.py`` would replace the
    package under test.
    """
    parts = path.lower().split("/")
    if parts[0] != "tests" or len(parts) < 2:
        return None
    names = _shadowable_names()
    *dirs, last = parts[1:]
    for part in dirs:
        if part in names:
            return part
    if last.endswith(_IMPORTABLE_SUFFIXES):
        stem = last.split(".", 1)[0]
        if stem in names:
            return stem
    return None


def _common_reason(path: str) -> str | None:
    if is_agent_config(path):
        return "agent config"
    if is_tool_config(path):
        return "tool config"
    if is_package_metadata(path):
        return "package metadata"
    module = shadowed_module(path)
    if module is not None:
        return f"shadows module {module!r}"
    return None


def stage1_violations(changes: list[tuple[str, str]]) -> list[str]:
    """Stage 1 (write tests) may only add or change files under tests/."""
    out: list[str] = []
    for status, path in changes:
        reason = _common_reason(path)
        if reason is None and not (status in ("A", "M") and path.lower().startswith(_TESTS)):
            reason = "stage 1 may only add or change tests/"
        if reason:
            out.append(f"{status} {path}: {reason}")
    return out


def _stage2_reason(status: str, path: str, locked: set[str]) -> str | None:
    low = path.lower()
    if is_agent_config(path):
        return "agent config"
    if low in {p.lower() for p in locked}:
        return "locked test"
    if low.startswith(LOCKS_DIR + "/"):
        return "lock manifest"
    reason = _common_reason(path)
    if reason is not None:
        return reason
    if low.startswith(".snowbot/"):
        return "snowbot state"
    if low.startswith(".github/"):
        return "CI config"
    if low in _PROJECT_CONFIG:
        return "project config"
    if low.startswith("scripts/"):
        return "scripts"
    if any(fnmatchcase(_base(path), pat) for pat in _CONFIG_BASENAMES):
        return "build or tool config"
    if any(low == p or low.startswith(p) for p in _GOVERNANCE):
        return "governance path"
    if low.startswith(_TESTS) and status != "A":
        return {"M": "existing test modified", "D": "existing test deleted"}.get(
            status, "existing test changed"
        )
    if low.startswith(_STAGE2_ALLOWED_PREFIXES) or low in _STAGE2_ALLOWED_FILES:
        return None
    return "outside allowed paths"


def stage2_violations(changes: list[tuple[str, str]], locked: set[str]) -> list[str]:
    """Stage 2 (write code) may only touch the allowlisted paths, never old tests or config."""
    out: list[str] = []
    for status, path in changes:
        reason = _stage2_reason(status, path, locked)
        if reason:
            out.append(f"{status} {path}: {reason}")
    return out
