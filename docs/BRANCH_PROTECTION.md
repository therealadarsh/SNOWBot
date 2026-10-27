# Branch protection (manual setup)

CI enforces quality gates, but GitHub rulesets must be configured on the repository settings page (or via API). **Do not run `scripts/apply_branch_protection.sh` from automated agents without owner approval.**

## Simple mode (recommended)

See **[GITHUB_SETUP.md](GITHUB_SETUP.md)** for the full owner checklist:

- **0** required PR approvals (architect validation is CI, not GitHub “Approve”)
- Required checks include **`architect-gate`**, CI test matrix, `conventional-commit`, `pip-audit`, and (when enabled) `dependency-review`
- Optional squash auto-merge after all checks pass

## Classic / strict rules for `main`

1. Require a pull request before merging (add 1+ approvals if your team wants human review in addition to CI).
2. Require status checks to pass (exact names):
   - `architect-gate`
   - `test (3.11)`, `test (3.12)`, `test (3.13)`
   - `conventional-commit`
   - `pip-audit`
   - `dependency-review` (after Dependency graph is enabled)
3. Require branches to be up to date before merging.
4. Disallow force pushes and deletions on `main`.
5. Enable Dependabot security updates (`.github/dependabot.yml`).

## Helper script

`scripts/apply_branch_protection.sh` documents equivalent `gh api` calls. It requires:

- `GH_TOKEN` or `GITHUB_TOKEN` with admin rights
- `gh` CLI authenticated

Review the script before executing locally.
