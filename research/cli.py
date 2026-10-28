"""Command line for the research harness.

``run`` does not call model providers. Without ``--dry-run`` or
``--i-understand-the-budget`` it exits before any cell. A satisfied budget and
the acknowledgement still do not execute Claude Code, Codex, or Inspect.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from research.archive import archive_version, preserve_current_version
from research.budget import RunBudget, budget_allows
from research.conditions import load_conditions
from research.drift import check_drift
from research.errors import (
    BudgetError,
    ConfigError,
    DockerUnavailable,
    HashMismatch,
    ImmutableRecordError,
    ResearchError,
)
from research.jsonio import load_json_object
from research.ledger import evaluate_caps, load_ledger, spend_allowed
from research.manifest import build_manifest, load_manifest, write_manifest
from research.oracle import load_oracle_rules
from research.runner import noop_agent, run_cell
from research.stability import evaluate_stability
from research.status import load_status
from research.tasks.build import load_catalog
from research.versioning import current_version_string, verify_freeze
from research.yamlio import as_mapping, as_str, load_yaml

_LIVE_AGENTS = frozenset({"claude-code", "codex", "inspect"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="research")
    sub = parser.add_subparsers(dest="command", required=True)

    manifest = sub.add_parser("manifest", help="hash the cell matrix before any run")
    manifest.add_argument("--config", required=True, type=Path)
    manifest.add_argument("--out", type=Path)

    run = sub.add_parser("run", help="plan or execute cells without calling providers")
    run.add_argument("--manifest", required=True, type=Path)
    run.add_argument("--budget-usd", required=True, type=float)
    run.add_argument("--run-dir", type=Path, default=Path("research-runs"))
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--i-understand-the-budget", action="store_true")

    extract = sub.add_parser("extract", help="aggregate run records")
    extract.add_argument("--run-dir", required=True, type=Path)
    extract.add_argument("--out-dir", type=Path)

    version = sub.add_parser("version", help="show or check the frozen research version")
    version.add_argument("--root", type=Path, default=Path("."))
    version.add_argument("--check", action="store_true")

    drift = sub.add_parser("drift-check", help="compare pins to upstream sources")
    drift.add_argument("--root", type=Path, default=Path("."))
    drift.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    drift.add_argument("--ledger", type=Path)
    drift.add_argument("--status", type=Path)
    drift.add_argument("--timeout", type=float, default=5.0)
    drift.add_argument("--retired-model", action="append", default=[])
    drift.add_argument("--oracle-self-check", action=argparse.BooleanOptionalAction, default=True)
    drift_infra = drift.add_mutually_exclusive_group()
    drift_infra.add_argument("--infrastructure-failure", action="store_true")
    drift_infra.add_argument("--infrastructure-ok", action="store_true")
    drift_validate = drift.add_mutually_exclusive_group()
    drift_validate.add_argument("--validate-failed", action="store_true")
    drift_validate.add_argument("--validate-passed", action="store_true")

    stability = sub.add_parser("stability", help="evaluate recorded stability inputs")
    stability.add_argument("--input", required=True, type=Path)

    caps = sub.add_parser("caps", help="evaluate spend caps without writing status")
    caps.add_argument("--ledger", required=True, type=Path)
    caps.add_argument("--status", type=Path)
    caps.add_argument("--proposed-usd", type=float)
    caps.add_argument("--today", type=date.fromisoformat)
    caps.add_argument("--human-confirmed", action="store_true")

    archive = sub.add_parser("archive", help="archive a superseded version without pushing a tag")
    archive.add_argument("--root", type=Path, default=Path("."))
    archive.add_argument("--old-version", required=True)
    archive.add_argument("--new-version", required=True)
    archive.add_argument("--why", required=True)
    archive.add_argument("--fix-pr", required=True)
    archive.add_argument("--on", type=date.fromisoformat)
    archive.add_argument("--into", default="HEAD")
    archive.add_argument("--preserve-current", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "manifest":
            return _manifest(args.config, args.out)
        if args.command == "run":
            return _run(args)
        if args.command == "extract":
            return _extract(args.run_dir, args.out_dir)
        if args.command == "version":
            return _version(args.root, args.check)
        if args.command == "drift-check":
            return _drift(args)
        if args.command == "stability":
            return _stability(args.input)
        if args.command == "caps":
            return _caps(args)
        if args.command == "archive":
            return _archive(args)
    except (ResearchError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        if isinstance(exc, HashMismatch | ImmutableRecordError):
            return 4
        if isinstance(exc, BudgetError | ConfigError):
            return 2
        if isinstance(exc, DockerUnavailable):
            return 3
        return 1
    print(f"unknown command {args.command}", file=sys.stderr)
    return 2


def _manifest(config: Path, dest: Path | None) -> int:
    payload = build_manifest(config)
    if dest is None:
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        write_manifest(payload, dest)
        print(f"wrote {dest} {payload['manifest_sha256']}")
    return 0


def _run(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    count = _as_int(manifest.get("cell_count"), "cell_count")
    budget = as_mapping(manifest.get("budget"), label="budget")
    per_run = _as_float(budget.get("per_run_usd"), "per_run_usd")
    if args.budget_usd < 0:
        print("budget must be non-negative", file=sys.stderr)
        return 2
    if not budget_allows(count, per_run, args.budget_usd):
        nominal = count * per_run
        print(
            f"refusing to start: nominal cost {nominal:.2f} USD exceeds "
            f"--budget-usd {args.budget_usd:.2f}; no provider was called",
            file=sys.stderr,
        )
        return 2
    cells = _cells(manifest.get("cells"))
    if args.dry_run:
        _write_plan(args.run_dir, manifest, cells, args.budget_usd)
        print(f"dry-run planned {len(cells)} cells; provider_calls=0")
        return 0
    if not args.i_understand_the_budget:
        print(
            "refusing to start without --dry-run or --i-understand-the-budget; "
            "no provider was called",
            file=sys.stderr,
        )
        return 2
    agents = {str(cell["agent"]) for cell in cells}
    live = sorted(agent for agent in agents if agent in _LIVE_AGENTS)
    if live or any(agent != "local-noop" for agent in agents):
        names = ", ".join(sorted(agents))
        print(
            f"refusing to execute agent {names}; live CLIs are not run in this build "
            "and no provider was called",
            file=sys.stderr,
        )
        return 3
    _execute_noop(manifest, cells, args.run_dir, args.budget_usd)
    print(f"wrote {len(cells)} local-noop records; provider_calls=0")
    return 0


def _extract(run_dir: Path, out_dir: Path | None) -> int:
    from research.extract import extract_run

    paths = extract_run(run_dir, out_dir=out_dir)
    for key in ("results", "summary", "tables", "label_sample"):
        print(f"{key}: {paths[key]}")
    return 0


def _execute_noop(
    manifest: dict[str, object],
    cells: list[dict[str, str | int | float | bool]],
    run_dir: Path,
    budget_usd: float,
) -> None:
    root = Path(str(manifest["repo_root"]))
    config = Path(str(manifest["config_path"]))
    raw = as_mapping(load_yaml(config), label=str(config))
    catalog = load_catalog(_resolve(root, as_str(raw.get("catalog"), label="catalog")))
    loaded = load_conditions(_resolve(root, as_str(raw.get("conditions"), label="conditions")))
    rules = load_oracle_rules(_resolve(root, as_str(raw.get("oracle_rules"), label="oracle_rules")))
    if catalog.digest != manifest.get("catalog_sha256"):
        raise HashMismatch("catalog hash does not match the manifest")
    if rules.digest != manifest.get("oracle_rules_sha256"):
        raise HashMismatch("oracle rules hash does not match the manifest")
    budget_body = as_mapping(manifest.get("budget"), label="budget")
    per_run = _as_float(budget_body.get("per_run_usd"), "per_run")
    budget = RunBudget(total_usd=budget_usd, per_run_usd=per_run)
    limits = as_mapping(manifest.get("limits"), label="limits")
    timeout_s = _as_int(limits.get("timeout_s"), "timeout_s")
    max_turns = _as_int(limits.get("max_turns"), "max_turns")
    digest = str(manifest["manifest_sha256"])
    for cell in cells:
        task = catalog.by_id(str(cell["task_id"]))
        condition = loaded.by_id(str(cell["condition_id"]))
        run_cell(
            task=task,
            condition=condition,
            loaded=loaded,
            rules=rules,
            run_dir=run_dir,
            cell_id=str(cell["cell_id"]),
            model=str(cell["model"]),
            seed=_as_int(cell["seed"], "seed"),
            agent_name="local-noop",
            budget=budget,
            timeout_s=timeout_s,
            max_turns=max_turns,
            manifest_sha256=digest,
            agent=noop_agent,
        )


def _write_plan(
    run_dir: Path,
    manifest: dict[str, object],
    cells: list[dict[str, str | int | float | bool]],
    budget_usd: float,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    budget = as_mapping(manifest.get("budget"), label="budget")
    plan = {
        "dry_run": True,
        "provider_calls": 0,
        "manifest_sha256": manifest.get("manifest_sha256"),
        "budget_usd": budget_usd,
        "nominal_usd": budget.get("nominal_usd"),
        "cell_count": len(cells),
        "cells": [cell["cell_id"] for cell in cells],
    }
    (run_dir / "plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _cells(value: object) -> list[dict[str, str | int | float | bool]]:
    if not isinstance(value, list):
        raise ConfigError("manifest cells must be a list")
    cells: list[dict[str, str | int | float | bool]] = []
    for index, item in enumerate(value):
        body = as_mapping(item, label=f"cells[{index}]")
        cell: dict[str, str | int | float | bool] = {}
        for key in ("cell_id", "task_id", "condition_id", "model", "agent"):
            cell[key] = as_str(body.get(key), label=f"cells[{index}].{key}")
        seed = body.get("seed")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ConfigError(f"cells[{index}].seed must be an integer")
        cell["seed"] = seed
        cells.append(cell)
    return cells


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _as_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{label} must be an integer")
    return value


def _as_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{label} must be a number")
    return float(value)


def _version(root: Path, check: bool) -> int:
    if check:
        verify_freeze(root)
    print(current_version_string(root))
    return 0


def _drift(args: argparse.Namespace) -> int:
    if args.infrastructure_failure:
        infra: bool | None = True
    elif args.infrastructure_ok:
        infra = False
    else:
        infra = None
    if args.validate_failed:
        validate_failed: bool | None = True
    elif args.validate_passed:
        validate_failed = False
    else:
        validate_failed = None
    report = check_drift(
        args.root,
        timeout=args.timeout,
        ledger_path=args.ledger,
        status_path=args.status,
        infrastructure_failure_flag=infra,
        retired_model_ids=list(args.retired_model),
        validate_failed=validate_failed,
        run_oracle_self_check=args.oracle_self_check,
    )
    payload = report.to_json()
    payload["dry_run"] = bool(args.dry_run)
    payload["applied"] = False
    payload["opened_pr"] = False
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if not args.dry_run:
        print(
            "dry-run is off, but this command still does not push, merge, or open a pull request",
            file=sys.stderr,
        )
    return 0


def _stability(path: Path) -> int:
    payload = load_json_object(path)
    report = evaluate_stability(payload)
    sys.stdout.write(json.dumps(report.to_json(), indent=2, sort_keys=True) + "\n")
    return 0


def _caps(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    status = load_status(args.status) if args.status is not None else None
    version = str(status["version"]) if status is not None else current_version_string()
    result = evaluate_caps(
        ledger,
        version=version,
        today=date.today() if args.today is None else args.today,
        proposed_usd=args.proposed_usd,
        status=status,
    )
    allowed = spend_allowed(result, human_confirmed=bool(args.human_confirmed))
    body = {"applied": False, "spend_allowed": allowed, "status": result}
    sys.stdout.write(json.dumps(body, indent=2, sort_keys=True) + "\n")
    return 0


def _archive(args: argparse.Namespace) -> int:
    if args.preserve_current:
        preserve_current_version(args.root)
    result = archive_version(
        args.root,
        old_version=args.old_version,
        new_version=args.new_version,
        why=args.why,
        fix_pr=args.fix_pr,
        on=args.on,
        into=args.into,
    )
    print(f"archived {result.destination} idempotent={result.idempotent}")
    return 0
