"""Phase id string normalization."""

from __future__ import annotations

import pytest

from snowbot.models.phases import normalize_phase_id


def test_phase_ids() -> None:
    assert normalize_phase_id("1") == "1"
    assert normalize_phase_id("1b") == "1b"
    assert normalize_phase_id("2") == "2"


def test_invalid_phase() -> None:
    with pytest.raises(ValueError):
        normalize_phase_id("1-b")
