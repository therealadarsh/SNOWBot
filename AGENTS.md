# AGENTS.md — SNOWBot repository

Guidance for humans and coding agents working in **SNOWBot** (`therealadarsh/SNOWBot`).

## Project intent

SNOWBot is a backend-agnostic CLI that installs and runs an agent pipeline in any codebase. Phase **1** establishes Python packaging, configuration models, tests, and automation. Phase **1b** adds the phase validator and shared lessons memory.

## Phase identifiers

Phase ids are **strings**: `"1"`, `"1b"`, `"2"`, … — never use integer `2` to mean Phase 1b. Doctor/expansion work is phase `"2"`.

CLI: `snowbot validate --phase 1b`

## Layout (repo root)

```
src/snowbot/          # Python package
tests/                # Mirrors src layout
docs/                 # Specs, ADRs, open questions
.github/              # CI, templates, Dependabot
scripts/              # Maintenance scripts (branch protection helper)
snowbot.yaml          # Example config for this repo
.snowbot/memory/      # Shared pipeline memory (Phase 1b+)
```

Do **not** introduce a nested `SNOWBot/` directory; everything lives at the repository root.

## Naming

- CLI command and distribution: `snowbot`
- Config filename: `snowbot.yaml`
- Display name: **SNOWBot**
- Setup branch in templates: `chore/snowbot-setup`

## Shared memory (Phase 1b+)

Consumer repos keep pipeline memory under `.snowbot/memory/` (vision, lessons, validation reports, stops, generated `PLAYBOOK.md`). Lessons are **data only** — never execute lesson YAML. AGENTS.md safety rules beat accepted lessons beat proposed lessons.

## Independent validation (required before ready-for-review)

After implementer passes local gates, a **separate validator** (fresh context; different model when available) must run before marking a PR ready:

1. Inputs allowlist: repo, phase spec/`STATUS.md`, `AGENTS.md`, `VISION.md`, `PROGRESS.md`, `PLAYBOOK.md` — **not** implementer chat reasoning.
2. Run `./scripts/independent_validate.sh` (or equivalent commands in `docs/INDEPENDENT_VALIDATION.md`).
3. Validator runs `snowbot validate --phase <id> --base-ref <merge-base>` plus full ruff/mypy/pytest/coverage and `snowbot status --check`.
4. **Fail:** keep PR draft, stop event + proposed lesson, max two fix rounds.
5. **Pass / pass_with_notes:** prepend verdict + checks + notes to PR description; then mark ready.

Merge policy: **human approval only** — no auto-merge.

## Anti-gaming (mandatory)

- Do **not** delete, skip, xfail, or weaken tests to pass — fix product code.
- Do **not** lower coverage thresholds or strictness in ruff/mypy/CI; no broad ignores without governance review.
- Do **not** mock away the behavior under test or hardcode outputs / test-detection branches.
- Do **not** edit validator, `checklist.yaml`, CI workflows, test/coverage config, or `AGENTS.md` in the same PR as feature work — use a **`governance`**-labeled PR with CODEOWNERS approval.
- Honest fail beats gamed pass — document in PR/`STATUS.md` when a gate cannot pass honestly.

Validator enforces diff checks (`anti_gaming_diff`) for threshold drops, skips, deleted tests, hardcoded test branches, and governance/product mixing.

## Commands (Phase 1–1b)

| Command | Behavior |
| ------- | -------- |
| `snowbot doctor` | Basic Python + optional config validation |
| `snowbot validate --phase <id>` | Phase checklist + anti-gaming diff (use `--base-ref`) |
| `snowbot lesson add\|list\|show\|accept\|retire\|promote` | Lessons store with evidence required |
| `snowbot playbook` | Generate capped playbook from accepted lessons |
| `snowbot onboard --stage …` | Render stage role onboard packs |
| `snowbot status --check` | Memory structure and INDEX/PLAYBOOK freshness |
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
