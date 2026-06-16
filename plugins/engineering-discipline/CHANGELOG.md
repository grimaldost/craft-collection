# Changelog — engineering-discipline

All notable changes to this plugin are documented here. Bump the `version` in
`.claude-plugin/plugin.json` with each release.

## 0.1.4 — 2026-06-15

Clears the carried-forward axiom-2 corollaries the 2026-06-13 / 2026-06-14
triages marked "still UNBUILT" (`2026-06-09-triage-craft-collection` clusters
`T3`, `T4`, `T5`, `T7`, `T9`, surfaced again in the 2026-06-14 carry-forward
list), plus the two `python-engineering` items (`2026-06-13-triage` `T9a`
edit-lane and `T9b` `@override` caveat) and the `T13` testing-strength /
shift-left asks. Reference/body content only — no skill's `description` (the
eval-gated trigger surface) changed, so no holdout re-seal.

### Added

- `references/llm-failure-modes.md` — the **absence-read-as-state** pair, the
  mirror of the 0.1.3 fabrication family (Modes 9–11):
  - **Mode 12 — silence read as status on an unattended run** (`T3`): a frozen
    tracker / unmoved HEAD is slow-vs-dead-ambiguous, not terminal; disambiguate
    with an independent observable (process tree + artifact mtimes) before any
    takeover, and read completion from the materialized result, never from
    quiet. Includes the stall→takeover recovery sequence (quiescence → in-diff
    review → independent re-verify → merge). Extends Mode 9's disk-truth
    protocol rather than restating it.
  - **Mode 13 — fail-open tooling** (`T9`): a gate where *did-not-run* and
    *found-nothing* produce the same green (`command | filter` + "no output ⇒
    pass", return-code-blind, exception-swallowing) manufactures false
    confidence; assert the tool exists and exited zero, treat non-zero as
    BLOCKED, prefer built-ins for fences, and prove the gate red twice (planted
    violation + tool removed).
  - Cross-mode synthesis gains an "absence read as a state" entry; the
    mechanical-defenses table gains liveness-probe and fail-closed-tooling rows.
    `SKILL.md` quick-warning list + resource count updated (11 → 13 modes).
- `references/principles.md` — Principle 20 gains a **blast-radius corollary**
  (`T4`): an "all sites" precondition by grep must not be `src`-only — scope to
  `tests/`, `docs/`, config / generated trees, and sibling consumer repos, and
  treat the result as a checklist, not a one-time count. Cross-referenced from
  the consumer-enumeration steps in `scenarios.md` (2.3 lineage walk, 4.2
  input inventory).
- `references/parity-recipes.md` — two checks that govern whether any strictness
  rung can be trusted:
  - **Recipe 12 — cover every unit, not a sample** (`T5`): enumerate the
    complete set from the source-of-truth registry and assert the gate covers
    all of it (the CONSUMER-SWAP input-set diff included); a gate that pins a
    sample is hollow in coverage.
  - **Recipe 13 — prove the check can fail before trusting it green** (`T7`):
    plant a known divergence and watch the check catch it before trusting the
    pass; covers the fixture-must-participate trap and the verbatim-move
    `git show HEAD:… | diff` recipe.
  - Strictness-ladder note added distinguishing these (coverage / non-vacuity
    preconditions) from the strictness layers.
- `skills/python-engineering/SKILL.md` — a **"modifying existing code (the edit
  lane)"** section (`T9a`) surfacing only edit-relevant rules (match local
  convention, Protocol-first seams, `@override` semantics, import hygiene under
  strip-on-save, quoting, scope discipline) without the scaffold / Docker /
  observability / CI payload; and the **`@override` PEP-698 caveat** (`T9b`) in
  the Typing Philosophy section (do not annotate `@override` on a plain
  structural class that doesn't subclass its Protocol — the two are mutually
  exclusive).
- `skills/python-engineering/references/testing_and_qa.md` — **mutation testing**
  (test strength vs. presence; `mutmut`, killed/total score) and **the economics
  of shift-left** (the cost-of-defect curve that makes the pyramid's cheap layers
  non-optional) (`T13`), with a pointer added from the `SKILL.md` reference-files
  index.

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
*Update: the four axiom-2 corollaries shipped in 0.1.4; `N2e` remains `watch`.*

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
