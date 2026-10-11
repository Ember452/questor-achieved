# Security Policy

## Reporting a Vulnerability

Do **not** open a public issue for security vulnerabilities.

Report privately to the maintainer via GitHub [Security Advisories](https://github.com/Ember452/questor/security/advisories/new)
("Report a vulnerability" button). You will get a response within 7 days.

Please include:

- A description of the issue and its impact;
- Steps to reproduce (a minimal proof of concept is ideal);
- The version / commit you tested against.

## Scope

Questor is a **local-first** application: the desktop app talks to a local core over
stdio, and the web host binds `127.0.0.1` without authentication. Anything that
requires exposing the web host beyond localhost is an L4 capability gated behind a
separate ADR (see `docs/architecture/overview.md` §9 and ADR-0007) — reports about
the unauthenticated localhost binding of the default configuration are informative
but known.

Key trust boundaries to test against:

- The permission gate (`limen`) is the single authority for tool calls; approval
  can only tighten, never escalate (`docs/architecture/overview.md` §9).
- Sensitive-path guards apply in **all** permission modes including `unconfined`.
- Session transcripts under `~/.questor/` are append-only audit records.

## Supported versions

Pre-alpha: only the latest commit on `main` is supported.
