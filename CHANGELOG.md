# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
