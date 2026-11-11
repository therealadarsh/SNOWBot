from __future__ import annotations

import pytest

from snowbot.runner.policy import is_agent_config, stage1_violations, stage2_violations


def test_stage1_allows_only_tests() -> None:
    assert stage1_violations([("A", "tests/test_x.py")]) == []
    assert stage1_violations([("M", "tests/test_x.py")]) == []
    assert stage1_violations([("M", "src/snowbot/cli.py")]) == [
        "M src/snowbot/cli.py: stage 1 may only add or change tests/"
    ]
    assert stage1_violations([("D", "tests/test_x.py")]) == [
        "D tests/test_x.py: stage 1 may only add or change tests/"
    ]


def test_stage2_blocks_locked_and_existing_tests() -> None:
    v = stage2_violations(
        [
            ("M", "tests/test_cli.py"),
            ("A", "tests/test_new.py"),
            ("M", "tests/test_issue_7.py"),
            ("A", ".snowbot/locks/issue-7.json"),
            ("M", ".github/workflows/ci.yml"),
            ("M", "pyproject.toml"),
            ("M", "src/snowbot/cli.py"),
        ],
        locked={"tests/test_issue_7.py"},
    )
    assert [s.split(":")[0] for s in v] == [
        "M tests/test_cli.py",
        "M tests/test_issue_7.py",
        "A .snowbot/locks/issue-7.json",
        "M .github/workflows/ci.yml",
        "M pyproject.toml",
    ]


def test_stage2_blocks_deleted_test() -> None:
    assert stage2_violations([("D", "tests/test_cli.py")], set()) == [
        "D tests/test_cli.py: existing test deleted"
    ]


def test_stage2_blocks_any_github_path() -> None:
    v = stage2_violations([("A", ".github/CODEOWNERS"), ("M", ".github/dependabot.yml")], set())
    assert [s.split(":")[0] for s in v] == ["A .github/CODEOWNERS", "M .github/dependabot.yml"]


def test_stage2_blocks_governance_and_config() -> None:
    v = stage2_violations(
        [("M", "AGENTS.md"), ("M", "snowbot.yaml"), ("M", "src/snowbot/validator/x.py")], set()
    )
    assert len(v) == 3


def test_stage2_allows_product_code() -> None:
    assert stage2_violations([("M", "src/snowbot/cli.py"), ("A", "tests/test_new.py")], set()) == []


AGENT_CONFIG_PATHS = [
    "tests/CLAUDE.md",
    "tests/.claude/settings.json",
    "tests/conftest.py",
    "CLAUDE.md",
    ".claude/settings.json",
    ".mcp.json",
    "src/x/AGENTS.md",
    "a/.Cursor/rules",
    "a/.codex/x",
    "x/claude.local.md",
]


@pytest.mark.parametrize("path", AGENT_CONFIG_PATHS)
def test_agent_config_blocked_in_both_stages(path: str) -> None:
    assert is_agent_config(path)
    assert stage1_violations([("A", path)]) == [f"A {path}: agent config"]
    assert stage2_violations([("A", path)], set()) == [f"A {path}: agent config"]


def test_is_agent_config_negatives() -> None:
    assert not is_agent_config("src/snowbot/claude_helper.py")
    assert not is_agent_config("tests/test_x.py")


@pytest.mark.parametrize(
    "path",
    [
        ".GitHub/workflows/x.yml",
        "requirements-dev.txt",
        "sub/requirements.txt",
        "uv.lock",
        "package-lock.json",
        "setup.cfg",
        "tox.ini",
        ".coveragerc",
        "pytest.ini",
        "scripts/x.sh",
        ".snowbot/memory/PLAYBOOK.md",
        "pyproject.toml",
    ],
)
def test_stage2_blocks_more_governance(path: str) -> None:
    assert len(stage2_violations([("M", path)], set())) == 1


@pytest.mark.parametrize("path", [".githubfoo/x", "sub/pyproject.toml", "sub/snowbot.yaml"])
def test_stage2_allows_lookalikes(path: str) -> None:
    assert stage2_violations([("M", path)], set()) == []
