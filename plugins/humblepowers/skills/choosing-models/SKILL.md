---
name: choosing-models
description: >-
  Choose which Claude model and effort a task should run on — a
  capacity-dispatch step when work is about to be delegated or priced. Use when
  spawning subagents or workflow agents, when authoring a governed multi-PR
  series file (e.g. a convoy series.toml governance block, and per-PR tiers
  where the engine supports them), when a planning tool asks for a per-task
  tier (a route-and-budget phase, per-role picks in an execution plan), when
  sizing a review panel's model ladder, or when deciding "is Haiku enough for
  this task?" / "which tier should this PR run at?". Scores the task with the
  bundled rubric, maps score to tier to current model via models.toml, then
  applies context modifiers (oracle coverage, reversibility, retry economics).
  Model facts — ids, prices, context windows, API mechanics — belong to the
  platform's model reference (e.g. the claude-api skill); this skill reads that
  data and owns only the task-to-tier routing policy. Not for choosing which
  skill owns a task (that is choosing-tools), not for toolkit inventory (that
  is toolkit-awareness), and not an in-run auto-escalation mechanism —
  escalation is an authoring or retry decision.
---

# Choosing Models

Capacity dispatch. choosing-tools decides which skill owns a task; this skill
decides how much model the task gets. The output is a **(model, effort)
pair** — model is capacity, effort is thinking depth, and the two are chosen
together, per task, at the moment work is delegated or priced.

This is a **flexible** skill: the procedure below is the default shape of the
decision; the judgment inside each step is yours.

## Where the decision is taken

Consulting the rubric costs what the deciding session costs, and that runs
opposite to what it is worth: across three deciding tiers the measured premium
per task spans two orders of magnitude, while agreement with the session's
unaided choice rises as the decider gets dearer. So:

- **A strong-tier session routing a single task skips the rubric.** It lands
  on the tier it would have chosen unaided, at the highest price of any
  deciding context — a break-even no correction rate reaches.
- **Score batches, and score them at the weak tier.** The fixed cost amortises
  there, and that is the only deciding context where the scoring changed any
  decision at all. It is also the tier where the rubric was seen misapplied, so
  check an emitted tier against the thresholds. Numbers: `models.toml`.

## The procedure

1. **Score the task** with [references/scoring-rubric.md](references/scoring-rubric.md),
   at authoring or spawn time. The rubric owns *how to score* and never moves
   without calibration evidence.
2. **Map score → tier** with the thresholds in [models.toml](models.toml),
   which owns *what runs* and changes when models ship.
3. **Map tier → the surface's vocabulary** (table below).
4. **Apply the context modifiers** (next section).
5. **For batches**, present the per-task table (task, score, tier, model,
   estimated cost) with an all-top-tier comparison row, so the saving is
   visible.
6. **Persist the prediction** where run telemetry can reach it — comments on
   each task block of the series file (`# choosing-models: score=42 tier=mid`)
   or the series design doc. A score that lives only in chat is never
   reconciled, and recurring misses are the rubric's evidence.

## Context modifiers

- **Oracle-coverage discount.** Downshifting one tier on implementation work
  is licensed by the *quality of the oracle around the task*, not by the
  presence of a gate. Ask what oracle will exist for **this** task in **this**
  run — including one about to be authored — not the one the environment
  already has. Downshift when the gate carries independent checks covering
  the task's dominant failure classes; a lint-plus-types-plus-tests gate does
  not qualify on its own. The discount presumes the gated failure is
  **diagnosable at the discounted tier** — a red gate the cheaper model cannot
  read buys a repair loop, not a saving — and that a gate sees it at all:
  where the fix site sits outside the shipped suite's coverage, that suite
  caught none of 26 measured failures. Evidence: `models.toml`.
- **Ungated, hard-to-reverse, or interface-defining work** stays at or above
  its scored tier.
- **Review and design judgment route by stakes,** not by implementation
  score — the top tier for a hard-to-reverse call, a lower rung when the
  stakes don't justify it.
- **Escalation is an authoring or retry decision.** The frontier tier is
  never score-assigned; opt in when a strong-tier attempt failed and the
  retry needs more model, for the batch's highest-stakes hardest-to-reverse
  design work, or at score ≥ 90 when the task cannot be decomposed. No in-run auto-escalation — an
  engine that tried it cut it ("fired on the wrong signal"), and stronger
  models attempting more ambitious strategies can be *less* reliable on
  long-horizon irreversible work.

## Effort defaults

Defaults, not calibrated thresholds: `high` unless a row below applies —
mechanical, tightly scoped work runs `low`–`medium`, hard agentic or coding
work `xhigh`, both from mid up (the weak tier has no effort knob); `max` only
where correctness dominates cost. A surface without an effort knob (the Agent
tool today) inherits the session's setting — say so rather than pretending.

## Emission surfaces

Tier names are not shared across surfaces — emit each surface's own words:

| Surface | Emits | Vocabulary |
|---|---|---|
| series-file governance (e.g. convoy) | `tier` or `model`, plus `effort` | `weak/mid/strong/frontier` or API string |
| Agent-tool spawn | `model` | family alias (`haiku/sonnet/opus/fable`) |
| workflow `agent()` | `model` + `effort` | family alias + effort level |
| planning-tool per-PR tier (e.g. keel) | tier per task | family names — translate, don't assume |
| direct API tooling | model id | undated API string |

A workflow `agent()` with no `model` inherits the session model (possibly
frontier); no engine-level cap exists — under a tier cap, every call carries
an explicit `model`.

While an engine is series-global (no per-task keys): score every task anyway,
set the series tier to the modal tier, and consider splitting at a tier
boundary when the spread is two or more tiers — splitting buys tier fit at
coordination cost; sometimes accepting the overpay is right.

## Staleness tripwires

- **Age (always fires):** `models.toml` carries `review_by`; past that date,
  offer `/refresh-models` before trusting the table.
- **Environment (partial):** `scripts/lineup_check.py <model id>` exits 1 when
  the session's own model is not in `models.toml` — run it rather than checking
  by hand. It cannot see a model the session doesn't know about; the age check
  is for that.

## Data and overrides

`models.toml` owns the thresholds, tier assignments, aliases, provenance and
cost observations; its header carries the thin-file rule and the
**project-override chain** — a project copy wins over the plugin's.
`/refresh-models` updates all of it.

## Boundaries

- **choosing-tools** owns which skill or tool runs; the two fire at the same
  moments and answer different questions.
- **toolkit-awareness** owns what is installed.
- **Model facts** (ids, prices, limits, API mechanics) come from the
  platform's model reference (e.g. the claude-api skill); this skill consumes
  those facts and owns only the routing policy.
- **skill-authoring** owns this description; when the skill wins or loses
  dispatch wrongly, fix the trigger surface there.
