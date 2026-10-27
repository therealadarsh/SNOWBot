# Contributing to SNOWBot

Thank you for helping improve **SNOWBot**. This project uses Conventional Commits, pre-commit hooks, and CI gates on every pull request.

## Development setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Branch naming

- Feature work: `feat/<short-description>`
- Fixes: `fix/<short-description>`
- Chores/docs/CI: `chore/`, `docs/`, or `ci/` prefixes

Phase 1 landed on `feat/phase-1-scaffold`. Template setup branches in consumer repos use `chore/snowbot-setup`.

## Quality gates

Before opening a PR:

```bash
ruff check src tests && ruff format src tests
mypy
pytest --cov=snowbot --cov-fail-under=85
```

Rebase onto `main` and update `CHANGELOG.md` (Unreleased) and `STATUS.md` when behavior or scope changes.

## Independent validation

Implementers run local gates first. Before marking a PR **ready for review**, an independent validator (separate agent or human with fresh context) must run:

```bash
export SNOWBOT_VALIDATE_BASE=origin/main   # PR merge base
export PR_URL=https://github.com/therealadarsh/SNOWBot/pull/N
./scripts/independent_validate.sh
```

See [docs/INDEPENDENT_VALIDATION.md](docs/INDEPENDENT_VALIDATION.md). Do not trust the PR description alone.

## Anti-gaming

See [AGENTS.md](AGENTS.md). Governance changes (validator, checklist, CI, coverage/mypy/ruff config, `AGENTS.md`) belong in PRs labeled **`governance`** with CODEOWNERS approval — not mixed with feature PRs.

## Pull requests

Use the PR template checklist (validation verdict at top). PR titles must follow Conventional Commits (see `.github/workflows/pr-title.yml`).

**Merge policy:** human approval required; no auto-merge.

## Security

Report vulnerabilities privately per [SECURITY.md](SECURITY.md). Never commit API keys; use `CURSOR_API_KEY` locally.
