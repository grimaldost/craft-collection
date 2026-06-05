# Changelog — session-workflow

All notable changes to this plugin are documented here. Bump the `version` in
`.claude-plugin/plugin.json` with each release.

## 0.1.1 — 2026-06-05

- Fixed: corrected the `repository` URL to `grimaldost/craft-collection` (the
  previous `grimaldo-stanzani` owner did not resolve).

## 0.1.0 — 2026-06-04

Initial release.

- `journaling-sessions` skill — generic core + on-demand references, with an
  automatic internal multi-pass loop (replaces the old manual "do another pass").
- `context-handoff` skill — generalized for any fresh context (new session,
  spawned task, teammate, issue); SUBTASK and FORK modes.
- `toolkit-awareness` skill — live `scan_toolkit.py` inventory + durable guidance
  on referencing the toolkit in prompts; optional inert SessionStart inject hook.
