# Changelog — session-workflow

All notable changes to this plugin are documented here. Bump the `version` in
`.claude-plugin/plugin.json` with each release.

## 0.10.0 — 2026-07-05

First build round of the 2026-07-05 triage (`docs/feedback/2026-07-05-triage-craft-collection.md`,
clusters N25–N32). Body, reference, and script work only — no skill `description`
changed, no holdout implications.

### Changed

- **review-panel** (N25b + N26a): one firing-mechanics rework absorbing five open
  rows instead of five appends — launch/publish trigger in "When to convene"
  (before an irreversible outward step; fresh eyes found launch-blockers on
  self-verified trees twice); Level-3 Workflow execution variant (per-lens
  reasoning-effort + schema-forced comparable output, which the Agent tool lacks);
  a persist-raw-before-synthesis step with the destination named at plan time (a
  truncated notification or dead orchestrator otherwise loses the corpus);
  durable pre-authorization counts as the go-ahead (autonomous sessions
  deadlocked on the mandatory fresh ask); corpus-audit negative space →
  `corpus-review` (N24b, open since 06-28); copy-skew guard-rail. Cost guard-rail
  tightened to offset.
- **toolkit-awareness / `scan_toolkit.py`** (N27a): flags installed-vs-source
  version skew per plugin — compares each installed version against its
  marketplace source manifest (live working tree for `directory` marketplaces,
  local clone for git), annotates rows with `source_version` + a visible suffix,
  and emits one scan caveat. Third-arc promotion (a stale 0.2.2 cache once hid an
  entire skill); graduates the N18b watch row. Six new fixture tests, no CLI
  required; unresolvable sources are skipped — absence of evidence is not skew.
- **tool-feedback + feedback-triage** (N32a/b): first consolidation pass under
  the 0.9.0 shrink doctrine — eager bodies 1541→1309 (−15%) and 1808→1578 (−13%)
  words, edge-case mechanics folded into each skill's new
  `references/mechanics.md` (copy-skew directions, destination fine print,
  H1-only triage-doc detection rationale, concurrent-session choreography,
  fan-out owner taxonomy). No rule lost; the duplicated index-build command
  deduped. Short of the rows' ≥20% aspiration — the remaining prose is layered
  (contracts, worked examples, fresh doctrine), per the verify-redundancy-first
  contingency the rows carry.

## 0.9.0 — 2026-07-05

The digestion side of the feedback loop gains a structural-fix preference and a
standing shrink path — the direct response to the stress panel's accretion
finding (loop bodies grew one clause per promoted finding, 806→1621 and 907→1491
words in 19 days, with no disposition that ever removes prose; see
`2026-07-02-stress-panel-repo-infra-and-meta` §Misses + proposal #9, plus a user
directive to digest cause-first and prefer structural fixes over appends).
Body-only — no skill `description` changed, no holdout implications.

### Changed

- **feedback-triage**: ATTACK now names a **fix shape derived from the cause**,
  with an explicit preference order — remove/simplify → restructure → mechanize
  → append prose (last, and only naming what it displaces). The promotion table
  gains a `fix shape` column so the choice is visible and auditable per row. New
  pipeline step 6, **"Consolidate before you grow"**: every pass emits shrink
  rows for homes that took appends, carry unexercised clauses, or near the size
  cap — the loop can now shrink a tool, not only grow it. The promotion-gate
  ledger's closing assertion adds "no prose append shipped without a named
  displacement". Offset: the re-prosing anti-pattern tightened to one sentence
  (it duplicated the escalation ladder).
- **tool-feedback**: proposals open with the suspected cause
  (`<cause> → <the change that removes it>`) — the reporter holds the richest
  evidence and triage clusters by cause, so capture now hands the cluster step a
  warm hypothesis instead of a cold symptom. Friction/misses quantify when cheap
  (minutes, $, retries — the corpus's strongest findings are the quantified
  ones), and the self-check verifies cause-before-symptom.

## 0.8.0 — 2026-07-04

The anchor gains its mechanical layer: automatic re-injection after compaction
or resume. Evidence-gated per the memory-suite v2 design — shipped only after
measurement established prevalence (32 real sessions with compaction events in
~30 days of local history; two same-day CC restarts wiped in-session state
while the on-disk anchor survived). No skill `description` changed.

### Added

- **Anchor re-injection hook** (`skills/compaction-survival/scripts/anchor_inject.py`
  + a second SessionStart entry in `hooks/hooks.json`, matcher `compact|resume`):
  re-injects the newest non-closed `.claude/anchors/*.md` as `additionalContext`
  in freshly compacted or resumed sessions. INERT by default — enable with
  `SESSION_WORKFLOW_ANCHOR_HOOKS=1`. Stale anchors (>24h) inject with an
  explicit warning rather than being silently trusted or suppressed; oversized
  anchors truncate at 8K chars; every injection appends an `anchor-inject`
  NDJSON telemetry line; every failure path exits 0 (a broken hook must never
  break a session start). Stdlib-only, TDD'd (8 tests, red-first).

### Changed

- **compaction-survival body**: "Explicit surfaces" documents the env-gated
  re-injection hook alongside `/compaction-survival` and `/anchor`. Body-only;
  the trigger description is untouched (no holdout implications).
- **hooks.json description** now names both inert hooks and their env gates.

### Not shipped, deliberately

- **PreCompact freshness gate**: parked. The measured local incident profile
  justifies re-injection (recovery), not compaction-blocking (gating) — and
  the gate carries a wedge risk at full context that remains unvalidated.
- **Synthetic fidelity matrix** (the 20-trial dyno bank): retired unrun. A
  4/4-unanimous analyst panel scored its value-of-information below cost, and
  retrospective mining of real session history supersedes it as evidence.

## 0.7.0 — 2026-07-04

The anchor gains an explicit command surface. No skill `description` changed —
no holdout implications; the new command has no auto-trigger surface at all
(explicit invocation only).

### Added

- **`/anchor` command** (`commands/anchor.md`): one-off control-anchor snapshot
  on demand — the manual backstop before a deliberate `/compact`, usable with
  or without the compaction-survival protocol armed. Writes the six anchor
  categories to `.claude/anchors/<run>.md` (identity frontmatter with a step
  counter), drops a self-ignoring `.claude/anchors/.gitignore` (`*`), appends
  an `anchor-write` NDJSON telemetry line per use, and supports `/anchor close`
  to archive a finished run's anchor. Telemetry doubles as the measurement
  seed for the dogfood-telemetry path named in the memory-suite v2 design.

### Changed

- **compaction-survival body** gains an "Explicit surfaces" section: direct
  invocation arms the protocol immediately (create/refresh the anchor now, then
  keep the cadence); `/anchor` is named as the one-off backstop and the
  boundary between the two is stated — the backstop replaces the prose ask,
  not the cadence. Body-only edit; the trigger description is untouched.

## 0.6.5 — 2026-07-02

context-handoff trigger-surface retune, closing the 0.6.4 holdout re-validation
flag. **The skill `description` changed again**; the spent 2026-06 holdout is
folded into the dev set and a fresh holdout ships **with a baseline measured at
seal time** — no holdout is "sealed" without a birth number again (a sealed-but-
never-run holdout hid this skill's overfit for four days).

### Changed

- **context-handoff description (v2 of the retune):** names the intent category
  ("packaged so a receiver with zero shared context can take it cold") and adds
  packaging vocabulary ("package this up…", "bundle this…", "standalone brief /
  self-contained handoff") alongside the existing trigger phrases; SUBTASK/FORK
  glosses tightened; the redundant `user-invocable: true` dropped (docs: menu-only,
  default true — an ablation run confirmed no trigger effect).
- **Dev trigger set 8+/8− → 12+/11−:** the spent holdout's 7 queries folded in.
  Two folded positives are marked `expected_hard` on semantic grounds (recorded in
  their notes): "offload… to a **background task**… paste the result back" and
  "carve… into a bounded **sub-task**… hand the result back" carry legitimate
  Task-tool readings in today's Claude Code, and flickered 0–2/3 across four
  same-day runs regardless of description wording. They are reported separately
  (`recall_hard`), not hidden.
- **Fresh holdout sealed with baseline** (4 intent-level positives avoiding all
  description vocabulary + 3 near-misses): dev gated recall **0.80** CI[0.63,0.90],
  specificity **1.00**; held-out baseline **0.08** (1/12 fires) / specificity 1.00.
  Recorded, deliberately NOT tuned against.

### Finding (recorded, not fixable by description tuning)

- Same-day control runs show the June dev number (0.95, r5) does not replicate:
  the pre-0.6.4 description scores 0.69 on today's folded dev set, and four
  description variants land 0.64–0.80 inside overlapping CIs. Combined with the
  0.08 fresh-holdout baseline, the evidence says **auto-triggering is dominated
  by lexical proximity to the description; pure intent-level paraphrases rarely
  trigger under any wording measured.** Routed to the mechanism-level eval
  backlog (competition arm / trigger-mechanics, issue #54) rather than another
  rewording round.

## 0.6.4 — 2026-07-02

Nine fixes from the second (post-fix) stress-review panel — seams of the 0.6.3/
eval-harness fixes plus loop-closing gaps. Code fixes test-first. **One skill
`description` changed (context-handoff — the fake slash-command triggers were
demoted to plain words): its trigger holdout
(`evals/trigger/holdout/context-handoff.json`) must be re-validated, and treated
as spent for the next description-tuning round.**

### Fixed

- **`judge.py` double-counted repeated criterion ids.** A judge verdict repeating
  a criterion id summed its weight twice — the recomputed score could exceed 1.0
  and flip a fail into a pass. Met ids are now deduped before weighing, unknown
  ids score 0, and the score is clamped to [0, 1]. (Synced to the bundled
  evaluate-skill engine.)
- **`run_triggers.py` reported query-level CIs with no matching point estimates.**
  `recall_ci_query` shipped without `recall_query`, so a downstream consumer
  paired the POOLED point with the query-level interval — the point could sit
  outside its own CI. The report now carries `recall_query` /
  `specificity_query` (majority-fire per query, same unit as the CIs). (Synced.)
- **`holdout_check.py` mixed estimator families.** The dev pooled recall point was
  compared against the query-level interval's lower bound, tripping false
  "DROP/overfit" verdicts. `dev_recall_pair()` now picks point + CI from one
  family (query-level when the report has both, pooled otherwise), and the
  held-out point is chosen in the same unit.
- **`scan_toolkit.py` rendered YAML quotes literally.** A quoted frontmatter
  `name`/`description` kept its surrounding quotes in the inventory (6 installed
  skills rendered with a leading `"`). Matched quote pairs are stripped, `\"`
  and doubled `''` unescaped.
- **`build_feedback_index.py` was blind to §Misses/§Friction.** tool-feedback and
  feedback-triage sanction `extends <stem> §Misses` as a recurrence target, but
  the index only listed `## Proposed` items — the affordance pointed at nothing
  greppable. Flush-left bullets under `## Misses` / `## Friction` are now indexed
  as `§`-stub entries (fence-aware, severity tags stripped).
- **tool-feedback / feedback-triage invoked the index builder by a cwd-relative
  path** (`skills/feedback-triage/scripts/…`), which resolves nowhere on an
  installed plugin. Both now use the
  `"${CLAUDE_PLUGIN_ROOT}/skills/feedback-triage/scripts/build_feedback_index.py"` form.
- **feedback-triage's triage-doc rule contradicted its script.** The skill said
  H1 `# Triage —` *or* a `triage` filename; `build_feedback_index.py`
  deliberately uses H1-only (a filename test misclassifies input reports about
  the triage tool itself). The doctrine now states the H1-only rule and why.
- **context-handoff advertised `/subtask` `/fork` `/spinoff`** — none ship as
  commands, so following the skill's own invocation table dead-ends. The
  description, invocation table, and examples now use plain trigger phrases;
  `user-invocable: true` added (the skill itself is `/context-handoff`). This is
  the description change flagged above.
- **consolidate-knowledge had no default write location** — step 1 read "prior
  promoted guidance" and step 7 emitted entries, but no path existed, so each
  run re-promoted the same clusters. The durable layer is now pinned to
  `docs/journal/guidance.md` by default (a store's configured path wins),
  referenced by both steps and the no-store fallback.

### Docs

- Plugin README: added the two shipped-but-unlisted skills
  (`compaction-survival`, `corpus-review`).

## 0.6.3 — 2026-07-02

Five fixes from the #52 stress-review panel. No skill
`description` (the eval-gated trigger surface) changed, so no holdout re-seal.

### Fixed

- **`toolkit-awareness` / `scan_toolkit.py`** — the scan was blind to
  plugin-provided components: `_scan_plugins` parsed `claude plugin list --json`
  for each plugin's `installPath` but never walked the components under it, so a
  machine with ~40 plugin skills and 4 active plugin hooks still reported
  `SKILLS (2)` / `HOOKS (0)`. A new pure `_enumerate_plugin_components(name,
  install_path)` walks each plugin's `skills/*/SKILL.md`, `commands/*.md`,
  `agents/*.md`, and `hooks/hooks.json` events, tags each item with its owning
  plugin, and merges them into the per-kind sections; the table now annotates
  plugin-owned rows `[plugin]`. When the CLI or an `installPath` is unavailable,
  the output degrades to an explicit caveat ("plugin-provided components not
  enumerated") instead of a misleading bare `HOOKS (0)`. Unit-tested against a
  fixture plugin tree (no `claude` CLI required).
- **`feedback-triage` / `build_feedback_index.py`** — two parser defects minted
  phantom finding IDs. `_PROPOSAL` matched any indented numbered line and was
  fence-unaware, so a proposal's nested numbered sub-list and numbered lines
  inside fenced code blocks became extra/duplicate IDs (`stem#1` mapping to two
  titles); it now tracks fenced-code state and accepts a proposal only flush-left
  (`^\d+\.`, no leading whitespace — where the template writes them). And the
  `_SEVERITY` charset widened to `[A-Za-z0-9/-]+` so digit/hyphen tags like
  `**[P1]**` / `**[P2-HIGH]**` are stripped, not left glued to the title.
  Regression tests added.

### Changed

- **`consolidate-knowledge`** — the pipeline gains an input ledger and an
  already-promoted reconciliation, mirroring its sibling `feedback-triage`: Gather
  now reads prior promoted guidance first and records an **Inputs** scope (entry
  count / sessions / date range), and a new step 2 opens the output with an
  **"Already promoted — NOT re-promoted"** reconciliation so an overlapping re-run
  no longer re-promotes the same guidance (the durable-layer pollution the skill
  warns against).
- **`journaling-sessions` + `consolidate-knowledge`** — closed the storage
  contract between the pair: journaling now names a default journal location
  (`docs/journal/<YYYY-MM-DD>-<session>.md`, overridable by a `target_store`
  `path`), and consolidate's Gather step states it reads from there by default —
  previously journaling never said where the file went and consolidate had no
  defined place to gather from.
- **README** — the `context-handoff` line dropped the `/subtask` and `/fork`
  slash-command formatting (no such command files exist — they are only trigger
  phrases in the skill's description, so a cold user typing `/subtask` got an
  unknown-command failure) in favor of naming the trigger phrasing ("spin this
  off", "hand this off", "new session for this").
## 0.6.2 — 2026-07-02

Eval-harness correctness (from the 2026-07-02 adversarial stress panel). Fixes the
bundled `evaluate-skill` engine and `evals/harness/` in lockstep (`#49`).

### Fixed

- **`judge.py` — the LLM judge no longer inherits the user's real `~/.claude`.**
  `judge_pointwise` / `judge_pairwise` now take an isolated, skill-free `config_dir`
  (threaded from `grade_tasks` via a dedicated `config_judge`); without it the judge
  spawn loaded the user's CLAUDE.md, hooks, and installed plugins — including the
  skill under evaluation — contaminating verdicts and making them non-reproducible.
- **`grade_tasks.py` — an infrastructure failure no longer persists a fake score.**
  `main` now runs the `preflight_auth` probe before the fan-out and refuses to write
  a report when every WITH arm errored; `_summarize` excludes errored units from
  `correct_usage` and the pairwise tallies (adds `n_usage_valid` / `n_pairwise_valid`),
  so a 401/timeout no longer overwrites a real `grading.json` entry with `0.00`.
- **`grade_tasks.py` / `run_all.py` — a skill with no `evals/tasks/` suite is skipped,
  not crashed on.** `config.json` maps more skills than have grading suites; the
  grading stage now skips the missing ones cleanly instead of dying with an unhandled
  `FileNotFoundError` after the trigger stage already spent its spawn budget.
- **`run_triggers.py` / `holdout_check.py` — honest, query-level confidence intervals.**
  The pooled `recall_ci` treated correlated `query × repeat` outcomes as independent
  trials (intervals too narrow); `score_skill` now also reports `recall_ci_query` /
  `specificity_ci_query` (unit = the query, majority-fire = pass), and `holdout_check`
  consumes the query-level bound so a within-noise held-out recall no longer trips a
  spurious "overfit" verdict.

## 0.6.1 — 2026-07-01

### Fixed

- **`feedback-triage` / `build_feedback_index.py`** — a consolidated `BACKLOG.md`
  kept beside a feedback dir's reports is a loop OUTPUT (a status digest), not a
  source report; it is now excluded from the generated index by exact name, like
  `INDEX.md` and `README.md`. Previously it was counted as a report, inflating
  the report count and emitting a spurious `## BACKLOG` section. Regression test
  added.

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
