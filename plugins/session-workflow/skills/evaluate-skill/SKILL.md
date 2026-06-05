---
name: evaluate-skill
description: Use when you want to behaviorally evaluate a Claude Code skill — measure whether it auto-activates on the prompts it should and stays quiet on near-misses (trigger recall and specificity), whether its output actually satisfies its own discipline (correct-usage), and whether it beats the no-skill baseline (with/without) — producing a scorecard with confidence intervals. Triggers on "evaluate this skill", "test my skill", "does my skill fire", "measure or benchmark skill performance", "is my description triggering", "build an eval for this skill", or running "/evaluate-skill". Claude Code only — it spawns many headless `claude -p` runs, so it is cost-gated; show the plan first. Not for a one-off manual spot-check, and not for judging a skill's design qualitatively (that is a fresh-eyes panel, not a behavioral eval).
user-invocable: true
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Evaluate Skill

Behaviorally evaluate a Claude Code skill — not by reading it (that is a design
review), but by **running it headless many times and measuring what it does**. The
engine that produced this collection's own scorecards ships in `scripts/`; this
skill points it at any skill.

## What it measures — three axes

1. **Triggering** — does the skill auto-activate on prompts it should (recall) and
   stay quiet on near-misses it shouldn't (specificity)? Each prompt is run headless
   with the plugin loaded; the run is a hit if the Skill tool fired.
2. **Correct-usage** — when it fires, does the output satisfy the skill's own
   discipline? An LLM judge scores the WITH-skill output against a rubric you write.
3. **With/without** — does the skill beat the no-skill baseline? A swap-order
   pairwise judge compares WITH vs WITHOUT output — a win counts only if *both*
   orderings agree, else it is a tie (this cancels position bias).

Every rate carries a **Wilson 95% CI**, so you can tell signal from small-N noise.

## When to use

- You wrote or edited a skill and want to know if it actually triggers and helps.
- A description changed and you need to catch a triggering regression.
- You're choosing between two phrasings of a description.

**Not for:** a one-off manual check (just try it), or judging a skill's *design*
qualitatively — bloat, correctness, redundancy — which is a fresh-eyes review (see
the `review-panel` skill), not a behavioral eval. The two answer different questions;
run both.

This is **heavyweight** — it spawns dozens of headless `claude -p` runs. Show the
plan and rough cost (≈ spawns × per-run budget) and get a go-ahead before firing.

## Setup — an `evals/` layout in the target project

The engine reads a small directory tree; create it once per project:

```
evals/
  config.json                  # models, repeats, gates, plugin_of_skill map
  trigger/<skill>.json         # positive + negative trigger prompts
  tasks/<skill>/tasks.json     # grading tasks (prompt + optional fixture)
  tasks/<skill>/rubric.json    # weighted correct-usage criteria
  tasks/<skill>/fixtures/*.md  # optional scenario inputs
  harness/                     # copy this skill's scripts/*.py here
```

Copy this skill's `scripts/*.py` into `evals/harness/` — the engine resolves paths
relative to `evals/` (two levels up from `harness/`). The exact JSON formats and a
worked example are in **`references/eval-harness.md`**.

## Run it (from the project root)

```bash
python evals/harness/run_all.py --concurrency 6   # every skill: triggers + grading -> scorecard
python evals/harness/run_triggers.py <skill>      # just triggering
python evals/harness/grade_tasks.py <skill>       # just correct-usage + with/without
python evals/harness/aggregate.py                 # rebuild report/scorecard.md from report/*.json
```

Then read `report/scorecard.md`: per-skill recall/specificity/correct-usage with CIs
and gate verdicts, the **trigger misses** (your description-tuning signal), and the
with/without per-task table.

## Read the result honestly

- **Triggering is usually the weakness, not output quality** — a good skill that
  never fires helps no one. The trigger-miss list is the highest-value output.
- **Specificity 1.00 with low recall** means the description is too narrow; widen
  the triggers. Low specificity means too broad; add "do NOT activate" clauses.
- **Single-run rate deltas under ~0.15 are noise** — check the CIs before
  concluding a change helped or hurt; re-run if it matters.
- A **command-first skill** (slash-invoked) will show low auto-recall headless;
  that is expected, not a failure — report its recall as informational.

## Pitfalls the engine handles (and you should understand)

`references/eval-harness.md` covers these; the load-bearing ones:

- **Config contamination** — WITH and WITHOUT must use *separate* temp config dirs.
  A `--plugin-dir` run caches the plugin into its config, so a shared dir leaks the
  skill into the "baseline" and makes the skill look worthless. (The single nastiest
  trap; it once made a skill look like it *lost* 78%.)
- **Output capture** — a skill that writes its deliverable to a file or a mid-stream
  message, not the final message, must still be judged on it. Capture assistant text
  + Write/Edit contents, not just the final `result` — or quality reads as ~0.
- **Frontmatter colon-space** — a `": "` inside a single-line `description:` scalar
  silently breaks the skill so it never loads; the eval catches it as an instant,
  total recall collapse. Use an em-dash or a `>` folded block.
- **Headless slash commands** — `/foo` in `claude -p` is literal text, so
  slash-triggered skills read as misses headless even when they work interactively.

## What this does NOT do

It measures behavior, not design. It will not tell you a skill is bloated, wrong, or
redundant — only whether it fires and helps on *your* dataset, which is only as good
as the prompts and rubric you wrote. Pair it with a qualitative fresh-eyes review for
the other half of the picture.
