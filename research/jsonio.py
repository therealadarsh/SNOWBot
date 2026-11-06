"""JSON object loading for research documents."""

from __future__ import annotations

import json
from pathlib import Path

from research.errors import ConfigError


def load_json_object(path: Path) -> dict[str, object]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConfigError(f"{path} must be a JSON object")
    out: dict[str, object] = {}
    for key, value in loaded.items():
        if not isinstance(key, str):
            raise ConfigError(f"{path} has a non-string key")
        out[key] = value
    return out
