# Architect gate (CI merge validator)

## Model

| Concern | Mechanism |
| ------- | --------- |
| Independent technical validation | Required check **`architect-gate`** |
| Human / product sign-off | Optional; not required in **simple mode** ([GITHUB_SETUP.md](GITHUB_SETUP.md)) |
| GitHub PR “Approve” | Not used as the architect gate (no PAT review bots) |

The **Senior Software Architect** is a **persona** (see `src/snowbot/templates/roles/architect.md.j2`) whose rules are enforced by automation:

1. Checkout the PR head at full git depth (for anti-gaming diffs).
2. `pip install -e ".[dev]"`, then `ruff`, `mypy`, `pytest` with **≥85%** coverage.
3. `./scripts/independent_validate.sh` when that script exists on `main`, otherwise the same commands inline.
4. `snowbot validate --phase <id>` with phase from PR label `phase:1b` / `phase:2`, body line `Phase: 1b`, or default **`1b`** for **`governance`** PRs.

On success, the workflow may post a **summary comment** (informational only — **not** a GitHub approval).

On failure, the job exits **1** and blocks merge when the check is required.

## Skip label

`skip-architect` — emergency only; document rationale in the PR.

## Ruleset

In **Settings → Rules → Rulesets**, require status check **`architect-gate`** alongside the CI matrix, conventional commit title, `pip-audit`, and (when enabled) `dependency-review`.

## Related docs

- [INDEPENDENT_VALIDATION.md](INDEPENDENT_VALIDATION.md) — validator role and local commands
- [GITHUB_SETUP.md](GITHUB_SETUP.md) — owner checklist for simple mode
