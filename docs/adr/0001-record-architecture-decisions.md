# 1. Record architecture decisions

Date: 2026-10-27

## Status

Accepted

## Context

SNOWBot spans multiple phases (CLI, backends, templates, orchestration). We need a durable log of decisions without heavy process.

## Decision

Use Markdown ADRs in `docs/adr/` numbered sequentially. New decisions add a file; superseded decisions update status in place.

## Consequences

- Easy for agents and humans to scan history.
- Slight overhead to add an ADR for non-trivial cross-phase choices.
