# SNOWBot project status

**Display name:** SNOWBot  
**CLI / package:** `snowbot`  
**Config file:** `snowbot.yaml` (override with `SNOWBOT_CONFIG`)

## Phase overview

| Phase | Scope | Status |
| ----- | ----- | ------ |
| 1 | Scaffold, models, errors, logging, tests, CI, repo meta | In review (PR #1) |
| 1b | Phase validator + shared lessons memory | In progress |
| 2 | `doctor` command and environment checks | Not started |
| 3 | Backend adapters (Cursor first) | Not started |
| 4 | `init`, VCS, Jinja2 templates | Not started |
| 5 | `run` pipeline orchestrator | Not started |
| 6 | `update`, hardening, release docs | Not started |

## Phase 1b deliverables (current)

- Shared memory tree under `.snowbot/memory/` (vision, state, lessons, validation, stops, generated playbook).
- `snowbot validate --phase N`, `snowbot lesson …`, `snowbot playbook`, `snowbot onboard`, `snowbot status check`.
- Packages: `snowbot.validator`, `snowbot.lessons`, `snowbot.memory`, pipeline stage hooks and role templates.
- Stop-event capture for validator failure, gate rejection, retries, CI failure, and human lesson adds.
- CI runs `snowbot status --check` after tests.

## Phase 1 deliverables (baseline)

- Editable install: `pip install -e ".[dev]"`.
- CLI entrypoint `snowbot` with subcommands:
  - `doctor` — Python version + optional config load (expanded in Phase 2).
  - `init`, `run`, `update` — **stubs** exiting with code `2` and a Phase 1 message.
- Models under `src/snowbot/models/` for config, pipeline spec, and backlog YAML.
- Secret redaction in `snowbot.logging_setup`.
- Tests under `tests/` with ≥85% coverage enforced in CI.

## Environment variables

| Variable | Required | Purpose |
| -------- | -------- | ------- |
| `CURSOR_API_KEY` | For Cursor backend (Phase 3+) | API authentication |
| `SNOWBOT_BACKEND` | No | Override `backend.kind` in config |
| `SNOWBOT_CONFIG` | No | Path to YAML config (default `./snowbot.yaml`) |

## Consumer repo conventions

- Setup branch name in templates/docs: `chore/snowbot-setup`
- Agent guidance file: `AGENTS.md`
- Shared memory directory: `.snowbot/memory/`

## Open questions

See [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) for unverified Cursor API details.
