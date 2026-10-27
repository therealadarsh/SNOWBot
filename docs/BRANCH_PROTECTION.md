# Branch protection (manual setup)

CI enforces quality gates, but GitHub **rulesets** and security settings must be configured in the repository UI (or via an admin token). Cloud agents and integration tokens **cannot** change rulesets, merge PRs, or toggle the dependency graph — the repo owner must do that.

See [GITHUB_SETUP.md](GITHUB_SETUP.md) for click-by-click steps.

## Recommended ruleset for `main`

Align the live ruleset with these settings:

| Setting | Value |
| ------- | ----- |
| Pull requests required | Yes |
| Required approving reviews | **1** |
| Require review from Code Owners | **Yes** (see `.github/CODEOWNERS`; label governance PRs `governance`) |
| Dismiss stale pull request approvals when new commits are pushed | **Yes** |
| Require conversation resolution before merging | **Yes** |
| Require branches to be up to date before merging (strict status checks) | **Yes** |
| Allowed merge methods | **Squash merge only** (disable merge commit and rebase if desired) |
| Force pushes / branch deletion | **Blocked** on `main` |

### Required status checks (exact job names)

Add these in the ruleset **Required checks** picker (names must match GitHub’s check labels):

| Check name |
| ---------- |
| `test (3.11)` |
| `test (3.12)` |
| `test (3.13)` |
| `conventional-commit` |
| `pip-audit` |

These correspond to workflow jobs:

- **CI** workflow → matrix jobs `test (3.11)`, `test (3.12)`, `test (3.13)`
- **PR Title** workflow → `conventional-commit`
- **Security** workflow → `pip-audit`

Do **not** require `dependency-review` until the dependency graph is enabled (see below). That job uses `continue-on-error: true` so PRs stay unblocked while the graph is off.

### Dependabot and PR titles

The **PR Title** workflow skips conventional-commit validation when `github.actor` is `dependabot[bot]` or `app/dependabot`, so Dependabot PRs are not failed by semantic title rules.

## Owner-only (cannot be done by agents)

The following require a human with admin access on **therealadarsh/SNOWBot**:

1. **Ruleset required checks** — Settings → Rules → rulesets → edit `main` ruleset → add the five check names above in the status checks UI.
2. **Dependency graph** — Settings → **Security** → **Code security and analysis** → enable **Dependency graph** (needed for `dependency-review` in `.github/workflows/security.yml` to be meaningful; optional as a required check until enabled).
3. **Approving and merging PRs** — especially governance changes covered by CODEOWNERS.
4. **Running `scripts/apply_branch_protection.sh`** with an admin `GH_TOKEN` — review the script first; default is dry-run only.

## Helper script

`scripts/apply_branch_protection.sh` documents equivalent `gh api` calls for legacy branch protection. Rulesets are preferred on new repos; use the UI steps in [GITHUB_SETUP.md](GITHUB_SETUP.md) when rulesets are already in use.

Requirements:

- `gh` CLI authenticated
- Token with admin rights on the repository

Review the script before executing locally.

## Dependabot

Enable Dependabot security updates and keep `.github/dependabot.yml` current so dependency PRs stay manageable alongside the checks above.
