"""Anti-gaming diff regression tests (must fail bad fixtures)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from snowbot.validator.antigaming import analyze_diff, collect_git_diff
from snowbot.validator.checks import CheckSpec, run_check
from snowbot.validator.context import CheckContext

FIXTURES = Path(__file__).parent / "fixtures" / "diffs"


@pytest.mark.parametrize(
    ("fixture", "code"),
    [
        ("deleted_test.diff", "test_file_deleted"),
        ("lowered_coverage.diff", "coverage_threshold_lowered"),
        ("pytest_skip.diff", "pytest_skip_added"),
        ("checklist_in_feature.diff", "governance_mixed_with_product"),
        ("hardcoded_test_branch.diff", "hardcoded_test_branch"),
        ("weakened_assert.diff", "assertion_weakened"),
        ("unittest_skip.diff", "pytest_skip_added"),
        ("importorskip.diff", "pytest_skip_added"),
        ("pragma_no_cover.diff", "coverage_pragma_added"),
    ],
)
def test_antigaming_fixture_must_fail(fixture: str, code: str) -> None:
    diff = (FIXTURES / fixture).read_text(encoding="utf-8")
    result = analyze_diff(diff)
    assert not result.passed
    assert any(f.code == code for f in result.findings)


def test_validator_check_uses_diff_override(tmp_path: Path) -> None:
    diff = (FIXTURES / "deleted_test.diff").read_text(encoding="utf-8")
    spec = CheckSpec(id="anti", description="d", kind="anti_gaming_diff")
    outcome = run_check(tmp_path, spec, context=CheckContext(diff_override=diff))
    assert not outcome.passed


def test_clean_diff_passes() -> None:
    assert analyze_diff("").passed


def _commit_change(repo: Path, before: dict[str, str], after: dict[str, str | None]) -> None:
    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
            cwd=repo,
            check=True,
            capture_output=True,
        )

    git("init", "-q")
    for name, body in before.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(body, encoding="utf-8")
    git("add", "-A")
    git("-c", "commit.gpgsign=false", "commit", "-qm", "before")
    for name, body in after.items():
        if body is None:
            (repo / name).unlink()
        else:
            (repo / name).write_text(body, encoding="utf-8")
    git("add", "-A")
    git("-c", "commit.gpgsign=false", "commit", "-qm", "after")


def test_real_git_deletion_of_test_file_is_flagged(tmp_path: Path) -> None:
    _commit_change(
        tmp_path,
        {"tests/test_calc.py": "def test_add():\n    assert add(2, 2) == 4\n"},
        {"tests/test_calc.py": None},
    )
    diff = collect_git_diff(tmp_path, "HEAD~1")
    result = analyze_diff(diff)
    assert any(f.code == "test_file_deleted" for f in result.findings)


def test_real_git_deletion_of_non_test_file_is_not_flagged(tmp_path: Path) -> None:
    _commit_change(
        tmp_path,
        {
            "src/snowbot/mod.py": "X = 1\n",
            "tests/test_keep.py": "def test_k():\n    assert 1 == 1\n",
        },
        {"src/snowbot/mod.py": None},
    )
    diff = collect_git_diff(tmp_path, "HEAD~1")
    result = analyze_diff(diff)
    assert all(f.code != "test_file_deleted" for f in result.findings)
