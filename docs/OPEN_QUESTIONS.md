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
