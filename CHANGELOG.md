# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Phase 1b: phase validator (`snowbot validate --phase 1b`), string phase ids (`1`, `1b`, `2`, …), shared lessons memory, anti-gaming diff checks, independent validation script/docs, governance CODEOWNERS, and `snowbot status --check`.
- Phase 1 scaffold: `snowbot` Typer CLI (`doctor`, stub `init`/`run`/`update`), Pydantic v2 models for `snowbot.yaml`, pipeline spec, and backlog.
- Structured errors, logging with secret redaction, pytest suite mirroring `src/snowbot/`.
- `pyproject.toml`, pre-commit, CI (ruff, mypy, pytest 85% coverage), security and PR title workflows.
- Repository metadata: CONTRIBUTING, SECURITY, AGENTS.md, ADRs, branch protection docs/script, GitHub templates, Dependabot, CODEOWNERS.
- Example root `snowbot.yaml`, `docs/pipeline-spec.yaml`, and `docs/backlog.yaml`.
