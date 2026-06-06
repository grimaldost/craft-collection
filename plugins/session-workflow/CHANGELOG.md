# Changelog — session-workflow

All notable changes to this plugin are documented here. Bump the `version` in
`.claude-plugin/plugin.json` with each release.

## 0.1.2 — 2026-06-06

Make `journaling-sessions` output faithful to a structured memory store without
losing its store-agnostic default — every addition below is optional, and with no
`target_store` profile the output is unchanged.

### Added

- Optional `validated:` envelope field. A stress-tested DECISION now emits **both**
  the structured field (which a store filters and weights on) and the in-prose
  `VALIDATED:` marker (for the embedder); previously only the marker existed, so
  every ingested entry was `validated=None`.
- Optional `target_store` profile that binds `author` and `area` to a downstream
  store's existing vocabulary, so entries are not silently orphaned by generic
  scope keys. New `references/store-binding.md`.
- `PATTERN` entry type — the positive mirror of `ANTI_PATTERN`.
- `references/envelope-schema.json` — a versioned (`schema_version` 1),
  machine-readable envelope contract (fields, required set, enum sets) a consuming
  store can conformance-test its parser against.

### Changed

- The prose-only (no-envelope) output branch is now gated on an **explicit** "no
  store" opt-in instead of being inferred; a `target_store` profile makes the
  envelope mandatory.
- Documented `area`/`author` as downstream scope/partition keys, with an enum
  subset rule (matching value **and** case) for stores that strict-parse enums.

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
