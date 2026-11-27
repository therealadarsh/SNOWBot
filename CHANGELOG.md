# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Lesson index lists each lesson once. Proposed and retired lessons share one directory; scanning it twice had duplicated every entry in `INDEX.yaml`.
- `snowbot lesson accept` (and `promote`) refuses a lesson when an evidence ref is not an existing project file, a pull request present in git history or on GitHub, or the id of a recorded stop event. Lessons are found by id even when the YAML filename differs.
- `snowbot playbook` omits accepted lessons that recommend an action forbidden by AGENTS.md safety rules.
- Anti-gaming scanner now detects real `git diff` test-file deletions (`+++ /dev/null`; the old `b/dev/null` pattern never matched git output) and flags tautological test assertions (`assert True`/`assert 1`), `unittest.skip`/`pytest.skip`/`pytest.importorskip`, and added `# pragma: no cover`. Fixtures are regenerated from real git output (`tests/validator/fixtures/regen_diffs.sh`).

### Added

- Runner settings (`runner:` block in `snowbot.yaml`: repo, sandbox, poll interval, daily run, turn, budget, timeout and fix-round limits, model, base branch) and the `claude_code` backend kind. The runner refuses to start unless `sandbox: host` is set explicitly.
- Claude Code backend (`snowbot.backends.claude_code`): builds the isolated `claude -p` command (project and local settings only, no MCP servers, sandbox on, turn and budget caps, allow and deny rules) and runs it on the owner's own login with an allowlisted environment (`HOME`, `PATH`, `USER`, locale and a few shell and conda variables; no `ANTHROPIC_*`, `CLAUDE*`, GitHub or AWS variables), plus caller-supplied `extra_env`. Edit and Write are denied on agent instructions and tool config (`.claude/**`, `CLAUDE.md`, `AGENTS.md`, `.mcp.json`, `conftest.py`, `pyproject.toml`, `pytest.ini`, `mypy.ini`, `ruff.toml`). Turn and budget caps can be overridden per call. A timeout kills the agent's whole process group. Signed-out, error, non-`success` result subtypes (such as `error_max_turns`), timeout and start-up OS errors come back as failed `AgentResult`s. Unknown keys in the `runner:` config block are rejected, and `max_budget_usd` must be at least 0.01.
- Research version loop: `research/versions/current/VERSION` pins the task suite, oracle, conditions, scanner commit, Inspect and agent CLIs, model id, ImpossibleBench commit, and an explicit unpinned Docker digest. `drift-check` reports outdated or unchecked pins without opening a pull request. `archive` moves a superseded version and prints `research-v<version>` without pushing a tag. Spend caps default to 50 USD per month and 1.50 USD per run; `STATUS.json` stays `paused` until a human activates it. `stability` evaluates recorded inputs and returns a draft body only when every check holds. Results rows include `version` and are not pooled across versions. No pilot was run.
- Research harness (`research/`): study-task fixtures, condition arms A0–A4, an independent path/pattern outcome oracle, a cell runner with budget and sandbox boundaries, a hashed manifest, and extract tables. No model provider is called. The pilot matrix is configuration only.
- Governance for the unattended build: `checklist.yaml` entries for phases `2b`, `2`, `4`, `3`, `5`, `5b`, `7`, `8`, `2c`, `6` and `9`; `ui` and `aws` extras and dev dependencies for every phase; `ui`, `docker` and `aws` pytest markers (deselected by default, run in their own CI jobs); `test-inventory` CI job; `deploy-uat` workflow (skips without `AWS_UAT_ROLE_ARN`); approver role template with a nonce-fenced JSON output contract; hash-pinned `infra/requirements.txt` and a locked CDK CLI in `infra/package-lock.json`.
- Owner setup guide (`docs/OWNER_SETUP.md`): unattended build, `main` and `uat` rulesets, labels, and which credentials each agent backend uses. README, STATUS, and open questions match that plan.
- **Architect gate CI** (`.github/workflows/architect-gate.yml`): required check `architect-gate` runs independent validation (`ruff`, `mypy`, `pytest`, `snowbot validate`, memory status); optional PR summary comment (not an approval). (The `skip-architect` label was removed later in this release.)
- Senior Software Architect role template (`src/snowbot/templates/roles/architect.md.j2`) and docs: `docs/ARCHITECT_GATE.md`, `docs/GITHUB_SETUP.md` (simple mode: 0 approvals, CI validator).
- Phase 1b: phase validator (`snowbot validate --phase 1b`), string phase ids (`1`, `1b`, `2`, …), shared lessons memory, anti-gaming diff checks, independent validation script/docs, governance CODEOWNERS, and `snowbot status --check`.
- Governance docs (#7): owner ruleset and dependency graph steps; expanded `docs/BRANCH_PROTECTION.md` with exact required check names and owner-only settings.
- Phase 1 scaffold: `snowbot` Typer CLI (`doctor`, stub `init`/`run`/`update`), Pydantic v2 models for `snowbot.yaml`, pipeline spec, and backlog.
- Structured errors, logging with secret redaction, pytest suite mirroring `src/snowbot/`.
- `pyproject.toml`, pre-commit, CI (ruff, mypy, pytest 85% coverage), security and PR title workflows.
- Repository metadata: CONTRIBUTING, SECURITY, AGENTS.md, ADRs, branch protection docs/script, GitHub templates, Dependabot, CODEOWNERS.
- Example root `snowbot.yaml`, `docs/pipeline-spec.yaml`, and `docs/backlog.yaml`.

### Fixed

- Wheel builds: drop the hatch `force-include` block that added `templates/` and `checklist.yaml` twice and made `pip wheel` and `pipx install` fail. A CI job now builds and installs the wheel.
- Anti-gaming scanner now detects real `git diff` test-file deletions (`+++ /dev/null`; the old `b/dev/null` pattern never matched git output) and flags tautological test assertions (`assert True`/`assert 1`), `unittest.skip`/`pytest.skip`/`pytest.importorskip`, and added `# pragma: no cover`. Fixtures are regenerated from real git output (`tests/validator/fixtures/regen_diffs.sh`).

### Changed

- `architect-gate` runs the validator and checklist from the PR's base commit against the PR head, diffs against the PR's real base, decides from check ids and finding codes instead of grepping output, takes the phase from `feat/<phase>-<slug>` or a `phase:` label, posts its comment from a job with no checkout, and no longer has a `skip-architect` label.
- Workflows: top-level `permissions: {}` with per-job grants, `persist-credentials: false`, actions pinned to commit SHAs, CI on pushes to `uat`, one aggregate `CI` check, and `dependency-review` is blocking.
- Anti-gaming governance paths match `AGENTS.md` (adds `.github/`, `scripts/`, `.snowbot/memory/`, agent config folders, test config, lockfiles and requirements files anywhere). Role templates alone no longer count as product code.
- Validator role template states its `VERDICT <nonce>: …` output contract.
- `.github/CODEOWNERS` covers the full governance list in `AGENTS.md`.
- CI: skip conventional-commit PR title check for Dependabot actors.
