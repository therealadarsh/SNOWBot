from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from tests.helpers.gitrepo import commit_files, make_repo

from snowbot.errors import SnowbotError
from snowbot.runner.workspace import (
    changed_files,
    checkout,
    commit_all,
    create_worktree,
    head_sha,
    push,
    remove_worktree,
)


def test_changed_files_ignores_out_dir(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    base = commit_files(repo, {"tests/test_old.py": "x\n", "src/a.py": "a\n"}, "base")
    (repo / ".snowbot-out").mkdir()
    (repo / ".snowbot-out" / "log.txt").write_text("noise")
    (repo / "tests").joinpath("test_new.py").write_text("n\n")
    (repo / "src/a.py").write_text("changed\n")
    (repo / "tests/test_old.py").unlink()
    assert changed_files(repo, base) == [
        ("M", "src/a.py"),
        ("A", "tests/test_new.py"),
        ("D", "tests/test_old.py"),
    ]


def test_worktree_roundtrip(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    wt = create_worktree(repo, "feat/issue-7", "main")
    assert wt == repo.parent / "repo-run-feat-issue-7"
    assert wt.is_dir()
    (wt / "tests").mkdir()
    (wt / "tests" / "test_x.py").write_text("x\n")
    (wt / ".snowbot-out").mkdir()
    (wt / ".snowbot-out" / "o.txt").write_text("o")
    sha = commit_all(wt, "add test")
    assert sha == head_sha(wt)
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=wt, capture_output=True, text=True, check=True
    ).stdout.split()
    assert "tests/test_x.py" in tracked
    assert ".snowbot-out/o.txt" not in tracked
    base = head_sha(repo)
    checkout(wt, base)
    assert head_sha(wt) == base
    remove_worktree(repo, wt)
    assert not wt.exists()


def test_push_to_local_bare_remote(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=repo, check=True)
    wt = create_worktree(repo, "feat/p", "main")
    (wt / "f.txt").write_text("f\n")
    sha = commit_all(wt, "f")
    push(wt, "feat/p")
    out = subprocess.run(
        ["git", "rev-parse", "feat/p"], cwd=bare, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == sha


def test_push_failure_carries_stderr(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    subprocess.run(
        ["git", "remote", "add", "origin", str(tmp_path / "missing.git")], cwd=repo, check=True
    )
    with pytest.raises(SnowbotError) as exc:
        push(repo, "main")
    assert "missing.git" in str(exc.value)


def test_changed_files_reports_ignored_agent_config(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    base = commit_files(
        repo, {".gitignore": ".claude/settings.local.json\n*.pyc\n.coverage\n"}, "ignore"
    )
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.local.json").write_text("{}")
    (repo / "x.pyc").write_text("c")
    (repo / ".coverage").write_text("c")
    assert changed_files(repo, base) == [("A", ".claude/settings.local.json")]
