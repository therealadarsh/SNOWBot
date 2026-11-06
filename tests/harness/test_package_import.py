"""The harness tests import the repo package, not a tests/ directory."""

from __future__ import annotations

from pathlib import Path

import research
import research.budget


def test_research_package_is_the_repo_package() -> None:
    root = Path(__file__).resolve().parents[2]
    assert research.__file__ is not None
    assert Path(research.__file__).resolve() == root / "research" / "__init__.py"
    assert Path(research.budget.__file__).resolve() == root / "research" / "budget.py"
