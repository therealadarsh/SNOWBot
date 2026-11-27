"""Gates run against real ruff, mypy and pytest on scratch worktrees an attacker wrote.

Each scratch tree plants modules that would stand in for the tools if the worktree were on
``sys.path`` (``ruff/``, ``mypy/``, ``pytest/``, ``sitecustomize.py``). The gates must still run
the installed tools and report the tree's real problems.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from snowbot.runner.gates import red_check, run_gates, suite_passes_without

PYPROJECT = """\
[tool.mypy]
strict = true
packages = ["snowbot"]
mypy_path = "src"

[tool.pytest.ini_options]
testpaths = ["tests"]
"""


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _plant_shadows(root: Path, exit_code: int) -> None:
    """Fake tools that print SHADOW and exit with ``exit_code`` if they ever run."""
    fake_main = f'import sys\n\nprint("SHADOW")\nsys.exit({exit_code})\n'
    for pkg in ("mypy", "ruff", "src/mypy", "src/ruff", "pytest"):
        _write(root, f"{pkg}/__init__.py", "")
        _write(root, f"{pkg}/__main__.py", fake_main)
    # Imported at interpreter start-up if the worktree root were on sys.path.
    _write(root, "sitecustomize.py", f'import os\n\nprint("SHADOW")\nos._exit({exit_code})\n')


def _init_git(root: Path) -> None:
    for cmd in (
        ["git", "init", "-q"],
        ["git", "config", "user.name", "t"],
        ["git", "config", "user.email", "t@example.com"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "init"],
    ):
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)


def _dirty_tree(root: Path) -> None:
    _write(root, "pyproject.toml", PYPROJECT)
    # F401 (unused import) and a strict-mode type error.
    _write(root, "src/snowbot/__init__.py", 'import os\n\n\ndef f() -> int:\n    return "x"\n')
    _write(root, "src/snowbot/fmt.py", "x = {  'a':1}\n")  # not ruff-formatted
    _write(root, "tests/test_x.py", "def test_x() -> None:\n    assert 1 == 2\n")
    _plant_shadows(root, exit_code=0)
    _init_git(root)


def _clean_tree(root: Path) -> None:
    _write(root, "pyproject.toml", PYPROJECT)
    _write(root, "src/snowbot/__init__.py", "def f() -> int:\n    return 1\n")
    _write(
        root,
        "tests/test_x.py",
        "from snowbot import f\n\n\ndef test_x() -> None:\n    assert f() == 1\n",
    )
    _plant_shadows(root, exit_code=3)
    _init_git(root)


def test_shadow_tools_cannot_pass_a_broken_tree(tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    _dirty_tree(wt)
    report = run_gates(wt, base_ref="HEAD", timeout_s=300)
    by_name = {r.name: r for r in report.results}
    for name in ("ruff check", "ruff format", "mypy", "pytest"):
        assert by_name[name].passed is False, by_name[name].tail
        assert "SHADOW" not in by_name[name].tail
    assert "F401" in by_name["ruff check"].tail
    assert "fmt.py" in by_name["ruff format"].tail
    # mypy read pyproject.toml from the cwd and checked src/ through mypy_path.
    assert "Incompatible return value type" in by_name["mypy"].tail
    assert report.test_outcomes == {"tests/test_x.py::test_x": "failed"}
    assert report.passed is False


def test_isolated_tools_still_pass_a_clean_tree(tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    _clean_tree(wt)
    report = run_gates(wt, base_ref="HEAD", timeout_s=300)
    by_name = {r.name: r for r in report.results}
    for name in ("ruff check", "ruff format", "mypy", "pytest"):
        assert by_name[name].passed is True, by_name[name].tail
        assert "SHADOW" not in by_name[name].tail
    assert "Success" in by_name["mypy"].tail
    assert report.test_outcomes == {"tests/test_x.py::test_x": "passed"}
    assert not (wt / ".mypy_cache").exists() and not (wt / ".ruff_cache").exists()


def test_red_check_ignores_root_pytest_shadow(tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    _clean_tree(wt)
    _write(wt, "tests/test_new.py", "def test_new() -> None:\n    assert False\n")
    ok, outcomes, reason = red_check(wt, ["tests/test_new.py"], timeout_s=120)
    assert ok is True, reason
    assert outcomes == {"tests/test_new.py::test_new": "failed"}


EXIT_ZERO_AFTER_FAILURE = """\
import pytest


def test_a() -> None:
    assert False


def test_b() -> None:
    pytest.exit("x", returncode=0)
"""

HARD_EXIT = """\
import os


def test_a() -> None:
    os._exit(0)
"""


def test_suite_rejects_pytest_exit_zero(tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    _clean_tree(wt)
    _write(wt, "tests/test_attack.py", EXIT_ZERO_AFTER_FAILURE)
    res = suite_passes_without(wt, ["tests/test_other.py"], timeout_s=120)
    assert res.passed is False and "failed or errored" in res.tail


def test_suite_rejects_os_exit_zero(tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    _clean_tree(wt)
    _write(wt, "tests/test_attack.py", HARD_EXIT)
    res = suite_passes_without(wt, ["tests/test_other.py"], timeout_s=120)
    assert res.passed is False and "no junit" in res.tail


def test_run_gates_rejects_pytest_exit_zero(tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    _clean_tree(wt)
    _write(wt, "tests/test_attack.py", EXIT_ZERO_AFTER_FAILURE)
    report = run_gates(wt, base_ref="HEAD", timeout_s=300)
    pytest_gate = next(r for r in report.results if r.name == "pytest")
    assert pytest_gate.passed is False and "failed or errored" in pytest_gate.tail
