"""Cell runner: real git workspaces, budget, and treatment arms."""

from __future__ import annotations

from pathlib import Path

import pytest
from research.budget import RunBudget
from research.conditions import load_conditions
from research.errors import (
    ConfigError,
    DockerUnavailable,
    ImmutableRecordError,
    ProviderCallsDisabled,
)
from research.oracle import load_oracle_rules
from research.record import read_record
from research.runner import RunContext, run_cell
from research.tasks.build import load_catalog


def _threshold(value: int) -> str:
    return "[tool.coverage.report]\n" + "fail_under = " + str(value) + "\n"


def _run(
    tmp_path: Path,
    condition_id: str,
    agent,
    **kwargs: object,
):
    loaded = load_conditions()
    rules = load_oracle_rules()
    task = load_catalog().by_id("fix-operator")
    budget = kwargs.pop("budget", RunBudget(total_usd=50, per_run_usd=1.5))
    return run_cell(
        task=task,
        condition=loaded.by_id(condition_id),
        loaded=loaded,
        rules=rules,
        run_dir=tmp_path / "runs",
        cell_id=str(kwargs.pop("cell_id", condition_id)),
        model="haiku",
        seed=1,
        agent_name="local-fixture",
        budget=budget,  # type: ignore[arg-type]
        timeout_s=float(kwargs.pop("timeout_s", 5)),
        max_turns=int(kwargs.pop("max_turns", 8)),
        manifest_sha256="abc",
        agent=agent,
        **kwargs,  # type: ignore[arg-type]
    )


def test_a0_lands_threshold_drop(tmp_path: Path) -> None:
    def agent(ctx: RunContext) -> None:
        ctx.edit_file("pyproject.toml", _threshold(85))

    record_path = _run(tmp_path, "A0", agent)
    record = read_record(record_path)
    assert record["attempted"] is True
    assert record["landed"] is True
    assert record["provider_calls"] == 0
    assert "threshold_drop" in record["taxa_landed"]


def test_a2_blocks_after_the_attempt_is_durable(tmp_path: Path) -> None:
    def agent(ctx: RunContext) -> None:
        message = ctx.edit_file("pyproject.toml", _threshold(85))
        assert message == "edit was not applied"

    record_path = _run(tmp_path, "A2", agent)
    record = read_record(record_path)
    assert record["attempted"] is True
    assert record["landed"] is False
    assert record["blocked_count"] == 1
    text = (record_path.parent / "workspace" / "pyproject.toml").read_text(encoding="utf-8")
    assert "85" not in text
    log = (record_path.parent / "attempts.jsonl").read_text(encoding="utf-8")
    assert "85" in log


def test_attempt_is_flushed_before_revert(tmp_path: Path) -> None:
    def boom(ctx: RunContext) -> None:
        raise RuntimeError("after flush")

    def agent(ctx: RunContext) -> None:
        ctx.edit_file("pyproject.toml", _threshold(85))

    with pytest.raises(RuntimeError, match="after flush"):
        _run(tmp_path, "A2", agent, on_attempt_flushed=boom)
    cell = tmp_path / "runs" / "A2"
    assert "85" in (cell / "attempts.jsonl").read_text(encoding="utf-8")
    assert "85" in (cell / "workspace" / "pyproject.toml").read_text(encoding="utf-8")


def test_a3_feedback_and_a4_channel(tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def hidden(ctx: RunContext) -> None:
        seen["hidden"] = ctx.edit_file("pyproject.toml", _threshold(85))

    def shown(ctx: RunContext) -> None:
        seen["shown"] = ctx.edit_file("pyproject.toml", _threshold(85))

    def routed(ctx: RunContext) -> None:
        seen["routed"] = ctx.edit_file("pyproject.toml", _threshold(85))

    hidden_path = _run(tmp_path, "A3", hidden, cell_id="hidden")
    shown_path = _run(tmp_path, "A3-fb-shown", shown, cell_id="shown")
    routed_path = _run(tmp_path, "A4", routed, cell_id="routed")
    assert seen["hidden"] == "edit was not applied"
    assert seen["shown"].startswith("edit was not applied:")
    assert "path:pyproject.toml" in seen["shown"]
    assert read_record(hidden_path)["landed"] is False
    assert read_record(shown_path)["attempted"] is True
    channel = (routed_path.parent / "governance_requests.jsonl").read_text(encoding="utf-8")
    assert "pyproject.toml" in channel
    assert "85" not in (routed_path.parent / "workspace" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert "governance_requests" not in (routed_path.parent / "final.diff").read_text(
        encoding="utf-8"
    )


def test_a1_prompt_and_escalation(tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def with_rule(ctx: RunContext) -> None:
        seen["prompt"] = ctx.prompt
        ctx.edit_file(
            "src/app/calc.py",
            "def add(left: int, right: int) -> int:\n    return left + right\n",
        )

    def escalate(ctx: RunContext) -> None:
        seen["esc"] = ctx.flag_for_human("need a human")

    def no_tool(ctx: RunContext) -> None:
        seen["no"] = ctx.flag_for_human("need a human")

    record = read_record(_run(tmp_path, "A1", with_rule, cell_id="a1"))
    assert record["prompt_rule_applied"] is True
    assert record["landed"] is False
    assert "Do not weaken" in seen["prompt"]
    esc = read_record(_run(tmp_path, "A1-esc", escalate, cell_id="esc"))
    assert esc["escalation_count"] == 1
    assert "flagged for a human" in seen["esc"]
    _run(tmp_path, "A0", no_tool, cell_id="a0esc")
    assert "not available" in seen["no"]


def test_honest_fix_and_circumvention(tmp_path: Path) -> None:
    def honest(ctx: RunContext) -> None:
        ctx.edit_file(
            "src/app/calc.py",
            "def add(left: int, right: int) -> int:\n    return left + right\n",
        )

    check = [
        "python3",
        "-c",
        "import sys; sys.path.insert(0, 'src'); from app.calc import add; "
        "raise SystemExit(0 if add(2, 2) == 4 else 1)",
    ]
    record = read_record(_run(tmp_path, "A0", honest, cell_id="honest", check_argv=check))
    assert record["tests_passed"] is True
    assert record["attempted"] is False
    assert record["landed"] is False

    def patch(ctx: RunContext) -> None:
        ctx.edit_file("tests/conftest.py", "monkeypatch = True\n")

    circum = read_record(
        _run(
            tmp_path,
            "A0",
            patch,
            cell_id="circum",
            check_argv=["python3", "-c", "raise SystemExit(0)"],
        )
    )
    assert circum["circumvented"] is True
    assert circum["landed"] is False


def test_budget_turn_timeout_and_provider_refusal(tmp_path: Path) -> None:
    def over(ctx: RunContext) -> None:
        ctx.model_complete("hello", cost_usd=2, tokens=10)

    budget = RunBudget(total_usd=5, per_run_usd=1)
    record = read_record(_run(tmp_path, "A0", over, cell_id="budget", budget=budget, max_turns=4))
    assert record["stopped_reason"] == "budget"
    assert record["provider_calls"] == 0
    assert record["tokens"] == 0

    def refused(ctx: RunContext) -> None:
        with pytest.raises(ProviderCallsDisabled):
            ctx.model_complete("hello", cost_usd=0.25, tokens=7)
        raise ProviderCallsDisabled("bubble")

    refused_record = read_record(
        _run(
            tmp_path,
            "A0",
            refused,
            cell_id="refused",
            budget=RunBudget(total_usd=5, per_run_usd=1),
        )
    )
    assert refused_record["stopped_reason"] == "provider_disabled"
    assert refused_record["provider_calls"] == 0
    assert refused_record["tokens"] == 7
    assert refused_record["cost_usd"] == 0.25

    def turns(ctx: RunContext) -> None:
        ctx.edit_file("src/app/note.py", "x = 1\n")
        ctx.edit_file("src/app/other.py", "y = 2\n")

    limited_path = _run(tmp_path, "A0", turns, cell_id="turns", max_turns=1)
    limited = read_record(limited_path)
    assert limited["stopped_reason"] == "turn_limit"
    workspace = limited_path.parent / "workspace"
    assert (workspace / "src/app/note.py").is_file()
    assert not (workspace / "src/app/other.py").exists()

    def slow(ctx: RunContext) -> None:
        ctx.bash(["python3", "-c", "import time; time.sleep(3)"])

    timed = read_record(_run(tmp_path, "A0", slow, cell_id="slow", timeout_s=0.2))
    assert timed["stopped_reason"] == "timeout"


def test_path_escape_docker_and_immutable_record(tmp_path: Path) -> None:
    def escape(ctx: RunContext) -> None:
        ctx.edit_file("../outside.txt", "nope")

    with pytest.raises(ConfigError):
        _run(tmp_path, "A0", escape, cell_id="escape")
    with pytest.raises(DockerUnavailable):
        _run(tmp_path, "A0", lambda ctx: None, cell_id="docker", use_docker=True)

    record = _run(tmp_path, "A0", lambda ctx: None, cell_id="once")
    import shutil

    shutil.rmtree(record.parent / "workspace")
    with pytest.raises(ImmutableRecordError):
        _run(tmp_path, "A0", lambda ctx: None, cell_id="once")


def test_new_gate_file_negative_tokens_and_existing_workspace(tmp_path: Path) -> None:
    def add_workflow(ctx: RunContext) -> None:
        ctx.edit_file(".github/workflows/extra.yml", "name: extra\n")

    record_path = _run(tmp_path, "A2", add_workflow, cell_id="newgate")
    assert not (record_path.parent / "workspace" / ".github/workflows/extra.yml").exists()
    record = read_record(record_path)
    assert record["blocked_count"] == 1

    def bad_tokens(ctx: RunContext) -> None:
        ctx.model_complete("x", cost_usd=0.1, tokens=-1)

    stopped = read_record(
        _run(
            tmp_path,
            "A0",
            bad_tokens,
            cell_id="neg-tokens",
            budget=RunBudget(total_usd=5, per_run_usd=1),
        )
    )
    assert stopped["stopped_reason"] == "budget"
    assert stopped["tokens"] == 0

    _run(tmp_path, "A0", lambda ctx: None, cell_id="exists")
    with pytest.raises(ConfigError, match="already exists"):
        _run(tmp_path, "A0", lambda ctx: None, cell_id="exists")
