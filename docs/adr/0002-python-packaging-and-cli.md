# 2. Python packaging and Typer CLI

Date: 2026-10-27

## Status

Accepted

## Context

SNOWBot targets Python 3.11+ with a single console script and strict typing in CI.

## Decision

- Build with Hatchling, `src/snowbot/` layout, console script `snowbot = snowbot.cli:main`.
- Typer for subcommands; `doctor`, `init`, `run`, `update` exposed from Phase 1 (stubs where not implemented).
- Dev tooling: ruff, mypy (strict), pytest, pytest-cov (85% floor), pre-commit.

## Consequences

- Fast local iteration via `pip install -e ".[dev]"`.
- Stub commands document upcoming phases without blocking Phase 1 merge.
