# SNOWBot project status

**Display name:** SNOWBot  
**CLI / package:** `snowbot`  
**Config file:** `snowbot.yaml` (override with `SNOWBOT_CONFIG`)

## Phase overview

Phase ids are strings (`"1"`, `"1b"`, `"2"`, …). Phase **1b** is not phase **2** (doctor).

| Phase id | Scope | Status |
| -------- | ----- | ------ |
| `1` | Scaffold, models, errors, logging, tests, CI, repo meta | In review (PR #1) |
| `1b` | Phase validator + shared lessons memory | In progress (PR #2) |
| `2` | `doctor` command and environment checks | Not started |
| `3` | Backend adapters (Cursor first) | Not started |
| `4` | `init`, VCS, Jinja2 templates | Not started |
| `5` | `run` pipeline orchestrator | Not started |
| `6` | `update`, hardening, release docs | Not started |

## Phase 1b deliverables (current)

- Shared memory tree under `.snowbot/memory/` (vision, state, lessons, validation, stops, generated playbook).
- String phase ids in CLI, checklist, reports, and `state.json`.
- `snowbot validate --phase <id> [--base-ref …]`, lesson/playbook/onboard commands, `snowbot status --check`.
- Anti-gaming diff checks; independent validation script (`scripts/independent_validate.sh`).
- Lesson admission: `INDEX.yaml` has one entry per lesson; `lesson accept` requires evidence that resolves to a file, pull request, or stop event; playbook generation drops lessons that contradict AGENTS.md safety rules.
- Governance paths in CODEOWNERS; PR template validation block.
- **Architect merge gate:** CI job `architect-gate` (Senior Software Architect validator); see `docs/ARCHITECT_GATE.md` and `docs/GITHUB_SETUP.md` (simple mode: no PAT approval bots).

**Bootstrap note (PR #2):** This PR introduces governance and product changes together. Independent validation may report `governance_mixed_with_product` — documented exception; future feature PRs must split governance.

## Phase 1 deliverables (baseline)

- Editable install: `pip install -e ".[dev]"`.
- CLI entrypoint `snowbot` with subcommands:
  - `doctor` — Python version + optional config load (expanded in phase `2`).
  - `init`, `run`, `update` — **stubs** exiting with code `2`.
- Models under `src/snowbot/models/` for config, pipeline spec, and backlog YAML.
- Secret redaction in `snowbot.logging_setup`.
- Tests under `tests/` with ≥85% coverage enforced in CI.

## Environment variables

| Variable | Required | Purpose |
| -------- | -------- | ------- |
| `CURSOR_API_KEY` | For Cursor backend (Phase 3+) | API authentication |
| `SNOWBOT_BACKEND` | No | Override `backend.kind` in config |
| `SNOWBOT_CONFIG` | No | Path to YAML config (default `./snowbot.yaml`) |
| `SNOWBOT_VALIDATE_BASE` | No | Git ref for anti-gaming diff during validate |

## Consumer repo conventions

- Setup branch name in templates/docs: `chore/snowbot-setup`
- Agent guidance file: `AGENTS.md`
- Shared memory directory: `.snowbot/memory/`

## Governance (repo admin)

Branch rules, required checks, and Dependency graph are documented for the owner in [docs/BRANCH_PROTECTION.md](docs/BRANCH_PROTECTION.md) and [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md). Agents cannot edit GitHub rulesets or merge governance PRs.

## Open questions

See [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) for unverified Cursor API details.
