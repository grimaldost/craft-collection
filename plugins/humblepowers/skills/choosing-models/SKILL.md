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
together, per task, at the moment work is delegated or priced. The rubric and
thresholds descend from a calibrated predecessor cycle and stay honest the
same way: observed-run evidence moves them, not taste.

This is a **flexible** skill: the procedure below is the default shape of the
decision; the judgment inside each step is yours.

## The procedure

1. **Score the task** with [references/scoring-rubric.md](references/scoring-rubric.md)
   — mentally, at authoring or spawn time, zero cost. The rubric owns *how to
   score*; it never moves without calibration evidence.
2. **Map score → tier** with the thresholds in [models.toml](models.toml) —
   the data file owns *what runs* (tier assignments, current lineup) and is
   the part that changes when models ship.
3. **Map tier → the surface's vocabulary** (table below).
4. **Apply the context modifiers** (next section).
5. **For batches** — a series, a workflow, a panel — present the per-task
   table (task, score, tier, model, estimated cost) with an all-top-tier
   comparison row, so the saving is visible.
6. **Persist the prediction.** A score that lives only in chat can never be
   reconciled with outcomes. Land the batch table where run telemetry can
   reach it — comments on each task block of the series file
   (`# choosing-models: score=42 tier=mid`) or the series design doc. Run
   feedback then checks predictions against gate results, and recurring
   misses become rubric evidence.

## Context modifiers

- **Oracle-coverage discount — a labeled hypothesis, pending a crossed
  calibration.** Downshifting one tier on implementation work is licensed by
  the *quality of the oracle around the task*, not by the presence of a gate:
  the strongest replicated finding: a suite-only gate at the weak tier
  neither detects nor lifts (gates green, escapes reach the oracle); gate
  value tracks the independence and coverage of the checks. Downshift when the gate carries independent checks covering
  the task's dominant failure classes; a lint-plus-types-plus-tests gate does
  not qualify on its own. What is established twice over: scored tiers
  over-provision in the small, and on feature-refactor shapes an iterative
  implement→gate→fix loop beat a bigger one-shot model.
- **Ungated, hard-to-reverse, or interface-defining work** stays at or above
  its scored tier. The discount never applies where no oracle exists.
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
- **Cost caveats that keep getting re-learned:** cheaper per token is not
  cheaper per task (tokenizer and thinking-volume differences); cheaper is
  not faster wall-clock; a large prompt at max effort costs 5–10× the
  small-prompt baselines.

## Effort defaults

Defaults, not calibrated thresholds: `high` unless a row below applies —
mechanical, tightly scoped work runs `low`–`medium`; hard agentic or coding
work at the strong tier runs `xhigh` where the surface exposes it; `max` only
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
Silently pinning the top tier for a whole series is the failure mode this
skill ends.

## Staleness tripwires

- **Age (always fires):** `models.toml` carries `review_by`; past that date,
  offer `/refresh-models` before trusting the table.
- **Environment (partial):** where the session environment lists the current
  model lineup, a model named there but missing from `models.toml` flags the
  table stale. This cannot see a model the session doesn't know about — the
  age check and the quarterly refresh are for that.

## Data and overrides

`models.toml` stays thin: thresholds, tier assignments, aliases, calibration
provenance, typical-cost observations. Prices are read from the platform's
model reference at the point of use, not duplicated here. Calibration is
distribution-relative, so a **project-level override wins**: a project copy of
`models.toml` (project skill dir or a method binding) takes precedence over
the plugin's; project-specific corrections land there, not in the global
file. `/refresh-models` is the update path for all of it.

## Boundaries

- **choosing-tools** owns which skill or tool runs; this skill owns how much
  model. The two fire at the same moments and answer different questions.
- **toolkit-awareness** owns what is installed.
- **Model facts** (ids, prices, limits, API mechanics) come from the
  platform's model reference (e.g. the claude-api skill); this skill consumes
  those facts and owns only the routing policy.
- **skill-authoring** owns this description; when the skill wins or loses
  dispatch wrongly, fix the trigger surface there.
