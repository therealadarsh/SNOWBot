"""Conditions, budget, sandbox, agents, and extension points."""

from __future__ import annotations

from pathlib import Path

import pytest
from research.agents import (
    UNVERIFIED_ASSUMPTIONS,
    claude_print_argv,
    codex_exec_argv,
    inspect_eval_argv,
)
from research.budget import RunBudget, budget_allows, nominal_cost
from research.conditions import load_conditions
from research.errors import (
    BudgetError,
    ConfigError,
    DockerUnavailable,
    ExtensionNotInThisPullRequest,
)
from research.extensions import registered_extensions, require_extension
from research.gitutil import scrub_env
from research.sandbox import (
    DockerSandbox,
    HostProxy,
    LocalSubprocessSandbox,
    docker_run_argv,
    inspect_compose_yaml,
)


def test_condition_crosses() -> None:
    loaded = load_conditions()
    assert loaded.record_attempts_before_block is True
    assert {arm.id for arm in loaded.arms} == {"A0", "A1", "A2", "A3", "A4"}
    assert loaded.escalation_crossed_with == ("A1", "A2", "A3")
    assert loaded.scanner_feedback_crossed_with == ("A3",)
    by_arm: dict[str, list[tuple[bool, str]]] = {}
    for condition in loaded.conditions:
        by_arm.setdefault(condition.arm.id, []).append(
            (condition.escalation, condition.scanner_feedback)
        )
    assert (True, "hidden") not in by_arm["A0"]
    assert (False, "hidden") in by_arm["A1"]
    assert (True, "hidden") in by_arm["A1"]
    assert "shown" in {feedback for _, feedback in by_arm["A3"]}
    assert "hidden" in {feedback for _, feedback in by_arm["A3"]}
    assert loaded.by_id("A4").arm.governance_split is True
    matched = loaded.treatment.matches("src/app.py", "fail_under = 90\n")
    assert matched is not None
    assert loaded.treatment.matches("src/app.py", "return 1\n") is None


def test_path_matching() -> None:
    from research.paths import is_test_path, path_matches

    assert path_matches(".github/workflows/ci.yml", [".github/workflows/"]) is True
    assert path_matches("./.github/workflows/ci.yml", [".github/workflows/"]) is True
    assert path_matches(".github/workflows", [".github/workflows/"]) is True
    assert path_matches("src/app.py", [".github/workflows/", "**/*.py"]) is True
    assert path_matches("foo.py", ["*.py"]) is True
    assert path_matches("src/app.py", ["*.md"]) is False
    assert path_matches("dir/pyproject.toml", ["pyproject.toml"]) is True
    assert path_matches(".pre-commit-config.yaml", [".pre-commit-config.yaml"]) is True
    assert path_matches("notes.md", ["pyproject.toml"]) is False
    assert is_test_path("tests/test_a.py", r"(^|/)tests/.+\.py$") is True
    assert is_test_path("src/app.py", r"(^|/)tests/.+\.py$") is False


def test_budget_caps() -> None:
    assert nominal_cost(180, 1.5) == 270
    assert budget_allows(180, 1.5, 50) is False
    assert budget_allows(1, 1.5, 50) is True
    assert budget_allows(1, 60, 50) is False
    assert budget_allows(-1, 1, 1) is False
    study = RunBudget(total_usd=1.2, per_run_usd=1)
    study.authorize(1)
    study.begin_cell()
    with pytest.raises(BudgetError, match="study cap"):
        study.authorize(0.5)
    budget = RunBudget(total_usd=2, per_run_usd=1)
    budget.authorize(1)
    budget.begin_cell()
    budget.authorize(1)
    with pytest.raises(BudgetError):
        budget.authorize(0.5)
    with pytest.raises(BudgetError):
        RunBudget(total_usd=1, per_run_usd=1).authorize(-1)


def test_agent_argv_uses_documented_flags(tmp_path: Path) -> None:
    assert UNVERIFIED_ASSUMPTIONS
    claude = claude_print_argv(
        prompt="fix the test",
        model="haiku",
        max_turns=3,
        max_budget_usd=1.5,
        system_prompt_file=tmp_path / "rule.txt",
    )
    assert claude[:3] == ["claude", "-p", "fix the test"]
    assert "--max-turns" in claude
    assert "--max-budget-usd" in claude
    assert "--bare" in claude
    assert "ANTHROPIC_API_KEY" not in claude
    codex = codex_exec_argv(
        prompt="fix",
        model="gpt",
        proxy_base_url="http://127.0.0.1:9/v1",
        workspace=tmp_path,
    )
    assert codex[:2] == ["codex", "exec"]
    assert "--sandbox" in codex and "workspace-write" in codex
    assert "openai_base_url=http://127.0.0.1:9/v1" in codex
    assert "OPENAI_API_KEY" not in " ".join(codex)
    inspect_argv = inspect_eval_argv(
        task="task.py",
        model="mock",
        proxy_base_url="http://127.0.0.1:9/v1",
    )
    assert "--timeout" not in inspect_argv
    with_timeout = inspect_eval_argv(
        task="task.py",
        model="mock",
        proxy_base_url="http://127.0.0.1:9/v1",
        model_api_timeout_s=30,
    )
    assert with_timeout[with_timeout.index("--timeout") + 1] == "30"


def test_sandbox_strips_keys_and_builds_docker_argv(tmp_path: Path) -> None:
    proxy = HostProxy(base_url="http://127.0.0.1:9/v1")
    argv = docker_run_argv(
        image="example:local",
        workspace=tmp_path,
        command=["true"],
        proxy=proxy,
    )
    assert argv[:5] == ["docker", "run", "--rm", "--network", "none"]
    rendered = " ".join(argv)
    assert "ANTHROPIC_API_KEY" not in rendered
    assert "ANTHROPIC_BASE_URL=http://127.0.0.1:9/v1" in rendered
    compose = inspect_compose_yaml(image="example:local")
    assert "network_mode: none" in compose
    env = scrub_env({"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "secret", "OK": "1"})
    assert "ANTHROPIC_API_KEY" not in env
    assert env["OK"] == "1"
    sandbox = LocalSubprocessSandbox(tmp_path, proxy=proxy)
    result = sandbox.run(
        ["python3", "-c", "import os; print(os.environ.get('ANTHROPIC_API_KEY'))"],
        timeout_s=5,
        host_env={"PATH": "/usr/bin:/bin", "ANTHROPIC_API_KEY": "secret"},
    )
    assert result.timed_out is False
    assert result.stdout.strip() == "None"
    assert "ANTHROPIC_BASE_URL" not in result.stdout
    timed = sandbox.run(["python3", "-c", "import time; time.sleep(2)"], timeout_s=0.2)
    assert timed.timed_out is True
    with pytest.raises(DockerUnavailable):
        DockerSandbox(tmp_path, image="example", available=False).run(["true"], timeout_s=1)
    with pytest.raises(DockerUnavailable, match="does not start"):
        DockerSandbox(tmp_path, image="example", available=True).run(["true"], timeout_s=1)


def test_extensions_are_unimplemented() -> None:
    assert "archiver" in registered_extensions()
    with pytest.raises(ExtensionNotInThisPullRequest):
        require_extension("stability_evaluator")
    with pytest.raises(KeyError):
        require_extension("not-an-extension")


def test_invalid_condition_cross(tmp_path: Path) -> None:
    path = tmp_path / "conditions.yaml"
    path.write_text(
        """
schema_version: 1
record_attempts_before_block: true
arms:
  A0:
    label: open
    gates_editable: true
    prompt_rule: null
    path_lock: false
    posthoc_scanner: false
    governance_split: false
escalation_crossed_with: []
scanner_feedback_crossed_with: []
gate_paths: [pyproject.toml]
treatment_scanner:
  blocked_path_globs: [pyproject.toml]
  blocked_substrings: [fail_under]
conditions:
  - id: A0
    arm: A0
    escalation: true
    scanner_feedback: hidden
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_conditions(path)
