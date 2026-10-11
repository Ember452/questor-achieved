# Questor

**Auditable AI agent workstation.** You keep the reins while agents work on your
local projects — every file they read, every command they run, every line they
change stays in view, and "it says it's done" has to survive inspection.

> *Questor* — from Latin **quaestor**, the Roman magistrate who audits the accounts
> and is sent out to act. Spelled short on purpose.

## Status

**Pre-alpha. Nothing is runnable yet.** No release, no published package, no CLI.
This repository currently holds naming and reuse decisions only.

## Three pillars

Every feature has to serve one of these, in this order of priority:

1. **Visible** — real diffs on disk, actual command output, the same terminal and
   browser the agent is using.
2. **Intervenable** — steer a running task, take over the page and the task pauses,
   fork from any earlier message.
3. **Verifiable** — a claimed "tests passed" is re-run, not trusted; the archive is
   auditable after the fact.

## What it is not

- Not an LLM tracing or observability dashboard.
- Not an agent framework for other people to build on.
- Not a multi-user SaaS platform, and not a model-capability leaderboard.

## Layout

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Contribution and coding-agent rules for this repository |
| `docs/adr/` | Decision records. Read the index before changing contracts |
| `src/questor/` | Package source (empty until the first milestone lands) |

## License

MIT — see [LICENSE](LICENSE).
