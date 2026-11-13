# Branch protection

CI enforces the quality gates, but GitHub rulesets and security settings are configured by the repository owner in the UI (or with an admin token). Agents and integration tokens can't change rulesets, merge PRs, or toggle the dependency graph.

The settings for `main` and `uat`, with exact check names, are in [GITHUB_SETUP.md](GITHUB_SETUP.md). The rest of the owner checklist is in [OWNER_SETUP.md](OWNER_SETUP.md).

## Required checks

| Check | Workflow |
| ----- | -------- |
| `CI` | `.github/workflows/ci.yml` (aggregates every CI job) |
| `architect-gate` | `.github/workflows/architect-gate.yml` |
| `test-inventory` | `.github/workflows/ci.yml` |

## Owner-only

1. Rulesets and their required checks.
2. Dependency graph (Settings → Security → Code security and analysis).
3. Approving and merging PRs into `main`, especially governance changes covered by CODEOWNERS.
4. Running `scripts/apply_branch_protection.sh` with an admin `GH_TOKEN`. Review it first; it defaults to a dry run. Rulesets are preferred over the legacy branch protection it configures.

## Dependabot

Keep `.github/dependabot.yml` current. Dependabot PRs target `main` and touch governance files, so a person merges them.
