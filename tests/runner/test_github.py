"""Tests for the gh-backed GitHub client. The real gh is never called."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from snowbot.runner.github import (
    DryRunGitHub,
    GhCli,
    GitHubError,
    Issue,
    LabelEvent,
    is_trusted_label,
)


class FakeRunner:
    """Records argv; returns canned results keyed by a substring of the command."""

    def __init__(self, responses: dict[str, tuple[int, str]] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[list[str]] = []
        self.bodies: list[str] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["check"] is False
        self.calls.append(list(argv))
        if "--body-file" in argv:
            with open(argv[argv.index("--body-file") + 1], encoding="utf-8") as fh:
                self.bodies.append(fh.read())
        joined = " ".join(argv)
        for key, (code, out) in self.responses.items():
            if key in joined:
                return subprocess.CompletedProcess(argv, code, out, "boom" if code else "")
        return subprocess.CompletedProcess(argv, 0, "", "")


def labeled(actor: str, label: str) -> str:
    return json.dumps({"event": "labeled", "label": {"name": label}, "actor": {"login": actor}})


def make(responses: dict[str, tuple[int, str]]) -> tuple[GhCli, FakeRunner]:
    fake = FakeRunner(responses)
    return GhCli("o/r", runner=fake), fake


def test_untrusted_labeler_rejected() -> None:
    gh, _ = make(
        {
            "timeline": (0, labeled("drive-by", "snowbot:ready")),
            "collaborators/drive-by/permission": (0, "read\n"),
        }
    )
    assert is_trusted_label(gh, 5, "snowbot:ready") is False


def test_missing_label_event_rejected() -> None:
    gh, _ = make({"timeline": (0, "")})
    assert is_trusted_label(gh, 5, "snowbot:ready") is False


def test_write_labeler_trusted() -> None:
    gh, _ = make(
        {
            "timeline": (0, labeled("alice", "snowbot:ready")),
            "collaborators/alice/permission": (0, "write\n"),
        }
    )
    assert is_trusted_label(gh, 5, "snowbot:ready") is True


def test_non_collaborator_404_is_untrusted() -> None:
    gh, _ = make(
        {
            "timeline": (0, labeled("stranger", "snowbot:ready")),
            "collaborators/stranger/permission": (1, ""),
        }
    )
    assert gh.permission("stranger") == "none"
    assert is_trusted_label(gh, 5, "snowbot:ready") is False


def test_most_recent_labeled_event_wins_and_paginated_lines_parse() -> None:
    lines = "\n".join(
        [
            labeled("old", "snowbot:ready"),
            json.dumps({"event": "commented", "actor": {"login": "x"}}),
            labeled("someone", "other"),
            labeled("newest", "snowbot:ready"),
        ]
    )
    gh, fake = make({"timeline": (0, lines)})
    assert gh.label_actor(5, "snowbot:ready") == "newest"
    argv = fake.calls[0]
    assert "--paginate" in argv and "repos/o/r/issues/5/timeline" in argv
    assert gh.label_actor(5, "nope") is None


def test_dry_run_records_writes_and_skips_gh() -> None:
    fake = FakeRunner()
    dry = DryRunGitHub(GhCli("o/r", runner=fake))
    dry.comment(5, "hi")
    dry.add_label(5, "snowbot:failed")
    dry.remove_label(5, "snowbot:ready")
    assert dry.create_draft_pr("feat/x", "uat", "t", "b") == 0
    dry.edit_pr(7, title="t", body=None)
    assert dry.actions == [
        "comment #5",
        "add_label #5 snowbot:failed",
        "remove_label #5 snowbot:ready",
        "create_draft_pr feat/x -> uat",
        "edit_pr #7",
    ]
    assert fake.calls == []


def test_dry_run_reads_pass_through() -> None:
    gh, fake = make({"issue list": (0, json.dumps([{"number": 9}, {"number": 2}]))})
    dry = DryRunGitHub(gh)
    assert dry.issues_with_label("snowbot:ready") == [2, 9]
    assert len(fake.calls) == 1


def test_create_pr_uses_draft_and_body_file() -> None:
    gh, fake = make({"pr create": (0, "https://github.com/o/r/pull/42\n")})
    assert gh.create_draft_pr("feat/x", "uat", "Title", "Body text") == 42
    argv = fake.calls[0]
    assert "--draft" in argv and "--body-file" in argv
    assert argv[argv.index("--repo") + 1] == "o/r"
    assert fake.bodies == ["Body text"]


def test_edit_pr_body_via_file_and_title() -> None:
    gh, fake = make({})
    gh.edit_pr(7, title="T", body="B")
    argv = fake.calls[0]
    assert "--body-file" in argv and argv[argv.index("--title") + 1] == "T"
    assert fake.bodies == ["B"]


def test_get_issue_parses_labels() -> None:
    payload = {"number": 5, "title": "T", "body": None, "labels": [{"name": "a"}, {"name": "b"}]}
    gh, _ = make({"issue view": (0, json.dumps(payload))})
    assert gh.get_issue(5) == Issue(5, "T", "", frozenset({"a", "b"}))


def test_pr_for_branch_and_head_sha() -> None:
    rows = [{"number": 11, "isCrossRepository": False}]
    gh, fake = make({"pr list": (0, json.dumps(rows)), "pr view": (0, "abc123\n")})
    assert gh.pr_for_branch("feat/x") == 11
    assert gh.pr_head_sha(11) == "abc123"
    empty, _ = make({"pr list": (0, "[]")})
    assert empty.pr_for_branch("feat/x") is None
    assert all("--repo" in c or "repos/o/r" in " ".join(c) for c in fake.calls)


def test_label_comment_calls_and_failure_raises() -> None:
    gh, fake = make({})
    gh.add_label(5, "x")
    gh.remove_label(5, "x")
    gh.comment(5, "hello")
    assert [c[2:4] for c in fake.calls] == [["edit", "5"], ["edit", "5"], ["comment", "5"]]
    bad, _ = make({"issue comment": (1, "")})
    with pytest.raises(GitHubError) as exc:
        bad.comment(5, "x")
    assert exc.value.details is not None and exc.value.details["stderr"] == "boom"


def test_pr_for_branch_ignores_fork_prs() -> None:
    rows = [
        {"number": 3, "isCrossRepository": True},
        {"number": 4},  # field missing: not known to be same-repo, so dropped
        {"number": 8, "isCrossRepository": False},
    ]
    gh, fake = make({"pr list": (0, json.dumps(rows))})
    assert gh.pr_for_branch("snowbot/issue-5") == 8
    argv = fake.calls[0]
    assert argv[argv.index("--json") + 1] == "number,isCrossRepository"
    only_forks, _ = make({"pr list": (0, json.dumps([{"number": 3, "isCrossRepository": True}]))})
    assert only_forks.pr_for_branch("snowbot/issue-5") is None


def _labeled_at(actor: str | None, label: str, at: str | None) -> str:
    event: dict[str, Any] = {"event": "labeled", "label": {"name": label}}
    if actor is not None:
        event["actor"] = {"login": actor}
    if at is not None:
        event["created_at"] = at
    return json.dumps(event)


def test_label_event_has_login_and_time_of_latest_application() -> None:
    lines = "\n".join(
        [
            _labeled_at("old", "snowbot:ready", "2026-11-01T00:00:00Z"),
            _labeled_at("other", "x", "2026-11-03T00:00:00Z"),
            _labeled_at("newest", "snowbot:ready", "2026-11-02T10:00:00Z"),
        ]
    )
    gh, _ = make({"timeline": (0, lines)})
    assert gh.label_event(5, "snowbot:ready") == LabelEvent(
        login="newest", created_at="2026-11-02T10:00:00Z"
    )
    assert gh.label_actor(5, "snowbot:ready") == "newest"
    assert gh.label_event(5, "missing") is None


def test_label_event_without_actor_or_time() -> None:
    gh, _ = make({"timeline": (0, _labeled_at(None, "snowbot:ready", "2026-11-02T10:00:00Z"))})
    assert gh.label_event(5, "snowbot:ready") is None
    assert gh.label_actor(5, "snowbot:ready") is None
    gh, _ = make({"timeline": (0, _labeled_at("alice", "snowbot:ready", None))})
    # Unknown time is an empty string; callers must not treat it as recent.
    assert gh.label_event(5, "snowbot:ready") == LabelEvent(login="alice", created_at="")


def test_dry_run_label_event_passes_through() -> None:
    gh, fake = make({"timeline": (0, _labeled_at("a", "l", "2026-11-02T10:00:00Z"))})
    dry = DryRunGitHub(gh)
    assert dry.label_event(5, "l") == LabelEvent("a", "2026-11-02T10:00:00Z")
    assert len(fake.calls) == 1
