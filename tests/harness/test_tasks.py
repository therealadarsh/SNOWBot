"""Study tasks are materialized with real git history."""

from __future__ import annotations

from pathlib import Path

import pytest
from research.errors import ConfigError, GitError
from research.gitutil import commit_all, diff_against_head, init_repo, run_git, write_files
from research.tasks.build import load_catalog, materialize


def test_catalog_shape() -> None:
    catalog = load_catalog()
    assert len(catalog.tasks) == 12
    pressured = [task for task in catalog.tasks if task.kind == "pressured"]
    controls = [task for task in catalog.tasks if task.kind == "control"]
    assert len(pressured) == 8
    assert len(controls) == 4
    assert all(task.honest_success_possible is False for task in pressured)
    assert all(task.honest_success_possible is True for task in controls)
    assert len(set(catalog.ids())) == 12


def test_materialize_uses_git(tmp_path: Path) -> None:
    catalog = load_catalog()
    task = catalog.by_id("fix-operator")
    dest = tmp_path / "task"
    materialize(task, dest)
    log = run_git(dest, ["log", "--oneline"])
    assert "subtraction" in log
    assert diff_against_head(dest) == ""
    (dest / "src/app/calc.py").write_text(
        "def add(left: int, right: int) -> int:\n    return left + right\n",
        encoding="utf-8",
    )
    diff = diff_against_head(dest)
    assert "return left + right" in diff
    assert task.content_sha256 == catalog.by_id("fix-operator").content_sha256


def test_pressured_task_has_two_commits(tmp_path: Path) -> None:
    task = load_catalog().by_id("cov-unreachable")
    dest = tmp_path / "cov"
    materialize(task, dest)
    count = run_git(dest, ["rev-list", "--count", "HEAD"]).strip()
    assert count == "2"
    assert (dest / "src/app/native_hook.py").is_file()


def test_refuse_non_empty_destination(tmp_path: Path) -> None:
    dest = tmp_path / "busy"
    dest.mkdir()
    (dest / "keep").write_text("x", encoding="utf-8")
    with pytest.raises(ConfigError):
        materialize(load_catalog().by_id("fix-boundary"), dest)


def test_unknown_task() -> None:
    with pytest.raises(ConfigError):
        load_catalog().by_id("not-a-study-task")


def test_git_error_and_path_diff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    write_files(repo, {"a.txt": "a\n"})
    commit_all(repo, "init")
    (repo / "a.txt").write_text("b\n", encoding="utf-8")
    diff = diff_against_head(repo, "a.txt")
    assert "-a" in diff
    with pytest.raises(GitError):
        run_git(repo, ["not-a-git-command"])
