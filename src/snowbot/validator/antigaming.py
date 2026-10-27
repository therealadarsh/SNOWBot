"""Detect test/CI gaming patterns in git diffs."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

GOVERNANCE_PATH_PREFIXES: tuple[str, ...] = (
    "AGENTS.md",
    "CONTRIBUTING.md",
    ".github/workflows/",
    "src/snowbot/validator/",
    "src/snowbot/templates/",
    "docs/ARCHITECT_GATE.md",
    "docs/GITHUB_SETUP.md",
    "docs/INDEPENDENT_VALIDATION.md",
    "docs/BRANCH_PROTECTION.md",
    "scripts/independent_validate.sh",
    ".pre-commit-config.yaml",
)

GOVERNANCE_PYPROJECT_KEYS: tuple[str, ...] = (
    "fail_under",
    "tool.coverage",
    "tool.mypy",
    "tool.ruff",
    "tool.pytest",
)


@dataclass(frozen=True)
class AntiGamingFinding:
    code: str
    message: str


@dataclass
class AntiGamingResult:
    findings: list[AntiGamingFinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.findings


def collect_git_diff(root: Path, base_ref: str | None) -> str:
    """Return unified diff against *base_ref* (or empty when unavailable)."""
    if base_ref is None:
        return ""
    try:
        proc = subprocess.run(
            ["git", "diff", f"{base_ref}...HEAD", "--no-color"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ""
    if proc.returncode != 0:
        return proc.stdout or ""
    return proc.stdout


def analyze_diff(diff_text: str) -> AntiGamingResult:
    """Scan a unified diff for disallowed weakening patterns."""
    result = AntiGamingResult()
    if not diff_text.strip():
        return result

    _check_fail_under_lowered(diff_text, result)
    _check_pytest_skips(diff_text, result)
    _check_deleted_tests(diff_text, result)
    _check_broad_mypy_ignore(diff_text, result)
    _check_hardcoded_test_detection(diff_text, result)
    _check_governance_mixed_with_product(diff_text, result)
    return result


def run_anti_gaming(
    root: Path,
    base_ref: str | None,
    *,
    diff_override: str | None = None,
) -> AntiGamingResult:
    diff = diff_override if diff_override is not None else collect_git_diff(root, base_ref)
    return analyze_diff(diff)


def _check_fail_under_lowered(diff: str, result: AntiGamingResult) -> None:
    removed = [
        int(m.group(1))
        for line in diff.splitlines()
        if line.startswith("-") and (m := re.search(r"fail_under\s*=\s*(\d+)", line))
    ]
    added = [
        int(m.group(1))
        for line in diff.splitlines()
        if line.startswith("+") and (m := re.search(r"fail_under\s*=\s*(\d+)", line))
    ]
    if removed and added and min(added) < max(removed):
        result.findings.append(
            AntiGamingFinding(
                "coverage_threshold_lowered",
                f"Coverage fail_under lowered from {max(removed)} to {min(added)}",
            )
        )
    for value in added:
        if value < 85:
            result.findings.append(
                AntiGamingFinding(
                    "coverage_threshold_low",
                    f"Coverage fail_under set below 85: {value}",
                )
            )


def _check_pytest_skips(diff: str, result: AntiGamingResult) -> None:
    for line in diff.splitlines():
        if not line.startswith("+"):
            continue
        if "pytest.mark.skip" in line or "pytest.mark.xfail" in line:
            snippet = line[1:].strip()
            result.findings.append(
                AntiGamingFinding("pytest_skip_added", f"Added skip/xfail marker: {snippet}")
            )


def _check_deleted_tests(diff: str, result: AntiGamingResult) -> None:
    if re.search(r"^diff --git a/tests/.*\.py b/dev/null", diff, re.M):
        result.findings.append(AntiGamingFinding("test_file_deleted", "A test module was removed"))


def _check_broad_mypy_ignore(diff: str, result: AntiGamingResult) -> None:
    for line in diff.splitlines():
        if line.startswith("+") and "ignore_errors = true" in line.lower():
            result.findings.append(
                AntiGamingFinding("mypy_broad_ignore", "Added mypy ignore_errors")
            )
        if (
            line.startswith("+")
            and "ignore_missing_imports = true" in line
            and ("tests/" in diff or "src/snowbot/" in diff)
        ):
            result.findings.append(
                AntiGamingFinding(
                    "mypy_missing_imports",
                    "Added ignore_missing_imports (requires governance review)",
                )
            )


def _check_hardcoded_test_detection(diff: str, result: AntiGamingResult) -> None:
    patterns = (
        r'\+.*if\s+["\']pytest["\']\s+in\s+sys\.modules',
        r"\+.*os\.environ\.get\([\"']PYTEST",
        r"\+.*if\s+.*PYTEST_CURRENT_TEST",
    )
    for pattern in patterns:
        if re.search(pattern, diff):
            result.findings.append(
                AntiGamingFinding(
                    "hardcoded_test_branch",
                    "Detected test-environment conditional branch in diff",
                )
            )
            break


def _check_governance_mixed_with_product(diff: str, result: AntiGamingResult) -> None:
    touched = _touched_paths(diff)
    gov = {p for p in touched if _is_governance_path(p)}
    product = {p for p in touched if _is_product_path(p)}
    if gov and product:
        result.findings.append(
            AntiGamingFinding(
                "governance_mixed_with_product",
                "Governance files changed together with product code/tests "
                f"(governance={sorted(gov)[:3]}, product={sorted(product)[:3]})",
            )
        )


def _touched_paths(diff: str) -> set[str]:
    paths: set[str] = set()
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            paths.add(line[6:].strip())
        if line.startswith("--- a/"):
            paths.add(line[6:].strip())
    return paths


def _is_governance_path(path: str) -> bool:
    if path == "pyproject.toml":
        return True
    return any(path.startswith(prefix) or path == prefix for prefix in GOVERNANCE_PATH_PREFIXES)


def _is_product_path(path: str) -> bool:
    if path.startswith("tests/") and path.endswith(".py"):
        return True
    return bool(path.startswith("src/snowbot/") and not path.startswith("src/snowbot/validator/"))
