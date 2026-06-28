# Changelog — engineering-discipline

All notable changes to this plugin are documented here. Bump the `version` in
`.claude-plugin/plugin.json` with each release.

## 0.1.9 — 2026-06-28

From the 2026-06-28 structural review. No skill `description` changed (body /
references / scripts only), so no holdout re-seal.

### Changed

- `data-engineering-discipline`: a consolidated "a producer can look verified and
  still mislead" table under Axiom 2 (wrong layer/version · build on a behavior
  the code doesn't deliver · read the reasons not the verdict · measure a
  paper-defined subgroup on real data) with a decline-on-recurrence cap — the
  last prose increment for this judgment-bound axiom. New `parity-recipes.md`
  Recipe 15 (differential-baseline: the stash-test and the base-commit set-diff)
  for proving net-zero regression in a noisy suite. Recipe 13 / Scenario 8.2 now
  cross-link `verification-before-completion`'s red-before-green. (The Axiom-2
  re-elaborations across `principles.md` / `llm-failure-modes.md` were assessed
  for consolidation and left — each carries a distinct anti-pattern/corrective,
  so they are layering, not redundancy.)
- `python-engineering`: SKILL.md trimmed 459 → 396 lines — the inlined
  `[dependency-groups]` TOML moved to its home in `project_templates.md`, the
  duplicated uv-command list de-duped, the `Settings` example and ruff-migration
  notes compressed, the Reference Files list collapsed to a compact index. No
  rule lost.

### Added (mechanize)

- `scaffold.py` emits a `uv run ty check src` CI step (ty has no pre-commit hook).
- `stop_nudge.py` names `freshness_check.py` for incremental-load changes.
- `uv_enforce.py` also blocks `poetry update` / `pipenv` / `conda install`
  (word-bounded; the `CLAUDE_ALLOW_PIP` escape hatch is intact).
- `doctor.py` recognizes GitLab CI and CircleCI alongside GitHub Actions.
- Deferred follow-up: `doctor.py` `@override`-on-structural-Protocol and
  `from __future__ import annotations`-on-3.14 checks (hard static analysis).

## 0.1.8 — 2026-06-19

(0.1.7 is the concurrent hooks/pre-commit `python`-portability fix; this N17a
change ceded it and took 0.1.8 since it is eval-gated and lands later.)

From the 2026-06-19 triage. **N17a** — the `data-engineering-discipline`
`description` (the eval-gated trigger surface) gains the operational/freshness
phrasing family it under-fired on across two arcs (`di-incremental-debug` +
`parquet-upsert-direct-serving`): a consumed dataset that "ran but didn't update /
is stale / isn't refreshing / the watermark didn't advance", **data-qualified**
("a consumed dataset", "a table/extract") so it does NOT fire on non-data "didn't
update" cases (a stale CI badge, a UI that won't re-render, an in-app memoized
value). A first held-out set (`evals/trigger/holdout/data-engineering-discipline.json`)
was sealed **before** the edit, and the base trigger dataset gains both freshness
positives and the non-data over-fire negatives so the gated specificity actually
tests the over-fire (not just the held-out recall, which is verdict-only).

**Trigger-surface change — gated on the eval before merge:** must clear
`run_triggers.py data-engineering-discipline` (specificity ≥ 0.9, recall ≥ 0.8) and
`holdout_check.py data-engineering-discipline` (held-out recall within the dev CI).

## 0.1.7 — 2026-06-19

Hook `python`-invocation portability. The three hooks — `ruff_format` (PostToolUse),
`uv_enforce` (PreToolUse), `stop_nudge` (Stop) — invoked a bare `python`, which on a
Windows machine without Python on PATH resolves to the Microsoft-Store app-execution
stub and aborts (the trap fixed for the index-builder in session-workflow 0.4.1). They
now run via `uv run --no-project -- python …`, the form `.pre-commit-config.yaml`'s
`validate-plugins` hook already uses (this release also brings the repo's `lint-register`
and `run-tests` pre-commit entries to the same form). Trade-off: ~150 ms of uv startup
per invocation — acceptable, since the project is uv-native and `ruff_format` already
shells to `uvx`. CI (`validate.yml`) is unaffected — `actions/setup-python` puts `python`
on PATH there. Hook-manifest / repo-config only; no skill `description` changed, so no
holdout re-seal.

## 0.1.6 — 2026-06-19

From the 2026-06-19 triage, hardened by a pre-mortem + 3-lens blind review before any
code. **N16a** — a new runnable freshness gate
(`data-engineering-discipline/scripts/freshness_check.py`): the executable escalation
of the prose "freshness monitor" checklist line that did not bind a 2nd
incremental-staleness recurrence (the cache-builds-once-never-re-pulls bug, where
`max(cursor)` freezes while the run self-reports `success`). The review hardened it
pre-ship: a typed-comparison contract (a string cursor — `'9' > '10'` mis-orders — and
a tz-aware-vs-naive mix are rejected as `uncomparable`, not silently compared), a
non-vacuous default (`ok=None` when neither a prior snapshot nor a source max is
available — never a false pass), and a per-group helper + a row-count-per-bucket recipe
so a single frozen partition or a skipped-rows gap is catchable rather than hidden
behind a global max. Red-green tested; Recipe 14 + a pre-shipping checklist line + the
"Runnable checks" entry wire it in. Script / reference / body only — no skill
`description` changed, so no holdout re-seal.

## 0.1.5 — 2026-06-17

From the 2026-06-17 triage (revised by a fresh-eyes review panel). The headline is
**N10** — the recurring strip-on-save trap, fixed at last at the **hook** layer after
three shipped prose notes failed to bind it (the worked example behind
session-workflow 0.4.0's new escalation rule). Mechanism / body / reference only; no
skill `description` changed, so no holdout re-seal.

### Changed

- **`hooks/ruff_format.py` is now format-only.** It ran `uvx ruff format` then
  `uvx ruff check --fix`; the `--fix` strips an import added in one edit before a later
  edit uses it (F401 is a false positive on an incomplete file). `--fix` is dropped —
  it is owned by the pre-commit/CI gate, where the file is complete (`ruff check .` in
  `validate.yml` is the non-silent backstop). Command construction is extracted to
  `ruff_commands()` and guarded by a red-green test (`test_never_runs_destructive_autofix`);
  `CONTRIBUTING.md` and the hook docstring are updated in lockstep so the behavior isn't
  "restored" by a future maintainer. Closes the 4×-recurring trap
  (`2026-06-15-eval-harness-hardening-build`, `2026-06-16-context-size-calibration#2`,
  and the two prior `planned-execution` instances).

### Added

- `data-engineering-discipline`: **Mode 14 — traced the wrong copy**
  (editable-vs-installed / stale-cache divergence) in `references/llm-failure-modes.md`,
  with its mechanical defense (resolve `module.__file__` + version before any
  source-based behavior claim) and a defenses-table row; Axiom 2 §2 now states that
  reading a non-executing copy is inference, not observation, and cross-links
  `systematic-debugging` for the debug-time check (`#N8d`, from the
  `2026-06-17-di-incremental-debug-data-engineering-discipline` arc — the data facet of
  the round's reinforced observe-don't-infer cluster).
- `python-engineering`: a **project-convention-deference** rule in the edit lane —
  where a project states its own conventions (`AGENTS.md` / `CLAUDE.md` / `ruff.toml`),
  those govern and this skill's defaults are the fallback — plus a micro-edit (one-line
  docstring/string) carve-out (`#N13a`); and an explicit **tests live in a top-level
  `tests/` tree, never under `src/`** layout rule, mechanically enforced by a new
  `doctor.py` `tests-not-in-src` check, since colocated tests ship in the built wheel
  (`#N13b`).

Deferred (watch): the incremental-freshness gate (`scripts/freshness_check.py`, `#N12a`)
— single-arc, so by this round's own escalation rule a new mechanism waits for a
reinforced recurrence; the trigger-phrasing tuning (`#N12b`) is reseal-gated.

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
