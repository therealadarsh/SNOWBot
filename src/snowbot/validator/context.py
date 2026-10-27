"""Per-run validation context (git base ref, injected diffs for tests)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckContext:
    base_ref: str | None = None
    diff_override: str | None = None
