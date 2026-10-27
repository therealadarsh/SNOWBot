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

## Pipeline orchestration (Phase 5)

- Step execution model: subprocess vs in-process hooks vs remote agent dispatch.
- How backlog status syncs with `STATUS.md` in consumer repos.
