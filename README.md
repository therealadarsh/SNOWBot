# SNOWBot

**SNOWBot** is a backend-agnostic CLI that installs and runs an agent pipeline in any code project. Phase 1 provides the Python scaffold, configuration models, tests, and CI — command stubs point to later phases.

## Requirements

- Python 3.11+
- Optional: [`CURSOR_API_KEY`](https://cursor.com) for Cursor backend integration (Phase 3+)

## Quick start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
snowbot --help
snowbot doctor
```

Configuration lives in [`snowbot.yaml`](snowbot.yaml) at the repository root (override path with `SNOWBOT_CONFIG`). Optional `SNOWBOT_BACKEND` overrides the configured backend kind.

## Commands

| Command | Description |
| ------- | ----------- |
| `doctor` | Environment and config sanity checks |
| `init` | Scaffold SNOWBot in a target repo (Phase 4) |
| `run` | Execute the pipeline (Phase 5) |
| `update` | Refresh templates and assets (Phase 6) |

See [STATUS.md](STATUS.md) for phase boundaries and [AGENTS.md](AGENTS.md) for contributor/agent guidance.

## Development

```bash
ruff check src tests && ruff format src tests
mypy
pytest --cov=snowbot --cov-fail-under=85
pre-commit install
```

## License

See repository license terms when published. Contributing and security policies: [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md).
