# ADR-0002 — AGENTS.md as the universal discovery surface

- **Status:** Accepted
- **Date:** 2026-07-16

## Context

Claude Code's efficiency comes from progressive disclosure: each skill costs
only its description (~100 words) until the model decides to load the body.
Other harnesses (Codex CLI, Gemini CLI, Cursor, Copilot and most custom agents)
have no Skill tool, but they do read a repo-root `AGENTS.md` (an open
convention those tools already honor). Without a discovery surface, a non-CC
agent either never finds the skills or must be hand-pointed at each one.

## Decision

We generate a repo-root `AGENTS.md` from SKILL.md frontmatter: a short
dispatch preamble (rank by description fit, load at most what clears the bar —
the compact form of humblepowers' choosing-tools procedure) followed by one
line per skill — name, trigger description, path — grouped by plugin. Commands
and the optional output style appear as pointer entries in the same index. The
file carries a "GENERATED — do not hand-edit" banner naming the generator.

## Alternatives considered

- **Symlink/copy skill dirs into each harness's native skills directory** —
  rejected as the primary mechanism: it only serves harnesses with a skills
  runtime, does nothing for discovery elsewhere, and pushes install complexity
  onto every consumer. Documented as an optional extra for harnesses that
  support the format.
- **Hand-written portability docs** — rejected: stale on the first skill edit;
  the repo already had this failure mode with hand-typed inventories (it is why
  `scan_toolkit.py` exists).
- **MCP resources for lazy discovery** — deferred with the MCP channel as a
  whole (ADR-0004).

## Consequences

- Progressive disclosure is preserved off-CC: an agent reads ~1 line per skill
  and opens SKILL.md bodies on demand.
- Requires the derived-artifact integrity invariant (ADR-0001): generator +
  freshness gate, wired into pre-commit and CI.
- The generator reuses the frontmatter parser already proven in
  `scan_toolkit.py`, which becomes shared code with two consumers.
