"""Gate runner and red/green checks, with fake subprocess runners."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from snowbot.runner import gates as gates_mod
from snowbot.runner.gates import (
    GateReport,
    GateResult,
    parse_junit,
    red_check,
    run_gates,
    suite_passes_without,
)
from snowbot.validator.checks import CheckOutcome, CheckSpec
from snowbot.validator.types import ValidationResult

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def validate_ok(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, str, str]]:
    """Stand-in for the in-process validator in fake-runner tests; records its calls."""
    seen: list[tuple[Path, str, str]] = []

    def fake(layout: Any, phase: str, **kw: Any) -> ValidationResult:
        seen.append((layout.root, phase, kw["base_ref"]))
        assert kw["dry_run"] is False
        spec = CheckSpec(id="c", description="c", kind="file_exists")
        return ValidationResult(phase=phase, title="t", outcomes=[CheckOutcome(spec, True, "ok")])

    monkeypatch.setattr(gates_mod, "run_phase_validation", fake)
    return seen


def _cp(rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=out, stderr=err)


def _junit_runner(fixture: str, rc: int = 1) -> Any:
    """Fake runner that drops a real-pytest junit fixture where red_check reads it."""

    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        out = Path(kw["cwd"]) / ".snowbot-out"
        out.mkdir(exist_ok=True)
        shutil.copy(FIX / fixture, out / "red.xml")
        return _cp(rc)

    return run


def test_parse_junit_outcomes() -> None:
    assert parse_junit(FIX / "junit_mixed.xml") == {
        "tests/test_a.py::test_ok": "passed",
        "tests/test_a.py::test_bad": "failed",
        "tests/test_b.py::<collection>": "error",
        "tests/test_a.py::test_skip": "skipped",
    }


def test_parse_junit_class_based_ids() -> None:
    assert parse_junit(FIX / "junit_class.xml") == {
        "tests/test_c.py::TestK::test_m": "failed",
        "tests/test_c.py::test_only_skip": "skipped",
    }


def test_parse_junit_missing_file(tmp_path: Path) -> None:
    assert parse_junit(tmp_path / "nope.xml") == {}


def test_red_check_rejects_passing_test(tmp_path: Path) -> None:
    ok, outcomes, reason = red_check(
        tmp_path, ["tests/test_p.py"], runner=_junit_runner("junit_passing.xml", rc=0)
    )
    assert not ok and "already passes" in reason
    assert outcomes == {"tests/test_p.py::test_fine": "passed"}


def test_red_check_accepts_import_error(tmp_path: Path) -> None:
    ok, outcomes, _ = red_check(
        tmp_path, ["tests/test_b.py"], runner=_junit_runner("junit_import_error.xml")
    )
    assert ok is True
    assert outcomes == {"tests/test_b.py::<collection>": "error"}


def test_red_check_accepts_failed_tests(tmp_path: Path) -> None:
    ok, _, _ = red_check(tmp_path, ["tests/test_c.py"], runner=_junit_runner("junit_class.xml"))
    assert ok is False  # test_only_skip is skipped, so not accepted
    ok, _, _ = red_check(
        tmp_path, ["tests/test_b.py", "tests/test_a.py"], runner=_junit_runner("junit_mixed.xml")
    )
    assert ok is False  # test_ok passes


def test_red_check_rejects_file_with_zero_tests(tmp_path: Path) -> None:
    ok, _, reason = red_check(
        tmp_path, ["tests/test_empty.py"], runner=_junit_runner("junit_empty.xml", rc=5)
    )
    assert not ok and "collected no tests" in reason


def test_red_check_zero_tests_file_next_to_good_file(tmp_path: Path) -> None:
    ok, _, reason = red_check(
        tmp_path,
        ["tests/test_b.py", "tests/test_empty.py"],
        runner=_junit_runner("junit_mixed.xml"),
    )
    assert not ok and "collected no tests" in reason and "tests/test_empty.py" in reason


def test_red_check_rejects_skipped(tmp_path: Path) -> None:
    ok, _, reason = red_check(
        tmp_path, ["tests/test_s.py"], runner=_junit_runner("junit_skipped.xml", rc=0)
    )
    assert not ok and "skipped" in reason


def test_red_check_command_and_missing_junit(tmp_path: Path) -> None:
    seen: list[list[str]] = []

    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        assert kw["cwd"] == tmp_path
        return _cp(2, err="boom")

    ok, outcomes, reason = red_check(tmp_path, ["tests/test_a.py"], runner=run)
    assert not ok and outcomes == {} and "no junit" in reason
    cmd = seen[0]
    assert cmd[:4] == [sys.executable, "-P", "-m", "pytest"]
    assert "tests/test_a.py" in cmd and "--junitxml=.snowbot-out/red.xml" in cmd
    assert "-p" in cmd and "no:cacheprovider" in cmd
    assert not any(c.startswith("--cov") for c in cmd)


def _gate_runner(
    fail: str | None = None,
    calls: list[tuple[list[str], dict[str, Any]]] | None = None,
    junit: str = "junit_passing.xml",
) -> Any:
    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        if calls is not None:
            calls.append((cmd, kw))
        tool = cmd[4] if cmd[3] == "ruff" else cmd[3]
        if tool == "pytest":
            out = Path(kw["cwd"]) / ".snowbot-out"
            assert out.is_dir()
            shutil.copy(FIX / junit, out / "junit.xml")
        if fail is not None and fail in " ".join(cmd):
            lines = "\n".join(f"line {i}" for i in range(50))
            return _cp(1, out=lines, err="error: bad types")
        return _cp(0, out=f"{tool} ok")

    return run


def test_run_gates_order_and_failure(
    tmp_path: Path, validate_ok: list[tuple[Path, str, str]]
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    report = run_gates(tmp_path, base_ref="uat", runner=_gate_runner("-m mypy", calls))
    assert isinstance(report, GateReport)
    assert [r.name for r in report.results] == [
        "ruff check",
        "ruff format",
        "mypy",
        "pytest",
        "validate",
    ]
    assert report.passed is False
    mypy = report.results[2]
    assert mypy.passed is False
    assert "error: bad types" in mypy.tail and len(mypy.tail.splitlines()) <= 30
    assert [r.passed for r in report.results] == [True, True, False, True, True]
    assert report.test_outcomes == {"tests/test_p.py::test_fine": "passed"}
    cmds = [c for c, _ in calls]
    assert len(cmds) == 4  # validate runs in-process, not as a worktree command
    assert cmds[0] == [sys.executable, "-I", "-m", "ruff", "check", "--no-cache", "src", "tests"]
    assert cmds[1] == [
        sys.executable,
        "-I",
        "-m",
        "ruff",
        "format",
        "--check",
        "--no-cache",
        "src",
        "tests",
    ]
    assert cmds[2][:5] == [sys.executable, "-I", "-m", "mypy", "--cache-dir"]
    assert len(cmds[2]) == 6
    assert Path(cmds[2][5]).name.startswith("snowbot-mypy-")
    assert not Path(cmds[2][5]).exists()  # fresh cache dir, removed afterwards
    assert not Path(cmds[2][5]).is_relative_to(tmp_path)
    assert cmds[3] == [
        sys.executable,
        "-P",
        "-m",
        "pytest",
        "--cov=snowbot",
        "--cov-fail-under=85",
        "--junitxml=.snowbot-out/junit.xml",
    ]
    assert validate_ok == [(tmp_path.resolve(), "issue", "uat")]


def test_run_gates_fresh_mypy_cache_each_run(
    tmp_path: Path, validate_ok: list[tuple[Path, str, str]]
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    run_gates(tmp_path, base_ref="uat", runner=_gate_runner(None, calls))
    run_gates(tmp_path, base_ref="uat", runner=_gate_runner(None, calls))
    caches = [c[5] for c, _ in calls if c[3] == "mypy"]
    assert len(caches) == 2 and caches[0] != caches[1]


_SECRETS = {
    "GH_TOKEN": "gh-secret",
    "GITHUB_TOKEN": "ghs-secret",
    "AWS_SECRET_ACCESS_KEY": "aws-secret",
    "AWS_PROFILE": "prod",
    "ANTHROPIC_API_KEY": "sk-ant-secret",
    "ANTHROPIC_AUTH_TOKEN": "ant-token",
    "PYTHONSTARTUP": "/evil.py",
    "COVERAGE_PROCESS_START": "/evil.cfg",
}


def test_run_gates_all_pass_and_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validate_ok: list[tuple[Path, str, str]]
) -> None:
    monkeypatch.setenv("PYTHONPATH", "/existing")
    monkeypatch.setenv("HOME", "/home/me")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    monkeypatch.setenv("CONDA_PREFIX", "/opt/env")
    for k, v in _SECRETS.items():
        monkeypatch.setenv(k, v)
    calls: list[tuple[list[str], dict[str, Any]]] = []
    report = run_gates(tmp_path, base_ref="uat", runner=_gate_runner(None, calls))
    assert report.passed is True
    for cmd, kw in calls:
        assert kw["cwd"] == tmp_path
        assert kw["capture_output"] is True and kw["text"] is True and kw["check"] is False
        assert kw["timeout"] == 1800
        env = kw["env"]
        assert env["HOME"] == "/home/me" and env["PATH"] == "/usr/bin:/bin"
        assert env["LC_ALL"] == "C.UTF-8" and env["CONDA_PREFIX"] == "/opt/env"
        assert not set(_SECRETS) & set(env)
        if cmd[3] == "pytest":
            assert env["PYTHONPATH"] == str(tmp_path / "src")  # the existing value is dropped
        else:
            assert "PYTHONPATH" not in env
        assert set(env) <= gates_mod.ENV_ALLOWLIST | {"PYTHONPATH"} | {
            k for k in env if k.startswith("LC_")
        }
    assert os.environ["PYTHONPATH"] == "/existing"


def test_run_gates_pythonpath_without_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, validate_ok: list[tuple[Path, str, str]]
) -> None:
    monkeypatch.delenv("PYTHONPATH", raising=False)
    calls: list[tuple[list[str], dict[str, Any]]] = []
    run_gates(tmp_path, base_ref="uat", runner=_gate_runner(None, calls))
    pytest_kw = next(kw for c, kw in calls if c[3] == "pytest")
    assert pytest_kw["env"]["PYTHONPATH"] == str(tmp_path / "src")


def test_red_check_and_suite_env_allowlisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for k, v in _SECRETS.items():
        monkeypatch.setenv(k, v)
    seen: list[dict[str, Any]] = []

    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.append(kw)
        return _cp(1)

    red_check(tmp_path, ["tests/test_a.py"], runner=run)
    suite_passes_without(tmp_path, ["tests/test_a.py"], runner=run)
    assert len(seen) == 2
    for kw in seen:
        assert not set(_SECRETS) & set(kw["env"])
        assert kw["env"]["PYTHONPATH"] == str(tmp_path / "src")
        assert kw["timeout"] == 1800


def test_run_gates_missing_junit_gives_empty_outcomes(
    tmp_path: Path, validate_ok: list[tuple[Path, str, str]]
) -> None:
    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        return _cp(0)

    report = run_gates(tmp_path, base_ref="uat", runner=run)
    assert report.test_outcomes == {}
    # Exit code 0 with no junit (e.g. a test called os._exit(0)) is not a pass.
    assert report.results[3].name == "pytest" and report.results[3].passed is False
    assert "no junit" in report.results[3].tail


def test_run_gates_pytest_exit_zero_with_recorded_failure(
    tmp_path: Path, validate_ok: list[tuple[Path, str, str]]
) -> None:
    # pytest.exit(returncode=0) after a failure: exit code 0, junit says failed.
    report = run_gates(tmp_path, base_ref="uat", runner=_gate_runner(junit="junit_mixed.xml"))
    pytest_gate = report.results[3]
    assert pytest_gate.passed is False and "failed or errored" in pytest_gate.tail
    assert report.passed is False


def test_run_gates_pytest_junit_without_testcases(
    tmp_path: Path, validate_ok: list[tuple[Path, str, str]]
) -> None:
    report = run_gates(tmp_path, base_ref="uat", runner=_gate_runner(junit="junit_empty.xml"))
    assert report.results[3].passed is False and "no testcases" in report.results[3].tail


def test_run_gates_timeout(tmp_path: Path, validate_ok: list[tuple[Path, str, str]]) -> None:
    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        if cmd[3] == "mypy":
            return _cp(-9, out="partial mypy output")
        if cmd[3] == "pytest":
            raise subprocess.TimeoutExpired(cmd, kw["timeout"], output=b"partial pytest")
        return _cp(0)

    report = run_gates(tmp_path, base_ref="uat", runner=run, timeout_s=7)
    by_name = {r.name: r for r in report.results}
    assert by_name["mypy"].passed is False
    assert "timeout after 7s" in by_name["mypy"].tail
    assert "partial mypy output" in by_name["mypy"].tail
    assert by_name["pytest"].passed is False
    assert "timeout after 7s" in by_name["pytest"].tail
    assert "partial pytest" in by_name["pytest"].tail


def test_red_check_and_suite_timeout(tmp_path: Path) -> None:
    timeouts: list[int] = []

    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        timeouts.append(kw["timeout"])
        return _cp(-9, out="still running")

    ok, outcomes, reason = red_check(tmp_path, ["tests/test_a.py"], runner=run, timeout_s=3)
    assert not ok and outcomes == {} and "timeout after 3s" in reason
    res = suite_passes_without(tmp_path, ["tests/test_a.py"], runner=run, timeout_s=4)
    assert res.passed is False and "timeout after 4s" in res.tail
    assert timeouts == [3, 4]


def test_gate_report_passed_property() -> None:
    assert GateReport(results=(GateResult("a", True, ""),), test_outcomes={}).passed
    assert not GateReport(
        results=(GateResult("a", True, ""), GateResult("b", False, "x")), test_outcomes={}
    ).passed


def test_suite_passes_without(tmp_path: Path) -> None:
    seen: list[list[str]] = []

    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        return _cp(1, out="FAILED x")

    res = suite_passes_without(tmp_path, ["tests/a.py", "tests/b.py"], runner=run)
    assert res.passed is False and "FAILED x" in res.tail
    assert seen[0] == [
        sys.executable,
        "-P",
        "-m",
        "pytest",
        "--ignore=tests/a.py",
        "--ignore=tests/b.py",
        "--junitxml=.snowbot-out/suite.xml",
    ]


def _suite_runner(fixture: str | None, rc: int = 0) -> Any:
    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        out = Path(kw["cwd"]) / ".snowbot-out"
        assert out.is_dir() and not (out / "suite.xml").exists()
        if fixture is not None:
            shutil.copy(FIX / fixture, out / "suite.xml")
        return _cp(rc, out="suite tail")

    return run


@pytest.mark.parametrize(
    ("fixture", "passed", "why"),
    [
        ("junit_passing.xml", True, ""),
        ("junit_mixed.xml", False, "failed or errored"),
        ("junit_import_error.xml", False, "failed or errored"),
        ("junit_empty.xml", False, "no testcases"),
        (None, False, "no junit"),
    ],
)
def test_suite_passes_without_needs_clean_junit(
    tmp_path: Path, fixture: str | None, passed: bool, why: str
) -> None:
    # A stale passing report from an earlier run must not count.
    (tmp_path / ".snowbot-out").mkdir()
    shutil.copy(FIX / "junit_passing.xml", tmp_path / ".snowbot-out" / "suite.xml")
    res = suite_passes_without(tmp_path, ["tests/a.py"], runner=_suite_runner(fixture))
    assert res.passed is passed and why in res.tail


def _git(wt: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=wt, capture_output=True, text=True, check=True).stdout


def _memory_repo(tmp_path: Path) -> Path:
    wt = tmp_path / "wt"
    (wt / ".snowbot" / "memory").mkdir(parents=True)
    _git(wt, "init", "-q")
    _git(wt, "config", "user.name", "t")
    _git(wt, "config", "user.email", "t@example.com")
    (wt / ".snowbot" / "memory" / "state.json").write_text("{}\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-qm", "init")
    return wt


def _dirtying_runner(fixture: str | None = None) -> Any:
    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        mem = Path(kw["cwd"]) / ".snowbot" / "memory"
        (mem / "validation").mkdir(exist_ok=True)
        (mem / "validation" / "x.md").write_text("report\n")
        (mem / "state.json").write_text('{"dirty": true}\n')
        if fixture:
            out = Path(kw["cwd"]) / ".snowbot-out"
            out.mkdir(exist_ok=True)
            shutil.copy(FIX / fixture, out / "red.xml")
        return _cp(1, out="fail")

    return run


def test_gates_leave_memory_clean(tmp_path: Path) -> None:
    # The real validator runs here too (no 'issue' phase in this checklist, so it fails).
    wt = _memory_repo(tmp_path)
    report = run_gates(wt, base_ref="uat", runner=_dirtying_runner())
    assert report.passed is False  # every gate failed, memory still restored
    assert _git(wt, "status", "--porcelain", "--", ".snowbot/memory") == ""
    assert (wt / ".snowbot" / "memory" / "state.json").read_text() == "{}\n"


def test_red_check_leaves_memory_clean(tmp_path: Path) -> None:
    wt = _memory_repo(tmp_path)
    red_check(wt, ["tests/test_a.py"], runner=_dirtying_runner("junit_mixed.xml"))
    assert _git(wt, "status", "--porcelain", "--", ".snowbot/memory") == ""


def test_memory_restored_when_runner_raises(tmp_path: Path) -> None:
    wt = _memory_repo(tmp_path)
    dirty = _dirtying_runner()

    def boom(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        dirty(cmd, **kw)
        raise RuntimeError("runner exploded")

    with pytest.raises(RuntimeError, match="exploded"):
        run_gates(wt, base_ref="uat", runner=boom)
    assert _git(wt, "status", "--porcelain", "--", ".snowbot/memory") == ""
    with pytest.raises(RuntimeError, match="exploded"):
        red_check(wt, ["tests/test_a.py"], runner=boom)
    assert _git(wt, "status", "--porcelain", "--", ".snowbot/memory") == ""


@pytest.mark.parametrize(
    "content", ["", '<?xml version="1.0"?><testsuites><testsuite><testcase cl']
)
def test_red_check_unparseable_junit(tmp_path: Path, content: str) -> None:
    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        out = Path(kw["cwd"]) / ".snowbot-out"
        out.mkdir(exist_ok=True)
        (out / "red.xml").write_text(content)
        return _cp(1, out="pytest tail text")

    ok, outcomes, reason = red_check(tmp_path, ["tests/test_a.py"], runner=run)
    assert ok is False and outcomes == {}
    assert "unparseable junit" in reason and "pytest tail text" in reason


@pytest.mark.parametrize(
    "content", ["", '<?xml version="1.0"?><testsuites><testsuite><testcase cl']
)
def test_run_gates_unparseable_junit(tmp_path: Path, content: str) -> None:
    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        if cmd[3] == "pytest":
            (Path(kw["cwd"]) / ".snowbot-out" / "junit.xml").write_text(content)
        return _cp(0)

    report = run_gates(tmp_path, base_ref="uat", runner=run)
    assert report.test_outcomes == {}
    # Flipped (C2): a truncated or empty junit is no longer a pytest pass.
    assert report.results[3].name == "pytest" and report.results[3].passed is False
    assert "unparseable junit" in report.results[3].tail


def test_run_gates_ignores_stale_junit(tmp_path: Path) -> None:
    out = tmp_path / ".snowbot-out"
    out.mkdir()
    shutil.copy(FIX / "junit_mixed.xml", out / "junit.xml")

    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        return _cp(0)

    assert run_gates(tmp_path, base_ref="uat", runner=run).test_outcomes == {}


def test_red_check_dot_slash_path_equals_plain(tmp_path: Path) -> None:
    ok, outcomes, _ = red_check(
        tmp_path, ["./tests/test_b.py"], runner=_junit_runner("junit_import_error.xml")
    )
    assert ok is True and outcomes == {"tests/test_b.py::<collection>": "error"}


def test_red_check_rejects_absolute_path(tmp_path: Path) -> None:
    called: list[int] = []

    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        called.append(1)
        return _cp(1)

    abs_path = str(tmp_path / "tests" / "test_b.py")
    ok, outcomes, reason = red_check(tmp_path, [abs_path], runner=run)
    assert ok is False and outcomes == {} and "absolute" in reason
    assert called == []


def test_red_check_prefix_name_does_not_match(tmp_path: Path) -> None:
    ok, _, reason = red_check(
        tmp_path, ["tests/test_a.py"], runner=_junit_runner("junit_prefix.xml")
    )
    assert not ok and "collected no tests" in reason and "tests/test_a.py" in reason


def test_red_check_no_files_does_not_run(tmp_path: Path) -> None:
    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("runner must not be called")

    assert red_check(tmp_path, [], runner=run) == (False, {}, "no test files")


def test_validate_gate_real_validator_without_issue_phase(tmp_path: Path) -> None:
    wt = _memory_repo(tmp_path)

    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        assert "snowbot" not in cmd  # the worktree's own snowbot never runs
        return _cp(0)

    report = run_gates(wt, base_ref="HEAD", runner=run)
    validate = report.results[4]
    assert validate.name == "validate" and validate.passed is False
    # The validator's ValueError (this checklist has no usable 'issue' phase yet) is the tail.
    assert "'issue'" in validate.tail and validate.tail.count("\n") == 0


def _issue_checklist(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    # 'issue' is not yet an accepted phase id, so a stand-in id carries the checklist.
    monkeypatch.setattr(gates_mod, "VALIDATE_PHASE", "9z")
    checklist = {
        "phases": {
            "9z": {
                "title": "Issue",
                "checks": [{"id": "readme", "kind": "file_exists", "path": path}],
            }
        }
    }
    monkeypatch.setattr("snowbot.validator.runner._load_checklist", lambda: checklist)


@pytest.mark.parametrize(("path", "passed"), [("README.md", True), ("MISSING.md", False)])
def test_validate_gate_runs_installed_validator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str, passed: bool
) -> None:
    wt = _memory_repo(tmp_path)
    (wt / "README.md").write_text("hi\n")
    _issue_checklist(monkeypatch, path)
    report = run_gates(wt, base_ref="HEAD", runner=lambda cmd, **kw: _cp(0))
    validate = report.results[4]
    assert validate.passed is passed
    assert ("[pass] readme" if passed else "[FAIL] readme") in validate.tail
    # The report (and, on failure, the stop event) it wrote are cleaned up.
    assert _git(wt, "status", "--porcelain", "--", ".snowbot/memory") == ""


def test_validate_gate_os_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **kw: Any) -> ValidationResult:
        raise PermissionError("memory dir not writable")

    monkeypatch.setattr(gates_mod, "run_phase_validation", boom)
    report = run_gates(tmp_path, base_ref="uat", runner=lambda cmd, **kw: _cp(0))
    assert report.results[4].passed is False
    assert report.results[4].tail == "memory dir not writable"


def test_safe_env_extra_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    env = gates_mod.safe_env({"PYTHONPATH": "/wt/src"})
    assert env["PYTHONPATH"] == "/wt/src" and env["LANG"] == "en_US.UTF-8"
    assert "GH_TOKEN" not in env
