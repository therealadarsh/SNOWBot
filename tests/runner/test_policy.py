from __future__ import annotations

from snowbot.runner.policy import stage1_violations, stage2_violations


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
