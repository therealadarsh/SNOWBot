# Owner setup

Checklist for the person who owns `therealadarsh/SNOWBot`. Agents cannot change GitHub rulesets, merge into `main`, or create cloud accounts. Click-by-click ruleset steps for today's `main` branch also live in [GITHUB_SETUP.md](GITHUB_SETUP.md) and [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md).

## What you can do today

| Piece | Status |
| ----- | ------ |
| `snowbot doctor`, `snowbot validate`, lessons, playbook | On `main` (phases `1` and `1b`) |
| `snowbot init`, `snowbot run`, `snowbot update` | Stubs. They exit with code 2 until phases `4`, `5`, and `6`. |
| Impact tool, role pipeline, `snowbot login` | Not built yet. The unattended run below is building them. |
| `docs/OWNER_SETUP.md` | This file. The bootstrap PR is expected to keep it current. |

Install the CLI that exists now:

```bash
pip install -e ".[dev]"
snowbot doctor
snowbot validate --phase 1b
```

On this machine, run Python tools inside the conda env `snakeenv` (`/opt/anaconda3/envs/snakeenv/bin/python`).

## Unattended build of SNOWBot itself

`docs/research/impact-run/run_loop.py` (gitignored) drives the build. It feeds prompts to a builder agent and a different-vendor validator. You do not paste a prompt into chat. The agent runs in Docker with no GitHub credentials. The loop, on your Mac, pushes and opens PRs.

Do this once, from the repo root, on a clean `main`:

1. Start Docker Desktop and wait until the daemon answers.
2. Build the sandbox:

   ```bash
   docker build -t snowbot-agent --build-arg WITH_CURSOR=1 --build-arg WITH_BROWSER=1 docs/research/impact-run/agent-sandbox
   ```

3. Install Cursor's CLI (`curl https://cursor.com/install -fsS | bash`) and put `~/.local/bin` on `PATH`. Sign in with `cursor agent login`, or create a key in the Cursor dashboard.
4. Confirm `gh auth status` shows the GitHub account that can push this repo.
5. List model slugs (`cursor agent --list-models`) and export them. Do not use `auto`.

   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   export CURSOR_API_KEY='<dashboard key>'
   # If you signed in with `cursor agent login` and have no dashboard key, the macOS
   # keychain token works in place of CURSOR_API_KEY:
   # export CURSOR_AUTH_TOKEN=$(security find-generic-password -s cursor-access-token -a cursor-user -w)
   export HEAVY_MODEL='<Claude Opus 5.5 slug>'
   export LIGHT_MODEL='<Claude Sonnet 5.5 slug>'
   export VALIDATOR_MODEL='<a GPT or Gemini slug, different from the two above>'
   export SANDBOX='docker run --rm -i -v {workdir}:/work -v snowbot-agent-home:/home/agent -e CURSOR_API_KEY --mount type=bind,src={workdir}/docs/research/prompts,dst=/work/docs/research/prompts,readonly --mount type=bind,src={workdir}/docs/research/specs,dst=/work/docs/research/specs,readonly --mount type=bind,src={workdir}/docs/research/impact-run/run_loop.py,dst=/work/docs/research/impact-run/run_loop.py,readonly snowbot-agent'
   export AGENT_CMD="$SANDBOX cursor-agent -p --force --model {model} --output-format text {prompt}"
   export VALIDATOR_CMD='docker run --rm -i -v {workdir}:/work -v snowbot-validator-home:/home/agent -e CURSOR_API_KEY --mount type=bind,src={repo}/docs/research/specs,dst=/work/docs/research/specs,readonly snowbot-agent cursor-agent -p --force --model {model} --output-format text {prompt}'
   ```

   When using the keychain token, change both `-e CURSOR_API_KEY` mounts to `-e CURSOR_AUTH_TOKEN`. Check `cursor-agent --help` first. If `-p`, `--force`, `--model`, or `--output-format` were renamed, use the names `--help` prints.

6. Start or resume:

   ```bash
   /opt/anaconda3/envs/snakeenv/bin/python docs/research/impact-run/run_loop.py --max-hours 12
   ```

Exports last for that terminal only. Re-running the same command resumes. Progress is in `docs/research/impact-run/RUN_STATE.json` and `PROGRESS.md`.

| Exit code | Meaning |
| --------- | ------- |
| 0 | Finished. Read `docs/research/impact-run/FINAL_REPORT.md`. |
| 1 | Agent hard stop. Read `stop_reason` in `RUN_STATE.json`. |
| 2 | A guard stopped the run. |
| 3 | Time or iteration cap. Re-run to continue. |
| 4 | Setup problem. The message says what to fix. |
| 5 | A CLI failed before doing work (often auth). |
| 6 | Waiting for you. Do the steps it prints, then re-run. |

The one pause near the start (exit 6) is the bootstrap governance PR. Review it, merge it to `main`, and add the two rulesets below. The loop checks those through the GitHub API and will not continue until they exist.

## Rulesets the build waits for

Settings → Rules → Rulesets. Block force pushes and deletions. No bypass actors.

**`main`**

- Require a pull request.
- Required checks: `CI`, `architect-gate`, `test-inventory`. GitHub lists a check name only after it has run once; the bootstrap PR's own runs make all three appear.
- Allow merge commits. Release PRs (`release/<date>` → `main`) use merge commits only.

**`uat`**

- Require a pull request.
- Require the same three checks.
- Require branches to be up to date before merging.
- Allow merge commits. The loop merges with `--merge --match-head-commit` and puts `Snowbot-*` trailers on the merge commit.
- Do not enable "restrict creations". The loop creates `uat` from `main` after the bootstrap merge.

`CI` is one job that passes only when every CI job passed (Python 3.11 to 3.13 tests, the wheel build, `ui` and `docker` marker tests, and `cdk synth` once `infra/cdk.json` exists). `test-inventory` fails when any test id on the base branch is missing on the PR head. `architect-gate` runs the validator and checklist from the PR's base commit against the PR head; there is no skip label.

People merge `main`. The loop is the only thing that merges into `uat`.

## Labels and security settings

Create these labels:

| Label | Use |
| ----- | --- |
| `governance` | PRs that change validator, CI, `AGENTS.md`, templates, or other governance paths |
| `needs-human` | Impact risk gate stopped an auto-merge to `uat` (phase `5`) |

Enable Dependency graph: Settings → Code security and analysis → Dependency graph. The `dependency-review` job is blocking from the bootstrap PR on, and it fails while the graph is off. The loop treats any failing check as a CI failure, so feature PRs can't merge into `uat` until the graph is on.

## Credentials for agents

Chat windows are not backends. VS Code Copilot Chat (personal or enterprise), the Cursor sidebar, and the Gemini chat box stay for you. The pipeline calls a headless CLI or an API and stores the verdict.

`snowbot login` (phase `4`) will keep tokens in the OS keychain under service `snowbot`. Until that command exists, export the token in the shell that starts the run. Never commit a key.

| Backend | When | What to set |
| ------- | ---- | ----------- |
| Cursor CLI | Builder. Used by the factory now. Phase `3` wraps it. | `CURSOR_API_KEY`, or `CURSOR_AUTH_TOKEN` after `cursor agent login` |
| Claude Code | Builder. Phase `3`. | `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` |
| Codex / OpenAI | Builder. Phase `3`. | OpenAI API key |
| Gemini (or another non-builder vendor) | Approver. One JSON call, no tools. | `GEMINI_API_KEY`, or the vendor key you pick as `VALIDATOR_MODEL` |
| VS Code + Copilot subscription | Not a backend. The IDE login does not give this CLI a programmable agent. | Use Copilot CLI or GitHub Models only if the org allows that token in Docker. Many enterprises allow only their own endpoint (Azure OpenAI, Bedrock, GitHub Models). |

The approver must be a different vendor from the builder. If only one vendor is available, phase `5` will allow a different model from that vendor and will record that in the audit log.

A Linux container cannot read the macOS keychain. `snowbot login` and the factory both pass an exportable token in the environment. The container does not get `gh`, a GitHub token, or SSH keys.

## Optional later setup

Skip these until the matching phase says they are required. The build still proceeds without them.

| Item | Phase | Notes |
| ---- | ----- | ----- |
| AWS account for UAT | `7` | See "UAT on AWS" below. No role means the deploy workflow skips. The sample app is not production. |
| ServiceNow OAuth app | `5b` | Read incidents and write work notes for one assignment group. |
| PyPI trusted publisher | `6` | Release workflow is human-triggered. |

### UAT on AWS (phase `7`, optional)

1. Use a separate AWS account for UAT. Add a service control policy that denies IAM user and access-key creation.
2. Add GitHub as an OIDC identity provider (`token.actions.githubusercontent.com`) and create a deploy role whose trust policy pins `aud = sts.amazonaws.com` and `sub = repo:therealadarsh/SNOWBot:environment:uat`. Give the CloudFormation execution role a permissions boundary.
3. In GitHub: create the environment `uat` (Settings → Environments), then set repository variables `AWS_UAT_ROLE_ARN` and, if not `us-east-1`, `AWS_UAT_REGION`. These are variables, not secrets: the role ARN is not a credential.
4. `cdk bootstrap` the account once, from your machine, with your own admin credentials.

The `deploy-uat` workflow runs on every push to `uat`. It skips with a notice until `AWS_UAT_ROLE_ARN`, `infra/cdk.json` and `examples/sample-app/` all exist. A real deploy runs in the `uat` environment, which records the deployed SHA through GitHub's Deployments API.

## After `uat` has something to try

```bash
pipx install git+https://github.com/therealadarsh/SNOWBot@uat
```

Try the commands listed in `docs/research/impact-run/FINAL_REPORT.md`. Accept or reject from the shell. Merge the release PR (`uat` → `main`) yourself.

## Doc map

| File | What it covers |
| ---- | -------------- |
| [README.md](../README.md) | Install and the commands that exist |
| [STATUS.md](../STATUS.md) | Phase table |
| [GITHUB_SETUP.md](GITHUB_SETUP.md) | Ruleset clicks for `main` as of phase `1b` |
| [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md) | Required check names and the helper script |
| [ARCHITECT_GATE.md](ARCHITECT_GATE.md) | What the `architect-gate` CI job runs |
| [INDEPENDENT_VALIDATION.md](INDEPENDENT_VALIDATION.md) | Validator commands |
| [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | Decisions not settled in code yet |
| [AGENTS.md](../AGENTS.md) | Rules for agents. Beats prompts and lessons. |
