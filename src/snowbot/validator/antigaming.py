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

# Fixture diffs intentionally contain gaming patterns for unit tests.
DIFF_EXCLUDE_PREFIXES: tuple[str, ...] = ("tests/validator/fixtures/",)
# This module's diff contains literal patterns the scanner searches for.
DIFF_EXCLUDE_FILES: tuple[str, ...] = ("src/snowbot/validator/antigaming.py",)


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


def filter_diff_paths(
    diff_text: str,
    exclude_prefixes: tuple[str, ...] = DIFF_EXCLUDE_PREFIXES,
    exclude_files: tuple[str, ...] = DIFF_EXCLUDE_FILES,
) -> str:
    """Drop diff hunks for excluded paths (e.g. anti-gaming test fixtures)."""
    if not diff_text.strip():
        return diff_text
    parts = re.split(r"(?=^diff --git )", diff_text, flags=re.M)
    kept: list[str] = []
    for part in parts:
        if not part.strip():
            continue
        path_a = re.search(r"^diff --git a/(\S+)", part, re.M)
        path_b = re.search(r"^diff --git a/\S+ b/(\S+)", part, re.M)
        left = path_a.group(1) if path_a else ""
        right = path_b.group(1) if path_b else ""
        path = left if left != "dev/null" else right
        if (
            path
            and path != "dev/null"
            and (
                path in exclude_files or any(path.startswith(prefix) for prefix in exclude_prefixes)
            )
        ):
            continue
        kept.append(part)
    return "".join(kept)


def analyze_diff(diff_text: str) -> AntiGamingResult:
    """Scan a unified diff for disallowed weakening patterns."""
    result = AntiGamingResult()
    diff_text = filter_diff_paths(diff_text)
    if not diff_text.strip():
        return result

    _check_fail_under_lowered(diff_text, result)
    _check_pytest_skips(diff_text, result)
    _check_deleted_tests(diff_text, result)
    _check_assertion_weakened(diff_text, result)
    _check_coverage_pragma(diff_text, result)
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
    marker = re.compile(
        r"@pytest\.mark\.(skip|xfail)\b|pytest\.mark\.(skip|xfail)\("
        r"|@unittest\.skip\b|\bunittest\.skip\("
        r"|\bpytest\.(skip|importorskip)\("
    )
    for line in diff.splitlines():
        if not line.startswith("+"):
            continue
        body = line[1:]
        if marker.search(body):
            snippet = body.strip()
            result.findings.append(
                AntiGamingFinding("pytest_skip_added", f"Added skip/xfail marker: {snippet}")
            )


def _check_deleted_tests(diff: str, result: AntiGamingResult) -> None:
    # Real git marks a deletion with ``+++ /dev/null`` under ``diff --git a/X b/X``.
    for block in re.split(r"(?=^diff --git )", diff, flags=re.M):
        header = re.match(r"diff --git a/(\S+) b/\S+", block)
        if not header:
            continue
        path = header.group(1)
        deleted = re.search(r"^deleted file mode ", block, re.M) or re.search(
            r"^\+\+\+ /dev/null$", block, re.M
        )
        if deleted and path.startswith("tests/") and path.endswith(".py"):
            result.findings.append(
                AntiGamingFinding("test_file_deleted", f"A test module was removed: {path}")
            )


def _added_lines(diff: str) -> list[tuple[str, str]]:
    """Return ``(path, text)`` for every added line in a unified diff."""
    path = ""
    lines: list[tuple[str, str]] = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
        elif line.startswith("+") and not line.startswith("+++"):
            lines.append((path, line[1:]))
    return lines


def _check_assertion_weakened(diff: str, result: AntiGamingResult) -> None:
    tautology = re.compile(r"^\s*assert\s+(True|1)\s*(#.*)?$")
    for path, text in _added_lines(diff):
        if path.startswith("tests/") and tautology.match(text):
            result.findings.append(
                AntiGamingFinding(
                    "assertion_weakened",
                    f"Added tautological assertion in {path}: {text.strip()}",
                )
            )


def _check_coverage_pragma(diff: str, result: AntiGamingResult) -> None:
    pragma = re.compile(r"#\s*pragma:\s*no\s*cover", re.I)
    for path, text in _added_lines(diff):
        if pragma.search(text):
            result.findings.append(
                AntiGamingFinding(
                    "coverage_pragma_added",
                    f"Added coverage exclusion pragma in {path}",
                )
            )


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
