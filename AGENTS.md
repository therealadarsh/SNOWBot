# AGENTS.md — SNOWBot repository

Guidance for humans and coding agents working in **SNOWBot** (`therealadarsh/SNOWBot`).

## Project intent

SNOWBot is a backend-agnostic CLI that installs and runs an agent pipeline in any codebase. Phase 1 establishes Python packaging, configuration models, tests, and automation — not full pipeline execution.

## Layout (repo root)

```
src/snowbot/          # Python package
tests/                # Mirrors src layout
docs/                 # Specs, ADRs, open questions
.github/              # CI, templates, Dependabot
scripts/              # Maintenance scripts (branch protection helper)
snowbot.yaml          # Example config for this repo
```

Do **not** introduce a nested `SNOWBot/` directory; everything lives at the repository root.

## Naming

- CLI command and distribution: `snowbot`
- Config filename: `snowbot.yaml`
- Display name: **SNOWBot**
- Setup branch in templates: `chore/snowbot-setup`

## Commands (Phase 1)

| Command | Phase 1 behavior |
| ------- | ---------------- |
| `snowbot doctor` | Basic Python + optional config validation |
| `snowbot init` | Stub |
| `snowbot run` | Stub |
| `snowbot update` | Stub |

## Development

```bash
pip install -e ".[dev]"
ruff check src tests && ruff format src tests
mypy
pytest --cov=snowbot --cov-fail-under=85
```

Use Conventional Commits. Update `CHANGELOG.md` (Unreleased) and `STATUS.md` when shipping user-visible changes.

## Secrets

- Prefer `CURSOR_API_KEY` in the environment; never commit secrets.
- Logging uses redaction filters — still treat logs as untrusted when debugging.

## Phases

Follow `STATUS.md` for phase boundaries. Do not implement later-phase adapters or orchestration inside Phase 1 PRs unless explicitly assigned.
