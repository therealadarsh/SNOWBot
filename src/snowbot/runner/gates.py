"""Gates and red/green checks the runner itself executes.

The agent never decides whether its work is good. After it proposes tests or code, the runner
runs these checks in the worktree: ``red_check`` (proposed tests must fail on the unchanged
code) and ``run_gates`` (lint, types, tests with coverage, phase validation must pass).
"""

from __future__ import annotations

import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

TAIL_LINES = 30
OUT_DIR = ".snowbot-out"
MEMORY_DIR = ".snowbot/memory"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class GateResult:
    """One gate command's outcome with the last lines of its output."""

    name: str
    passed: bool
    tail: str


@dataclass(frozen=True)
class GateReport:
    """All gate results plus per-test outcomes from the pytest junit file."""

    results: tuple[GateResult, ...]
    test_outcomes: dict[str, str]

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)


def _tail(proc: subprocess.CompletedProcess[str]) -> str:
    text = (proc.stdout or "") + (proc.stderr or "")
    return "\n".join(text.splitlines()[-TAIL_LINES:])


def _env(wt: Path) -> dict[str, str]:
    """Environment that makes the worktree's own package importable first."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    src = str(wt / "src")
    env["PYTHONPATH"] = os.pathsep.join([src, existing]) if existing else src
    return env


def _exec(runner: Runner, wt: Path, cmd: list[str]) -> subprocess.CompletedProcess[str]:
    proc: subprocess.CompletedProcess[str] = runner(
        cmd, cwd=wt, capture_output=True, text=True, check=False, env=_env(wt)
    )
    return proc


def _restore_memory(wt: Path) -> None:
    """Undo whatever pytest and ``snowbot validate`` wrote under ``.snowbot/memory``."""
    if not (wt / MEMORY_DIR).is_dir():
        return
    for cmd in (
        ["git", "checkout", "--", MEMORY_DIR],
        ["git", "clean", "-fdq", MEMORY_DIR],
    ):
        subprocess.run(cmd, cwd=wt, capture_output=True, text=True, check=False)


def _outcome(case: ET.Element) -> str:
    if case.find("error") is not None:
        return "error"
    if case.find("failure") is not None:
        return "failed"
    if case.find("skipped") is not None:
        return "skipped"
    return "passed"


def _file_and_rest(classname: str, name: str, root: Path | None) -> tuple[str, str]:
    """Map a junit classname/name pair to ``(file path, test name)``."""
    if not classname:
        # Collection error: pytest writes the dotted module as the name.
        return "/".join(name.split(".")) + ".py", "<collection>"
    parts = classname.split(".")
    split = len(parts)
    for i in range(len(parts), 0, -1):
        if root is not None and (root / ("/".join(parts[:i]) + ".py")).is_file():
            split = i
            break
    else:
        for i, part in enumerate(parts, start=1):
            if part.startswith("test_") or part.endswith("_test") or part == "tests":
                split = i
                if part != "tests":
                    break
    file = "/".join(parts[:split]) + ".py"
    rest = "::".join([*parts[split:], name])
    return file, rest


def parse_junit(path: Path, root: Path | None = None) -> dict[str, str]:
    """Map ``<file>::<test>`` to passed, failed, error or skipped. Missing file gives ``{}``.

    ``root`` (the worktree) lets file names be resolved against real files; without it a
    ``test_*`` module name is assumed.
    """
    try:
        tree = ET.parse(path)
    except FileNotFoundError:
        return {}
    outcomes: dict[str, str] = {}
    for case in tree.getroot().iter("testcase"):
        file, rest = _file_and_rest(case.get("classname", ""), case.get("name", ""), root)
        outcomes[f"{file}::{rest}"] = _outcome(case)
    return outcomes


def _safe_parse(path: Path, root: Path) -> dict[str, str] | None:
    """``parse_junit`` that returns None for a truncated, empty or unreadable file."""
    try:
        return parse_junit(path, root)
    except (ET.ParseError, OSError):
        return None


def red_check(
    wt: Path, test_files: list[str], *, runner: Runner = subprocess.run
) -> tuple[bool, dict[str, str], str]:
    """Proposed tests must fail (or fail to collect) on the unchanged code.

    Returns ``(ok, outcomes, reason)``. ``ok`` only when every file collected at least one
    test and every outcome is ``failed`` or ``error``.
    """
    if not test_files:
        return False, {}, "no test files"
    absolute = [f for f in test_files if Path(f).is_absolute()]
    if absolute:
        return False, {}, "absolute test file path not allowed: " + ", ".join(absolute)
    files = [Path(f).as_posix().removeprefix("./") for f in test_files]
    report = wt / OUT_DIR / "red.xml"
    try:
        (wt / OUT_DIR).mkdir(exist_ok=True)
        report.unlink(missing_ok=True)
        proc = _exec(
            runner,
            wt,
            [
                sys.executable,
                "-m",
                "pytest",
                *files,
                f"--junitxml={OUT_DIR}/red.xml",
                "-q",
                "-p",
                "no:cacheprovider",
                # Without this one collection error aborts the run and hides the other files.
                "--continue-on-collection-errors",
            ],
        )
        if not report.is_file():
            return False, {}, f"pytest produced no junit report: {_tail(proc)}"
        parsed = _safe_parse(report, wt)
        if parsed is None:
            return False, {}, f"unparseable junit report: {_tail(proc)}"
        outcomes = parsed
    finally:
        _restore_memory(wt)

    problems: list[str] = []
    empty = [f for f in files if not any(k.startswith(f"{f}::") for k in outcomes)]
    if empty:
        problems.append("collected no tests: " + ", ".join(empty))
    passing = sorted(k for k, v in outcomes.items() if v == "passed")
    if passing:
        problems.append("already passes: " + ", ".join(passing))
    skipped = sorted(k for k, v in outcomes.items() if v == "skipped")
    if skipped:
        problems.append("skipped: " + ", ".join(skipped))
    if problems:
        return False, outcomes, "; ".join(problems)
    return True, outcomes, "all proposed tests fail before implementation"


def run_gates(wt: Path, *, base_ref: str, runner: Runner = subprocess.run) -> GateReport:
    """Run lint, format, types, tests with coverage and phase validation, in that order."""
    py = sys.executable
    gates: list[tuple[str, list[str]]] = [
        ("ruff check", [py, "-m", "ruff", "check", "src", "tests"]),
        ("ruff format", [py, "-m", "ruff", "format", "--check", "src", "tests"]),
        ("mypy", [py, "-m", "mypy"]),
        (
            "pytest",
            [
                py,
                "-m",
                "pytest",
                "--cov=snowbot",
                "--cov-fail-under=85",
                f"--junitxml={OUT_DIR}/junit.xml",
            ],
        ),
        (
            "validate",
            [py, "-m", "snowbot", "validate", "--phase", "issue", "--base-ref", base_ref],
        ),
    ]
    results: list[GateResult] = []
    try:
        (wt / OUT_DIR).mkdir(exist_ok=True)
        (wt / OUT_DIR / "junit.xml").unlink(missing_ok=True)
        for name, cmd in gates:
            proc = _exec(runner, wt, cmd)
            results.append(GateResult(name, proc.returncode == 0, _tail(proc)))
        outcomes = _safe_parse(wt / OUT_DIR / "junit.xml", wt) or {}
    finally:
        _restore_memory(wt)
    return GateReport(results=tuple(results), test_outcomes=outcomes)


def suite_passes_without(
    wt: Path, excluded: list[str], *, runner: Runner = subprocess.run
) -> GateResult:
    """Run the suite with the given test files ignored (stage 1 of the issue flow)."""
    cmd = [sys.executable, "-m", "pytest", *(f"--ignore={e}" for e in excluded)]
    try:
        proc = _exec(runner, wt, cmd)
    finally:
        _restore_memory(wt)
    return GateResult("pytest", proc.returncode == 0, _tail(proc))


__all__ = [
    "GateReport",
    "GateResult",
    "parse_junit",
    "red_check",
    "run_gates",
    "suite_passes_without",
]
