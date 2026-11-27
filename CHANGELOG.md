# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Lesson index lists each lesson once. Proposed and retired lessons share one directory; scanning it twice had duplicated every entry in `INDEX.yaml`.
- `snowbot lesson accept` (and `promote`) refuses a lesson when an evidence ref is not an existing project file, a pull request present in git history or on GitHub, or the id of a recorded stop event. Lessons are found by id even when the YAML filename differs.
- `snowbot playbook` omits accepted lessons that recommend an action forbidden by AGENTS.md safety rules.

### Added

- Runner settings (`runner:` block in `snowbot.yaml`: repo, sandbox, poll interval, daily run, turn, budget, timeout and fix-round limits, model, base branch) and the `claude_code` backend kind. The runner refuses to start unless `sandbox: host` is set explicitly.
- Claude Code backend (`snowbot.backends.claude_code`): builds the isolated `claude -p` command (project and local settings only, no MCP servers, sandbox on, turn and budget caps, allow and deny rules) and runs it on the owner's own login with an allowlisted environment (`HOME`, `PATH`, `USER`, locale and a few shell and conda variables; no `ANTHROPIC_*`, `CLAUDE*`, GitHub or AWS variables), plus caller-supplied `extra_env`. Edit and Write are denied on agent instructions and tool config (`.claude/**`, `CLAUDE.md`, `AGENTS.md`, `.mcp.json`, `conftest.py`, `pyproject.toml`, `pytest.ini`, `mypy.ini`, `ruff.toml`). Turn and budget caps can be overridden per call. A timeout kills the agent's whole process group. Signed-out, error, non-`success` result subtypes (such as `error_max_turns`), timeout and start-up OS errors come back as failed `AgentResult`s. Unknown keys in the `runner:` config block are rejected, and `max_budget_usd` must be at least 0.01.
- Research version loop: `research/versions/current/VERSION` pins the task suite, oracle, conditions, scanner commit, Inspect and agent CLIs, model id, ImpossibleBench commit, and an explicit unpinned Docker digest. `drift-check` reports outdated or unchecked pins without opening a pull request. `archive` moves a superseded version and prints `research-v<version>` without pushing a tag. Spend caps default to 50 USD per month and 1.50 USD per run; `STATUS.json` stays `paused` until a human activates it. `stability` evaluates recorded inputs and returns a draft body only when every check holds. Results rows include `version` and are not pooled across versions. No pilot was run.
- Research harness (`research/`): study-task fixtures, condition arms A0–A4, an independent path/pattern outcome oracle, a cell runner with budget and sandbox boundaries, a hashed manifest, and extract tables. No model provider is called. The pilot matrix is configuration only.
- **Architect gate CI** (`.github/workflows/architect-gate.yml`): required check `architect-gate` runs independent validation (`ruff`, `mypy`, `pytest`, `snowbot validate`, memory status); optional PR summary comment (not an approval). Emergency label `skip-architect`.
- Senior Software Architect role template (`src/snowbot/templates/roles/architect.md.j2`) and docs: `docs/ARCHITECT_GATE.md`, `docs/GITHUB_SETUP.md` (simple mode: 0 approvals, CI validator).
- Phase 1b: phase validator (`snowbot validate --phase 1b`), string phase ids (`1`, `1b`, `2`, …), shared lessons memory, anti-gaming diff checks, independent validation script/docs, governance CODEOWNERS, and `snowbot status --check`.
- Governance docs (#7): owner ruleset and dependency graph steps; expanded `docs/BRANCH_PROTECTION.md` with exact required check names and owner-only settings.
- Phase 1 scaffold: `snowbot` Typer CLI (`doctor`, stub `init`/`run`/`update`), Pydantic v2 models for `snowbot.yaml`, pipeline spec, and backlog.
- Structured errors, logging with secret redaction, pytest suite mirroring `src/snowbot/`.
- `pyproject.toml`, pre-commit, CI (ruff, mypy, pytest 85% coverage), security and PR title workflows.
- Repository metadata: CONTRIBUTING, SECURITY, AGENTS.md, ADRs, branch protection docs/script, GitHub templates, Dependabot, CODEOWNERS.
- Example root `snowbot.yaml`, `docs/pipeline-spec.yaml`, and `docs/backlog.yaml`.

### Changed

- `.github/CODEOWNERS`: restore Phase 1b governance paths (workflows, packaging, validator, contributor docs).
- CI: skip conventional-commit PR title check for Dependabot actors; `dependency-review` continues on error until Dependency graph is enabled.
