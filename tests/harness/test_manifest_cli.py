"""Manifest hashing and the run command's refusal path."""

from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from research.cli import main
from research.errors import ConfigError, HashMismatch
from research.manifest import build_manifest, load_manifest, probe_version, write_manifest
from research.record import read_record

ROOT = Path(__file__).resolve().parents[2]


def _tiny(tmp_path: Path, agent: str = "local-noop") -> Path:
    config = tmp_path / "matrix.yaml"
    config.write_text(
        f"""
schema_version: 1
catalog: {ROOT / "research" / "tasks" / "catalog.yaml"}
conditions: {ROOT / "research" / "conditions.yaml"}
oracle_rules: {ROOT / "research" / "configs" / "oracle_rules.yaml"}
tasks: [fix-operator]
condition_ids: [A0]
models:
  - id: local
    provider: none
    agent: {agent}
seeds: [1]
budget:
  total_usd: 50
  per_run_usd: 1.5
limits:
  timeout_s: 30
  max_turns: 4
image:
  ref: null
  digest: null
""",
        encoding="utf-8",
    )
    return config


def test_pilot_manifest_is_over_budget(tmp_path: Path) -> None:
    payload = build_manifest(ROOT / "research" / "configs" / "pilot.yaml")
    assert payload["cell_count"] == 180
    assert payload["research_version"] == "0.1.0"
    budget = payload["budget"]
    assert isinstance(budget, dict)
    assert budget["nominal_usd"] == 270
    assert budget["budget_satisfied"] is False
    assert budget["total_usd"] == 50
    assert budget["per_run_usd"] == 1.5
    first = build_manifest(ROOT / "research" / "configs" / "pilot.yaml")
    assert first["manifest_sha256"] == payload["manifest_sha256"]
    dest = tmp_path / "pilot.json"
    write_manifest(payload, dest)
    loaded = load_manifest(dest)
    assert loaded["manifest_sha256"] == payload["manifest_sha256"]
    dest.write_text(dest.read_text(encoding="utf-8").replace("haiku", "other"), encoding="utf-8")
    with pytest.raises(HashMismatch):
        load_manifest(dest)


def test_unknown_task_rejected(tmp_path: Path) -> None:
    config = _tiny(tmp_path)
    text = config.read_text(encoding="utf-8").replace("fix-operator", "missing-task")
    config.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        build_manifest(config)


def test_cli_dry_run_and_refusals(tmp_path: Path) -> None:
    pilot = tmp_path / "pilot.json"
    assert (
        main(
            [
                "manifest",
                "--config",
                str(ROOT / "research" / "configs" / "pilot.yaml"),
                "--out",
                str(pilot),
            ]
        )
        == 0
    )
    dry = tmp_path / "dry"
    code = main(
        ["run", "--manifest", str(pilot), "--budget-usd", "50", "--dry-run", "--run-dir", str(dry)]
    )
    assert code == 2
    assert not (tmp_path / "dry" / "plan.json").exists()

    tiny_manifest = tmp_path / "tiny.json"
    assert main(["manifest", "--config", str(_tiny(tmp_path)), "--out", str(tiny_manifest)]) == 0
    run_dir = tmp_path / "plan"
    assert (
        main(
            [
                "run",
                "--manifest",
                str(tiny_manifest),
                "--budget-usd",
                "50",
                "--dry-run",
                "--run-dir",
                str(run_dir),
            ]
        )
        == 0
    )
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    assert plan["provider_calls"] == 0
    assert plan["cell_count"] == 1
    refused = main(
        [
            "run",
            "--manifest",
            str(tiny_manifest),
            "--budget-usd",
            "50",
            "--run-dir",
            str(tmp_path / "nope"),
        ]
    )
    assert refused == 2

    live = tmp_path / "live.json"
    live_config = _tiny(tmp_path, agent="claude-code")
    assert main(["manifest", "--config", str(live_config), "--out", str(live)]) == 0
    assert (
        main(
            [
                "run",
                "--manifest",
                str(live),
                "--budget-usd",
                "50",
                "--i-understand-the-budget",
                "--run-dir",
                str(tmp_path / "live-run"),
            ]
        )
        == 3
    )

    noop_dir = tmp_path / "noop"
    assert (
        main(
            [
                "run",
                "--manifest",
                str(tiny_manifest),
                "--budget-usd",
                "50",
                "--i-understand-the-budget",
                "--run-dir",
                str(noop_dir),
            ]
        )
        == 0
    )
    records = list(noop_dir.rglob("record.json"))
    assert len(records) == 1
    record = read_record(records[0])
    assert record["provider_calls"] == 0
    assert record["agent"] == "local-noop"
    assert main(["extract", "--run-dir", str(noop_dir), "--out-dir", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "results.jsonl").is_file()


def test_probe_version_and_bad_yaml(tmp_path: Path) -> None:
    from research.yamlio import (
        as_bool,
        as_float,
        as_int,
        as_list,
        as_mapping,
        as_str,
        as_str_list,
        load_yaml,
        optional_str,
    )

    assert probe_version("python3") != "unavailable"
    assert probe_version("not-a-real-binary-xyz") == "unavailable"
    assert optional_str(None, label="x") is None
    bad = tmp_path / "bad.yaml"
    bad.write_text(":\n  - [", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_yaml(bad)
    with pytest.raises(ConfigError):
        as_mapping([], label="x")
    with pytest.raises(ConfigError):
        as_mapping({1: "a"}, label="x")
    with pytest.raises(ConfigError):
        as_list("nope", label="x")
    with pytest.raises(ConfigError):
        as_str("  ", label="x")
    with pytest.raises(ConfigError):
        as_bool("yes", label="x")
    with pytest.raises(ConfigError):
        as_int(True, label="x")
    with pytest.raises(ConfigError):
        as_float("no", label="x")
    with pytest.raises(ConfigError):
        as_str_list(["ok", 1], label="x")


def test_corrupt_manifest_exits_4(tmp_path: Path) -> None:
    dest = tmp_path / "tiny.json"
    assert main(["manifest", "--config", str(_tiny(tmp_path)), "--out", str(dest)]) == 0
    text = dest.read_text(encoding="utf-8").replace("local-noop", "other")
    dest.write_text(text, encoding="utf-8")
    code = main(
        [
            "run",
            "--manifest",
            str(dest),
            "--budget-usd",
            "50",
            "--dry-run",
            "--run-dir",
            str(tmp_path / "x"),
        ]
    )
    assert code == 4
    again = tmp_path / "again"
    again.mkdir()
    fresh = tmp_path / "fresh.json"
    assert main(["manifest", "--config", str(_tiny(again)), "--out", str(fresh)]) == 0
    negative = main(
        [
            "run",
            "--manifest",
            str(fresh),
            "--budget-usd",
            "-1",
            "--dry-run",
            "--run-dir",
            str(tmp_path / "neg"),
        ]
    )
    assert negative == 2


def test_module_entrypoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "manifest.json"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "research",
            "manifest",
            "--config",
            str(ROOT / "research" / "configs" / "pilot.yaml"),
            "--out",
            str(dest),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert dest.is_file()
    help_proc = subprocess.run(
        [sys.executable, "-m", "research"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_proc.returncode == 2
    dest = tmp_path / "from-dunder.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "research",
            "manifest",
            "--config",
            str(ROOT / "research" / "configs" / "pilot.yaml"),
            "--out",
            str(dest),
        ],
    )
    with pytest.raises(SystemExit) as caught:
        runpy.run_module("research", run_name="__main__")
    assert caught.value.code == 0
    assert dest.is_file()
