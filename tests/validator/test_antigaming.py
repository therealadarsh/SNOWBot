"""Anti-gaming diff regression tests (must fail bad fixtures)."""

from __future__ import annotations

from pathlib import Path

import pytest

from snowbot.validator.antigaming import analyze_diff
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
