"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_yaml_dir(tmp_path: Path) -> Path:
    """Empty directory for writing YAML fixtures."""
    return tmp_path
