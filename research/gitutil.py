"""Git helpers that build fixtures and capture real diffs."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from research.errors import GitError

_STRIP_EXACT = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "OPENAI_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "CURSOR_API_KEY",
    }
)
_STRIP_SUFFIXES = ("_API_KEY", "_AUTH_TOKEN", "_SECRET", "_PASSWORD")


def scrub_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy an environment without provider credentials."""
    source = os.environ if base is None else base
    cleaned: dict[str, str] = {}
    for key, value in source.items():
        if key in _STRIP_EXACT or key.endswith(_STRIP_SUFFIXES):
            continue
        cleaned[key] = value
    return cleaned


def git_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    env = scrub_env(base)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_PAGER"] = "cat"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def run_git(cwd: Path, args: Sequence[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=git_env(),
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "git failed"
        raise GitError(detail)
    return proc.stdout


def init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    run_git(path, ["init", "-b", "main"])
    run_git(path, ["config", "user.email", "research@snowbot.local"])
    run_git(path, ["config", "user.name", "SNOWBot Research"])


def write_files(path: Path, files: Mapping[str, str]) -> None:
    for rel, content in files.items():
        dest = path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")


def commit_all(path: Path, message: str) -> None:
    run_git(path, ["add", "-A"])
    run_git(path, ["commit", "-m", message])


def diff_against_head(path: Path, rel: str | None = None) -> str:
    """Return a real ``git diff HEAD`` including untracked files.

    Intent-to-add is reset afterward so the index is left clean and the
    worktree edits remain.
    """
    run_git(path, ["add", "-A", "-N"])
    args = ["diff", "--no-color", "--no-renames", "HEAD"]
    if rel is not None:
        args.extend(["--", rel])
    text = run_git(path, args)
    run_git(path, ["reset", "-q"])
    return text


def restore_worktree_file(path: Path, rel: str, *, existed: bool) -> None:
    target = path / rel
    if existed:
        run_git(path, ["checkout", "--", rel])
        return
    if target.exists() or target.is_symlink():
        target.unlink()
    try:
        run_git(path, ["reset", "-q", "--", rel])
    except GitError:
        return
