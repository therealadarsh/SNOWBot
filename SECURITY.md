# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |

## Reporting a vulnerability

Please report security issues privately to the repository owner via GitHub Security Advisories or direct message — do not open public issues for exploitable findings.

Include:

- Affected `snowbot` version
- Steps to reproduce
- Impact assessment

We aim to acknowledge reports within 7 days.

## Secrets handling

- SNOWBot reads `CURSOR_API_KEY` for Cursor backend integration (Phase 3+).
- Optional overrides: `SNOWBOT_BACKEND`, `SNOWBOT_CONFIG`.
- CLI logging applies secret redaction; still avoid pasting raw tokens into issues or CI logs.
