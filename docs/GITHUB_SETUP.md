# GitHub repository setup (owner)

Settings that only a repository admin can change. Agents and CI tokens can't do these steps. The full owner checklist (the unattended build, labels, credentials, optional AWS) is [OWNER_SETUP.md](OWNER_SETUP.md).

Repository: [therealadarsh/SNOWBot](https://github.com/therealadarsh/SNOWBot)

The independent technical check is CI (`architect-gate`), not GitHub approval bots or PAT-driven review automation.

## Rulesets on `main` and `uat`

Settings → Rules → Rulesets. Create one ruleset per branch.

| Setting | `main` | `uat` |
| ------- | ------ | ----- |
| Require a pull request | Yes | Yes |
| Required approvals | 0, or 1+ with Code Owners review (strict mode below) | 0 |
| Required checks | `CI`, `architect-gate`, `test-inventory` | Same |
| Require branches to be up to date | Optional | Yes |
| Allowed merge method | Merge commits | Merge commits |
| Block force pushes and deletions | Yes | Yes |
| Bypass actors | None | None |
| Restrict creations | No | No (the loop creates `uat`) |

Add each check by exact name. A name shows up in the picker after it has run once on a PR.

| Check | Workflow | What it does |
| ----- | -------- | ------------ |
| `CI` | CI | Passes only when every CI job passed: tests on 3.11 to 3.13, wheel build, `ui` and `docker` marker tests, `cdk synth` once `infra/` has an app |
| `architect-gate` | architect-gate | Validator and checklist from the PR base, run against the PR head |
| `test-inventory` | CI | Fails when a base test id is missing on the head |

`conventional-commit`, `pip-audit` and `dependency-review` also run on every PR. The loop treats any failing check as a CI failure, so they block `uat` merges without being required in the ruleset.

There is no bypass label for `architect-gate`.

## Dependency graph (for `dependency-review`)

1. Settings → Security → Code security and analysis.
2. Enable Dependency graph.

`dependency-review` is blocking and fails while the graph is off. [GitHub docs: dependency graph](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/configuring-the-dependency-graph)

## Governance PRs

- Branch `governance/<slug>` from `main`, label `governance`.
- `architect-gate` uses phase `1b` for non-feature branches unless the PR has exactly one `phase:<id>` label.
- A person merges them.

## Strict mode (teams)

- Required approving reviews: 1 or more.
- Require review from Code Owners (see `.github/CODEOWNERS`).
- `architect-gate` stays the independent technical check.

The PR Title workflow skips conventional-commit validation for `dependabot[bot]` and `app/dependabot`.

## Labels

Create `governance` and `needs-human` if they are missing.
