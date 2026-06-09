# Changelog — session-workflow

All notable changes to this plugin are documented here. Bump the `version` in
`.claude-plugin/plugin.json` with each release.

## 0.2.0 — 2026-06-09

### Added

- `tool-feedback` skill — per-session dogfooding feedback capture for registered
  in-development tools: one report per tool used (design-only use counts), into
  that tool's own feedback directory. Unified format: keel's six sections plus
  severity tags (BLOCKER/HIGH/MED/LOW), phase attribution on misses, stable
  finding IDs on proposals (`<file-stem>#<n>`), capture-time recurrence checks
  ("extends" refs instead of restatements), and an optional cost table. Targets
  bind via a user-supplied `feedback-targets` table (ask once, never hunt).
  Offer-first when self-activated.
- `feedback-triage` skill — the downstream pass: reconcile shipped work first,
  cluster reports by underlying cause (not symptom), assign ATTACK / ROUTE OUT /
  DECLINE dispositions, apply a promotion gate (reinforced ≥2 reports — single-
  report BLOCKERs exempt — specific, actionable), and emit a leverage-ordered
  triage doc with a `proposed/accepted/shipped(version)/declined` status table.
  Defers to tool-registered triage templates (e.g. keel's reflection-triage).
  `/feedback-triage`.

## 0.1.3 — 2026-06-07

### Changed

- `toolkit-awareness`: the description now covers ownership resolution — which
  installed skill owns a given concern (a rubric, a schema, project conventions),
  so a prompt references the owner instead of duplicating it — plus narrower
  inventory questions such as which hooks are configured. Triggers eval: recall
  0.79 (FAIL) → 1.00, with 0.92 on held-out unseen paraphrases and specificity
  1.00.

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
