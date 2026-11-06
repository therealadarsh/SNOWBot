"""Run one study cell inside a fresh workspace.

Live Claude Code, Codex, and Inspect processes are not started. Model
completions raise :class:`ProviderCallsDisabled` after the dollar cap is
checked. Docker execution raises :class:`DockerUnavailable`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from research.budget import RunBudget
from research.conditions import Condition, ConditionSet
from research.errors import (
    BudgetError,
    CellTimeout,
    ConfigError,
    ProviderCallsDisabled,
    TurnLimitExceeded,
)
from research.gitutil import diff_against_head, restore_worktree_file
from research.oracle import (
    OracleRules,
    ToolPayload,
    judge,
    measure_gate_strength,
)
from research.policy import Policy
from research.record import append_jsonl, write_record
from research.sandbox import DockerSandbox, HostProxy, LocalSubprocessSandbox, ProcessResult
from research.tasks.build import Task, materialize
from research.versioning import current_version_string, parse_semver

Agent = Callable[["RunContext"], None]


class RunContext:
    """Tools offered to an agent. Gate edits are logged before any block."""

    def __init__(
        self,
        *,
        workspace: Path,
        cell_dir: Path,
        condition: Condition,
        loaded: ConditionSet,
        budget: RunBudget,
        sandbox: LocalSubprocessSandbox,
        timeout_s: float,
        max_turns: int,
        prompt: str,
        on_attempt_flushed: Callable[[RunContext], None] | None,
    ) -> None:
        self.workspace = workspace
        self.cell_dir = cell_dir
        self.condition = condition
        self.prompt = prompt
        self.budget = budget
        self.sandbox = sandbox
        self.timeout_s = timeout_s
        self.max_turns = max_turns
        self.on_attempt_flushed = on_attempt_flushed
        self.policy = Policy(condition, loaded)
        self.attempts_path = cell_dir / "attempts.jsonl"
        self.governance_path = cell_dir / "governance_requests.jsonl"
        self.attempts: list[dict[str, object]] = []
        self.escalations: list[str] = []
        self.turns = 0
        self.tokens = 0
        self.blocked_count = 0
        self.stopped: str | None = None
        self._seq = 0

    def edit_file(self, rel: str, content: str) -> str:
        self._consume_turn()
        target = _inside(self.workspace, rel)
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        diff = diff_against_head(self.workspace, rel)
        attempt: dict[str, object] = {
            "seq": self._seq,
            "path": rel,
            "diff": diff,
            "event": "attempt",
            "blocked": False,
        }
        self._seq += 1
        append_jsonl(self.attempts_path, attempt)
        self.attempts.append(attempt)
        if self.on_attempt_flushed is not None:
            self.on_attempt_flushed(self)
        decision = self.policy.decide(rel, diff)
        if not decision.block:
            return self.policy.message(decision)
        blocked = {
            **attempt,
            "event": "blocked",
            "blocked": True,
            "rule": decision.rule,
        }
        append_jsonl(self.attempts_path, blocked)
        self.blocked_count += 1
        if decision.route_governance:
            append_jsonl(
                self.governance_path,
                {"path": rel, "diff": diff, "rule": decision.rule},
            )
        restore_worktree_file(self.workspace, rel, existed=existed)
        self.attempts[-1] = blocked
        return self.policy.message(decision)

    def bash(self, argv: Sequence[str]) -> ProcessResult:
        self._consume_turn()
        result = self.sandbox.run(argv, timeout_s=self.timeout_s)
        if result.timed_out:
            self.stopped = "timeout"
            raise CellTimeout(f"command exceeded {self.timeout_s}s")
        return result

    def flag_for_human(self, message: str) -> str:
        self._consume_turn()
        if not self.condition.escalation:
            return "escalation tool is not available in this condition"
        self.escalations.append(message)
        return "flagged for a human; no change was applied in this run"

    def model_complete(self, prompt: str, *, cost_usd: float, tokens: int) -> None:
        """Reserve budget, then refuse the provider call."""
        del prompt
        self._consume_turn()
        self.budget.authorize(cost_usd)
        if tokens < 0:
            raise BudgetError("tokens must be non-negative")
        self.tokens += tokens
        raise ProviderCallsDisabled(
            "model calls are not executed in this build; keys stay on the host proxy"
        )

    def _consume_turn(self) -> None:
        self.turns += 1
        if self.turns > self.max_turns:
            self.stopped = "turn_limit"
            raise TurnLimitExceeded(f"turn limit {self.max_turns} exceeded")


def noop_agent(ctx: RunContext) -> None:
    """Agent that does not edit the workspace or call a model."""
    del ctx


def run_cell(
    *,
    task: Task,
    condition: Condition,
    loaded: ConditionSet,
    rules: OracleRules,
    run_dir: Path,
    cell_id: str,
    model: str,
    seed: int,
    agent_name: str,
    budget: RunBudget,
    timeout_s: float,
    max_turns: int,
    manifest_sha256: str,
    agent: Agent | None = None,
    check_argv: Sequence[str] | None = None,
    on_attempt_flushed: Callable[[RunContext], None] | None = None,
    proxy: HostProxy | None = None,
    use_docker: bool = False,
    version: str | None = None,
) -> Path:
    cell_dir = run_dir / cell_id
    workspace = cell_dir / "workspace"
    if workspace.exists():
        raise ConfigError(f"workspace already exists: {workspace}")
    if use_docker:
        DockerSandbox(workspace, image="unused").run(["true"], timeout_s=timeout_s)
    materialize(task, workspace)
    sandbox = LocalSubprocessSandbox(workspace, proxy=proxy)
    budget.begin_cell()
    before = measure_gate_strength(workspace, rules)
    prompt = task.prompt
    if condition.arm.prompt_rule:
        prompt = task.prompt.rstrip() + "\n\n" + condition.arm.prompt_rule.strip() + "\n"
    ctx = RunContext(
        workspace=workspace,
        cell_dir=cell_dir,
        condition=condition,
        loaded=loaded,
        budget=budget,
        sandbox=sandbox,
        timeout_s=timeout_s,
        max_turns=max_turns,
        prompt=prompt,
        on_attempt_flushed=on_attempt_flushed,
    )
    actor = agent or noop_agent
    stopped = _invoke_agent(ctx, actor)
    tests_passed = _run_check(ctx, check_argv, stopped)
    final_diff = diff_against_head(workspace)
    (cell_dir / "final.diff").write_text(final_diff, encoding="utf-8")
    after = measure_gate_strength(workspace, rules)
    payloads = [
        ToolPayload(diff=str(item.get("diff", "")), blocked=bool(item.get("blocked", False)))
        for item in ctx.attempts
    ]
    verdict = judge(
        final_diff=final_diff,
        tool_payloads=payloads,
        before=before,
        after=after,
        tests_passed=tests_passed,
        rules=rules,
    )
    resolved_version = current_version_string() if version is None else version
    parse_semver(resolved_version)
    record = {
        "record_version": 1,
        "version": resolved_version,
        "cell_id": cell_id,
        "task_id": task.id,
        "condition_id": condition.id,
        "arm": condition.arm.id,
        "agent": agent_name,
        "model": model,
        "seed": seed,
        "tests_passed": tests_passed,
        "attempted": verdict.attempted,
        "landed": verdict.landed,
        "circumvented": verdict.circumvented,
        "taxa_attempted": list(verdict.taxa_attempted),
        "taxa_landed": list(verdict.taxa_landed),
        "cost_usd": budget.cell_spent,
        "tokens": ctx.tokens,
        "provider_calls": 0,
        "stopped_reason": stopped,
        "escalation_count": len(ctx.escalations),
        "blocked_count": ctx.blocked_count,
        "sandbox_kind": sandbox.kind,
        "network": sandbox.network,
        "manifest_sha256": manifest_sha256,
        "prompt_rule_applied": condition.arm.prompt_rule is not None,
        "timeout_s": timeout_s,
        "max_turns": max_turns,
    }
    return write_record(cell_dir, record)


def _invoke_agent(ctx: RunContext, agent: Agent) -> str | None:
    try:
        agent(ctx)
    except TurnLimitExceeded:
        return "turn_limit"
    except BudgetError:
        return "budget"
    except ProviderCallsDisabled:
        return "provider_disabled"
    except CellTimeout:
        return "timeout"
    return ctx.stopped


def _run_check(
    ctx: RunContext,
    check_argv: Sequence[str] | None,
    stopped: str | None,
) -> bool | None:
    if check_argv is None or stopped is not None:
        return None
    result = ctx.sandbox.run(check_argv, timeout_s=ctx.timeout_s)
    if result.timed_out:
        return False
    return result.returncode == 0


def _inside(root: Path, rel: str) -> Path:
    parts = Path(rel).parts
    if not rel or rel.startswith("/") or ".." in parts:
        raise ConfigError("path escapes the workspace")
    target = (root / rel).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ConfigError("path escapes the workspace")
    return target
