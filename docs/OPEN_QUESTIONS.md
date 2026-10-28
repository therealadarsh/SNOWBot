# Open questions

Track unverified or pending API / product decisions. Remove items once confirmed in code and tests.

## Cursor backend (Phase 3)

- Exact REST base URL and auth header format for Cursor Cloud Agents API (assumed bearer token via `CURSOR_API_KEY`).
- Rate limits, pagination, and idempotency keys for agent run creation.
- Whether project linking requires organization slug vs repository URL only.

## Keyring (Phase 3+)

- Preferred keyring service name for storing `CURSOR_API_KEY` on macOS vs Linux vs Windows.

## Init templates (Phase 4)

- Canonical set of files copied into consumer repos (`.cursor/rules`, skills, `AGENTS.md` fragments).
- Whether `init` should default to git branch `chore/snowbot-setup` or only document it.

## Research harness

- Docker was not installed where this package was added. `docker run --network none` is built and unit-tested, not executed. The local subprocess sandbox strips provider credentials and is not a network namespace.
- Inspect `--timeout` is the model HTTP timeout. No Inspect cell wall-clock flag was verified, so the harness does not pass one. Cell timeout is enforced by the runner.
- Codex `--ignore-user-config` and `-c openai_base_url=...` are each documented. They were not executed together.
- Claude Code and Codex argv builders were checked against primary docs on 2026-10-28 and were not run.
- Pilot model id `haiku` is a documented Claude Code alias used as config data. It was not called. USD 1.50 per run is an operator cap, not a provider price.

## Pipeline orchestration (Phase 5)

- Step execution model: subprocess vs in-process hooks vs remote agent dispatch.
- How backlog status syncs with `STATUS.md` in consumer repos.
