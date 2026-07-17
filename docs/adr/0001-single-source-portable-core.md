# ADR-0001 — Single portable source, generated per-harness adapters

- **Status:** Accepted
- **Date:** 2026-07-16

## Context

The three craft plugins couple to Claude Code at four layers: packaging
(`.claude-plugin/marketplace.json`, `plugin.json`), hooks (the CC event
protocol), discovery (model-invoked skill dispatch by description), and
harness-specific wording inside skill bodies. The goal is to make the toolkit
usable by any AI agent without losing the two efficiency mechanisms that make
it valuable: progressive disclosure (only descriptions occupy context until a
skill triggers) and mechanical enforcement (hooks that act without being
remembered). Maintaining parallel per-harness copies of 23 skills is the
failure mode to avoid — divergence is certain, and the repo's word-budget and
register gates cannot police copies.

## Decision

The `SKILL.md` + `references/` + `scripts/` tree (the open Agent Skills
format) is the single canonical source. Every additional consumption surface —
the `AGENTS.md` discovery index, rules-file exports, command conversions — is
**generated** from that source and freshness-gated in CI. Claude Code remains a
first-class consumer through the existing marketplace packaging, unchanged.

## Alternatives considered

- **Fork per harness** (a `skills-codex/`, `skills-cursor/` tree) — rejected:
  guaranteed divergence; every register/word-budget/eval gate would need to run
  N times or silently stop covering the copies.
- **Rewrite the toolkit as an MCP server as the primary form** — rejected as
  primary channel: tool schemas occupy context up front (the opposite of
  progressive disclosure), and file-native skills already work in every harness
  that can read a file. Revisited as an optional complement in ADR-0004.
- **Strip to a lowest common denominator** (drop CC-specific frontmatter and
  hooks) — rejected: it buys portability by deleting the mechanical-enforcement
  layer, violating the "without losing efficiency and functionality" constraint.

## Consequences

- New invariant: **derived-artifact integrity** — a generated surface is never
  hand-edited; the generator plus a freshness gate are the only writers. This
  becomes a guardrail and a review-checklist item.
- Description text becomes dual-consumer (CC dispatch *and* the generated
  index), raising the stakes of description edits — the existing trigger-eval
  discipline covers this.
- One more generator script and CI step to maintain.
