# GitHub repository setup (owner)

Repository: [therealadarsh/SNOWBot](https://github.com/therealadarsh/SNOWBot)

SNOWBot uses a **simple merge gate**: the **Senior Software Architect** role is enforced by CI (`architect-gate`), not by GitHub PR approval bots or PAT-driven review automation.

## Simple mode (recommended)

Configure the ruleset on **`main`** as follows:

| Setting | Value |
| ------- | ----- |
| Required pull request approvals | **0** |
| Require review from Code Owners | **Off** (optional; see below) |
| Require status checks | **On** (strict / up to date) |
| Required checks (exact names) | See table below |
| Auto-merge | Optional (squash); still requires all checks green |

### Required status checks

Add these **by exact job name** after they appear on a PR (open a draft PR once if names are missing from the picker):

| Check name | Workflow | Purpose |
| ---------- | -------- | ------- |
| `architect-gate` | Architect Gate | Independent validator: lint, types, tests, `snowbot validate`, memory status |
| `test (3.11)` | CI | Python matrix |
| `test (3.12)` | CI | Python matrix |
| `test (3.13)` | CI | Python matrix |
| `conventional-commit` | PR Title | Conventional Commits title |
| `pip-audit` | Security | Dependency audit |
| `dependency-review` | Security | PR dependency diff (requires Dependency graph) |

Do **not** require PAT-based “architect bot” approvals. The architect persona is documented in `src/snowbot/templates/roles/architect.md.j2` and executed in CI.

### Emergency bypass

Label a PR `skip-architect` to skip the architect gate (incidents only; explain in the PR).

### Dependency graph (for `dependency-review`)

1. **Settings** → **Security** → **Code security and analysis**
2. Enable **Dependency graph**
3. [GitHub docs: dependency graph](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/configuring-the-dependency-graph)

### Governance PRs

- Label: **`governance`**
- Filter in the PR list; default validation phase **`1b`** when no `phase:*` label or `Phase:` line in body
- Owners squash-merge after checks are green; no separate approval token required in simple mode

See also [ARCHITECT_GATE.md](ARCHITECT_GATE.md) and [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md).

## Strict mode (teams)

If you prefer human CODEOWNERS review in addition to CI, enable **Require review from Code Owners** and set approvals to **1+**. CI `architect-gate` remains the independent technical validator.
