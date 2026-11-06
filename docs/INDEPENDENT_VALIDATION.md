# Independent validation workflow

Phase PRs must pass **independent validation** before they are marked ready for review.

## Roles

| Role | Context | Responsibility |
| ---- | ------- | -------------- |
| Implementer | Full task history | Code, tests, docs; run local ruff/mypy/pytest |
| Validator / **Senior Software Architect** | Fresh context only | Re-run gates; do not trust PR description |
| **CI `architect-gate`** | GitHub Actions, base validator against PR head | Checklist, anti-gaming diff and memory status; blocks merge when required |

The validator role template is `src/snowbot/templates/roles/validator.md.j2`; it ends with an output contract (a `VERDICT <nonce>: …` last line). The approver for consumer-repo tickets (phase `5`) uses `approver.md.j2`, which returns schema-checked JSON. CI automation is in `.github/workflows/architect-gate.yml` (see [ARCHITECT_GATE.md](ARCHITECT_GATE.md)).

## Validator inputs (allowlist)

- Repository checkout at the PR head
- Phase checklist (`snowbot validate --phase <id>`)
- `AGENTS.md`, `.snowbot/memory/VISION.md`, `PROGRESS.md`, `PLAYBOOK.md`
- Phase spec / `STATUS.md` scope for the phase id

Do **not** feed validator agents implementer reasoning or chat transcripts.

## Validator commands

```bash
export SNOWBOT_VALIDATE_BASE=origin/uat    # the PR's base: origin/uat for feat/*, origin/main for governance/*
export SNOWBOT_PHASE_ID=2b                 # from the feat/<phase>-<slug> branch name
export PR_URL=https://github.com/org/repo/pull/N
./scripts/independent_validate.sh
```

Or manually:

```bash
pip install -e ".[dev]"
ruff check src tests && ruff format --check src tests
mypy
pytest --cov=snowbot --cov-fail-under=85
snowbot validate --phase "$SNOWBOT_PHASE_ID" --base-ref "$SNOWBOT_VALIDATE_BASE" --pr "$PR_URL"
snowbot status --check
```

Then confirm no base test id disappeared (`test-inventory` does the same in CI):

```bash
pytest --collect-only -q -m "" | grep '::' | sort > /tmp/head.txt
# same command in a checkout of the base commit, into /tmp/base.txt
comm -23 /tmp/base.txt /tmp/head.txt   # must print nothing
```

## Outcomes

| Verdict | Action |
| ------- | ------ |
| `pass` | Mark PR ready; prepend validation block to PR description |
| `pass_with_notes` | Mark ready; include notes (e.g. documented bootstrap exception) |
| `fail` | Keep PR **draft**; write stop event + proposed lesson; fix (max 2 rounds) |

## Merge gate

Feature PRs merge into `uat` only through the orchestrator, after the validator passed the exact head commit and the required checks (`CI`, `architect-gate`, `test-inventory`) are green. Governance PRs and release PRs into `main` are merged by a person. There is no bypass label.
