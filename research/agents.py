"""Agent CLI interfaces. Flags below were checked against primary docs.

Claude Code: https://code.claude.com/docs/en/cli-reference
  ``claude -p`` / ``--print``, ``--model``, ``--max-turns``, ``--max-budget-usd``,
  ``--output-format json``, ``--bare``, ``--append-system-prompt-file``.
  ``ANTHROPIC_BASE_URL`` routes API calls at a proxy; ``ANTHROPIC_API_KEY`` is
  the credential and is not placed in the sandbox env.
  https://code.claude.com/docs/en/env-vars

Codex: https://developers.openai.com/codex/cli/reference and
  https://developers.openai.com/codex/noninteractive.md
  ``codex exec``, ``--model``, ``--sandbox workspace-write``, ``--json``,
  ``--ephemeral``, ``--ignore-user-config``, ``--skip-git-repo-check``,
  ``--cd``, ``-c key=value``.
  ``openai_base_url`` is the documented config key for a proxy
  (https://developers.openai.com/codex/config-file/config-advanced).

Inspect: https://inspect.aisi.org.uk/reference/inspect_eval.html
  ``inspect eval``, ``--model``, ``--model-base-url``, ``--sandbox``,
  ``--json``, ``--max-retries``. ``--timeout`` is the model HTTP timeout, not
  a cell wall clock, so the harness does not pass it for the cell limit.

This module does not execute the CLIs.
"""

from __future__ import annotations

from pathlib import Path

# Combination not executed: Codex documents ``--ignore-user-config`` and ``-c``
# separately. This builder passes both so user config cannot override the proxy.
UNVERIFIED_ASSUMPTIONS: tuple[str, ...] = (
    "codex --ignore-user-config combined with -c openai_base_url was not executed",
    "Inspect --timeout is the model HTTP timeout; no cell wall-clock flag was verified",
    "docker run --network none is constructed from Docker's network mode and was not executed here",
)


def claude_print_argv(
    *,
    prompt: str,
    model: str,
    max_turns: int,
    max_budget_usd: float,
    system_prompt_file: Path | None = None,
) -> list[str]:
    argv = [
        "claude",
        "-p",
        prompt,
        "--bare",
        "--model",
        model,
        "--max-turns",
        str(max_turns),
        "--max-budget-usd",
        f"{max_budget_usd:.2f}",
        "--output-format",
        "json",
    ]
    if system_prompt_file is not None:
        argv.extend(["--append-system-prompt-file", str(system_prompt_file)])
    return argv


def codex_exec_argv(
    *,
    prompt: str,
    model: str,
    proxy_base_url: str,
    workspace: Path,
) -> list[str]:
    return [
        "codex",
        "exec",
        "--model",
        model,
        "--sandbox",
        "workspace-write",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--skip-git-repo-check",
        "--cd",
        str(workspace),
        "-c",
        f"openai_base_url={proxy_base_url}",
        prompt,
    ]


def inspect_eval_argv(
    *,
    task: str,
    model: str,
    proxy_base_url: str,
    sandbox: str = "docker",
    model_api_timeout_s: int | None = None,
) -> list[str]:
    """Build ``inspect eval`` argv.

    ``model_api_timeout_s`` maps to the documented ``--timeout`` model HTTP
    timeout. Omit it to leave Inspect's default. It is not the cell wall clock.
    """
    argv = [
        "inspect",
        "eval",
        task,
        "--model",
        model,
        "--model-base-url",
        proxy_base_url,
        "--sandbox",
        sandbox,
        "--json",
        "--max-retries",
        "0",
    ]
    if model_api_timeout_s is not None:
        argv.extend(["--timeout", str(model_api_timeout_s)])
    return argv
