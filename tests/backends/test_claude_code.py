"""Tests for the Claude Code headless backend (fake runner only)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from snowbot.backends.claude_code import (
    ALWAYS_DENIED,
    STAGE1_ALLOWED,
    STAGE2_ALLOWED,
    build_argv,
    run_agent,
)
from snowbot.models.config import RunnerConfig


def _argv(**kw: Any) -> list[str]:
    base: dict[str, Any] = {
        "prompt": "Read .snowbot-out/TASK.md",
        "system_prompt_file": Path("/x/sys.md"),
        "cfg": RunnerConfig(sandbox="host"),
        "allowed_tools": ["Read", "Bash(python -m pytest *)"],
        "disallowed_tools": ["Bash(gh *)", "WebFetch"],
    }
    base.update(kw)
    return build_argv(**base)


def _fake(
    stdout: str = "", stderr: str = "", code: int = 0, captured: dict[str, Any] | None = None
):
    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if captured is not None:
            captured.update(kwargs)
            captured["argv"] = argv
        return subprocess.CompletedProcess(argv, code, stdout, stderr)

    return runner


def test_argv_never_bare_and_has_isolation_flags() -> None:
    argv = _argv()
    assert argv[:3] == ["claude", "-p", "Read .snowbot-out/TASK.md"]
    assert "--bare" not in argv
    for flag in [
        "--setting-sources",
        "--strict-mcp-config",
        "--mcp-config",
        "--permission-mode",
        "--settings",
        "--output-format",
        "--max-turns",
        "--max-budget-usd",
        "--append-system-prompt-file",
        "--allowedTools",
        "--disallowedTools",
    ]:
        assert flag in argv
    assert "--permission-prompts" not in argv
    settings = json.loads(argv[argv.index("--settings") + 1])
    assert settings == {"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": False}}
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert argv[argv.index("--max-budget-usd") + 1] == "3.00"
    assert argv[argv.index("--max-turns") + 1] == "40"
    assert argv[argv.index("--setting-sources") + 1] == "project,local"
    assert json.loads(argv[argv.index("--mcp-config") + 1]) == {"mcpServers": {}}
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--append-system-prompt-file") + 1] == "/x/sys.md"
    assert "--model" not in argv
    assert "--resume" not in argv


def test_tool_rules_are_separate_items_after_other_flags() -> None:
    argv = _argv()
    a = argv.index("--allowedTools")
    d = argv.index("--disallowedTools")
    assert argv[a + 1 : d] == ["Read", "Bash(python -m pytest *)"]
    assert argv[d + 1 :] == ["Bash(gh *)", "WebFetch"]
    assert argv.index("--append-system-prompt-file") < a


def test_model_and_resume_flags() -> None:
    argv = _argv(cfg=RunnerConfig(sandbox="host", model="opus"), resume_session="s1")
    assert argv[argv.index("--model") + 1] == "opus"
    assert argv[argv.index("--resume") + 1] == "s1"
    assert argv.index("--resume") < argv.index("--allowedTools")
    assert argv.index("--model") < argv.index("--allowedTools")


def test_default_rule_sets() -> None:
    assert "Bash(python -m pytest *)" in STAGE1_ALLOWED
    assert "Bash(python3 -m pytest *)" in STAGE2_ALLOWED
    for rule in ["Bash(git push *)", "Bash(git commit *)", "Bash(gh *)", "WebFetch", "WebSearch"]:
        assert rule in ALWAYS_DENIED


def test_parses_success_json() -> None:
    out = json.dumps(
        {
            "result": "done",
            "session_id": "s1",
            "total_cost_usd": 0.12,
            "num_turns": 5,
            "is_error": False,
        }
    )
    r = run_agent(["claude"], cwd=Path("."), timeout_s=10, runner=_fake(out))
    assert r.ok and r.result_text == "done" and r.session_id == "s1"
    assert r.cost_estimate_usd == 0.12 and r.num_turns == 5 and r.exit_code == 0
    assert r.error is None


def test_is_error_true_is_failure() -> None:
    out = json.dumps({"result": "boom", "is_error": True})
    r = run_agent(["claude"], cwd=Path("."), timeout_s=10, runner=_fake(out))
    assert r.ok is False and r.error == "boom"


def test_signed_out_json() -> None:
    out = json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": True,
            "result": "Not logged in · Please run /login",
            "total_cost_usd": 0,
        }
    )
    r = run_agent(["claude"], cwd=Path("."), timeout_s=10, runner=_fake(out, code=1))
    assert not r.ok and r.error == "Not logged in · Please run /login" and r.exit_code == 1


def test_nonzero_exit_with_clean_json_is_failure() -> None:
    out = json.dumps({"result": "x", "is_error": False})
    r = run_agent(["claude"], cwd=Path("."), timeout_s=10, runner=_fake(out, code=2))
    assert not r.ok and r.error


def test_non_json_stdout_is_failure_with_text() -> None:
    r = run_agent(["claude"], cwd=Path("."), timeout_s=10, runner=_fake("not signed in", code=1))
    assert not r.ok and "not signed in" in (r.error or "")


def test_non_json_uses_stderr_when_stdout_empty() -> None:
    r = run_agent(["claude"], cwd=Path("."), timeout_s=10, runner=_fake("", "kaput", code=1))
    assert not r.ok and "kaput" in (r.error or "")


def test_timeout_is_failure() -> None:
    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, 1800)

    r = run_agent(["claude"], cwd=Path("."), timeout_s=1800, runner=runner)
    assert r.ok is False and r.error == "timeout after 1800s" and r.exit_code == -1


def test_missing_binary_is_failure() -> None:
    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("claude")

    r = run_agent(["claude"], cwd=Path("."), timeout_s=10, runner=runner)
    assert r.ok is False and "claude" in (r.error or "") and r.exit_code == -1


def test_json_not_an_object_is_failure() -> None:
    r = run_agent(["claude"], cwd=Path("."), timeout_s=10, runner=_fake("[1]"))
    assert not r.ok and r.error


def test_env_strips_credentials_and_claude_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"]:
        monkeypatch.setenv(name, "x")
    monkeypatch.setenv("SNOW_KEEP", "yes")
    captured: dict[str, Any] = {}
    out = json.dumps({"result": "ok", "is_error": False})
    run_agent(["claude"], cwd=Path("/w"), timeout_s=7, runner=_fake(out, captured=captured))
    env = captured["env"]
    assert env["SNOW_KEEP"] == "yes"
    assert not any(
        k in env
        for k in ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"]
    )
    assert captured["cwd"] == Path("/w") and captured["timeout"] == 7
    assert captured["capture_output"] is True and captured["text"] is True
