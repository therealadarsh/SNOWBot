# SNOWBot

**SNOWBot** is a CLI you install in a git repository. It takes work from a GitHub issue, a ServiceNow incident, or a sentence in its shell, plans and builds it with agents, has a different model approve it after CI, and merges into `uat`. A person approves the release from `uat` to `main`.

Phases `1` and `1b` are on `main`: packaging, config models, CI, the phase validator, and lessons memory. `init`, `run`, and `update` are stubs until later phases. The impact tool and the ticket pipeline are not in this install yet. Phase status is in [STATUS.md](STATUS.md). Owner steps (GitHub rulesets, credentials, the unattended build) are in [docs/OWNER_SETUP.md](docs/OWNER_SETUP.md).

## Requirements

- Python 3.11+
- `git`, and `gh` when you want the unattended build to open pull requests
- Optional, phase `3` and later: a headless agent CLI (Cursor, Claude Code, or Codex) plus an API key or setup token. Chat panes in VS Code, Cursor, and Gemini are not backends. See [docs/OWNER_SETUP.md](docs/OWNER_SETUP.md).

## Quick start

```bash
pip install -e ".[dev]"
snowbot --help
snowbot doctor
snowbot validate --phase 1b
```

On a machine that uses the `snakeenv` conda env, call that env's Python instead of creating a virtualenv.

Configuration lives in [`snowbot.yaml`](snowbot.yaml) at the repository root (override path with `SNOWBOT_CONFIG`). Optional `SNOWBOT_BACKEND` overrides the configured backend kind.

## Commands

| Command | Description |
| ------- | ----------- |
| `doctor` | Python version and optional config load. Fuller environment checks arrive in phase `2`. |
| `validate` | Phase checklist and anti-gaming diff (`--phase`, `--base-ref`) |
| `lesson`, `playbook`, `onboard`, `status` | Shared lessons memory (phase `1b`) |
| `init` | Stub. Scaffold a consumer repo in phase `4`. |
| `run` | Stub. Ticket pipeline in phase `5`. |
| `update` | Stub. Refresh consumer templates in phase `6`. |

Agent rules: [AGENTS.md](AGENTS.md).

## Development

```bash
ruff check src tests && ruff format src tests
mypy
pytest --cov=snowbot --cov-fail-under=85
pre-commit install
```

## License

See repository license terms when published. Contributing and security policies: [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md).
