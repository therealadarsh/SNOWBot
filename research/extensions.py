"""Version registry, drift check, archiver, and stability evaluator."""

from __future__ import annotations

EXTENSIONS: tuple[str, ...] = (
    "version_registry",
    "drift_check",
    "archiver",
    "stability_evaluator",
)

_MODULES = {
    "version_registry": "research.versioning",
    "drift_check": "research.drift",
    "archiver": "research.archive",
    "stability_evaluator": "research.stability",
}


def registered_extensions() -> tuple[str, ...]:
    return EXTENSIONS


def require_extension(name: str) -> str:
    try:
        return _MODULES[name]
    except KeyError:
        raise KeyError(name) from None
