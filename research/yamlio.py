"""Typed YAML loading."""

from __future__ import annotations

from pathlib import Path

import yaml

from research.errors import ConfigError


def load_yaml(path: Path) -> object:
    try:
        loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    return loaded


def as_mapping(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(f"{label} must be a mapping")
    out: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ConfigError(f"{label} has a non-string key")
        out[key] = item
    return out


def as_list(value: object, *, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ConfigError(f"{label} must be a list")
    return list(value)


def as_str(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label} must be a non-empty string")
    return value


def as_bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{label} must be a boolean")
    return value


def as_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{label} must be an integer")
    return value


def as_float(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{label} must be a number")
    return float(value)


def as_str_list(value: object, *, label: str) -> tuple[str, ...]:
    items = as_list(value, label=label)
    out: list[str] = []
    for index, item in enumerate(items):
        out.append(as_str(item, label=f"{label}[{index}]"))
    return tuple(out)


def optional_str(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    return as_str(value, label=label)
