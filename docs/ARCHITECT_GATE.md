# Architect gate (CI merge validator)

`architect-gate` is a required check on `main` and `uat`. It judges a PR with the rules that are already on the PR's base branch, so a PR can't loosen the rules it is checked against.

## What it runs

1. Checks out the PR head (full history) and, separately, the PR's base commit.
2. Installs SNOWBot from the base commit into its own virtual environment. That copy's validator and `checklist.yaml` are the ones that run.
3. Resolves the phase:
   - from the branch name `feat/<phase>-<slug>`;
   - otherwise from exactly one `phase:<id>` label;
   - otherwise `1b` for non-feature branches (`governance/…`, `release/…`, Dependabot).
   A `feat/` branch that doesn't match the pattern fails.
4. Runs the phase checklist and the anti-gaming diff against the PR's base commit (`git diff <base>...HEAD`), and `snowbot status --check`. Results are collected as JSON: check ids with pass/fail, and anti-gaming finding codes.
5. Decides the verdict from those ids:
   - `fail`: any checklist check failed, any anti-gaming finding other than `governance_mixed_with_product`, `governance_mixed_with_product` on a non-governance branch, or `status --check` failed.
   - `pass_with_notes`: the only finding is `governance_mixed_with_product` on a `governance/` branch.
   - `pass`: nothing found.
6. A second job with `pull-requests: write` and no checkout posts the report as a PR comment. The comment is informational, not a GitHub approval.

Lint, types and tests run in the `CI` workflow, and `test-inventory` checks that no base test id disappeared.

There is no skip label.

## Related docs

- [INDEPENDENT_VALIDATION.md](INDEPENDENT_VALIDATION.md): the validator role and local commands
- [GITHUB_SETUP.md](GITHUB_SETUP.md): rulesets and check names
