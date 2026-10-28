"""Frozen research version pins.

Results from different versions are never pooled. After a pre-registration
freeze, a change to the oracle, tasks, scanner commit, or conditions requires
a new MAJOR.MINOR.PATCH version.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from research.errors import ConfigError, VersionBumpRequired
from research.hashutil import canonical_json, sha256_file
from research.jsonio import load_json_object
from research.yamlio import as_mapping, as_str, load_yaml

POOLING_RULE = "results from different versions are never pooled"

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_LIVE_PATHS = (
    ("task_suite_sha256", "task_suite"),
    ("oracle_config_sha256", "oracle_config"),
    ("conditions_sha256", "conditions"),
)
_SNAPSHOT_PATHS = (
    ("task_suite_sha256", "task_suite_snapshot"),
    ("oracle_config_sha256", "oracle_config_snapshot"),
    ("conditions_sha256", "conditions_snapshot"),
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_semver(value: str) -> tuple[int, int, int]:
    match = _SEMVER.fullmatch(value)
    if match is None:
        raise ConfigError(f"version must be MAJOR.MINOR.PATCH, got {value!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def version_file(root: Path) -> Path:
    return root / "research" / "versions" / "current" / "VERSION"


def load_version(path: Path) -> dict[str, object]:
    return load_json_object(path)


def current_document(root: Path | None = None) -> dict[str, object]:
    base = repo_root() if root is None else root
    return load_version(version_file(base))


def version_of(document: Mapping[str, object]) -> str:
    text = as_str(document.get("version"), label="version")
    parse_semver(text)
    return text


def current_version_string(root: Path | None = None) -> str:
    return version_of(current_document(root))


def pins_of(document: Mapping[str, object]) -> dict[str, object]:
    return as_mapping(document.get("pins"), label="pins")


def paths_of(document: Mapping[str, object]) -> dict[str, str]:
    raw = as_mapping(document.get("paths"), label="paths")
    paths: dict[str, str] = {}
    for key, value in raw.items():
        paths[key] = as_str(value, label=f"paths.{key}")
    return paths


def require_version_bump(previous: Mapping[str, object], proposed: Mapping[str, object]) -> None:
    """Reject a pin change that keeps the same or an older version."""
    old_version = parse_semver(version_of(previous))
    new_version = parse_semver(version_of(proposed))
    old_pins = canonical_json(pins_of(previous))
    new_pins = canonical_json(pins_of(proposed))
    if new_version < old_version:
        raise VersionBumpRequired("version went backwards")
    if old_pins != new_pins and new_version <= old_version:
        raise VersionBumpRequired(
            "pin change without a version bump; oracle, tasks, scanner commit, "
            "and conditions require a new MAJOR.MINOR.PATCH"
        )


def verify_freeze(root: Path, *, version_path: Path | None = None) -> None:
    """Live files and snapshots must match the pins in VERSION."""
    path = version_file(root) if version_path is None else version_path
    document = load_version(path)
    version = version_of(document)
    pins = pins_of(document)
    paths = paths_of(document)
    for pin_key, path_key in (*_LIVE_PATHS, *_SNAPSHOT_PATHS):
        if path_key not in paths:
            raise ConfigError(f"paths.{path_key} is required")
        expected = as_str(pins.get(pin_key), label=f"pins.{pin_key}")
        rel = paths[path_key]
        actual = sha256_file(_contained(root, rel))
        if actual != expected:
            raise VersionBumpRequired(
                f"{rel} hash {actual} does not match pins.{pin_key} at version {version}; "
                "a pin change requires a version bump"
            )
    _scanner_matches_oracle(root, pins, paths)


def _scanner_matches_oracle(
    root: Path,
    pins: Mapping[str, object],
    paths: Mapping[str, str],
) -> None:
    if "oracle_config" not in paths:
        raise ConfigError("paths.oracle_config is required")
    raw = as_mapping(load_yaml(_contained(root, paths["oracle_config"])), label="oracle")
    recorded = as_str(raw.get("scanner_commit"), label="oracle.scanner_commit")
    pinned = as_str(pins.get("scanner_commit"), label="pins.scanner_commit")
    if recorded != pinned:
        raise VersionBumpRequired(
            "scanner commit pin does not match the frozen oracle config; "
            "a pin change requires a version bump"
        )


def _contained(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ConfigError(f"{relative} escapes the repository")
    resolved_root = root.resolve()
    resolved = (root / path).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ConfigError(f"{relative} escapes the repository")
    if not resolved.is_file():
        raise ConfigError(f"missing frozen file {relative}")
    return resolved
