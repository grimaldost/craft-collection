# Changelog — session-workflow

All notable changes to this plugin are documented here. Bump the `version` in
`.claude-plugin/plugin.json` with each release.

## 0.1.1 — 2026-06-05

### Added

- `consolidate-knowledge` skill — the downstream pass that distills many
  `journaling-sessions` entries across sessions into durable, promoted guidance
  (cluster → synthesize → promotion gate → reconcile supersession).
  `/consolidate-knowledge`.
- `review-panel` skill — convene fresh, blind, adversarial reviewer subagents on
  an artifact you've anchored on; neutral brief, structured comparable output,
  synthesis over averaging, a stakes-scaled ladder. Claude Code only; asks before
  firing. `/review-panel`.
- `evaluate-skill` skill — behaviorally evaluate a skill by running it headless
  many times: triggering (recall / specificity), correct-usage (rubric judge),
  and a with/without baseline, each with Wilson 95% CIs. Ships the eval engine in
  `scripts/`. Claude Code only; cost-gated. `/evaluate-skill`.

  These three landed on 2026-06-04, after the initial-release docs were written,
  and shipped in the `0.1.1` tag — recorded here to match.

### Fixed

- Corrected the `repository` URL to `grimaldost/craft-collection` (the previous
  `grimaldo-stanzani` owner did not resolve).

## 0.1.0 — 2026-06-04

Initial release.

- `journaling-sessions` skill — generic core + on-demand references, with an
  automatic internal multi-pass loop (replaces the old manual "do another pass").
- `context-handoff` skill — generalized for any fresh context (new session,
  spawned task, teammate, issue); SUBTASK and FORK modes.
- `toolkit-awareness` skill — live `scan_toolkit.py` inventory + durable guidance
  on referencing the toolkit in prompts; optional inert SessionStart inject hook.
