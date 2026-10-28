"""Path matching shared by the treatment lock and the outcome oracle.

The two callers pass independently authored pattern lists.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Sequence


def _normalize(path: str) -> str:
    text = path.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def path_matches(path: str, patterns: Sequence[str]) -> bool:
    normalized = _normalize(path)
    for pattern in patterns:
        candidate = pattern.replace("\\", "/")
        if candidate.endswith("/"):
            if normalized.startswith(candidate) or normalized == candidate.rstrip("/"):
                return True
            continue
        if candidate.startswith("**/"):
            if fnmatch.fnmatch(normalized, candidate) or fnmatch.fnmatch(normalized, candidate[3:]):
                return True
            continue
        if any(token in candidate for token in "*?["):
            if fnmatch.fnmatch(normalized, candidate):
                return True
            continue
        if normalized == candidate or normalized.endswith("/" + candidate):
            return True
    return False


def is_test_path(path: str, test_path_regex: str) -> bool:
    return re.search(test_path_regex, path.replace("\\", "/")) is not None
