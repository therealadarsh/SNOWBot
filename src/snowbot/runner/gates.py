"""Gates and red/green checks the runner itself executes.

The agent never decides whether its work is good. After it proposes tests or code, the runner
runs these checks in the worktree: ``red_check`` (proposed tests must fail on the unchanged
code) and ``run_gates`` (lint, types, tests with coverage, phase validation must pass).

The worktree is agent-written, so none of its files may stand in for the tools:

- ruff and mypy run under ``python -I`` (no cwd, no ``PYTHONPATH``, no user site on
  ``sys.path``), with ruff's cache off and mypy's cache in a fresh temporary directory.
- pytest has to import worktree code, so it runs under ``python -P`` (the cwd is not
  prepended) with ``PYTHONPATH=<wt>/src``. Shadow packages under ``src/`` are rejected by the
  diff policy before the gates run.
- Phase validation runs in-process with the runner's own installed validator.
- A pytest gate passes only on exit code 0 *and* a junit report showing a passing suite.
- Every child gets an allowlisted environment (no tokens) and a timeout that kills its whole
  process group.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from snowbot.memory.layout import MemoryLayout
from snowbot.runner.proc import TIMEOUT_RETURNCODE, run_killing_group
from snowbot.validator.runner import run_phase_validation

TAIL_LINES = 30
OUT_DIR = ".snowbot-out"
MEMORY_DIR = ".snowbot/memory"
DEFAULT_TIMEOUT_S = 1800
VALIDATE_PHASE = "issue"

# Ruling R16: only these variables, and every LC_*, reach a gate's child process.
ENV_ALLOWLIST = frozenset(
    {
        "HOME",
        "PATH",
        "USER",
        "LOGNAME",
        "TERM",
        "LANG",
        "TMPDIR",
        "SHELL",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
    }
)

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


def safe_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """The allowlisted part of ``os.environ`` plus ``extra``. Tokens never get through."""
    env = {k: v for k, v in os.environ.items() if k in ENV_ALLOWLIST or k.startswith("LC_")}
    if extra:
        env.update(extra)
    return env


def _pytest_env(wt: Path) -> dict[str, str]:
    """Allowlisted environment that makes the worktree's own package importable first."""
    return safe_env({"PYTHONPATH": str(wt / "src")})


def _pytest_cmd(*args: str) -> list[str]:
    # -P: the cwd (the worktree root) is not prepended to sys.path.
    return [sys.executable, "-P", "-m", "pytest", *args]


def _isolated_cmd(tool: str, *args: str) -> list[str]:
    # -I: no cwd, no PYTHONPATH and no user site on sys.path, so the installed tool runs.
    return [sys.executable, "-I", "-m", tool, *args]


def _as_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


def _exec(
    runner: Runner, wt: Path, cmd: list[str], env: dict[str, str], timeout_s: int
) -> subprocess.CompletedProcess[str]:
    """Run one gate command. A timeout comes back as returncode ``TIMEOUT_RETURNCODE``."""
    try:
        proc: subprocess.CompletedProcess[str] = runner(
            cmd,
            cwd=wt,
            env=env,
            timeout=timeout_s,
            capture_output=True,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # An injected ``subprocess.run`` raises instead of returning.
        return subprocess.CompletedProcess(
            cmd, TIMEOUT_RETURNCODE, _as_text(exc.stdout), _as_text(exc.stderr)
        )
    return proc


def _timed_out(proc: subprocess.CompletedProcess[str]) -> bool:
    return proc.returncode == TIMEOUT_RETURNCODE


def _with_note(note: str, proc: subprocess.CompletedProcess[str]) -> str:
    tail = _tail(proc)
    return f"{note}\n{tail}" if tail else note


def _tool_result(name: str, proc: subprocess.CompletedProcess[str], timeout_s: int) -> GateResult:
    if _timed_out(proc):
        return GateResult(name, False, _with_note(f"timeout after {timeout_s}s", proc))
    return GateResult(name, proc.returncode == 0, _tail(proc))


def _restore_memory(wt: Path) -> None:
    """Undo whatever pytest and phase validation wrote under ``.snowbot/memory``."""
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


def junit_verdict(path: Path) -> str | None:
    """Why a junit report does not show a passing suite, or None when it does.

    The exit code alone is not trusted: a test can call ``pytest.exit(returncode=0)`` after a
    failure, or ``os._exit(0)`` before any report is written. A passing suite needs a junit
    file that parses, holds at least one testcase, and has no failed or errored testcase.
    Testcase elements are counted directly, so two cases with the same id cannot hide a
    failure.
    """
    try:
        tree = ET.parse(path)
    except FileNotFoundError:
        return "pytest produced no junit report"
    except (ET.ParseError, OSError):
        return "unparseable junit report"
    cases = list(tree.getroot().iter("testcase"))
    if not cases:
        return "junit report has no testcases"
    bad = [c for c in cases if c.find("failure") is not None or c.find("error") is not None]
    if bad:
        names = ", ".join(f"{c.get('classname', '')}::{c.get('name', '')}" for c in bad[:5])
        return f"junit records {len(bad)} failed or errored testcase(s): {names}"
    return None


def _pytest_result(
    name: str, proc: subprocess.CompletedProcess[str], junit: Path, timeout_s: int
) -> GateResult:
    """Pass only on exit code 0 and a junit report that shows a passing suite."""
    result = _tool_result(name, proc, timeout_s)
    if not result.passed:
        return result
    problem = junit_verdict(junit)
    if problem is not None:
        return GateResult(name, False, _with_note(problem, proc))
    return result


def _validate_gate(wt: Path, base_ref: str) -> GateResult:
    """Phase validation with the runner's own validator, never the worktree's ``snowbot``."""
    try:
        result = run_phase_validation(
            MemoryLayout.from_project_root(wt),
            VALIDATE_PHASE,
            base_ref=base_ref,
            dry_run=False,
        )
    except (ValueError, OSError) as exc:
        return GateResult("validate", False, str(exc))
    lines = [
        f"[{'pass' if o.passed else 'FAIL'}] {o.spec.id}: {o.message}" for o in result.outcomes
    ]
    return GateResult("validate", result.passed, "\n".join(lines[-TAIL_LINES:]))


def red_check(
    wt: Path,
    test_files: list[str],
    *,
    runner: Runner = run_killing_group,
    timeout_s: int = DEFAULT_TIMEOUT_S,
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
            _pytest_cmd(
                *files,
                f"--junitxml={OUT_DIR}/red.xml",
                "-q",
                "-p",
                "no:cacheprovider",
                # Without this one collection error aborts the run and hides the other files.
                "--continue-on-collection-errors",
            ),
            _pytest_env(wt),
            timeout_s,
        )
        if _timed_out(proc):
            return False, {}, _with_note(f"timeout after {timeout_s}s", proc)
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


def run_gates(
    wt: Path,
    *,
    base_ref: str,
    runner: Runner = run_killing_group,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> GateReport:
    """Run lint, format, types, tests with coverage and phase validation, in that order.

    ``timeout_s`` applies to each command separately.
    """
    junit = wt / OUT_DIR / "junit.xml"
    results: list[GateResult] = []
    mypy_cache = tempfile.mkdtemp(prefix="snowbot-mypy-")
    try:
        (wt / OUT_DIR).mkdir(exist_ok=True)
        junit.unlink(missing_ok=True)
        tool_env = safe_env()
        tools: list[tuple[str, list[str]]] = [
            ("ruff check", _isolated_cmd("ruff", "check", "--no-cache", "src", "tests")),
            (
                "ruff format",
                _isolated_cmd("ruff", "format", "--check", "--no-cache", "src", "tests"),
            ),
            ("mypy", _isolated_cmd("mypy", "--cache-dir", mypy_cache)),
        ]
        for name, cmd in tools:
            proc = _exec(runner, wt, cmd, tool_env, timeout_s)
            results.append(_tool_result(name, proc, timeout_s))
        proc = _exec(
            runner,
            wt,
            _pytest_cmd("--cov=snowbot", "--cov-fail-under=85", f"--junitxml={OUT_DIR}/junit.xml"),
            _pytest_env(wt),
            timeout_s,
        )
        results.append(_pytest_result("pytest", proc, junit, timeout_s))
        results.append(_validate_gate(wt, base_ref))
        outcomes = _safe_parse(junit, wt) or {}
    finally:
        shutil.rmtree(mypy_cache, ignore_errors=True)
        _restore_memory(wt)
    return GateReport(results=tuple(results), test_outcomes=outcomes)


def suite_passes_without(
    wt: Path,
    excluded: list[str],
    *,
    runner: Runner = run_killing_group,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> GateResult:
    """Run the suite with the given test files ignored (stage 1 of the issue flow).

    Same pass rule as the pytest gate: exit code 0 and a junit report showing a passing suite.
    """
    junit = wt / OUT_DIR / "suite.xml"
    cmd = _pytest_cmd(*(f"--ignore={e}" for e in excluded), f"--junitxml={OUT_DIR}/suite.xml")
    try:
        (wt / OUT_DIR).mkdir(exist_ok=True)
        junit.unlink(missing_ok=True)
        proc = _exec(runner, wt, cmd, _pytest_env(wt), timeout_s)
        return _pytest_result("pytest", proc, junit, timeout_s)
    finally:
        _restore_memory(wt)


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "ENV_ALLOWLIST",
    "GateReport",
    "GateResult",
    "junit_verdict",
    "parse_junit",
    "red_check",
    "run_gates",
    "safe_env",
    "suite_passes_without",
]
