"""Headless Claude Code (``claude -p``) backend on the owner's own login.

Never passes ``--bare`` (it disables the subscription login) and never
``--permission-prompts`` (not in Claude Code 2.1.153). Observed CLI behaviour
is in ``docs/research/notes/2026-11-claude-spike.md``.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowbot.models.config import RunnerConfig

# Path limits come from deny rules and the runner's diff check, not from these allow rules.
STAGE1_ALLOWED: tuple[str, ...] = (
    "Read",
    "Edit",
    "Write",
    "Bash(python -m pytest *)",
    "Bash(python3 -m pytest *)",
    "Bash(ruff *)",
    "Bash(mypy *)",
)
STAGE2_ALLOWED: tuple[str, ...] = STAGE1_ALLOWED
ALWAYS_DENIED: tuple[str, ...] = (
    "Bash(git push *)",
    "Bash(git commit *)",
    "Bash(gh *)",
    "Bash(curl *)",
    "WebFetch",
    "WebSearch",
)

_SETTINGS = {"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": False}}
_STRIPPED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "CLAUDECODE")
_SNIPPET = 300


@dataclass(frozen=True)
class AgentResult:
    """Outcome of one headless agent run."""

    ok: bool
    result_text: str
    session_id: str | None
    cost_estimate_usd: float | None
    num_turns: int | None
    exit_code: int
    error: str | None


def build_argv(
    *,
    prompt: str,
    system_prompt_file: Path,
    cfg: RunnerConfig,
    allowed_tools: Sequence[str],
    disallowed_tools: Sequence[str],
    resume_session: str | None = None,
) -> list[str]:
    """Build the ``claude -p`` command line (tool lists last: they are variadic)."""
    argv = [
        "claude",
        "-p",
        prompt,
        "--setting-sources",
        "project,local",
        "--strict-mcp-config",
        "--mcp-config",
        json.dumps({"mcpServers": {}}),
        "--permission-mode",
        "acceptEdits",
        "--output-format",
        "json",
        "--settings",
        json.dumps(_SETTINGS),
        "--max-turns",
        str(cfg.max_turns),
        "--max-budget-usd",
        f"{cfg.max_budget_usd:.2f}",
        "--append-system-prompt-file",
        str(system_prompt_file),
    ]
    if cfg.model:
        argv += ["--model", cfg.model]
    if resume_session:
        argv += ["--resume", resume_session]
    argv += ["--allowedTools", *allowed_tools]
    argv += ["--disallowedTools", *disallowed_tools]
    return argv


def _child_env() -> dict[str, str]:
    """Environment for the agent: the owner's login only, no API key or nested-session vars."""
    return {
        k: v
        for k, v in os.environ.items()
        if k not in _STRIPPED_ENV and not k.startswith("CLAUDE_CODE_")
    }


def _fail(error: str, exit_code: int, text: str = "") -> AgentResult:
    return AgentResult(False, text, None, None, None, exit_code, error)


def _as_float(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def run_agent(
    argv: list[str],
    *,
    cwd: Path,
    timeout_s: int,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> AgentResult:
    """Run the agent and map its JSON result to an :class:`AgentResult`."""
    try:
        proc = runner(
            argv,
            cwd=cwd,
            timeout=timeout_s,
            capture_output=True,
            text=True,
            env=_child_env(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _fail(f"timeout after {timeout_s}s", -1)
    except FileNotFoundError as exc:
        return _fail(f"claude CLI not found: {exc}", -1)

    stdout = proc.stdout or ""
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        snippet = (stdout.strip() or (proc.stderr or "").strip())[:_SNIPPET]
        return _fail(
            f"claude exited {proc.returncode} without JSON output: {snippet}", proc.returncode
        )

    result = data.get("result")
    text = result if isinstance(result, str) else ""
    is_error = bool(data.get("is_error"))
    ok = proc.returncode == 0 and not is_error
    error = None
    if not ok:
        error = text or f"claude exited {proc.returncode}"
    sid = data.get("session_id")
    turns = data.get("num_turns")
    return AgentResult(
        ok=ok,
        result_text=text,
        session_id=sid if isinstance(sid, str) else None,
        cost_estimate_usd=_as_float(data.get("total_cost_usd")),
        num_turns=turns if isinstance(turns, int) and not isinstance(turns, bool) else None,
        exit_code=proc.returncode,
        error=error,
    )
