# ADR-0006 — Eval runner abstraction: measure portability, never assume it

- **Status:** Accepted
- **Date:** 2026-07-16

## Context

The collection's quality claims are eval-gated: trigger datasets, sealed
holdouts, and correct-usage suites run through
`evaluate-skill/scripts/claude_runner.py`, which spawns headless `claude -p`
and parses its stream. Portability work (ADR-0002, ADR-0005) changes the very
text those evals measure — and "the skills work on other agents" is exactly
the kind of comparative claim the repo's own doctrine refuses to make without
measurement. Today the harness can only measure Claude Code.

## Decision

The runner grows a seam: an `AgentRunner` interface (spawn a prompt in a
clean, skill-aware or skill-free context; return the parsed
activated-skills/result stream) with the existing `claude -p` implementation
as its first and only backend this wave. Portability claims in README/docs
stay phrased as "designed to work on any agents.md-reading harness; measured
on Claude Code" until a second backend exists and the trigger suites have run
on it. Adding backends (e.g. a Codex or Gemini CLI runner) is named follow-up
work, not part of this wave.

## Alternatives considered

- **Skip the seam; keep `claude_runner.py` monolithic** — rejected: the next
  wave would refactor under pressure to ship a second backend; cutting the
  seam now is cheap because the pure core (`parse_stream`, `build_command`,
  `AgentRun`) already exists.
- **Build a second backend now** — rejected: which harness to target is a
  product decision with no committed consumer yet; a speculative backend would
  ship unexercised parsing code.
- **Drop the measurement requirement for off-CC claims** — rejected: it
  contradicts the repo's evidence discipline (claims stay "observed", never
  assumed).

## Consequences

- New invariant: **portability claims carry their measurement scope** — any
  README/docs sentence claiming multi-agent support names where it was
  measured.
- The seam is a small refactor with zero behavior change on CC (existing
  runner tests must stay green).
- Off-CC trigger reliability remains formally unknown until a backend lands —
  an honest, named gap rather than an implied guarantee.
