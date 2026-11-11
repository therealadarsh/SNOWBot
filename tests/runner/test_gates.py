"""Gate runner and red/green checks, with fake subprocess runners."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from snowbot.runner.gates import (
    GateReport,
    GateResult,
    parse_junit,
    red_check,
    run_gates,
    suite_passes_without,
)

FIX = Path(__file__).parent / "fixtures"


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
    assert cmd[:3] == [sys.executable, "-m", "pytest"]
    assert "tests/test_a.py" in cmd and "--junitxml=.snowbot-out/red.xml" in cmd
    assert "-p" in cmd and "no:cacheprovider" in cmd
    assert not any(c.startswith("--cov") for c in cmd)


def _gate_runner(
    fail: str | None = None, calls: list[tuple[list[str], dict[str, Any]]] | None = None
) -> Any:
    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        if calls is not None:
            calls.append((cmd, kw))
        tool = cmd[3] if cmd[2] == "ruff" else cmd[2]
        if tool == "pytest":
            out = Path(kw["cwd"]) / ".snowbot-out"
            assert out.is_dir()
            shutil.copy(FIX / "junit_mixed.xml", out / "junit.xml")
        if fail is not None and fail in " ".join(cmd):
            lines = "\n".join(f"line {i}" for i in range(50))
            return _cp(1, out=lines, err="error: bad types")
        return _cp(0, out=f"{tool} ok")

    return run


def test_run_gates_order_and_failure(tmp_path: Path) -> None:
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
    assert report.test_outcomes["tests/test_a.py::test_bad"] == "failed"
    cmds = [c for c, _ in calls]
    assert cmds[0] == [sys.executable, "-m", "ruff", "check", "src", "tests"]
    assert cmds[1] == [sys.executable, "-m", "ruff", "format", "--check", "src", "tests"]
    assert cmds[2] == [sys.executable, "-m", "mypy"]
    assert cmds[3] == [
        sys.executable,
        "-m",
        "pytest",
        "--cov=snowbot",
        "--cov-fail-under=85",
        "--junitxml=.snowbot-out/junit.xml",
    ]
    assert cmds[4] == [
        sys.executable,
        "-m",
        "snowbot",
        "validate",
        "--phase",
        "issue",
        "--base-ref",
        "uat",
    ]


def test_run_gates_all_pass_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "/existing")
    calls: list[tuple[list[str], dict[str, Any]]] = []
    report = run_gates(tmp_path, base_ref="uat", runner=_gate_runner(None, calls))
    assert report.passed is True
    for _, kw in calls:
        assert kw["cwd"] == tmp_path
        assert kw["capture_output"] is True and kw["text"] is True and kw["check"] is False
        assert kw["env"]["PYTHONPATH"] == os.pathsep.join([str(tmp_path / "src"), "/existing"])
    assert os.environ["PYTHONPATH"] == "/existing"


def test_run_gates_pythonpath_without_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PYTHONPATH", raising=False)
    calls: list[tuple[list[str], dict[str, Any]]] = []
    run_gates(tmp_path, base_ref="uat", runner=_gate_runner(None, calls))
    assert calls[0][1]["env"]["PYTHONPATH"] == str(tmp_path / "src")


def test_run_gates_missing_junit_gives_empty_outcomes(tmp_path: Path) -> None:
    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        return _cp(0)

    report = run_gates(tmp_path, base_ref="uat", runner=run)
    assert report.test_outcomes == {}


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
    assert seen[0][:3] == [sys.executable, "-m", "pytest"]
    assert "--ignore=tests/a.py" in seen[0] and "--ignore=tests/b.py" in seen[0]


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
        if cmd[2] == "pytest":
            (Path(kw["cwd"]) / ".snowbot-out" / "junit.xml").write_text(content)
        return _cp(0)

    report = run_gates(tmp_path, base_ref="uat", runner=run)
    assert report.test_outcomes == {}
    assert report.results[3].name == "pytest" and report.results[3].passed is True


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
