# Changelog — engineering-discipline

All notable changes to this plugin are documented here. Bump the `version` in
`.claude-plugin/plugin.json` with each release.

## 0.1.3 — 2026-06-14

Acts on the data-engineering backlog from the 2026-06-13 / 2026-06-14 triages
(`2026-06-13-triage-craft-collection#T1`/`#T6`, reinforced by the
`datatools-bedrock-arc`, `ws-runtime-arc`, and `v1-cut-arc` reports). Reference
content only — the four non-negotiables, the 21 principles, and the
`data-engineering-discipline` `description` (the eval-gated trigger surface) are
unchanged, so no holdout re-seal.

### Added

- `references/llm-failure-modes.md` — the **fabrication family**: three new modes for
  inference *invented* as observation (the sharpest Axiom-2 violation, distinct from
  the drift modes 2/8):
  - **Mode 9 — fabricated telemetry**: async status events (notifications, monitor
    streams, dry-run callbacks, "approved / merged / complete" events) treated as
    system state; defense = a disk-truth protocol (verify every event against an
    append-only source before any status report or state-changing action).
  - **Mode 10 — confabulated anchors + projected verification**: a cited
    test / fixture / file / symbol never read or non-existent; one part verified and
    the whole recorded clean; a `file:lo-hi` slice ending inside a collection literal.
    Defense = an anchor-provenance pass (every cited anchor traces to a read; name the
    scope verified; read to the closing delimiter; a handed-down fix brief is a claim
    whose anchors are verified before applying).
  - **Mode 11 — the verifier inherits none of the design's documented traps**: fresh
    pattern-matching / verifier code reproduces a trap the design recorded; put traps
    in the artifacts verifiers read (review prompts, planted-failure fixtures), not
    only design docs.
  - Cross-mode synthesis + mechanical-defenses table updated; `SKILL.md` quick-warning
    list + resource count updated (8 → 11 modes).
- `references/scenarios.md` — three playbooks for wave shapes the prior scenarios
  didn't cover (per `#T6`):
  - **Scenario 8 — building an enforcement gate** (the data product is a verdict
    function): the dataset→verdict translation table, the non-vacuity matrix
    (plant-fires / empty-allow-list / real-tree negative-pin), green-on-arrival.
  - **Scenario 9 — repairing a contract to match shipped reality**: the
    backward-repair direction (consumers' observed reality outranks an unread
    declaration), retire the aspiration durably, land with a parity pin.
  - **Scenario 10 — cutting a release across independently-merged waves**: assembled
    re-seal, clean-room + strict real-data sweep, cross-wave docs / release-notes
    completeness via a blind audit panel.
  - Cross-scenario note: **the lint / format toolchain is a consumer** — run the
    repo's own gate on a representative transformed file before locking a diff-shape
    constraint; state constraints in content terms, not position terms.
- `references/parity-recipes.md` — **Recipe 11: contract fingerprint** (byte-stable
  surface token): the pin / re-seal mechanism Scenarios 9 and 10 rely on, with its
  strictness-ladder and recipe-selector rows.

Carried forward (still unbuilt): the prior triage's axiom-2 corollaries
(unattended-run observability, src-only blast-radius, non-vacuous-parity recipes,
fail-open tooling) and the `N2e` behavior-change-no-output proxy (`watch`).

## 0.1.2 — 2026-06-07

### Changed

- `python-engineering`: the description now scopes to existing, inherited, and
  legacy projects as much as greenfield — assessing and modernizing a current
  setup, not only scaffolding a new one — so "modernize this project's tooling"
  phrasings trigger. Surfaced by the triggers eval; narrow "is my config
  current?" asks remain a triggering-threshold limit (the model answers them
  directly) and were left unforced rather than overfit.

## 0.1.1 — 2026-06-05

- Fixed: corrected the `repository` URL to `grimaldost/craft-collection` (the
  previous `grimaldo-stanzani` owner did not resolve).

## 0.1.0 — 2026-06-04

Initial release.

- `python-engineering` skill with `stack.toml` as the single source of truth for
  version pins.
- `data-engineering-discipline` skill (relocated, examples genericized).
- Scripts: `scaffold.py`, `doctor.py`, `check_versions.py`, `schema_diff.py`,
  `parity_check.py`, `contract_check.py` — all with stdlib-runnable tests.
- Hooks: ruff-format (PostToolUse), uv-enforce (PreToolUse), optional data
  checklist nudge (Stop, off by default).
- Tier-3 freshness loop: drift detection + monthly `currency` cron +
  `/refresh-stack` review command.
