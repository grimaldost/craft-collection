# Changelog — session-workflow

All notable changes to this plugin are documented here. Bump the `version` in
`.claude-plugin/plugin.json` with each release.

## 0.6.0 — 2026-06-28

Structural-hardening release (from the 2026-06-28 structural review).

### Added

- **`compaction-survival`** skill (flexible) — maintain a persisted, re-readable
  control anchor so a long autonomous run survives context compaction: one file
  with the mission, a plan pointer, a live cursor, invariants, last-known-good
  state, and resume steps, updated each step and re-read each turn. Intra-actor
  state recovery, distinct from `context-handoff`'s inter-actor brief. (The
  blind cross-model panel that reviewed the 2026-06-23 triage re-homed this from
  a proposed `context-handoff` mode to a dedicated skill.)
- **`corpus-review`** skill (flexible) — audit a large file corpus by blind
  fan-out → adversarial-verify → disjoint-partition fix → re-audit to
  convergence, with an execute-the-artifact lens. Ships no engine of its own
  (orchestrates on the harness's parallel/workflow primitives; degrades to
  sequential), deliberately avoiding the bundled-script drift the eval-engine
  fix below addressed.
- Each new skill ships a calibrated description + balanced trigger dataset +
  sealed holdout under `evals/trigger/`, registered in `evals/config.json`. The
  live `run_triggers` recall/specificity gate is cost-gated; run it with
  oversight before merge.
- Sealed trigger holdouts for **`context-handoff`** and **`journaling-sessions`**
  — both auto-trigger surfaces that had a base trigger dataset but no protected
  generalization set.

### Fixed

- The bundled `evaluate-skill/scripts/` engine had drifted behind the tested
  `evals/harness/` source (it is a distribution template users copy into their
  own `evals/harness/`): `run_triggers` was missing `preflight_auth`,
  `expected_hard`/`recall_hard`, and error sampling; `aggregate` lacked
  action-discipline gating; `grade_tasks` / `claude_runner` lagged. Re-synced the
  four drifted files verbatim and added `evals/harness/test_scripts_in_sync.py`
  asserting byte-identity so the template cannot silently regress again (wired
  through `run_tests.py` → pre-push + CI). No existing skill `description`
  changed.

## 0.5.1 — 2026-06-24

Two fixes from a headless + leak-closed validation pass on the `step-digest` style.
(1) **Activation value corrected.** The plugin ships the style under its namespaced
name, so it is selected with `"outputStyle": "session-workflow:step-digest"` (or
picked in `/config`). The bare `step-digest` resolves only for a project-local
`.claude/output-styles/` file — the earlier instruction silently did nothing for
plugin installs. (2) **Doctrine tightened.** When a step produces a deliverable a
later step will reproduce or finalize (a function body, a snippet, an exact
message, a value), the digest now carries it verbatim rather than only describing
the change — a strict digest-only relay (no files crossing between steps) flagged
this as a major gap. No skill `description` changed, so no holdout re-seal.

## 0.5.0 — 2026-06-24

New `step-digest` **output style** (`output-styles/step-digest.md`) — the plugin's first
output style. It installs two communication registers while keeping Claude's coding behaviour
(`keep-coding-instructions: true`): lean working narration (brief action lines, with the
load-bearing reasoning behind a non-obvious decision and anything surprising still surfaced
mid-stream), then a fixed-field digest under a `## Digest` heading at the end of every
substantive turn (`TL;DR` / `Changed` / `Decisions` / `Verified` / `Next` / `Open`, later
fields omitted when they carry nothing). The aim: a long agent-driven run reads back from its
per-step digests instead of its full transcript. Selectable and off by default — enable with
`"outputStyle": "session-workflow:step-digest"` in user/project settings or via `/config`; not
forced over a user's other output-style choices. Design:
`docs/design/2026-06-24-step-digest-design.md` (a `SubagentStop` enforcement hook for subagent
coverage is the deferred Phase 2). New artifact — no skill `description` changed, so no holdout
re-seal.

## 0.4.4 — 2026-06-23

`review-panel` "When to convene" — name the **design/spec-before-build** case explicitly (a
qualifier on the high-stakes trigger, where pre-code defects are cheapest to catch) **with a
maturity gate**: a design is panel-ready only when concrete enough to critique (explicit
interfaces, failure modes, data flow, ≥1 worked example) — panelling a bare sketch yields
bikeshedding and false confidence, not defects. From the 2026-06-23 triage (**N19a**, reinforced
across two design-stage arcs — `2026-06-17-backlog-remediation-design-build#2` +
`2026-06-19-triage-round-review-panel#1`); a blind fresh-eyes review of the proposal added the
maturity guard. Body-only — no `description` change, so no holdout re-seal.

## 0.4.3 — 2026-06-19

`feedback-triage` index-builder (`scripts/build_feedback_index.py`) false-exclusion fix.
`_is_report` dropped any file whose name contained the substring `triage`, treating it as
a loop output — silently excluding legitimate INPUT reports from the generated `INDEX.md`:
a `tool-feedback` report *about* the `feedback-triage` tool, or a
`<date>-triage-round-<tool>` wave slug. With the report invisible to `INDEX.md`, the next
session's recurrence check (`extends`-lookup) could not see it. Observed this round: 7
`triage-round-*` reports plus the pre-existing `2026-06-14-feedback-triage-batch-run.md`,
and the keel `…-craft-triage-design-premortem.md` report, were all dropped. Triage docs are
now detected by their `# Triage` H1 (`_is_triage_doc`), not a filename substring; a report
whose slug merely contains `triage` is indexed. (`digest` stays name-based — no observed
false-exclusion.) Script + test only — no skill `description` changed, so no holdout re-seal.

## 0.4.2 — 2026-06-19

Hook `python`-invocation portability: the SessionStart toolkit-inventory hook
(`toolkit-awareness/scripts/scan_toolkit.py`) ran via a bare `python` (the
Microsoft-Store app-execution stub trap on Windows without Python on PATH). Now `uv run
--no-project -- python …` — completing the portability fix begun in 0.4.1 (the feedback
index-builder invocation). Hook-manifest only — no skill `description` changed.

## 0.4.1 — 2026-06-19

From the 2026-06-19 triage. **N18a** — the `feedback-triage` index-builder
(`scripts/build_feedback_index.py`) docstring and the `tool-feedback` /
`feedback-triage` invocation references now use `uv run --no-project python …`. A bare
`python` (or `python3`) resolves to the Microsoft-Store app-execution stub on a Windows
machine without Python on PATH and aborts — it cost a retry on each index rebuild in
the field. Doc / invocation only — no skill `description` changed, so no holdout re-seal.

Known broader scope (out of this fix, tracked separately): the plugins' `hooks.json` and
the pre-commit `lint_register` / `run_tests` entries invoke a bare `python` and have the
same failure on that setup.

## 0.4.0 — 2026-06-17

Two changes from the 2026-06-17 triage, both shaped by a fresh-eyes review panel.
Body/doctrine only — neither skill's `description` (the eval-gated trigger surface)
changed, so no holdout re-seal.

### Added

- `feedback-triage`: an **escalation rule** in the ATTACK disposition (step 4) plus a
  matching **"Re-prosing a recurrence"** anti-pattern. When a finding recurred *after*
  a fix already shipped at the same enforcement layer (≥2 post-fix reports) and its
  cause is **mechanically reachable** at the next layer, the promotion moves one rung
  down — prose → required structure → script/gate → hook → linter/CI — instead of
  re-prosing the same advice. Gated so it can't over-mechanize a judgment-bound
  recurrence (a dispatch-timing nudge, a naming call), which takes sharper prose or
  DECLINE, not a forced rung. Cross-references the existing `skill-authoring` rule
  ("a constraint that needs caps to hold needs a gate, not louder prose") so the two
  statements don't drift. (The meta-finding from this round: a class of finding that
  recurs despite shipped prose is signalling the wrong enforcement layer, not weak
  prose — e.g. the strip-on-save trap, fixed at last in the hook.)

### Changed

- `tool-feedback`: **destination resolution** folded into Workflow step 1, replacing
  the assumption that a report always lands in the tool's own repo. A report's
  destination, in precedence, is a dir the user named *this session* (a consolidated
  external sink with per-tool subdirs ⇒ `<sink>/<tool>/`) → the registered feedback
  dir → the tool's own repo; only a **named or registered** dir is resolved, never an
  inferred one (per `2026-06-17-datatools-docs-plugin-remediation-tool-feedback#2`,
  `2026-06-17-debt-engine-tool-feedback#2`). A **redirected write does not relocate
  the recurrence baseline** — when a registered binding exists, step 2 still reads
  *its* index, so a one-off sink can't sever recurrence and resurface settled findings
  (the silent-misroute bug the panel caught). Step 2 now **builds a missing `INDEX.md`
  first** rather than degrading to grep (`2026-06-17-debt-engine-tool-feedback#1`), and
  a tool the user *named* but the session never exercised gets an explicit "named but
  not exercised → no report" line, not a silent omission
  (`2026-06-17-datatools-docs-plugin-remediation-tool-feedback#3`,
  `2026-06-17-v1-publish-wheel-fix-tool-feedback#2`). The persistent-binding registry
  (`#N9c`) stays routed to the user's CLAUDE.md — a `TARGETS.md` under the gitignored
  `docs/feedback/` would not travel.

## 0.3.1 — 2026-06-15

Two watch-item refinements from the backlog; body-only, descriptions unchanged (no
holdout re-seal).

### Added

- `tool-feedback`: a proposal carries its **resolution and referents**, not just its
  question — record the clarification the session validated (or the deciding
  precedent) and name any counted objects, so the downstream lander doesn't re-derive
  or hunt (per `2026-06-09-feedback-skills-021-landing#1`, the prior triage's `#T4`).
- `evaluate-skill`: a boundary note — it evaluates one skill's triggering + output,
  not a whole plugin's end-task outcomes; a plugin-vs-plugin comparison is an
  outcome/task-bank harness (dyno-style), not this single-skill behavioral eval (per
  `2026-06-14-humble-vs-super-run#2`, the `#N7a` watch row).

## 0.3.0 — 2026-06-15

Feedback-loop ergonomics from the carried-forward 2026-06-14 triage backlog (`#T3`,
`#T5`, context-handoff `#T7`) plus the owner-tagging fix from
`2026-06-14-feedback-triage-batch-run`. Doctrine + a new stdlib script; the three
skills' `description` blocks (the eval-gated trigger surfaces) are unchanged, so no
holdout re-seal.

### Added

- `feedback-triage/scripts/build_feedback_index.py` — rebuilds a feedback dir's
  `INDEX.md` (one entry per report + its numbered proposals) so an `extends`-lookup
  is one Read instead of N phrasing-fragile greps (`#T5a`). `tool-feedback` rebuilds
  it on write and reads it in the recurrence check; `feedback-triage` rebuilds it at
  scope. Stdlib-only, unit-tested; the `INDEX.md` output is a generated, gitignored
  local artifact.
- `tool-feedback`: a **standing-directive = asked** branch — an autonomous session
  under a CLAUDE.md "run at session close" mandate treats it as asked and writes,
  instead of emitting an offer no one is present to accept (`#T3a`); and
  **maintaining a registered tool's own repo now explicitly counts as use** (`#T3b`).
- `feedback-triage`: a fan-out **owner-tagging** rule — enumerate each registered
  tool's own skills/components in a digest brief's owner taxonomy so a finding about
  tool X's own skill isn't misrouted (`2026-06-14-feedback-triage-batch-run#1`); a
  **digest-for-handoff** middle path for a tool that owns its triage flow (`#2`); and
  a **read-order convention** for same-wave `-execution`/`-authoring` pairs (`#T5c`).
- `context-handoff`: **state the INTENT behind an adaptable step**, not just the
  procedure — strongest in FORK mode, where an executor resolves novel situations in
  a step's spirit only if the spirit is written down (`#T7`).

### Changed

- `tool-feedback` recurrence check (step 2) now reads `INDEX.md` first, with grep as
  the fallback.

Deliberately not done: a committed `docs/feedback/README.md` (`#T5b`) — craft's
`docs/` is gitignored and its binding cites no format README (unlike keel's), so the
skill's own report template stays the format authority; a gitignored README would
only duplicate and drift.

## 0.2.3 — 2026-06-14

Body-only refinements to `tool-feedback` from the 2026-06-14 feedback batch
(`2026-06-13-dyno-skilleval-design-build-run`, `2026-06-14-humble-vs-super-design`
/ `-run`); the `description` (the eval-gated trigger surface) is unchanged, so no
holdout re-seal.

### Added

- `tool-feedback`: the cache-vs-working-tree note now covers **version skew in
  either direction** — the installed/cached copy can run *behind* the working tree
  (a stale install) or *ahead* of it (a newer install over an older manifest), so
  the manifest version and the executed version can disagree; record which copy you
  actually ran and flag the skew (per
  `2026-06-13-dyno-skilleval-design-build-run#5`, extending the 0.2.2
  working-tree-authoritative note).
- `tool-feedback`: a **README-fallback** rule — if a registered tool's `extras`
  cites a format README that doesn't exist in the tree, fall back to this skill's
  template and note the missing README as a maintainer gap (per
  `2026-06-14-humble-vs-super-design` §Friction, reinforced by `-run`).

## 0.2.2 — 2026-06-13

Two strands land together: body/process fixes from the three-tool digest run
(`2026-06-13-feedback-loop-multitool-run`), and trigger-surface calibration from
the feedback-loop eval remediation (`2026-06-09-feedback-loop-live-eval`,
`2026-06-10-feedback-loop-eval-remediation`).

### Added

- `feedback-triage`: reconcile-shipped (step 2) now also reads `git log` and the
  current source for a component that ships without its own CHANGELOG (an eval
  harness, a scripts dir) — its increments land as commits, so a CHANGELOG-only
  pass reads shipped work as still-open (per
  `2026-06-13-feedback-loop-multitool-run#1`; a triage subagent had filed three
  already-committed eval-harness fixes as open).
- `feedback-triage`: scope (step 1) recognizes a triage doc by a `# Triage —`
  first heading or a filename containing `triage`, not only a `*-triage-*.md`
  glob, so a house naming variant (keel's `<date>-backlog-triage.md`) is not
  silently re-triaged; the dir is listed directly rather than globbed (per
  `2026-06-13-feedback-loop-multitool-run#2`).
- `feedback-triage`: a concurrent-triage guard — note any triage doc already
  dated today at scope, and re-list the dir at emit (step 6) before writing, to
  avoid duplicating a concurrent session's triage (per
  `2026-06-13-feedback-loop-multitool-run#4`, extending
  `2026-06-09-cc-gitattributes-hygiene#2`).
- `tool-feedback`: a note that a skill under development is authoritative in its
  working-tree `SKILL.md`, not the installed/cached copy the `Skill` loader serves
  (per `2026-06-13-feedback-loop-multitool-run#3`).

### Changed

- `tool-feedback` `description`: added a clause targeting the canonical imperative
  ("write a dogfooding feedback report for keel") — the trigger measured as a miss
  (per `2026-06-10-feedback-loop-eval-remediation` Miss "canonical imperative
  0/14", `2026-06-09-feedback-loop-live-eval#3`). It is additive and
  specificity-safe, but the 2026-06-13 re-run shows it still fires 0/3 headless —
  see the eval note below; it reads as a triggering-threshold limit, not a
  description gap.
- `feedback-triage` `description`: negative space added — a governed series' own
  reflections go to the method tool's triage skill (e.g. keel's `keel-triage`),
  not this generic pass (specificity, per
  `2026-06-10-feedback-loop-eval-remediation`).
- `evals/trigger/tool-feedback.json`: swapped the journaling near-miss negative
  for a CHANGELOG/release-notes boundary negative — the spec-mandated boundary
  ("does not write CHANGELOG entries") was untested (per
  `2026-06-09-feedback-loop-live-eval#5`, `2026-06-09-pr9-premerge-gap-disposition#2`).

These are trigger-surface (`description`) and trigger-dataset changes.
`evaluate-skill` was re-run 2026-06-13 (132 spawns, ~$9): **specificity 1.00**
across dev + holdout for both skills (the new CHANGELOG-boundary negative is
correctly rejected). **Recall is inconclusive** — the trigger arm's
flail-to-error rate (~55–65%, the unshipped trigger-arm-damping residual) muddies
it; error-excluded recall is 0.89 (`tool-feedback`) / 0.79 (`feedback-triage`),
and the canonical imperative fires 0/3 (a likely triggering-threshold limit, to
flag as expected-hard rather than chase). Treat recall as provisional until the
harness damps flail.

## 0.2.1 — 2026-06-09

Wording promotions from the feedback-loop skills' first dogfood run, recorded
in `2026-06-09-feedback-skills-first-run` (craft-collection's feedback dir).
Body-only edits: both skills' `description` blocks — the eval-gated trigger
surfaces — are untouched.

### Added

- `feedback-triage`: **Promotion-gate ledger** as a first-class template
  section — the gate shows its work per cluster (cleared on reinforcement /
  BLOCKER-exempt / `watch` / raw, and why), closing with the assertion that no
  singleton non-BLOCKER was promoted; pipeline step 5 now requires it
  (per 2026-06-09-feedback-skills-first-run#1).
- `feedback-triage`: `watch` added to the status vocabulary — the middle
  disposition for an anchored-but-singleton row, parked until a second report
  corroborates it — and the BLOCKER exemption's scope clarified to the
  BLOCKER's own row: sibling rows from the same report need their own ledger
  justification or take `watch` (per 2026-06-09-feedback-skills-first-run#4).
- `feedback-triage`: the cluster-**splitting** rule named as the dual of
  collapsing — split one super-cause into separate clusters when its
  corollaries have distinct homes and distinct concrete fixes
  (per 2026-06-09-feedback-skills-first-run#3).
- `feedback-triage`: first-run base cases stated explicitly — no triage doc yet
  ⇒ the whole corpus is un-triaged (step 1); no last triage ⇒ the
  reconciliation window is the whole CHANGELOG to date (step 2); empty
  `extras` ⇒ the fallback template is authoritative (step 7)
  (per 2026-06-09-feedback-skills-first-run#2).
- `feedback-triage`: the disposition tie-breaker — route by where the fix
  lands, not where the artifact lives (step 4) — and the disk-is-authoritative
  scope note: an invocation-vs-directory discrepancy is resolved in the
  directory's favor and noted under Inputs (step 1)
  (per 2026-06-09-feedback-skills-first-run#7).
- `tool-feedback` + `feedback-triage`: the loop's two ID namespaces documented
  on both sides — report finding IDs (`<file-stem>#<n>`) vs triage promotion
  IDs (`T1a`) — and triage now explicitly follows `extends` chains when
  clustering, making capture-time `extends` refs load-bearing
  (per 2026-06-09-feedback-skills-first-run#5).

### Changed

- evals/README ("Reading the feedback-loop skills' numbers"): holdout
  interpretation note — two of `tool-feedback`'s three holdout positives are
  session-framed by design; if holdout recall drops, suspect those two before
  concluding the description fails to generalize
  (per 2026-06-09-feedback-skills-first-run#8).

Deliberately not in this release: per-task rubric support in the
`evaluate-skill` engine (2026-06-09-feedback-skills-first-run#6) — an engine
schema change, left recorded for a separate initiative.

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
