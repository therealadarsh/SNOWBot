# Independent validation workflow

Phase PRs must pass **independent validation** before they are marked ready for review.

## Roles

| Role | Context | Responsibility |
| ---- | ------- | -------------- |
| Implementer | Full task history | Code, tests, docs; run local ruff/mypy/pytest |
| Validator / **Senior Software Architect** | Fresh context only | Re-run gates; do not trust PR description |
| **CI `architect-gate`** | GitHub Actions on PR head | Same gates as the architect persona; blocks merge when required |

The architect agent **is** the validator: template `src/snowbot/templates/roles/architect.md.j2`, automation in `.github/workflows/architect-gate.yml`. No separate GitHub approval bot is required in [simple mode](GITHUB_SETUP.md).

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

## Merge gate

**Simple mode:** merge when required checks are green, including **`architect-gate`** — see [ARCHITECT_GATE.md](ARCHITECT_GATE.md). Optional human review; not a substitute for the architect CI job.

Emergency: label `skip-architect` (document why).
