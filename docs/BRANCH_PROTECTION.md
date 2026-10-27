# Branch protection (manual setup)

CI enforces quality gates, but GitHub branch protection must be configured on the repository settings page (or via API). **Do not run `scripts/apply_branch_protection.sh` from automated agents without owner approval.**

## Recommended rules for `main`

1. Require a pull request before merging (1+ approving reviews for teams).
2. Require status checks to pass:
   - `CI / test (3.11)` (or all matrix jobs if required individually)
   - `Security / pip-audit`
   - `PR Title / conventional-commit`
3. Require branches to be up to date before merging.
4. Disallow force pushes and deletions on `main`.
5. Enable Dependabot security updates (`.github/dependabot.yml`).

## Helper script

`scripts/apply_branch_protection.sh` documents equivalent `gh api` calls. It requires:

- `GH_TOKEN` or `GITHUB_TOKEN` with admin rights
- `gh` CLI authenticated

Review the script before executing locally.
