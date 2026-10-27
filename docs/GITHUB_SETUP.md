# GitHub repository setup (owner)

Short checklist for settings that **only a repository admin** can change. Agents and CI tokens cannot complete these steps.

Repository: [therealadarsh/SNOWBot](https://github.com/therealadarsh/SNOWBot)

SNOWBot uses a **simple merge gate**: the **Senior Software Architect** role is enforced by CI (`architect-gate`), not by GitHub PR approval bots or PAT-driven review automation.

## Simple mode (recommended)

Configure the ruleset on **`main`** as follows:

| Setting | Value |
| ------- | ----- |
| Required pull request approvals | **0** |
| Require review from Code Owners | **Off** (optional; see strict mode below) |
| Require status checks | **On** (strict / up to date) |
| Required checks (exact names) | See table below |
| Auto-merge | Optional (squash); still requires all checks green |

### Required status checks

1. Open **Settings** → **Rules** → **Rulesets** (or **Branches** if using classic protection).
2. Edit the ruleset that targets **`main`**.
3. Under **Require status checks to pass**, add each check **by exact name** (after a PR run makes them appear in the picker):

| Check name | Workflow | Purpose |
| ---------- | -------- | ------- |
| `architect-gate` | architect-gate | Independent validator: lint, types, tests, `snowbot validate`, memory status |
| `test (3.11)` | CI | Python matrix |
| `test (3.12)` | CI | Python matrix |
| `test (3.13)` | CI | Python matrix |
| `conventional-commit` | PR Title | Conventional Commits title |
| `pip-audit` | Security | Dependency audit |
| `dependency-review` | Security | PR dependency diff (requires Dependency graph) |

Do **not** require PAT-based “architect bot” approvals. The architect persona is in `src/snowbot/templates/roles/architect.md.j2` and runs in CI.

### Emergency bypass

Label a PR `skip-architect` to skip the architect gate (incidents only; explain in the PR).

### Dependency graph (for `dependency-review`)

1. **Settings** → **Security** → **Code security and analysis**
2. Enable **Dependency graph**
3. [GitHub docs: dependency graph](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/configuring-the-dependency-graph)

Do **not** add `dependency-review` as a required ruleset check until the graph is enabled and a PR shows a green (non-skipped) dependency review. See [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md).

### Governance PRs

- Label: **`governance`**
- Default validation phase **`1b`** when no `phase:*` label or `Phase:` line in the PR body
- Owners squash-merge after checks are green; no separate approval token required in simple mode

See also [ARCHITECT_GATE.md](ARCHITECT_GATE.md) and [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md).

## Strict mode (teams)

If you prefer human CODEOWNERS review in addition to CI:

- Set required approving reviews to **1+**
- Enable **Require review from Code Owners** (see `.github/CODEOWNERS`)
- Label governance PRs **`governance`** for filtering
- CI **`architect-gate`** remains the independent technical validator

The **PR Title** workflow skips conventional-commit validation for `dependabot[bot]` / `app/dependabot` actors.

## Merge and approve

Only maintainers can approve CODEOWNERS-requested reviews and squash-merge to `main`. Agents may open and update PRs but should not merge governance changes without owner review.
