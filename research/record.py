"""Immutable per-cell records."""

from __future__ import annotations

import json
import os
from pathlib import Path

from research.errors import HashMismatch, ImmutableRecordError
from research.hashutil import canonical_json, sha256_bytes


def write_record(directory: Path, payload: dict[str, object]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "record.json"
    digest_path = directory / "record.json.sha256"
    if path.exists() or digest_path.exists():
        raise ImmutableRecordError(f"record already exists at {path}")
    text = canonical_json(payload) + "\n"
    data = text.encode("utf-8")
    path.write_bytes(data)
    digest = sha256_bytes(data)
    digest_path.write_text(digest + "\n", encoding="utf-8")
    path.chmod(0o444)
    digest_path.chmod(0o444)
    return path


def read_record(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    digest_path = path.with_name(path.name + ".sha256")
    if not digest_path.is_file():
        raise HashMismatch(f"missing record hash for {path}")
    expected = digest_path.read_text(encoding="utf-8").strip()
    actual = sha256_bytes(data)
    if actual != expected:
        raise HashMismatch(f"record hash mismatch for {path}")
    loaded = json.loads(data.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise HashMismatch(f"record {path} is not an object")
    return {str(key): value for key, value in loaded.items()}


def append_jsonl(path: Path, payload: dict[str, object]) -> None:
    """Append one JSON object and fsync so a later block cannot hide it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = canonical_json(payload) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
