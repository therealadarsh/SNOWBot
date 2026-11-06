# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
