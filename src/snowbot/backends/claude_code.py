"""Headless Claude Code (``claude -p``) backend on the owner's own login.

Never passes ``--bare`` (it disables the subscription login) and never
``--permission-prompts`` (not in Claude Code 2.1.153). Observed CLI behaviour
is in ``docs/research/notes/2026-11-claude-spike.md``.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowbot.backends.proc import TIMEOUT_RETURNCODE, run_killing_group
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
# Agent instructions and tool config. First line of defense only: the runner's diff policy
# rejects these paths whatever the agent manages to write.
PROTECTED_PATHS: tuple[str, ...] = (
    ".claude/**",
    "**/CLAUDE.md",
    "**/AGENTS.md",
    ".mcp.json",
    "**/conftest.py",
    "**/pyproject.toml",
    "**/pytest.ini",
    "**/mypy.ini",
    "**/ruff.toml",
)
ALWAYS_DENIED: tuple[str, ...] = (
    "Bash(git push *)",
    "Bash(git commit *)",
    "Bash(gh *)",
    "Bash(curl *)",
    "WebFetch",
    "WebSearch",
    *(f"{tool}({pattern})" for pattern in PROTECTED_PATHS for tool in ("Edit", "Write")),
)

_SETTINGS = {"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": False}}
# Ruling R16: only these variables, and every LC_*, reach the agent. The spike signed in with
# the subscription login under ``env -i HOME PATH USER TERM``; no token is needed or passed.
ENV_ALLOWLIST = frozenset(
    {
        "HOME",
        "PATH",
        "USER",
        "LOGNAME",
        "TERM",
        "LANG",
        "TMPDIR",
        "SHELL",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
    }
)
_OK_SUBTYPES = (None, "success")
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
    max_turns: int | None = None,
    max_budget_usd: float | None = None,
) -> list[str]:
    """Build the ``claude -p`` command line (tool lists last: they are variadic).

    ``max_turns`` and ``max_budget_usd`` override the config, for a caller passing what is
    left of a stage's budget. A spent budget raises ``ValueError`` rather than sending a limit
    the CLI could read as "none".
    """
    turns = cfg.max_turns if max_turns is None else max_turns
    budget = cfg.max_budget_usd if max_budget_usd is None else max_budget_usd
    if turns < 1:
        msg = f"max_turns must be at least 1, got {turns}"
        raise ValueError(msg)
    if round(budget, 2) < 0.01:
        msg = f"max_budget_usd must be at least 0.01, got {budget}"
        raise ValueError(msg)
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
        str(turns),
        "--max-budget-usd",
        f"{budget:.2f}",
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


def _child_env(extra_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Allowlisted environment for the agent, then ``extra_env``. No token gets through."""
    env = {k: v for k, v in os.environ.items() if k in ENV_ALLOWLIST or k.startswith("LC_")}
    if extra_env:
        env.update(extra_env)
    return env


def _fail(error: str, exit_code: int, text: str = "") -> AgentResult:
    return AgentResult(False, text, None, None, None, exit_code, error)


def _as_float(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def run_agent(
    argv: list[str],
    *,
    cwd: Path,
    timeout_s: int,
    runner: Callable[..., subprocess.CompletedProcess[str]] = run_killing_group,
    extra_env: Mapping[str, str] | None = None,
) -> AgentResult:
    """Run the agent and map its JSON result to an :class:`AgentResult`.

    The default runner starts the agent in its own process group and, on timeout, kills the
    whole group, so tools the agent started do not outlive it. ``extra_env`` is merged over
    the allowlisted environment (the runner passes ``PYTHONPATH=<wt>/src``).
    """
    start = time.monotonic()
    try:
        proc = runner(
            argv,
            cwd=cwd,
            timeout=timeout_s,
            capture_output=True,
            text=True,
            env=_child_env(extra_env),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _fail(f"timeout after {timeout_s}s", -1)
    except FileNotFoundError as exc:
        return _fail(f"claude CLI not found: {exc}", -1)
    except OSError as exc:
        return _fail(f"could not start claude: {exc}", -1)
    if proc.returncode == TIMEOUT_RETURNCODE and time.monotonic() - start >= timeout_s:
        return _fail(f"timeout after {timeout_s}s", -1)

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
    subtype = data.get("subtype")
    good_subtype = subtype in _OK_SUBTYPES
    ok = proc.returncode == 0 and not is_error and good_subtype
    error = None
    if not ok:
        error = text or f"claude exited {proc.returncode}"
        if not good_subtype:
            # error_max_turns, error_max_budget_usd, error_during_execution, ...
            error = f"{subtype}: {error}"
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
