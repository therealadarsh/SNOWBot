"""Canonical hashing for frozen configs and manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(payload: object) -> str:
    """Stable JSON: sorted keys, no extra whitespace, UTF-8."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_canonical(payload: object) -> str:
    return sha256_bytes(canonical_json(payload).encode("utf-8"))
