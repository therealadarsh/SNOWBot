# GitHub repository setup (owner)

Short checklist for settings that **only a repository admin** can change. Agents and CI tokens cannot complete these steps.

Repository: [therealadarsh/SNOWBot](https://github.com/therealadarsh/SNOWBot)

## 1. Ruleset required status checks

1. Open **Settings** → **Rules** → **Rulesets** (or **Branches** if using classic protection).
2. Edit the ruleset that targets **`main`**.
3. Under **Require status checks to pass** (strict / “require branches to be up to date”):
   - Search and add each required check **by exact name**:
     - `test (3.11)`
     - `test (3.12)`
     - `test (3.13)`
     - `conventional-commit`
     - `pip-audit`
4. Confirm other rules match [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md) (1 approval, code owners, squash-only merge, dismiss stale reviews, resolve all threads).

After the first successful run on a PR, check names appear in the picker. If a name is missing, push a branch and open a PR so workflows run once, then refresh the ruleset UI.

## 2. Enable Dependency graph (optional but recommended)

Required for the **Security / dependency-review** job to analyze PR dependency changes.

1. **Settings** → **Security** → **Code security and analysis**
2. Enable **Dependency graph**
3. Documentation: [Enabling the dependency graph](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/configuring-the-dependency-graph)

Do **not** add `dependency-review` as a required ruleset check until this is enabled and a PR shows a green (non-skipped) dependency review. See [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md).

## 3. CODEOWNERS and governance PRs

- `.github/CODEOWNERS` assigns `@therealadarsh` on governance paths (workflows, `pyproject.toml`, `AGENTS.md`, etc.).
- Turn on **Require review from Code Owners** in the same ruleset.
- Label governance PRs with **`governance`** for filtering in the PR list.

## 4. Merge and approve

Only maintainers can approve CODEOWNERS-requested reviews and squash-merge to `main`. Agents may open and update PRs but should not merge governance changes without owner review.
