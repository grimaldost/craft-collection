# Changelog — humblepowers

Notable changes to this plugin. Bump the `version` in `.claude-plugin/plugin.json`
with each release. History before 0.3.2 lives in git (`git log -- plugins/humblepowers`):
0.1.0–0.3.1 covered the initial five-skill port, the `planned-execution` skill (0.3.0),
and the honest-cross-tool-references + MIT-license pass (0.3.1).

## 0.12.0 — 2026-08-12

`choosing-models` learns where a routing decision belongs. Three calibration
cycles asked whether the rubric's score predicts the right tier; the 2026-08-12
fathom wave asked what *asking* costs, and found that the cost of consulting the
rubric and the usefulness of consulting it both track the deciding context and
run in opposite directions. The skill now settles that before any scoring
happens. Minor bump rather than the 0.9.1 patch precedent: this changes what the
skill tells you to do, not only how it says it. No threshold moved, no scoring
mechanic changed, no lineup edit — see below for why the same wave does **not**
license those.

### Changed

- **A deciding-context rule, ahead of the procedure (`choosing-models`).** A
  strong-tier session routing a single task skips the rubric — it lands on the
  tier it would have chosen unaided, at the highest price of any deciding
  context. Scoring is for batches, taken at the weak tier, where the fixed cost
  amortises and where the scoring is the only thing that changed a decision at
  all; and because that is also where the rubric was seen misapplied, an emitted
  tier is checked against the thresholds rather than taken as given.
- **The oracle-coverage discount asks whether a gate sees the failure at all**,
  not only whether the failure is diagnosable at the discounted tier. Where the
  fix site sits outside the shipped suite's coverage, that suite caught none of
  26 measured failures — so on exactly the task shapes the rubric's cross-shape
  floor fires on, a discount presuming the failure will be caught buys nothing.
- **`models.toml` provenance** carries the wave as `[meta] deciding_context`,
  with the measured premiums and agreement rates, an explicit record of what the
  evidence did *not* license, and the four questions it leaves open. The
  `oracle_discount` entry takes the silent-failure count; the `calibration` entry
  drops its stale "designed and unrun" reading of the tier-separating bank, which
  has since run in part.

### Removed

- **The cost-caveats bullet from the skill body.** Two of its three clauses were
  already in `models.toml` verbatim (the tokenizer caveat on the `mid` row, the
  5–10× large-prompt multiplier in `[typical_cost]`); the third — cheaper is not
  faster wall-clock — moved there to sit with them. Restating the data file in
  the body is what the body has least room for.

### What paid for the new prose

The body is a ratchet, so the deciding-context rule and the sharpened oracle
clause displaced rather than appended (1006 → 997 words). Beyond the
cost-caveats bullet: the "Data and overrides" section stopped restating
`models.toml`'s own header and now points at it; the intro's rubric-lineage
sentence went, since step 1 and the rubric file both already say evidence moves
the rubric; step 1's claim that scoring is **zero cost** went because this wave
refutes it; steps 5 and 6, the staleness tripwire and the `choosing-tools`
boundary shed clauses each duplicated elsewhere on the page; and the
"silently pinning the top tier is the failure mode this skill ends" line went,
its work already done by step 5's all-top-tier comparison row.

### Measured — and, as much, what it does not license

**The wave.** fathom `routing-decision-v1` (54 trials, $14.04) read beside
`model-tier-v2`'s positive control and discordant slice (89 trials, $27.60).

Rubric premium per task over deciding unaided: **$0.0021** at the weak deciding
tier over a batch of nine, **$0.0748** at mid deciding one task, **$0.2026** at
strong deciding one task. Agreement with the same session's unaided choice
(modal route over 3 repeats, 9 briefs): **9/9 at strong, 8/9 at mid, 5/9 at
weak**. So the rubric is pure overhead exactly where it is dearest to run: at
strong on one task its break-even is 77.6% / 93.8% / 104.7% at a weak-tier pass
rate of 1.0 / 0.8 / 0.7 — above 100%, it cannot pay at any correction rate. At
mid on one task the bar is 28.6–38.6% against one disagreement in nine as the
ceiling.

**Not licensed, and not done.** No threshold moved: the only robust adequacy
readings in the wave are one brief's `weak` and `mid` arms, and the
pre-registration requires robust readings plus a cross-distribution rule. The
points system stays: of the two escalations off `mid` that proved unnecessary,
only one implicates the formula — on the other the formula said `mid` at score
45 and a weak model *applying* it emitted `strong`, which is a decider error,
not a design error. And no general over-provisioning claim: the four discordant
briefs split **2–2 by tier pair**, right to escalate off `weak` and wrong off
`mid`.

**Held open.** Whether the rubric routes *better* anywhere was never measured.
The weak decider's four upgrades cost **+$0.0580/task** in extra execution — 28×
its own decision premium — and only two of four were shown necessary. One brief
sits at 0.62 against a 0.70 bar and needs n ≈ 200 on one arm, so it is
permanently borderline at buyable n. And presentation moves the route: six of
nine arms routed the one shared brief differently alone than inside a batch of
nine, mechanism-independently — so batch and per-spawn routing are not
interchangeable. That last one is n=3 on one brief; it is recorded here and in
`models.toml`, and not leaned on.

The `description` is **unchanged**, deliberately. It is under a spent holdout
seal, the measurement says nothing about when the skill should be selected — it
measured the price of injecting the body once selected — and the rule that
landed is a judgment the body can carry with the nuance a trigger surface
cannot.

## 0.11.0 — 2026-08-11

> Renumbered from 0.10.0 before release. That number belongs to the
> `data-engineering-discipline` vNext entry directly below, which ships
> first; this entry is stacked above it so the file reads in release order
> once both are in. The 0.10.0 section is a **forward reference** until that
> release lands — it cites `references/evidence-fabrication.md`, which arrives
> with it. If that release is dropped rather than merged, delete the 0.10.0
> section and renumber this entry back to 0.10.0.

`verification-before-completion` gets the two delivery mechanisms it never had.
The skill body is **unchanged**, and that is the finding, not an omission: an
audit of the program behind it found that the body has never been an
experimental arm — no trial in the lineage carried the skill body at all — so
nothing measured to date speaks to the prose. What was measured is a stop-stage
gate that was not shipped. Minor bump: one new hook event and a tenth routed
row, no removals.

> **Correction to this entry, same day.** It first said "every trial in the
> lineage mounted the plugin identically in every arm, bare included". That is
> **false**, and the fact it got wrong matters for how the gate's own numbers
> read. Checked against the primary scenario files: the lineage's **main-agent**
> arms mounted `humblepowers` (plus two sibling plugins); every **delegated**
> arm — `bare-sub`, `gated-sub`, `disc-sub` — mounted **nothing**, or the gate
> plugin alone. Mount was confounded with the delegation split. Two consequences,
> both kept below: the conclusion "nothing speaks to the prose" survives and is
> in fact stronger (no arm carried the body, rather than all of them carrying
> it); and no main-agent-vs-delegated comparison in that program is
> interpretable, so the claim "delegation degrades verification" is withdrawn as
> **untested** — not reversed.

### Added

- **A `SubagentStop` gate, off by default**
  (`skills/verification-before-completion/scripts/subagent_gate.py`;
  `HUMBLEPOWERS_VERIFICATION_SUBAGENT_GATE=1` arms it). It blocks a subagent's
  first stop once with a discipline reconsideration and lets every later stop
  through. Mechanics come from the measured fixture unchanged — one shot per
  `(session_id, agent_id)` so the block cannot loop and concurrent subagents do
  not share a counter, and it fails open on any exception, because a hook that
  cannot decide must never be the reason a subagent cannot stop. The wording is
  byte-identical to the arm that was measured and is pinned by a test: a
  prescriptively-worded sibling on the same bank wrote a test on **every**
  trivial code edit and was rejected on that alone, so the words are the
  treatment rather than packaging. One deliberate divergence from the fixture:
  counters past a 24-hour window are pruned, so an opt-in hook does not
  accumulate files for the life of the machine.
- **A router row for the skill** — the tenth. It had **zero** rows, so the
  plugin's one shipped mechanism could not fire for it and the entire delivery
  surface was the skill description competing on its own. Dev-set recall 8/8 and
  specificity 8/8; cross-fire 2/176. The gated held-out number is precision on
  near-misses (2/2 clean), because a hint at a claim moment is cheap and one
  during a status question is the class that gets hooks turned off.

### Measured, and what it does not cover

The gate's evidence is **one bank**: two tasks, nine repeats per cell, three
tiers. On the rate at which delegated work leaves a regression check behind it
moved **+0.22 (haiku) / +0.56 (sonnet) / +0.44 (opus, 90% CI [+0.11, +0.78])**,
with **0/12** false positives on trivial edits where verification work would
have been over-scope. Four cautions ride every one of those numbers, and a
fifth — the sharpest — follows them. They are
the *discipline*-worded arm; a widely-quoted "+0.56 for the skill" is the
rejected prescriptive arm's figure and should not be repeated. The ladder is
non-monotone across one bank with overlapping intervals, which is why no
tier-conditional guidance appears anywhere in the skill. The contrast is
**gate-vs-no-gate with no skill body on either side** — both arms mounted no
plugins — so it says nothing about the gate's value *in addition to* the body
this plugin ships. And the default stays off until a replication on a different
task family, because a stop-blocking hook in every subagent is a larger bet than
one bank funds.

**A fifth caution, and it is the one to read before quoting the ladder: the
+0.44 is not known to be the gate firing.** A companion pass over the raw
streams found that at the strong tier the gate arm was mounted and **never
delivered its treatment** — the gate's own sentence appears in **0 of 15** opus
streams, against **16 of 21** haiku streams on the *same* plugin directory. The
+0.44 is real in the ledger (9/9 against 5/9) and the delivery gap is not a
formatting difference: the sentence is absent in any form. So the strong-tier
figure's **cause is unexplained** — not refuted, and not the gate firing.
Anyone citing a three-tier ladder is citing one number whose mechanism is open.
Two provenance limits on that check itself: the stream files it reads are
gitignored and exist in a single working directory rather than in any git
history, and the p-value quoted for it elsewhere is one-sided and computed on a
pooled table rather than on the 0/15-versus-16/21 pair — so the counts above are
the claim, and the p-value is not repeated here.

**This gate ships with its own proof obligation undischarged, and that is stated
rather than glossed.** The program commissioned to re-measure it pre-registered a
full gate — a lift of ≥ +0.15 on at least one tier, **and** a false-positive rate
≤ +0.05, **and** beating a shape-matched placebo by ≥ +0.10 — before this
mechanism was allowed to ship. **Not one gate trial and not one placebo trial was
ever bought.** All three conditions are therefore *unmeasured in this codebase*,
not merely unmet, and the figures above are inherited from a prior program on a
different contrast at n=9.

Two things follow, and neither is the other. Nothing here justifies **deleting**
the gate: an unmeasured mechanism is not a refuted one. And nothing here
justifies presenting it as **validated**: it is opt-in, it fails open, and those
are safety properties, not evidence. Anyone enabling
`HUMBLEPOWERS_VERIFICATION_SUBAGENT_GATE=1` is enabling a mechanism whose local
evidence is a wording-fidelity test and a fires-and-blocks fixture — not a
measured lift.

`HUMBLEPOWERS_VERIFICATION_GATE_SKIP_MODELS` is marked **provisional** in the
module, the README and its tests. No measurement licenses any value for it, the
payload key it reads is unconfirmed across harness versions, and an absent model
gates rather than skips. It exists because the hook is the only place a tier fact
is implementable at all — the harness cannot condition a skill's activation on a
subagent's model, so the same claim written into a description would name a
decision nothing can act on.

### Not changed, deliberately

The skill body did not move. A candidate body — three procedures displaced to a
reference, three new rows in *What claims require*, and a pristine-output clause
extended to warnings and a jumped runtime — lives under
`evals/arms/verification-vnext/` as an experimental arm with its obligations
written down, and a test fails if any of it reaches the plugin before its
evidence does. Also declined and recorded there rather than left implicit: a
tier clause, a config protocol row, an adversarial-re-read section, and any
growth of the failure-mode catalog.

## 0.10.0 — 2026-08-11

### Added

- **`verification-before-completion` gains
  `references/evidence-fabrication.md`** — four tool-general modes re-homed
  from `engineering-discipline:data-engineering-discipline`, where they were
  Modes 9, 10, 12 and 13 of a data-engineering taxonomy: fabricated telemetry,
  confabulated anchors, silence read as status on an unattended run, and
  fail-open tooling. None is about data. The clearest recorded instance of the
  fail-open mode diagnosed a defect in an eval harness, and that report's own
  promotion asked for a tool-general statement. Roughly 1,900 words of evidence
  discipline stop being reachable only by someone doing data work. The mode
  numbers are kept so older citations still resolve.

### Changed

- That skill's body points at the new reference and drops the empty-scan
  clause the reference now states at length: 790 -> 787 words, no budget bump.
- **The dispatch router accepts several rule groups per skill.** The data
  discipline's three ambient nouns (`pipeline`, `dataset`,
  `dashboard`/`warehouse`) name things that exist in build automation, CRM, HR,
  front-end and logistics prose, and each fired the rule on its own. They move
  into their own group at `min_hits: 2`: one is a lexical coincidence, two are
  a signal. Groups merge by skill id, and a denial on any group denies the
  skill, so the activation test and the negative patterns are stated once.
  Tuned on a dev set authored first
  (`evals/trigger/fixtures/router-ambient-noun-dev.json`), then the two sealed
  router holdouts were read once: recall unchanged on every register, null
  false-fires 2/28 -> 1/28, adversarial unchanged at its 2/20 budget.
- **The ambient-noun move cost true positives, and the fixture could not see
  it.** `dashboard`/`warehouse` shipped as ONE alternation, so a prompt naming
  both scored one hit and could never reach `min_hits: 2` — the group's own
  comment described a property its patterns could not express. Split into two.
  Separately, eight prompts squarely inside the skill's enumerated triggers went
  FIRE -> silent (column add/rename/drop on a dataset, duplicate rows, a
  partitioned write, reworking a transform, dashboard-versus-warehouse); the dev
  fixture's four must-survive positives all routed via other patterns, so it was
  structurally incapable of sampling the class, and the sealed set lacks the
  resolution — which is why "recall unchanged" was true and uninformative. All
  eight are now positives in the fixture (17 negatives / 12 positives) and five
  corroborating patterns, each worthless alone, recover them. Sealed pair
  re-read once, unchanged: overall 0.50, direct 0.94, 1/28 nulls.
- **The recovered null is now banked.** `test_recall_holdout_floors` still
  asserted `null_fires <= 3` after the measurement moved to 1/28, so nothing in
  the suite could fail if it regressed. Ratcheted to `<= 1`.
- `verification-before-completion` points back at the non-vacuity matrix. The
  re-homing replaced that pointer with one to the new reference, but the matrix
  itself stayed in `data-engineering-discipline` and was audit-classed
  keep-worthy, so its one external pointer had simply been deleted.

## 0.9.1 — 2026-08-11

Calibration pass on `choosing-models`, on evidence from the 2026-08-11 fathom
`model-tier-v1` recalibration (5 arms x 7 tasks x 5 repeats, adding
`claude-opus-5`). Doctrine prose and provenance only — no threshold moved, no
scoring mechanic changed, no lineup edit. Patch bump on the 0.7.3 precedent.

### Changed

- **`choosing-models` oracle-coverage discount, two clauses (CRAF-B12 / T37a).**
  The bullet now asks what oracle will exist for *this* task in *this* run —
  including one about to be authored — instead of reading the oracle off the
  environment as it already stands; and it states that the discount presumes
  the gated failure is diagnosable at the discounted tier, since a red gate the
  cheaper model cannot read buys a repair loop rather than a saving. The
  calibration-provenance preamble moved out to `models.toml`, where provenance
  already lives; the body came out 6 words shorter than it went in.
- **The scoring rubric reads the brief, not the problem (CRAF-B11, partial).**
  Coverage governs in both directions: where the prompt enumerates the edit
  sites, the decomposition or the acceptance cases, the structure and reasoning
  axes fall with it. A reading rule for the axes that exist — not a new axis and
  not an adjustment row. Displaces the paragraph restating the cross-shape
  floor's own table, and Example 5's duplicated contrast.
- **`models.toml` provenance** carries the third calibration run and the
  decision taken, plus a new `oracle_discount` entry holding the evidence
  displaced from the skill body.

### Measured (the honest headline)

**The bank could not answer the question CRAF-B11 asks, so no scoring mechanic
moved.** On-diagonal is 1/7 for the third run running, but 6 of 7 tasks sit at
100% for every arm, no task resolves empirically to `mid` or `strong`, and a
10/10 cell carries a Wilson 95% CI of [0.72, 1.00] — a true shortfall under ~28
points is invisible. With the outcome a near-constant, no predictor can be shown
to separate it, so the review's "delete the point system if the score does not
separate tiers" is not licensed: that null is manufactured by saturation, not
observed. T36a's second dimension is not landed either. The tier-separating bank
that would settle it is designed and unrun.

Two directional observations recorded rather than acted on: over-provisioning
persists (5 of 7 tasks were served by the weak tier), and the newest strong model
was quality-flat against its predecessor at ~1.4x the per-task cost. Separately,
the executing model authored a regression test in 70% of trials where four other
models did so in 0–3% — first evidence for the authored-oracle clause above, from
a bank not designed to test it.

## 0.9.0 — 2026-08-11

Backlog wave 1. The dispatch hook ships on, the hint became a decidable check,
and the tier data caught up with the lineup the machines are actually served.

### Changed

- **The dispatch-router hook ships ON** (`HUMBLEPOWERS_DISPATCH_PROMPT_INJECT=0`
  opts out). It was inert behind an unset variable; the one environment where
  that gate happened to be set produced 85 logged prompts of real dispatch signal
  no in-session inspection could have found. The no-match path returns zero with
  no output, so a default-on hook costs a subprocess. (CRAF-B02)
- **The hint names each candidate by its activation test**, not by the words that
  matched — the matched skill's own description explicitly does not rest on that
  token, so a reader had nothing to decide against. Nine routed rows, nine
  one-line questions. (CRAF-B05 / T35a)
- **A candidate whose skill is not installed is dropped.** Five of the nine rows
  name skills in sibling plugins and the hint emitted the raw id regardless, so a
  single-plugin install recommended skills that were not there. Checked against
  disk with stat calls, no CLI on the prompt path; the drop is still logged,
  since that count is the evidence for whether this router belongs at
  marketplace level. (CRAF-B05)
- **Directory names are no longer trigger vocabulary.** A project called
  `something-pipeline` fired the data rule on every prompt that named it, for the
  life of that project. (CRAF-B05 / T35b)
- **`models.toml`: the strong tier moves `claude-opus-4-8` → `claude-opus-5`.**
  Checked against the platform model reference; same price, same tier position —
  a lineup edit, not a threshold move. The file records the direction settled
  before any mirror walk: sibling price mirrors are keyed by family substring and
  are correct today, so the walk propagates a corrected lineup rather than a
  stale one over correct mirrors. (CRAF-B06 / T38b)
- **`verification-before-completion`:** the seen-red section asks for both halves
  now — that a check can fail, and that it read the input you think it did. A
  green over an empty scan is worse than a red one because it gets quoted.
  Carries the restore rule: remove a planted violation by the inverse edit, not a
  checkout. Equal-mass swap; the budget is unchanged at 800.
  (CRAF-B03 / T41a, CRAF-B26 / T50d)

### Added

- **`choosing-models/scripts/lineup_check.py`** turns the environment tripwire
  from prose the reader performs by hand into a command: exit 1 naming the absent
  model and `/refresh-models`. Dated snapshots and context-window variants of a
  known api_string pass, because a check that fires every session gets muted.
  `/refresh-models` step 1 runs it. (CRAF-B06 / T38a)
- **`refresh-models/references/mirrors-file.md`** — the mirror walk reads a
  bindings file (`$MODEL_MIRRORS_FILE`, else `~/.claude/model-mirrors.toml`)
  instead of a table in the operator's private instructions, with per-site
  `vocabulary` so a family-named copy is translated rather than substituted, and
  the rule the file enforces: a registered mirror with no row in its own
  repository's backlog. Absent, ask once. (CRAF-B13)

### Fixed

- The router's cost bound is relative, not wall-clock: growth of an 8x longer
  prompt over the short one, min over repeats. An absolute ceiling reddens under
  machine load, and a suite that is sometimes noise stops being a stop signal.
  The guard is proven against the exact unbounded pattern 0.7.0 shipped (~456x
  growth against a 32x bound, versus ~8.7x for the shipped rules).
  (CRAF-B26 / T50c)

## Unreleased

The `experiment-rigor` skill shipped on this branch as 0.9.0 and 0.10.0 and is
extracted into its own plugin before either was released
(`docs/adr/0008-experiment-discipline-plugin.md`); both entries moved with it to
`plugins/experiment-discipline/CHANGELOG.md` as that plugin's 0.1.0 birth entry,
and this plugin's version rolls back to **0.8.0**. What remains here is the one
change humblepowers actually owns.

### Changed

- **The dispatch router row for `experiment-rigor` is now cross-plugin**:
  `humblepowers:experiment-rigor` -> `experiment-discipline:experiment-rigor` in
  `skills/choosing-tools/scripts/router_rules.json`. Router ids are opaque
  `plugin:skill` strings and the dataset lookup splits the prefix off, so a routed
  skill living in another plugin is supported by construction; the patterns are
  byte-unchanged and both sealed router holdouts are unmoved (they contain no
  experiment-rigor case). This row doubles as the pointer to the new plugin.

## 0.8.0 — 2026-07-23

Dispatch retirement (redesign step R1). A 2026-07 content A/B (fathom
`inject-content-v1`, 30 sonnet-5 trials) measured the generic 8-step dispatch
protocol block as no better than no injection at all, and the per-prompt tiered
cadence (wall-clock / prompt-count re-escalation) was never validated. Both are
retired here as a standalone release, justified independently of any
replacement: reverting to a mechanism that equals bare cannot help. Only the
concrete-candidate lexical router — the injection shape the same A/B favored —
survives. The redesign (design doc + blind review panel) plans the semantic and
action-stream layers as measured, gated follow-ups.

### Removed

- **The session-start full-protocol inject** (`HUMBLEPOWERS_DISPATCH_INJECT`)
  and its SessionStart hook.
- **The per-prompt tiered cadence** — full/micro tiers and the
  `HUMBLEPOWERS_DISPATCH_FULL_EVERY` (default 10) / `HUMBLEPOWERS_DISPATCH_FULL_MINUTES`
  (default 30) knobs, plus the per-session cadence state file and the
  compact|clear `--reset-state` reset that served it. With no cadence state,
  the four stress regressions that pinned its corruption-resilience (bad field
  types, future-dated cursors, zero/negative knobs) are removed with it.

### Changed

- **The UserPromptSubmit hook is now the lexical router alone**: gate a
  substantive human prompt, route it, inject a `<toolkit-dispatch>` block naming
  candidate skills on a match, else stay silent. `HUMBLEPOWERS_DISPATCH_PROMPT_INJECT=1`
  still gates it; `HUMBLEPOWERS_DISPATCH_ROUTER=0` now silences the hook
  outright (nothing else is left to inject). Telemetry records router hits and
  whether a hint shipped (cadence-tier fields dropped).

### Added

- **`inject_dispatch.py --health`** — a human-invoked audit surface over the
  telemetry NDJSON (prompts seen, hints injected, most-matched skills, last
  record age). A fail-open-silent hook needs a way to prove it is alive; this is
  it.

## 0.7.4 — 2026-07-23

Router recall recalibration (backlog item 4), run seal-first: a fresh blind
recall holdout was authored (by a subagent forbidden from reading the router,
its rules, or the dev sets), baselined against the committed rules, and SEALED
before the post-tune measurement. Both sealed sets are regression-only.

### Changed

- **Two dev-evidenced router widenings** (frozen before the holdout was seen):
  the test-driven-development noun-phrase now allows up to three bounded words
  between article and head noun ("implement the new discount feature" fires);
  systematic-debugging gains a plain `debug(ging)` pattern with a lookahead
  excluding tooling nouns (debug log/build/mode/symbols/level/flag/print).
  Both reported real-session misses now route; dev bars unchanged (recall
  1.00/spec 1.00 on both skills), adversarial false-fire budget unchanged at
  2/20.

### Added

- **Sealed recall holdout + regression floors.**
  `evals/trigger/holdout/dispatch-router-recall.json` (76 cases: 8 skills x 6
  positives across direct/embedded/paraphrase registers, 16 hard negatives,
  12 silence) with its baseline row in `holdout/BASELINES.md`;
  `test_router.py::test_recall_holdout_floors` pins overall >= 0.45, direct
  >= 0.85, null false-fires <= 3.

### Measured (the honest headline)

The tuned rules move ZERO holdout cases — baseline and post-tune are
identical: overall 0.50, by register **direct 0.94 / embedded 0.44 /
paraphrase 0.12**, nulls 26/28 clean. This is the trigger-lexical-ceiling
measured on the router: direct phrasings are nearly solved, oblique phrasings
are structurally out of a lexical instrument's reach. Consequence, recorded
in the rules comment: further recall work on embedded/paraphrase registers
goes to the semantic layer (cadence-vs-content A/B; the 0.18.0
exercise-ledger activation telemetry), not to more patterns. The PT-BR arm
still requires its own labeled dev set before any PT tuning.

## 0.7.3 — 2026-07-23

Two doctrine one-liners from the 2026-07-23 triage, each reinforced across two
report arcs; both SKILL.md bodies held under their word budgets by trimming
existing prose (the displaced words are the flabbier phrasings, not content).

### Added

- **choosing-models (T5b):** after the emission-surfaces table — a workflow
  `agent()` with no `model` inherits the session model (possibly frontier);
  no engine-level cap exists, so under a tier cap every call carries an
  explicit `model`. Evidence: the stress and hooks-verify fan-outs both hit
  the inherit-Fable gotcha; the engine-side guardrail is routed upstream.
- **verification-before-completion (T8a):** the gate's Read step names the
  pipe-exit idiom — `$?` is the LAST command's exit code; read it right after
  the bare command, never after a pipe; capture output to a file instead.
  Evidence: recurred in the himed campaign past a written handoff warning
  (extends the convoy-backlog claims-over-unread-signals miss).

## 0.7.2 — 2026-07-23

### Fixed

- **Subagent completion counted as a human turn.** Headless probes confirmed
  subagent completion is delivered to the parent session as a synthetic prompt
  (starting `[SYSTEM NOTIFICATION` or `<task-notification>`) that passes through
  UserPromptSubmit like a real one; `--prompt-submit` now recognizes both
  prefixes and skips them silently before any state read or cadence increment,
  the same treatment as a slash command.

## 0.7.1 — 2026-07-22

### Fixed

Hardening from a 9-agent adversarial stress pass on 0.7.0 (attack cells + deep
review + blind holdouts + headless E2E). E2E confirmed the hook fires correctly
in a real `claude -p` process; these close the failure modes the attacks found.

- **ReDoS in the router (must-fix).** The data-engineering pattern's two chained
  unbounded `[\w\s]*` spans backtracked cubically — a crafted 4000-char prompt
  cost ~3.5s of the 10s UserPromptSubmit budget. Every span in `router_rules.json`
  is now bounded to `{0,40}`; the same bound also caps a matched span so an
  attacker sentence can no longer be echoed whole into the hint. Adversarial
  latency test added (~0.007s now).
- **ASCII output not enforced end-to-end.** The router echoed matched prompt text
  (Unicode `\w`) into the hint; a span capturing a non-cp1252 char (CJK/Cyrillic/
  emoji) made `print()` raise on a codepage-limited console, and the outer
  fail-open swallowed it — losing the whole injection *after* cadence state had
  already recorded it as delivered, suppressing the next full tier. Now: matched
  text is ASCII-sanitized, the body is ASCII-encoded before print, and **the print
  happens before state/telemetry persist** (best-effort, suppressed) so a delivery
  failure never burns a cadence slot. Latin accents (Portuguese) were always
  cp1252-safe; this closes the non-Latin-script path and honors the documented
  ASCII-only invariant.
- **Silent total loss on a failed state write.** `_write_state` was unwrapped and
  ran before the print, so an unwritable state dir (plausible under the machine's
  Application-Control history) disabled the injection 100% with exit 0 and no
  signal. Now best-effort and after the print.
- **Corrupt state degrades, not crashes.** `_read_state` validated dict-ness but
  not field types; a valid-JSON state with a wrong-typed `n` raised and produced
  permanent sticky silence. Fields are now coerced individually, and
  `last_full_n`/`last_full_ts` are clamped to reality so out-of-range values
  cannot starve the full tier.
- **Cadence env vars clamped.** `HUMBLEPOWERS_DISPATCH_FULL_EVERY`/`_FULL_MINUTES`
  of 0 or negative inverted the throttle into full-protocol-every-prompt; now
  treated as garbage → default.
- **Input robustness.** stdin is read as UTF-8 (utf-8-sig, so a BOM parses) rather
  than the host codepage — defense-in-depth, since the uv-managed interpreter
  already decoded UTF-8, but this makes it guaranteed across interpreters.
  Non-string and oversized `session_id` are coerced/truncated instead of dropping
  the turn. Zero-width/format chars are stripped before matching so an invisible
  character cannot defeat a negative pattern.
- **Router precision (calibration, not a code bug).** Blind adversarial holdouts
  measured 42–87% false-fire on baited out-of-context trigger words (vs the
  dev-set CI's 0.90 specificity — the datasets are the calibration corpus).
  Recall-safe negative patterns for the concrete non-technical senses (sales/
  warehouse/car/construction/physical/diary uses) cut it to 10% (2/20), and both
  residual fires are defensible (a genuinely-failing test → debugging; a column
  added to a fact table a report reads → a schema change with consumers). The
  holdout is sealed as `evals/trigger/holdout/dispatch-router-adversarial.json`
  with a `test_router.py` false-fire budget; dev recall is unchanged. A full
  semantic recalibration against a fresh sealed holdout remains owed
  (`docs/design/2026-07-22-hooks-program.md`). Documented: the router is
  monolingual-English (Portuguese-intent prompts degrade to silence, the safe
  default) and `planned-execution` is intentionally unrouted.
- **hooks.json:** the SessionStart inject entry gains `timeout: 10` for
  consistency with the two prompt entries.

## 0.7.0 — 2026-07-22

### Added

- **Per-prompt dispatch injection (UserPromptSubmit), env-gated inert.**
  `inject_dispatch.py --prompt-submit` (gate `HUMBLEPOWERS_DISPATCH_PROMPT_INJECT=1`)
  injects the dispatch protocol with tiered cadence — full 8-step protocol on
  the first prompt and on re-escalation (every `HUMBLEPOWERS_DISPATCH_FULL_EVERY`
  prompts, default 10, or `HUMBLEPOWERS_DISPATCH_FULL_MINUTES` minutes, default
  30), a two-line micro-reminder otherwise; slash-commands and short follow-ups
  are silent. Escalates the layer on triage cluster T18 (2026-07-22): dispatch
  never fires under momentum, SessionStart injection alone decays, and the
  description-tuning lever was A/B-refuted (b02adbf). Fails open on every path —
  a UserPromptSubmit error or timeout would otherwise block the user's prompt —
  and logs tier decisions to a size-capped local NDJSON for later
  cadence-vs-content A/Bs.
- **Lexical dispatch router** (`router.py` + `router_rules.json`): deterministic
  word-boundary regexes over the prompt name at most two candidate skills
  (matched words shown, hedged phrasing, silence on no match), for eight
  chronically under-firing skills. Calibrated against `evals/trigger/*.json`
  with CI bars in `test_router.py` (dev recall >= 0.60, own-negative
  specificity >= 0.90, cross-fire budget <= 0.15); dev-set numbers by
  construction — the datasets are the calibration corpus. Opt out with
  `HUMBLEPOWERS_DISPATCH_ROUTER=0`.
- **Cadence-state reset** on SessionStart `compact|clear` (`--reset-state`), so
  the first post-compaction/post-clear prompt re-escalates to the full protocol.

### Changed

- `--session-start` now stays silent when the per-prompt gate is on (the
  first-prompt full injection subsumes it); behavior under the old gate alone is
  unchanged. `inject_dispatch.py` gains its missing test sibling
  (`test_inject_dispatch.py`).

## 0.6.0 — 2026-07-16

### Changed

- **Capability-conditional inventory fallback (multi-agent portability).**
  choosing-tools' dispatch and boundary steps name the full inventory ladder:
  an inventory skill when installed, else the harness's skill listing, else a
  repo's `AGENTS.md` index — the skill no longer assumes a harness-provided
  in-context listing. planned-execution already carried its "Without
  subagents" ladder; choosing-models was already harness-neutral. Word-budget
  baseline bumped for choosing-tools (+9 words): the growth displaces nothing —
  it widens the fallback source list.

## 0.5.0 — 2026-07-14

The capacity-dispatch pair: choosing-models + /refresh-models, per the accepted
design `docs/design/2026-07-14-choosing-models-skill.md` (successor to
pr-pilot's model-tiers + pr-prompt-scorer, whose doctrine was orphaned by the
pr-pilot → convoy migration; design revised once after a blind review). Minor
bump: two new skills.

### Added

- **choosing-models** (flexible): task → (model, effort) dispatch at
  delegation/pricing moments. Ships the ported scoring rubric
  (`references/scoring-rubric.md` — trivial-task override, cross-shape floor,
  verification discount, worked examples, carried near-verbatim for its
  observed-run calibration) and a thin `models.toml` (thresholds, tier
  assignments, aliases, provenance, `review_by` age tripwire, typical-cost
  observations and budget guidance — no sticker prices; the platform's model
  reference owns those; project-level override documented). Doctrine keeps the
  ancestry's invariants (frontier never score-assigned; no in-run
  auto-escalation) and ships the oracle-coverage downshift as a labeled
  hypothesis pending a crossed calibration. Trigger dev set (8+/8−, absorbing
  choosing-tools' model-choice near-miss as its canonical positive; adversarial
  negatives against claude-api model-facts and toolkit-awareness inventory) and
  sealed holdout (4+/3−) authored at the same sitting; birth baseline recorded
  as pending (cost-gated) in `evals/trigger/holdout/BASELINES.md` per the
  data-engineering-discipline precedent.
- **refresh-models** (manual-only command, `/refresh-models`): the update leg —
  detect lineup drift against the platform's model reference, read release
  notes, classify lineup-only vs guidance-affecting vs needs-human, apply
  mechanical edits on approval, stamp `last_reviewed`/`review_by`. Downstream
  mirror sites come from a user-supplied binding (rule 4, bindings over
  assumptions — a plugin cannot know a stack's mirrors) with a closing grep for
  the outgoing model string as the catch-all. Threshold changes without
  calibration evidence are needs-human by definition.

### Changed

- **planned-execution:** the model-selection deference line now names the
  same-plugin sibling (choosing-models owns the call when present; the inline
  per-role heuristics stay as the standalone-install fallback). Net −1 word.
- **skill-authoring:** the cross-tool-reference rule's worked example
  re-pointed to a live cross-plugin instance (a capacity-dispatch policy, e.g.
  humblepowers' choosing-models — as now cited from session-workflow's
  review-panel), replacing "convoy's model-tiers", whose referent existed
  nowhere after the pr-pilot retirement. Net 0 words.
- **choosing-tools trigger eval:** the model-choice near-miss note now names
  its owner (`— choosing-models`); the case stays a negative for
  choosing-tools and is the new skill's first positive.

## 0.4.10 — 2026-07-09

Two red-shape clarifications in test-driven-development, from the 2026-07-09
craft triage (T9a/T9b; evidence `convoy-backlog-build#2`,
`triage-build-round#1` — both live builds where the bright line's letter
collided with an honest red).

### Changed

- **"Fails rather than errors" names its exception (T9a):** a reproducing test
  for a crash bug fails by the very exception under repair — that IS the right
  reason; "errors" means accidental ones (typos, wrong fixtures). Displaces the
  over-broad reading that pushed reporters to contort exception-shaped repro
  reds.
- **Self-discovering runners get a named route (T9b),** as a "When stuck" row:
  red against a fixture tree, never the real one — the root/target seam is
  itself built test-first, then the defect red runs through it. A naive red
  re-runs the runner inside itself (observed as a near fork-bomb red-testing
  `run_tests.py`). The review round reworded an earlier draft that sequenced
  "seam first, then red" — which self-granted a production-code-before-red
  exception the skill's own bright line forbids; the fixture-tree route stays
  inside it.
- Word budget re-seeded: test-driven-development 927→999 (the two rows above;
  no clause retired — both sharpen existing bright-line scope).

## 0.4.9 — 2026-07-05

pr-pilot → convoy rename completion (PRs #75, #81 from the 2026-07-05 polish
session's corpus review) plus a marketplace-description sync.

### Changed

- **Body sweep (#75):** planned-execution (the below/above-lane pointer, the
  model-tier example, the Boundaries owner line), skill-authoring (the rule-2
  role-generic cross-tool example), and the README dedup table now name convoy —
  pr-pilot's replacement as the governed multi-PR engine. Form unchanged; only
  the stale example name swapped.
- **Description completion (#81) — reseal note:** planned-execution's
  frontmatter `description` named pr-pilot twice ("doesn't warrant keel or
  pr-pilot", "keel and pr-pilot own that") — now convoy. This is a `description`
  edit made with maintainer sign-off: the skill's sealed trigger holdout
  predates it and should be re-baselined before the next description-tuning
  round (the edit is a factual example-name swap, not trigger tuning, so a
  recall shift is unlikely).
- **marketplace.json (repo-level):** the humblepowers entry's description now
  names midweight planned execution, syncing it to plugin.json — the clause had
  been missing since planned-execution shipped in 0.3.0 (the release updated
  plugin.json but not the marketplace copy).

## 0.4.8 — 2026-07-05

First humblepowers round of the 2026-07-05 craft triage (rows N25a, N28b, N29a,
N30a). Body/script edits only — no skill `description` changed, no holdout
implications.

### Changed

- **choosing-tools**: the dispatch procedure gains a required step — before
  settling the shortlist, read the newest feedback report's Misses/Friction for
  a tool the task will exercise (when a dogfooding intake is registered; skip
  otherwise, the step costs nothing). The escalation-ladder response to the
  review-panel under-dispatch recurring across six arcs, twice past shipped
  prose fixes and once the day after being written down: a recorded miss must
  resurface at dispatch time, not at the next feedback pass. The inert
  SessionStart frame (`inject_dispatch.py`) carries the same step.
- **skill-authoring** (Shipping requirement): a sealed holdout now requires a
  **birth baseline** — run once at seal time, result recorded next to the seal;
  a sealed-but-never-run holdout hid a dev-0.95/holdout-0.33 overfit for four
  days (the 0.6.5 context-handoff retune practiced this; now doctrine). And a
  **harness-ungateable branch**: cwd-dependent and heavy orchestration skills
  gate on manual-observation activation evidence + clean specificity, with the
  harness-fixture follow-up recorded (the corpus-review precedent) — not
  blocked on a 0.00 recall artifact. Offset: the YAML colon-trap paragraph
  tightened.
- **planned-execution** (authoring/dispatch notes): per-phase commits in a
  multi-phase worktree stage the phase's full file set and commit with no
  unrelated tracked-dirty files — pre-commit's stash of unstaged changes
  collides with a format hook's auto-fix of a staged file and aborts the
  commit (file left `MM`); recovery is re-`git add`. Second arc of the
  strip-on-save family.

## 0.4.7 — 2026-07-03

Doc accuracy: the register linter went marketplace-wide (repo-tooling change,
`scripts/lint_register.py`), so the README's "gates this plugin's markdown"
became an understatement.

### Changed

- README register-linter section: the linter now gates **every plugin's**
  markdown (the register doctrine governs the shared selection pool — a coercive
  description distorts selection whichever plugin ships it), not only
  humblepowers. Notes the one scoped exception: `non-negotiable` is flagged only
  in a frontmatter description, allowed as domain terminology in body prose.

## 0.4.6 — 2026-07-02

README-honesty fixes from the second (post-fix) stress-review panel. Docs only —
no skill `description` changed, no holdout re-seal.

### Fixed

- **Dead evidence citation.** The register-ablation section cited
  `report/grading.json` keys `<skill>@superpowers` — that file is gitignored
  local eval output and has since been overwritten by later runs, so the
  citation pointed at data that no longer exists anywhere. The README now says
  exactly that: the summary tables are the surviving record, with re-run
  instructions instead of a dead pointer. The Measured-behavior section gained
  the same provenance note.
- **Register-linter overclaim.** "The linter is the mechanical enforcement of
  the skill-authoring doctrine" promised more than a regex linter can deliver
  (0.4.5 had already fixed the same claim inside skill-authoring but missed the
  README). It now claims the *detectable subset* of the register rules, with
  the rest named as judgment.
- **"No dev→holdout collapse" contradicted the adjacent table.** Three cells
  drop (choosing-tools specificity 1.00 → 0.75, skill-authoring recall
  0.38 → 0.25, planned-execution recall 0.25 → 0.12). The claim is now
  qualified with the drops, the small-n context (holdout n = 4 positives / 2
  negatives — one query moves recall by 0.25), and a direction-not-points
  reading.

## 0.4.5 — 2026-07-02

Reference-doctrine correctness from a stress-review pass. The only `description`
edit is a factual scope correction to `skill-authoring`'s trailing linter clause
(no trigger phrasing or negative space changed), so no holdout re-seal.

### Changed

- `skill-authoring`: the "References between tools" section now states the
  missing tier explicitly — a reference to a **different plugin in the same
  marketplace is a cross-tool reference (rule 2 applies)**, because plugins
  install individually (`/plugin install humblepowers@craft-collection`) and a
  sibling plugin is therefore not guaranteed present. Rule 1's "same-plugin is
  free" scope is bounded to the same *plugin*, not the same marketplace.
- `skill-authoring`: the register-linter claim is made honest. Body and the
  description's trailing clause no longer say the linter "enforces the register
  rules" (which reads as all of them); both now say it enforces the detectable
  subset — banners, all-caps runs, and a fixed obedience/priority phrase list —
  with review holding obedience framing that dodges those literal patterns.
- `systematic-debugging`, `verification-before-completion`: the four
  unconditional references to the separately-installed `data-engineering-discipline`
  sibling are rewritten into rule-2 form. Each canonical rule is now **stated
  inline** so the skill stands alone on a humblepowers-only install (module
  `__file__`/version resolution; an edit's diff is its scope; prove a gate can
  fail before trusting it green; diff the failure set against a stashed or
  base-commit baseline), and the sibling pointer is made conditional and
  role-generic ("a data-engineering skill, when one is installed — e.g.
  `data-engineering-discipline` …"). Closes the plugin's own degradation-test
  failure (dead pointers on a solo install).

## 0.4.4 — 2026-06-28

From the 2026-06-28 structural review. Body / doc only — no `description`
changed, so no holdout re-seal.

### Changed

- `verification-before-completion`: names the general principle **a verifier is
  trusted green only after it has been seen red** (plant a violation, watch the
  check catch it, remove the plant) — the form that `test-driven-development`'s
  "verify red" and `data-engineering-discipline`'s prove-the-gate-can-fail are
  both instances of, unifying a principle that had been maintained as two
  uncross-linked lineages across two plugins. Also gains a pointer to
  `data-engineering-discipline`'s differential-baseline recipe for proving
  net-zero regression in a suite with pre-existing failures.
- `test-driven-development`: a one-line cross-link from its "verify red" step to
  the general form above.
- `systematic-debugging`: Phase 4's "no while-I'm-here" now cross-links
  `data-engineering-discipline` Principle 17 as the canonical scope-bounding rule.

## 0.4.3 — 2026-06-19

Hook `python`-invocation portability: the SessionStart dispatch hook
(`choosing-tools/scripts/inject_dispatch.py`) ran via a bare `python`, which hits the
Microsoft-Store app-execution stub on a Windows machine without Python on PATH. Now
`uv run --no-project -- python …`. Inert-by-default and once-per-session, so the uv
startup cost is negligible. Hook-manifest only — no skill `description` changed.

## 0.4.2 — 2026-06-17

The debugging facet of the 2026-06-17 triage's reinforced "observe, don't infer"
cluster (4 reports / 2 arcs), plus the choosing-tools re-dispatch refinement. Body
only — no `description` changed, so no holdout re-seal. Factored, not triplicated: the
principle's canonical statement stays in `data-engineering-discipline` Axiom 2; these
skills state their own facet and cross-link by name.

### Changed

- `systematic-debugging`: Phase 1's "reproduce" step now makes **dynamic observation
  precede static theory** — for a behavior/regression question, run the failing path and
  read real output before hypothesizing from source — with an explicit exception for
  destructive / irreversible / not-yet-buildable paths (read and instrument first), so
  the rigid skill doesn't mandate "run it" where running is the wrong move. Same step
  adds **confirm the code that ran is the code you read** (resolve `module.__file__` +
  version; editable vs installed diverge silently), cross-linking
  `data-engineering-discipline` Axiom 2. Two new "Common shortcuts" rows — "I read the
  code, so I know what it does" and "I'm pretty sure it's X" (no run yet) — keep the
  inference tripwire descriptive rather than adding a second bright line. (From the
  `2026-06-17-di-incremental-debug-systematic-debugging` and
  `2026-06-17-v1-publish-wheel-fix-systematic-debugging` arcs.)
- `verification-before-completion`: a claims-table row — **an artifact ships right only
  when the built artifact is inspected directly**; a green editable/CI run may never
  build the wheel/image/bundle it stands in for (per
  `2026-06-17-v1-publish-wheel-fix-verification-before-completion#1`).
- `choosing-tools`: "When this runs" now states that **inside a long autonomous task the
  internal phase shifts (design→build→run→report) are direction changes too** — a cheap
  re-dispatch and a one-line naming of the active discipline, rather than riding the
  opening choice for hours (per `2026-06-16-model-tier-calibration#1`,
  `2026-06-16-context-size-calibration#1`).

## 0.4.1 — 2026-06-15

A `skill-authoring` correctness note (the prior triage's `#T8a` watch item); body
only, no description changed.

### Added

- `skill-authoring`: the description contract now warns that a plain-scalar
  `description` must not contain `: ` (colon-space) — YAML reads it as a nested
  mapping and the frontmatter silently breaks, collapsing the skill's recall to zero,
  caught only by `validate_plugins`. Quote it, use a `>` folded block, or an em-dash.
  Shifts the catch left from `evaluate-skill`'s measurement-side pitfall to authoring
  time (per `2026-06-10-humblepowers-build#5`). (`#T8b`, an Edit-tool anchor-hygiene
  note, was declined as a niche, single-report workflow item.)

## 0.4.0 — 2026-06-15

Close the regression-test gap the humblepowers-vs-superpowers eval found (N4): on a
small bug fix the worth-loading bar declines the full `test-driven-development` skill,
and the regression test gets skipped ~half the time (50–60% vs superpowers' ~90–100%).
This is a calibration **refinement, not a reversal** — the bar still gates skill
*ceremony*, but a bug fix's cheap, durable core (leave a red-green regression test) now
applies even when the full skill isn't loaded. Body/doctrine + the inert dispatch
injection only; no `description` changed, so no holdout re-seal. **Validated by the
dyno `humble-vs-super-v1` outcome eval (2026-06-15, n=10/arm on the two bug-fix
tasks):** `regression_test_present` rose from **50% (humble-only) / 60%
(stack-humble)** to **100% / 100%** — matching superpowers (90% / 100%) — while
`fix_correct` and `no_regression` held at 100%. With the economy lead already
established (smaller corpus, ~30–40% cheaper per trial), humblepowers now
Pareto-dominates superpowers on these tasks.

### Changed

- `verification-before-completion`: a bug fix is **not done without a regression test
  that red-greens against the bug** — the "Bug fixed" completion gate now requires the
  test, not just symptom-gone. A fix's durability is a claim like any other; the
  evidence is a test that fails without the fix.
- `choosing-tools` (the loading bar): a third rule of thumb — **declining a skill is
  not declining its cheapest core**; after a bug fix leave the regression test even
  when the full `test-driven-development` skill isn't worth loading. The bar gates
  ceremony, not cheap insurance.
- `choosing-tools` dispatch injection (`inject_dispatch.py`): the always-on protocol
  gains the regression-test-after-fix line (interactive sessions with
  `HUMBLEPOWERS_DISPATCH_INJECT=1`).

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
