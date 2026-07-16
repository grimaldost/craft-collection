# Eval run — §3–§5 acceptance measurements (agent-portability wave)

- **Date:** 2026-07-16
- **Branch measured:** the portability wave at `e0603f2` (PR01–PR09 plus the
  advisory folds and the craft-floor pin); plugin versions session-workflow
  0.15.0, humblepowers 0.6.0, engineering-discipline 0.2.0
- **What this run is:** hand-off item 1 — the one acceptance criterion the
  implementing environment could not execute (no authenticated `claude` CLI
  there). This environment has one, so the owed §3–§5 trigger, holdout, and
  correct-usage evals were run and are recorded here for the merge PR.
- **Instrument:** `evals/harness/` at this branch (post-§8 seam),
  `claude-sonnet-4-6`, repeats=3, gates recall ≥ 0.8 / specificity ≥ 0.9 /
  correct-usage ≥ 0.7 (`evals/config.json`)

## Environment and its known noise

Managed remote Claude Code session (CLI 2.1.211). Two properties matter for
reading the numbers:

1. **Auth flows through the environment, not the config file.** There is no
   `~/.claude/.credentials.json`, so the harness's isolated config dir is
   empty rather than credentials-only. `smoke.py` functional checks 1–4 all
   pass (authed spawn, plugin loads, activation detected, judge parses,
   trigger arm cannot write); check 0's copied-file assertion is n/a here by
   construction. Isolation is preserved — the temp config carries nothing.
2. **Egress goes through a TLS-re-terminating proxy.** A minority of spawns
   fail with per-run API errors ("Self-signed certificate detected",
   "Prompt is too long") that the runner's transient matcher does not retry.
   These are surfaced, not hidden, per the N28a rule: a fired-then-errored
   run counts as fired; an errored-before-activation run is reported and the
   error-excluded recall is printed alongside the strict one. Sealed reads
   ran at `--concurrency 2` to minimize this.

The cross-environment anchor: compaction-survival's sealed holdout scored
1.00/1.00 here, matching its 2026-07-06 baseline row measured on the
maintainer's machine — the instrument transfers.

## Dev trigger sets

| skill | recall (CI) | recall excl. errors | specificity (CI) | reading |
|---|---|---|---|---|
| review-panel | 0.00 [0.00,0.14] | 0.00 | 1.00 [0.86,1.00] pass | command-first per `config.json`: auto-recall is informational; specificity is the gated number and passes |
| compaction-survival | 1.00 [0.86,1.00] pass | 1.00 | 1.00 [0.82,1.00] pass | clean pass |
| toolkit-awareness | 0.71 [0.51,0.85] fail | 0.71 (no positive-run errors) | 1.00 [0.86,1.00] pass | misses are clean, not infra; see attribution below |
| evaluate-skill | 0.96 [0.80,0.99] pass | — | 1.00 [0.86,1.00] pass | clean pass |
| choosing-tools | 0.50 [0.31,0.69] fail | 0.50 | 1.00 [0.86,1.00] pass | misses are clean; see attribution below |
| python-engineering | 0.71 [0.51,0.85] fail | 0.85 [0.64,0.95] pass | 1.00 [0.86,1.00] pass | pooled number depressed by 4 errored positive runs; error-excluded recall clears the gate |

## Correct-usage tasks (where a task exists)

| skill | correct-usage (CI) | mean score | notes |
|---|---|---|---|
| review-panel | 0.00 [0.00,0.56] fail | 0.00 | zero error runs; with-arm never activated the skill (it asks before firing — impossible headless); with-arm still won the pairwise judge 2/3 |
| toolkit-awareness | 1.00 [0.44,1.00] pass | 1.00 | fires-and-used-correctly on a real task |
| evaluate-skill | 0.00 [0.00,0.56] fail | 0.37–0.52 | first run had 2/3 infra-errored records; the sanctioned clean re-run (zero errors) reproduced 0.00 |
| python-engineering | 0.67 [0.30,0.90] fail | 0.74 | clean measurement (6/6 valid units, zero errors); marginal against the 0.7 gate |

**Systemic finding:** `with_activation_rate` was 0.00 on every task, including
the passing one. In this environment the task prompts never cause the Skill
tool to be invoked; the correct-usage number therefore measures "does the
model's default behavior meet the rubric", not "does the loaded skill improve
usage". toolkit-awareness passes because default behavior matches its rubric;
evaluate-skill and review-panel fail because their methods (harness evals,
panel spawning) do not happen spontaneously. This belongs in the item-4
experiment design: separate activation from rubric-compliance before reading
correct-usage as a skill property.

## Pre-wave A/B (attribution)

Setup: a worktree at `925d653` (the certified spec, before any §3–§5 edit)
with the branch-head harness copied in — same instrument, same datasets
(verified byte-identical), same environment; only the plugin tree differs.
review-panel is the only evaluated skill whose trigger surface (frontmatter
`description`) changed in the wave — verified by byte-comparison across all
six skills; evaluate-skill's §3 body edit could in principle affect usage, so
both were run in both arms.

| measurement | pre-wave | post-wave | reading |
|---|---|---|---|
| review-panel trigger recall | 0.08 [0.02,0.26] | 0.00 [0.00,0.14] | overlapping intervals; both arms sit in the command-first no-auto-fire regime |
| review-panel specificity | 1.00 | 1.00 | identical |
| review-panel correct-usage | 0.00 | 0.00 | identical |
| evaluate-skill correct-usage | 0.00 (mean 0.52) | 0.00 (mean 0.37–0.52) | identical; the §3 body never loads because the task prompt does not activate the skill in either arm |

**Conclusion:** no measured behavior differs between the pre-wave and
post-wave trees. Every under-gate number in this run is a property the
codebase already had (or a property of this measurement setup), not a
regression introduced by the wave.

## Sealed holdout reads (single sanctioned read each, at concurrency 2)

| skill | recall (CI) | specificity (CI) | verdict |
|---|---|---|---|
| compaction-survival | 1.00 [0.76,1.00] | 1.00 [0.70,1.00] | matches its 2026-07-06 baseline; harness comparator: generalizes |
| toolkit-awareness | 0.00 [0.00,0.24]; excl-err 0.00 [0.00,0.35] | 1.00 [0.61,1.00] | birth read; all 4 unseen positives missed cleanly |
| choosing-tools | 0.00 [0.00,0.24]; excl-err 0.00 [0.00,0.30] | 1.00 [0.61,1.00] | birth read; all 4 unseen positives missed cleanly |
| python-engineering | 0.00 [0.00,0.24]; excl-err 0.00 [0.00,0.30] | 1.00 [0.61,1.00] | birth read; all 4 unseen positives missed cleanly |

Rows recorded in `evals/trigger/holdout/BASELINES.md` per the N29a rule.

### Attribution for the three 0.00 birth reads

- The descriptions of all three skills are **byte-identical to the pre-wave
  tree** (verified) — the wave did not touch these trigger surfaces, so the
  numbers measure the long-standing descriptions, not the §3–§5 edits.
- The unseen positives are intent paraphrases by design (the sets were sealed
  to measure generalization beyond lexical overlap): "which installed skill
  owns X" (toolkit-awareness), "rank the plausible skills and load the right
  one before this task" (choosing-tools), "audit this project's dev setup
  against current standards" (python-engineering). None echo their
  description's vocabulary, and none routed.
- Every near-miss was correctly rejected (specificity 1.00 across the board),
  so the failure mode is purely under-triggering on paraphrased intent — the
  trigger-lexical-ceiling pattern the BASELINES preamble already names.
- Closing the gap means description tuning, which is out of scope for this
  wave (its §3–§5 edits deliberately avoided trigger surfaces) and is
  reseal-protocol work: tune on dev evidence, then reseal and re-baseline the
  holdouts. Recorded as follow-up, not fixed here.

## Disposition against the §3–§5 acceptance criteria

- **Run and recorded:** yes for every owed dataset — six dev trigger sets,
  four sealed holdouts, four correct-usage tasks, plus a pre/post-wave
  attribution A/B the criteria did not ask for.
- **Passing at gate:** compaction-survival (dev + holdout, at baseline),
  evaluate-skill triggers, python-engineering triggers via error-excluded
  recall, toolkit-awareness correct-usage, specificity everywhere,
  review-panel specificity (its gated number).
- **Under gate, attributed pre-existing:** toolkit-awareness and
  choosing-tools dev recall; the three 0.00 holdout birth reads;
  review-panel and evaluate-skill correct-usage (activation-bound);
  python-engineering correct-usage (0.67, marginal, clean).
- **The wave-regression clause:** the hand-off says to treat a recall drop
  below the holdout gate as a §3–§5 wording regression to fix. The A/B and
  byte-comparisons show no drop is attributable to the wave's wording — there
  is nothing in the §3–§5 diffs to revert or fix that would move these
  numbers. The under-gate results are recorded as first-measured floors with
  a named follow-up (description tuning under reseal) instead.

## Cost (list-equivalent, subscription auth)

Dev triggers $10.5 across 282 spawns; tasks $1.8 across 4 skills (plus $0.4
re-run); pre-wave A/B $1.7; holdouts $2.4 across 75 spawns. Total ≈ $17.

## Raw artifacts

`evals/report/triggers.json` and `evals/report/grading.json` in the working
tree of this session (untracked, per policy); the pre-wave arm's reports in
the throwaway worktree; full run logs preserved in the session scratchpad.
This document is the durable record.
