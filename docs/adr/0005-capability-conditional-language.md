# ADR-0005 — Capability-conditional language in skill bodies

- **Status:** Accepted
- **Date:** 2026-07-16

## Context

Several skills hard-bind instructions to Claude Code mechanics: review-panel
declares itself "Claude Code only (it spawns subagents)" and names the
Workflow/Agent tools; compaction-survival is written against `/compact` and a
SessionStart re-injection hook; toolkit-awareness shells out to
`claude plugin list`; planned-execution routes work through subagents. Read by
a non-CC agent, these instructions either abort the skill ("this isn't Claude
Code, skip it") or break at the point of use. The repo's register doctrine and
word budget (enforced by `lint_register.py` and `word_budget.py`) constrain
how much conditional text can be added.

## Decision

Load-bearing instructions in skill bodies state the **capability** they need
and a **degradation ladder**, never a harness name: "requires spawning
fresh-context subagents; without that capability, run each reviewer
sequentially in a clean context/session". Harness names remain allowed in
examples, deploy notes, and mechanism footnotes (e.g. "on Claude Code this is
the Workflow tool"). Every skill whose body names a CC-only mechanism gets one
pass under this policy, within the existing word budget — conditional text
replaces absolute text rather than adding to it.

## Alternatives considered

- **Per-harness variant skill files** — rejected: forks the source (violates
  ADR-0001) and multiplies the eval surface.
- **Leave bodies as-is, add an external compatibility note** — rejected: the
  instruction still fails at the moment the agent executes the skill; a note
  the agent read an hour earlier does not repair a step it cannot run.
- **Runtime capability detection blocks** (structured "if harness == X")
  — rejected: skills are prose for a model, not code; the register doctrine
  favors plain conditional sentences over pseudo-syntax.

## Consequences

- New invariant: **no bare harness-gating in load-bearing instructions** —
  reviewable mechanically as a grep for "Claude Code only" outside footnotes,
  and behaviorally by the trigger evals.
- Trigger/holdout evals must be re-run after each rewording pass (existing
  eval-gated discipline; the evals themselves still run on CC — measuring
  trigger behavior on other harnesses is ADR-0006's territory).
- Some precision is deliberately traded: a CC user reads one extra clause.
