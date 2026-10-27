"""String phase identifiers (``1``, ``1b``, ``2``, …)."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

_PHASE_ID_RE = re.compile(r"^[0-9]+(?:[a-z][a-z0-9]*)?$")


def normalize_phase_id(value: str | int) -> str:
    """Coerce CLI/config input to a canonical string phase id."""
    text = str(value).strip()
    if not text:
        msg = "Phase id must be non-empty"
        raise ValueError(msg)
    if not _PHASE_ID_RE.match(text):
        msg = f"Invalid phase id {text!r}; expected forms like 1, 1b, 2"
        raise ValueError(msg)
    return text


def _validate_phase_id(value: str) -> str:
    return normalize_phase_id(value)


PhaseId = Annotated[str, AfterValidator(_validate_phase_id)]
