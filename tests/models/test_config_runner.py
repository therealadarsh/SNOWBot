"""Tests for runner settings and the claude_code backend kind."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from snowbot.errors import ConfigError
from snowbot.models.config import BackendKind, RunnerConfig, SnowbotConfig


def test_runner_defaults() -> None:
    r = SnowbotConfig().runner
    assert (r.max_runs_per_day, r.max_turns, r.max_budget_usd, r.timeout_s, r.fix_rounds) == (
        5,
        40,
        3.0,
        1800,
        2,
    )
    assert (r.repo, r.sandbox, r.model, r.base_branch, r.poll_interval_s) == (
        None,
        None,
        None,
        "main",
        300,
    )


def test_runner_requires_explicit_host_sandbox() -> None:
    with pytest.raises(ConfigError) as e:
        RunnerConfig().require_host_sandbox()
    assert e.value.code == "sandbox_not_host"
    RunnerConfig(sandbox="host").require_host_sandbox()


def test_claude_code_backend_kind() -> None:
    cfg = SnowbotConfig.model_validate({"backend": {"kind": "claude_code"}})
    assert cfg.backend.kind is BackendKind.CLAUDE_CODE


@pytest.mark.parametrize(
    "field", ["poll_interval_s", "max_runs_per_day", "max_turns", "timeout_s", "fix_rounds"]
)
@pytest.mark.parametrize("value", [0, -1])
def test_runner_ints_must_be_positive(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        RunnerConfig.model_validate({field: value})


@pytest.mark.parametrize("value", [0, -0.5])
def test_runner_budget_must_be_positive(value: float) -> None:
    with pytest.raises(ValidationError):
        RunnerConfig(max_budget_usd=value)
