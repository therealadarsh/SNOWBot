# 3. Config and YAML-backed models

Date: 2026-10-27

## Status

Accepted

## Context

Consumer repositories need a stable config file and pipeline artifacts independent of backend SDKs.

## Decision

- Root config filename: `snowbot.yaml`, overridable with `SNOWBOT_BACKEND` and `SNOWBOT_CONFIG`.
- Pydantic v2 models: `SnowbotConfig`, `PipelineSpec`, `Backlog` with `schema_version: 1`.
- Pipeline artifacts default to `docs/pipeline-spec.yaml` and `docs/backlog.yaml`.
- Setup branch constant: `chore/snowbot-setup`.

## Consequences

- YAML loaders share error types (`ConfigError`, `FileOperationError`, `ValidationError`).
- Backend adapters read config without embedding YAML parsing logic.
