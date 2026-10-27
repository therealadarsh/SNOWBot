"""Individual phase validation checks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowbot.lessons.digest import PLAYBOOK_MAX_LINES
from snowbot.validator.antigaming import run_anti_gaming
from snowbot.validator.context import CheckContext


@dataclass(frozen=True)
class CheckSpec:
    id: str
    description: str
    kind: str
    path: str = ""
    needle: str = ""
    max_lines: int = PLAYBOOK_MAX_LINES


@dataclass
class CheckOutcome:
    spec: CheckSpec
    passed: bool
    message: str


def parse_check(raw: dict[str, Any]) -> CheckSpec:
    return CheckSpec(
        id=str(raw["id"]),
        description=str(raw.get("description", raw["id"])),
        kind=str(raw["kind"]),
        path=str(raw.get("path", "")),
        needle=str(raw.get("needle", "")),
        max_lines=int(raw.get("max_lines", PLAYBOOK_MAX_LINES)),
    )


def run_check(
    root: Path,
    spec: CheckSpec,
    *,
    context: CheckContext | None = None,
) -> CheckOutcome:
    ctx = context or CheckContext()
    runner = _CHECK_RUNNERS.get(spec.kind)
    if runner is None:
        return CheckOutcome(spec, False, f"Unknown check kind: {spec.kind}")
    return runner(root, spec, ctx)


def _anti_gaming_diff(root: Path, spec: CheckSpec, ctx: CheckContext) -> CheckOutcome:
    outcome = run_anti_gaming(root, ctx.base_ref, diff_override=ctx.diff_override)
    if outcome.passed:
        return CheckOutcome(spec, True, "No anti-gaming findings in diff")
    if len(outcome.findings) == 1 and outcome.findings[0].code == "governance_mixed_with_product":
        msg = outcome.findings[0].message
        return CheckOutcome(
            spec,
            True,
            f"pass_with_notes: governance_mixed_with_product — {msg} (bootstrap; see STATUS.md)",
        )
    first = outcome.findings[0]
    return CheckOutcome(
        spec,
        False,
        f"{first.code}: {first.message} ({len(outcome.findings)} finding(s))",
    )


def _file_exists(root: Path, spec: CheckSpec, _ctx: CheckContext) -> CheckOutcome:
    target = root / spec.path
    ok = target.is_file()
    return CheckOutcome(spec, ok, f"{'Found' if ok else 'Missing'} {spec.path}")


def _dir_exists(root: Path, spec: CheckSpec, _ctx: CheckContext) -> CheckOutcome:
    target = root / spec.path
    ok = target.is_dir()
    return CheckOutcome(spec, ok, f"{'Found' if ok else 'Missing'} directory {spec.path}")


def _file_nonempty(root: Path, spec: CheckSpec, _ctx: CheckContext) -> CheckOutcome:
    target = root / spec.path
    if not target.is_file():
        return CheckOutcome(spec, False, f"Missing {spec.path}")
    text = target.read_text(encoding="utf-8").strip()
    ok = len(text) > 0
    return CheckOutcome(spec, ok, f"{spec.path} {'non-empty' if ok else 'empty'}")


def _file_contains(root: Path, spec: CheckSpec, _ctx: CheckContext) -> CheckOutcome:
    target = root / spec.path
    if not target.is_file():
        return CheckOutcome(spec, False, f"Missing {spec.path}")
    ok = spec.needle in target.read_text(encoding="utf-8")
    return CheckOutcome(
        spec,
        ok,
        f"{'Found' if ok else 'Missing'} needle in {spec.path}",
    )


def _playbook_line_cap(root: Path, spec: CheckSpec, _ctx: CheckContext) -> CheckOutcome:
    target = root / spec.path
    if not target.is_file():
        return CheckOutcome(spec, True, f"{spec.path} not present (skipped)")
    line_count = len(target.read_text(encoding="utf-8").splitlines())
    ok = line_count <= spec.max_lines
    return CheckOutcome(
        spec,
        ok,
        f"{spec.path} has {line_count} lines (max {spec.max_lines})",
    )


_CHECK_RUNNERS: dict[str, Callable[[Path, CheckSpec, CheckContext], CheckOutcome]] = {
    "file_exists": _file_exists,
    "dir_exists": _dir_exists,
    "file_nonempty": _file_nonempty,
    "file_contains": _file_contains,
    "playbook_line_cap": _playbook_line_cap,
    "anti_gaming_diff": _anti_gaming_diff,
}
