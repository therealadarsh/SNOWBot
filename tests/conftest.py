"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The pytest console script does not put the repo root on sys.path. CI runs
# that script. Prepend mode also puts tests/ first, so a tests/ directory
# named research would be imported instead of the top-level package.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_repo = str(_REPO_ROOT)
if _repo not in sys.path:
    sys.path.insert(0, _repo)


@pytest.fixture
def tmp_yaml_dir(tmp_path: Path) -> Path:
    """Empty directory for writing YAML fixtures."""
    return tmp_path
