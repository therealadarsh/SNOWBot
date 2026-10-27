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

## Pull requests

Use the PR template checklist. PR titles must follow Conventional Commits (see `.github/workflows/pr-title.yml`).

## Security

Report vulnerabilities privately per [SECURITY.md](SECURITY.md). Never commit API keys; use `CURSOR_API_KEY` locally.
