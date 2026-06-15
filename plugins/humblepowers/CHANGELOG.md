# Changelog — humblepowers

Notable changes to this plugin. Bump the `version` in `.claude-plugin/plugin.json`
with each release. History before 0.3.2 lives in git (`git log -- plugins/humblepowers`):
0.1.0–0.3.1 covered the initial five-skill port, the `planned-execution` skill (0.3.0),
and the honest-cross-tool-references + MIT-license pass (0.3.1).

## 0.3.2 — 2026-06-14

`planned-execution` hardening from its first real-feature dogfood
(`2026-06-13-dyno-skilleval-design-build-run`, craft-collection feedback): a
design-locked build whose two-stage review caught two real defects but let a
dead-config runtime bug — a declared `max_turns` never plumbed to its consumer —
pass all three review layers and truncate 8/9 eval trials.

`brainstorming` picks up two refinements from the same dogfood batch
(`humble-vs-super-design`, `dyno-skilleval`).

### Changed

- `planned-execution`: the final review now includes an **integration trace** —
  every config field, limit, flag, or option the plan introduces is followed to a
  consumer and confirmed read end-to-end, not merely declared. Plan-fidelity review
  is blind by construction to wiring the plan itself omitted; this closes that gap.
  The pre-execution self-review gains the matching check (every introduced
  config/limit/flag is consumed by a task).
- `planned-execution`: added authoring/dispatch notes — a **strip-on-save** rule
  (author each import in the same step that first references it, or a format-on-save
  hook removes it before the later step uses it) and a **unit-batching** blessing
  (bite-sized means one action per step, not one subagent per step; batch tightly
  coupled small steps into one coherent unit that still runs the full review loop).
- `brainstorming`: design risk-surfacing now includes **resource-budget adequacy**
  — for work an agent or capped spawn will execute, sanity-check the turn/time/cost
  budget suffices (the exact gap behind the dyno `max_turns` truncation); and the
  question-flow principle softens to **one focused question per turn, batching
  orthogonal decisions for an expert user** via the host's question UI, rather than
  strict one-at-a-time. Both are body-only; the `description` is unchanged.

### Added

- `CHANGELOG.md` (this file) — prior history was git-only, which a CHANGELOG-based
  feedback reconciliation reads as never-shipped (per
  `2026-06-13-feedback-loop-multitool-run#1`).
