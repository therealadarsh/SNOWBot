"""Hashed cell manifest built before any run."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from research.budget import budget_allows, nominal_cost
from research.conditions import load_conditions
from research.errors import ConfigError, HashMismatch
from research.hashutil import canonical_json, sha256_canonical, sha256_file
from research.oracle import load_oracle_rules
from research.tasks.build import load_catalog
from research.versioning import current_version_string
from research.yamlio import as_float, as_int, as_list, as_mapping, as_str, load_yaml

_HASH_FIELD = "manifest_sha256"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_manifest(config_path: Path, *, root: Path | None = None) -> dict[str, object]:
    base = root or repo_root()
    raw = as_mapping(load_yaml(config_path), label=str(config_path))
    version = as_int(raw.get("schema_version"), label="matrix.schema_version")
    if version != 1:
        raise ConfigError("matrix schema_version must be 1")
    catalog = load_catalog(_resolve(base, as_str(raw.get("catalog"), label="catalog")))
    conditions = load_conditions(_resolve(base, as_str(raw.get("conditions"), label="conditions")))
    rules = load_oracle_rules(_resolve(base, as_str(raw.get("oracle_rules"), label="oracle_rules")))
    task_ids = _task_ids(raw.get("tasks"), catalog.ids())
    condition_ids = [
        as_str(item, label="condition_ids")
        for item in as_list(raw.get("condition_ids"), label="condition_ids")
    ]
    if not condition_ids:
        raise ConfigError("condition_ids must not be empty")
    models = _models(raw.get("models"))
    seeds = [as_int(item, label="seeds") for item in as_list(raw.get("seeds"), label="seeds")]
    if not seeds:
        raise ConfigError("seeds must not be empty")
    budget_raw = as_mapping(raw.get("budget"), label="budget")
    total = as_float(budget_raw.get("total_usd"), label="budget.total_usd")
    per_run = as_float(budget_raw.get("per_run_usd"), label="budget.per_run_usd")
    limits_raw = as_mapping(raw.get("limits"), label="limits")
    timeout_s = as_int(limits_raw.get("timeout_s"), label="limits.timeout_s")
    max_turns = as_int(limits_raw.get("max_turns"), label="limits.max_turns")
    if timeout_s <= 0 or max_turns <= 0:
        raise ConfigError("timeout_s and max_turns must be positive")
    image = _image(raw.get("image"))
    cells: list[dict[str, object]] = []
    for task_id in task_ids:
        task = catalog.by_id(task_id)
        for condition_id in condition_ids:
            condition = conditions.by_id(condition_id)
            for model in models:
                for seed in seeds:
                    cells.append(
                        {
                            "cell_id": f"{task.id}__{condition.id}__{model['id']}__s{seed}",
                            "task_id": task.id,
                            "task_sha256": task.content_sha256,
                            "condition_id": condition.id,
                            "arm": condition.arm.id,
                            "escalation": condition.escalation,
                            "scanner_feedback": condition.scanner_feedback,
                            "model": model["id"],
                            "provider": model["provider"],
                            "agent": model["agent"],
                            "seed": seed,
                            "timeout_s": timeout_s,
                            "max_turns": max_turns,
                            "per_run_usd": per_run,
                        }
                    )
    nominal = nominal_cost(len(cells), per_run)
    body: dict[str, object] = {
        "manifest_version": 1,
        "research_version": current_version_string(base),
        "repo_root": str(base.resolve()),
        "config_path": str(config_path.resolve()),
        "config_sha256": sha256_file(config_path),
        "catalog_sha256": catalog.digest,
        "conditions_sha256": sha256_file(conditions_path_of(raw, base)),
        "oracle_rules_sha256": rules.digest,
        "scanner_commit": rules.scanner_commit,
        "image": image,
        "cli_versions": probe_cli_versions(),
        "budget": {
            "total_usd": total,
            "per_run_usd": per_run,
            "nominal_usd": nominal,
            "budget_satisfied": budget_allows(len(cells), per_run, total),
        },
        "limits": {"timeout_s": timeout_s, "max_turns": max_turns},
        "cell_count": len(cells),
        "cells": cells,
    }
    body[_HASH_FIELD] = sha256_canonical({key: value for key, value in body.items()})
    return body


def conditions_path_of(raw: dict[str, object], base: Path) -> Path:
    return _resolve(base, as_str(raw.get("conditions"), label="conditions"))


def write_manifest(payload: dict[str, object], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_manifest(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ConfigError(f"{path} is not a manifest object")
    payload = {str(key): value for key, value in loaded.items()}
    expected = payload.get(_HASH_FIELD)
    if not isinstance(expected, str):
        raise HashMismatch("manifest is missing manifest_sha256")
    actual = manifest_digest(payload)
    if actual != expected:
        raise HashMismatch(f"manifest hash mismatch: {actual} != {expected}")
    return payload


def manifest_digest(payload: dict[str, object]) -> str:
    body = {key: value for key, value in payload.items() if key != _HASH_FIELD}
    return sha256_canonical(body)


def render_manifest(payload: dict[str, object]) -> str:
    return canonical_json(payload)


def probe_cli_versions() -> dict[str, str]:
    return {
        "claude": probe_version("claude"),
        "codex": probe_version("codex"),
        "inspect": probe_version("inspect"),
        "docker": probe_version("docker"),
    }


def probe_version(program: str) -> str:
    if shutil.which(program) is None:
        return "unavailable"
    try:
        proc = subprocess.run(
            [program, "--version"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    text = (proc.stdout or proc.stderr).strip()
    if not text:
        return "unavailable"
    return text.splitlines()[0]


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _task_ids(value: object, catalog_ids: tuple[str, ...]) -> list[str]:
    if value is None:
        return list(catalog_ids)
    ids = [as_str(item, label="tasks") for item in as_list(value, label="tasks")]
    if not ids:
        raise ConfigError("tasks must not be empty when set")
    missing = [task_id for task_id in ids if task_id not in catalog_ids]
    if missing:
        raise ConfigError(f"unknown tasks: {', '.join(missing)}")
    return ids


def _models(value: object) -> list[dict[str, str]]:
    models: list[dict[str, str]] = []
    for index, item in enumerate(as_list(value, label="models")):
        body = as_mapping(item, label=f"models[{index}]")
        models.append(
            {
                "id": as_str(body.get("id"), label=f"models[{index}].id"),
                "provider": as_str(body.get("provider"), label=f"models[{index}].provider"),
                "agent": as_str(body.get("agent"), label=f"models[{index}].agent"),
            }
        )
    if not models:
        raise ConfigError("models must not be empty")
    return models


def _image(value: object) -> dict[str, object]:
    raw = as_mapping(value, label="image")
    ref = raw.get("ref")
    digest = raw.get("digest")
    ref_text = ref if isinstance(ref, str) and ref else None
    digest_text = digest if isinstance(digest, str) and digest else None
    status = "pinned" if digest_text else "unavailable"
    return {"ref": ref_text, "digest": digest_text, "digest_status": status}
