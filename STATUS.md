# SNOWBot project status

**Display name:** SNOWBot  
**CLI / package:** `snowbot`  
**Config file:** `snowbot.yaml` (override with `SNOWBOT_CONFIG`)

## Phase overview

Phase ids are strings (`"1"`, `"1b"`, `"2"`, …). Phase **1b** is not phase **2** (doctor).

| Phase id | Scope | Status |
| -------- | ----- | ------ |
| `1` | Scaffold, models, errors, logging, tests, CI, repo meta | Merged on `main` |
| `1b` | Phase validator, lessons memory, architect gate | Merged on `main` |
| bootstrap | Governance for the unattended run (`AGENTS.md` merge policy, checklist, CI, `docs/OWNER_SETUP.md`) | In progress on `governance/autonomous-pipeline`. A person merges this PR before later phases continue. |
| `2b` | `snowbot impact` (git history, undoes-fix, callers, reports) | Not started |
| `2` | `snowbot doctor` environment and agent-CLI checks | Not started |
| `4` | `snowbot login`, `snowbot init`, shell, role templates with output contracts | Not started |
| `3` | Headless backends: Cursor CLI, Claude Code, Codex, in Docker | Not started |
| `5` | `snowbot run`: ticket pipeline, approval log, merge to `uat` | Not started |
| `5b` | GitHub Issues and ServiceNow intake | Not started |
| `7` | Sample app UAT deploy (AWS CDK, skipped without a role) | Not started |
| `8` | `snowbot ui` local dashboard | Not started |
| `2c` | `snowbot ask`, `snowbot drift` | Not started |
| `6` | `snowbot update`, release workflow, CI for impact and UI | Not started |
| `9` | `snowbot serve` hosted worker | Not started |

Order in the table after bootstrap is the build order.

## Phase 1b deliverables (current)

- Shared memory tree under `.snowbot/memory/` (vision, state, lessons, validation, stops, generated playbook).
- String phase ids in CLI, checklist, reports, and `state.json`.
- `snowbot validate --phase <id> [--base-ref …]`, lesson/playbook/onboard commands, `snowbot status --check`.
- Anti-gaming diff checks; independent validation script (`scripts/independent_validate.sh`).
- Lesson admission: `INDEX.yaml` has one entry per lesson; `lesson accept` requires evidence that resolves to a file, pull request, or stop event; playbook generation drops lessons that contradict AGENTS.md safety rules.
- Governance paths in CODEOWNERS; PR template validation block.
- **Architect merge gate:** CI job `architect-gate` (Senior Software Architect validator); see `docs/ARCHITECT_GATE.md` and `docs/GITHUB_SETUP.md` (simple mode: no PAT approval bots).

**Bootstrap:** `governance/autonomous-pipeline` is the governance PR the unattended run waits on. Feature work after it stays off governance paths. The historical phase `1b` PR mixed governance and product once; that exception does not extend to later feature PRs.

## Bootstrap deliverables

- `AGENTS.md` with the `uat` merge policy; CODEOWNERS and the validator's governance paths match its governance list.
- `checklist.yaml` entries for every phase in the table. Each phase checks the module its first PR creates, `CHANGELOG.md`, `STATUS.md` and the anti-gaming diff.
- Dependencies for every phase in `pyproject.toml` (`ui` and `aws` extras; `hypothesis`, `jsonschema`, `pytest-playwright`, `boto3-stubs` in `dev`) and `infra/requirements.txt` with hashes.
- Pytest markers `ui`, `docker`, `aws` and `integration` are deselected by default. CI runs `pytest -m ui` and `pytest -m docker` in their own jobs; `aws` and `integration` tests run only by hand.
- Required checks `CI`, `architect-gate` and `test-inventory`; `deploy-uat` workflow; approver and validator role templates with output contracts.

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
| `CURSOR_API_KEY` | Cursor CLI (factory now, phase `3`) | Dashboard key. `CURSOR_AUTH_TOKEN` is the CLI login token and works in Docker the same way. |
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code builder (phase `3`) | From `claude setup-token` |
| `GEMINI_API_KEY` | Approver when Gemini is the other vendor | Not read by the phase `1` CLI |
| `SNOWBOT_BACKEND` | No | Override `backend.kind` in config |
| `SNOWBOT_CONFIG` | No | Path to YAML config (default `./snowbot.yaml`) |
| `SNOWBOT_VALIDATE_BASE` | No | Git ref for anti-gaming diff during validate |

## Consumer repo conventions

- Setup branch name in templates/docs: `chore/snowbot-setup`
- Agent guidance file: `AGENTS.md`
- Shared memory directory: `.snowbot/memory/`

## Governance (repo admin)

Branch rules, required checks, Dependency graph, labels, and agent credentials are documented for the owner in [docs/OWNER_SETUP.md](docs/OWNER_SETUP.md). Today's `main` clicks are also in [docs/BRANCH_PROTECTION.md](docs/BRANCH_PROTECTION.md) and [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md). Agents cannot edit GitHub rulesets or merge governance PRs.

## Research harness

Not a phase id. Draft package `research/` holds task fixtures, condition arms, an independent path/pattern outcome oracle, a cell runner, a hashed manifest, and extract tables for a later gate-weakening study. No pilot or main-study model run is executed here. The outcome measure is not `anti_gaming_diff`. The pinned scanner commit is metadata in `research/configs/oracle_rules.yaml`.

Version registry, drift check, archiver, and stability evaluation live under `research/` (`versions/current/VERSION`, `drift-check`, `archive`, `stability`, `STATUS.json`, `ledger.json`). The committed schedule is `paused` (`version_state: current`, `kill: false`, fix-attempt counter `0`). Drift checks do not open pull requests or spend money. Stability is evaluated from recorded inputs and does not mark the committed status `stable`. No pilot or paid model run is executed here. A workflow that would launch the harness is intentionally absent; Docker image digests stay `unpinned` (drift treats that as outdated) because no digest was available to pin.

## Open questions

See [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md). The Cursor REST client is not a planned backend.
