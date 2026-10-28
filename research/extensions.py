"""Extension points left for later pull requests.

Not implemented here: version registry, drift check, archiver, and the
stability-evaluator loop.
"""

from __future__ import annotations

from research.errors import ExtensionNotInThisPullRequest

EXTENSIONS: tuple[str, ...] = (
    "version_registry",
    "drift_check",
    "archiver",
    "stability_evaluator",
)


def registered_extensions() -> tuple[str, ...]:
    return EXTENSIONS


def require_extension(name: str) -> None:
    if name in EXTENSIONS:
        raise ExtensionNotInThisPullRequest(
            f"{name} is a registered extension point and is not implemented in this pull request"
        )
    raise KeyError(name)
