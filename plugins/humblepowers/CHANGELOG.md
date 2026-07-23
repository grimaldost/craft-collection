# Changelog — humblepowers

Notable changes to this plugin. Bump the `version` in `.claude-plugin/plugin.json`
with each release. History before 0.3.2 lives in git (`git log -- plugins/humblepowers`):
0.1.0–0.3.1 covered the initial five-skill port, the `planned-execution` skill (0.3.0),
and the honest-cross-tool-references + MIT-license pass (0.3.1).

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
