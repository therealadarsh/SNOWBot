"""Git worktree handling for the issue runner."""

from __future__ import annotations

import subprocess
from pathlib import Path

from snowbot.errors import SnowbotError

OUT_DIR = ".snowbot-out"


class WorkspaceError(SnowbotError):
    """A git operation in a runner worktree failed."""

    def __init__(self, message: str, *, code: str = "workspace_error") -> None:
        super().__init__(message=message, code=code)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise WorkspaceError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def create_worktree(repo_root: Path, branch: str, base: str) -> Path:
    """Create a worktree on a new branch cut from base, beside the repo."""
    path = repo_root.parent / f"{repo_root.name}-run-{branch.replace('/', '-')}"
    _git(repo_root, "worktree", "add", "-b", branch, str(path), base)
    return path


def remove_worktree(repo_root: Path, path: Path) -> None:
    _git(repo_root, "worktree", "remove", "--force", str(path))


def _in_out_dir(path: str) -> bool:
    return path == OUT_DIR or path.startswith(OUT_DIR + "/")


def changed_files(wt: Path, base: str) -> list[tuple[str, str]]:
    """(status, path) for the working tree versus base, untracked files as A."""
    found: dict[str, str] = {}
    parts = _git(wt, "diff", "--name-status", "--no-renames", "-z", base).split("\0")
    for i in range(0, len(parts) - 1, 2):
        found[parts[i + 1]] = parts[i][:1]
    untracked = _git(wt, "ls-files", "--others", "--exclude-standard", "-z")
    for path in untracked.split("\0"):
        if path:
            found.setdefault(path, "A")
    return sorted(((s, p) for p, s in found.items() if not _in_out_dir(p)), key=lambda c: c[1])


def head_sha(wt: Path) -> str:
    return _git(wt, "rev-parse", "HEAD").strip()


def commit_all(wt: Path, message: str) -> str:
    _git(wt, "add", "-A", "--", ".", f":!{OUT_DIR}")
    _git(wt, "commit", "-q", "-m", message)
    return head_sha(wt)


def push(wt: Path, branch: str) -> None:
    _git(wt, "push", "-u", "origin", branch)


def checkout(wt: Path, sha: str) -> None:
    _git(wt, "checkout", "-q", "--detach", sha)
