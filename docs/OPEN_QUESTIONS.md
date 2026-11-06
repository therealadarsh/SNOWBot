# Open questions

Remove an item once the code and tests confirm it. Settled decisions stay in ADRs and in `STATUS.md`.

## Settled for the build (do not re-open in product code)

- Phase `3` backends are headless CLIs: Cursor CLI, Claude Code, and Codex. The Cursor Cloud Agents REST client is not a backend. `backend.kind: cursor` remains an alias for the Cursor CLI.
- API keys and setup tokens live in the OS keychain under service `snowbot`, account = provider. Environment variables override the keychain. Keys are never written into the repo.
- The approver is a different vendor from the builder. It is one schema-checked call with no tools.
- VS Code Copilot Chat, personal or enterprise, is not a backend. An IDE subscription does not give `snowbot run` a programmable agent.

## Still open

- Which Gemini or GitHub Models slug the approver should default to when the owner does not pass one. The factory uses whatever `VALIDATOR_MODEL` is set to.
- Whether an enterprise that forbids third-party model APIs should be served only by Bedrock (phase `9`) or also by Azure OpenAI and GitHub Models in phase `3`.
- Copilot CLI as an extra builder backend. Not in the phase `3` list. Add it only if `copilot` (or the documented headless equivalent) can run non-interactively inside Docker with an exportable token.
- ServiceNow: OAuth app shape, assignment-group filter, and which state change counts as acceptance. Needed at phase `5b`.
- Consumer-repo `init` file set beyond `snowbot.yaml`, `AGENTS.md`, `.snowbot/memory/`, and the `uat` branch. Phase `4` decides the rest.
- Preferred keyring service name for storing `CURSOR_API_KEY` on macOS vs Linux vs Windows.
- Canonical set of files copied into consumer repos (`.cursor/rules`, skills, `AGENTS.md` fragments) and whether `init` should default to git branch `chore/snowbot-setup` or only document it (phase `4`).
- Docker was not installed where the research harness was added. `docker run --network none` is built and unit-tested, not executed. The local subprocess sandbox strips provider credentials and is not a network namespace.
- Inspect `--timeout` is the model HTTP timeout. No Inspect cell wall-clock flag was verified, so the harness does not pass one. Cell timeout is enforced by the runner.
- Codex `--ignore-user-config` and `-c openai_base_url=...` are each documented. They were not executed together.
- Claude Code and Codex argv builders were checked against primary docs on 2026-10-28 and were not run.
- Pilot model id `haiku` is a documented Claude Code alias used as config data. It was not called. USD 1.50 per run is an operator cap, not a provider price.
- Step execution model: subprocess vs in-process hooks vs remote agent dispatch (phase `5`).
- How backlog status syncs with `STATUS.md` in consumer repos (phase `5`).
