# Independent validation workflow

Phase PRs must pass **independent validation** before they are marked ready for review.

## Roles

| Role | Context | Responsibility |
| ---- | ------- | -------------- |
| Implementer | Full task history | Code, tests, docs; run local ruff/mypy/pytest |
| Validator | Fresh context only | Re-run gates; do not trust PR description |

## Validator inputs (allowlist)

- Repository checkout at the PR head
- Phase checklist (`snowbot validate --phase <id>`)
- `AGENTS.md`, `.snowbot/memory/VISION.md`, `PROGRESS.md`, `PLAYBOOK.md`
- Phase spec / `STATUS.md` scope for the phase id

Do **not** feed validator agents implementer reasoning or chat transcripts.

## Validator commands

```bash
export SNOWBOT_VALIDATE_BASE=origin/main   # or merge-base of PR
export PR_URL=https://github.com/org/repo/pull/N
./scripts/independent_validate.sh
```

Or manually:

```bash
pip install -e ".[dev]"
ruff check src tests && ruff format --check src tests
mypy
pytest --cov=snowbot --cov-fail-under=85
snowbot validate --phase 1b --base-ref "$SNOWBOT_VALIDATE_BASE" --pr "$PR_URL"
snowbot status --check
```

## Outcomes

| Verdict | Action |
| ------- | ------ |
| `pass` | Mark PR ready; prepend validation block to PR description |
| `pass_with_notes` | Mark ready; include notes (e.g. documented bootstrap exception) |
| `fail` | Keep PR **draft**; write stop event + proposed lesson; fix (max 2 rounds) |

## Human merge gate

`merge_policy: human approval` — no auto-merge. Reviewers use the 2-minute template at the top of the PR (verdict, summary, risks).
