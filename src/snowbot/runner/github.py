"""GitHub client over the ``gh`` CLI, with a dry-run wrapper."""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from snowbot.errors import SnowbotError

TRUSTED_PERMISSIONS = frozenset({"admin", "maintain", "write"})

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class GitHubError(SnowbotError):
    """A ``gh`` call failed."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "github_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, details=details)


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str
    labels: frozenset[str]


class GitHub(Protocol):
    def get_issue(self, n: int) -> Issue: ...
    def label_actor(self, n: int, label: str) -> str | None: ...
    def permission(self, login: str) -> str: ...
    def add_label(self, n: int, label: str) -> None: ...
    def remove_label(self, n: int, label: str) -> None: ...
    def comment(self, n: int, body: str) -> None: ...
    def create_draft_pr(self, branch: str, base: str, title: str, body: str) -> int: ...
    def edit_pr(self, n: int, *, title: str | None, body: str | None) -> None: ...
    def pr_for_branch(self, branch: str) -> int | None: ...
    def pr_head_sha(self, n: int) -> str: ...
    def issues_with_label(self, label: str) -> list[int]: ...


class GhCli:
    """``GitHub`` implemented by shelling out to ``gh``."""

    def __init__(self, repo: str, runner: Runner = subprocess.run) -> None:
        self.repo = repo
        self._run = runner

    def _gh(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self._run(["gh", *args], capture_output=True, text=True, check=False)

    def _ok(self, *args: str) -> str:
        proc = self._gh(*args)
        if proc.returncode != 0:
            raise GitHubError(
                f"gh {' '.join(args[:2])} failed",
                details={"argv": ["gh", *args], "stderr": proc.stderr},
            )
        return str(proc.stdout)

    def get_issue(self, n: int) -> Issue:
        out = self._ok(
            "issue", "view", str(n), "--repo", self.repo, "--json", "number,title,body,labels"
        )
        data = json.loads(out)
        return Issue(
            number=int(data["number"]),
            title=str(data["title"]),
            body=str(data.get("body") or ""),
            labels=frozenset(str(label["name"]) for label in data.get("labels", [])),
        )

    def label_actor(self, n: int, label: str) -> str | None:
        out = self._ok("api", f"repos/{self.repo}/issues/{n}/timeline", "--paginate", "--jq", ".[]")
        actor: str | None = None
        for line in out.splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("event") != "labeled":
                continue
            if (event.get("label") or {}).get("name") != label:
                continue
            login = (event.get("actor") or {}).get("login")
            actor = str(login) if login else None
        return actor

    def permission(self, login: str) -> str:
        proc = self._gh(
            "api", f"repos/{self.repo}/collaborators/{login}/permission", "--jq", ".permission"
        )
        if proc.returncode != 0:
            return "none"
        return str(proc.stdout).strip() or "none"

    def add_label(self, n: int, label: str) -> None:
        self._ok("issue", "edit", str(n), "--repo", self.repo, "--add-label", label)

    def remove_label(self, n: int, label: str) -> None:
        self._ok("issue", "edit", str(n), "--repo", self.repo, "--remove-label", label)

    def comment(self, n: int, body: str) -> None:
        self._ok("issue", "comment", str(n), "--repo", self.repo, "--body", body)

    def create_draft_pr(self, branch: str, base: str, title: str, body: str) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            body_file = Path(tmp) / "body.md"
            body_file.write_text(body, encoding="utf-8")
            out = self._ok(
                "pr", "create", "--draft", "--repo", self.repo, "--head", branch,
                "--base", base, "--title", title, "--body-file", str(body_file),
            )  # fmt: skip
        tail = out.strip().rsplit("/", 1)[-1]
        if not tail.isdigit():
            raise GitHubError("could not parse PR number", details={"stdout": out})
        return int(tail)

    def edit_pr(self, n: int, *, title: str | None, body: str | None) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = ["pr", "edit", str(n), "--repo", self.repo]
            if title is not None:
                args += ["--title", title]
            if body is not None:
                body_file = Path(tmp) / "body.md"
                body_file.write_text(body, encoding="utf-8")
                args += ["--body-file", str(body_file)]
            self._ok(*args)

    def pr_for_branch(self, branch: str) -> int | None:
        out = self._ok(
            "pr", "list", "--repo", self.repo, "--head", branch, "--state", "open",
            "--json", "number",
        )  # fmt: skip
        rows = json.loads(out)
        return int(rows[0]["number"]) if rows else None

    def pr_head_sha(self, n: int) -> str:
        out = self._ok(
            "pr", "view", str(n), "--repo", self.repo, "--json", "headRefOid", "--jq", ".headRefOid"
        )
        return out.strip()

    def issues_with_label(self, label: str) -> list[int]:
        out = self._ok(
            "issue", "list", "--repo", self.repo, "--label", label, "--state", "open",
            "--json", "number",
        )  # fmt: skip
        return sorted(int(row["number"]) for row in json.loads(out))


class DryRunGitHub:
    """Reads pass through to the wrapped client; writes are recorded, not sent."""

    def __init__(self, inner: GitHub) -> None:
        self._inner = inner
        self.actions: list[str] = []

    def get_issue(self, n: int) -> Issue:
        return self._inner.get_issue(n)

    def label_actor(self, n: int, label: str) -> str | None:
        return self._inner.label_actor(n, label)

    def permission(self, login: str) -> str:
        return self._inner.permission(login)

    def pr_for_branch(self, branch: str) -> int | None:
        return self._inner.pr_for_branch(branch)

    def pr_head_sha(self, n: int) -> str:
        return self._inner.pr_head_sha(n)

    def issues_with_label(self, label: str) -> list[int]:
        return self._inner.issues_with_label(label)

    def add_label(self, n: int, label: str) -> None:
        self.actions.append(f"add_label #{n} {label}")

    def remove_label(self, n: int, label: str) -> None:
        self.actions.append(f"remove_label #{n} {label}")

    def comment(self, n: int, body: str) -> None:
        self.actions.append(f"comment #{n}")

    def create_draft_pr(self, branch: str, base: str, title: str, body: str) -> int:
        self.actions.append(f"create_draft_pr {branch} -> {base}")
        return 0

    def edit_pr(self, n: int, *, title: str | None, body: str | None) -> None:
        self.actions.append(f"edit_pr #{n}")


def is_trusted_label(gh: GitHub, n: int, label: str) -> bool:
    """True when the latest applier of ``label`` on issue ``n`` has write access."""
    try:
        actor = gh.label_actor(n, label)
        if actor is None:
            return False
        return gh.permission(actor) in TRUSTED_PERMISSIONS
    except GitHubError:
        return False
