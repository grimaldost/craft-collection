# `choosing-models` on trial for net value

**Status:** measurement designed and pre-registered; **nothing changed in the skill**,
and nothing should be until the evidence exists. $0 spent.

Measurement lives in fathom: bank `routing-decision-v1`, arms
`scenarios/routing-decision/`, analysis `src/fathom/routing.py`, design of record
`docs/specs/2026-08-12-routing-mechanism-eval-design.md` on branch
`eval/routing-mechanisms`.

## The question this repo has to answer

`choosing-models` scores a task on a rubric, maps the score to a tier, and maps the
tier to a model. Three calibration cycles have asked whether that score *predicts the
right tier*. None has asked what asking costs.

That omission matters because of where the question gets asked. The routing decision is
taken by the session dispatching the work, and that session is frequently running on an
expensive model. The skill body plus its scoring rubric plus `models.toml` is about
3,800 words — roughly 6,100 tokens loaded into an Opus session so it can decide whether
some downstream task deserves Haiku.

**If the decision costs more than the routing saves, the skill is net-negative however
well it routes.** That is the trial. Accuracy is one input to the verdict, not the
verdict.

## The estimand

```
C(m) = decision_cost(m) + execution_cost(tier chosen by m) + retry_cost(m)
subject to   quality(m) >= quality(best) - delta,   delta = 0.05 (primary), 0.02 (sensitivity)
```

Cheapest mechanism wins. **Quality is a constraint, not the objective** — the owner's
objective is the lowest spend per session that does not lose quality, and this is that
sentence written as arithmetic.

Candidates: the shipped `rubric`; a `shortcuts` card (below); `always-weak-escalate`;
`fixed-mid`; and `none` — no mechanism at all, whatever the session would do unaided.
`none` is free and it is the true baseline. **If `none` wins, that is the finding**, and
this repo should act on it.

## The candidate replacement, in case the rubric loses

Authored for the trial, and authored to win if it can — measuring the shipped skill
against a strawman would prove nothing. It keeps the rubric's one genuinely learned
insight (that coverage of the fix site, not breadth of the change, is what raises a
task's tier) and drops the arithmetic that carries most of the token cost. Canonical
text: `scenarios/routing-decision/assets/shortcuts.md` in fathom.

Shape: a ten-row lookup from task shape to tier; a three-line floor that only ever
raises (the brief does not name every site that must change -> not below `mid`; nothing
will check the work -> not below `mid`; two implementations must agree -> not below
`strong`); and a tie-break that takes the cheaper tier when a gate will catch a wrong
answer and the dearer one when nothing will. About 335 words, 14x smaller than what
ships today.

**It is a candidate, not a decision.** It replaces nothing unless the measurement says
it should.

## The projection, and what follows from it

**A projection from existing numbers, not a result.** Decision costs come from a
forward token model; execution costs are `model-tier-v1` ledger medians (35 trials per
arm) — a different, saturated bank, so they carry the shape of real agentic coding work
but not the difficulty of the bank that will decide this.

Observed per-task execution cost: weak $0.076, mid $0.225, strong $0.337. So one
strong-to-weak correction saves $0.261 and one mid-to-weak saves $0.150.

Against that, the rubric's decision-cost premium over deciding unaided, and the share
of decisions it must therefore correct just to break even:

| decision taken at | tasks per decision | premium/task | must correct (strong->weak) |
|---|--:|--:|--:|
| weak tier | 9 | $0.0030 | 1.2% |
| weak tier | 1 | $0.0160 | 6.1% |
| mid tier | 9 | $0.0091 | 3.5% |
| mid tier | 1 | $0.0480 | 18.4% |
| strong tier | 9 | $0.0152 | 5.8% |
| **strong tier** | **1** | **$0.0800** | **30.6%** |

The bottom row is the ordinary case: an Opus session deciding one spawn's tier. There
the rubric has to beat unaided judgment on roughly **one decision in three** — and on
about one in two if its corrections are mid-to-weak rather than strong-to-weak. Nothing
on record shows it clearing that. Three calibration runs put the on-diagonal count at
1/7; the honest reading each time was "the bank had no headroom", not "the rubric is
wrong", but a third of decisions is a lot of correcting to assume.

**The constructive half is the more useful one.** Read down the table: the premium is
driven by *where the decision is taken and how many tasks it covers*, not by what the
rubric says. Deciding at the weak tier cuts the bar about 5x. Batching nine tasks cuts
it about 5x again. Both together cut it roughly 25x, to about 1% — a bar almost any
sane policy clears.

So the change this evidence points at is not "delete the rubric". It is **stop paying
strong-tier prices to run it one task at a time** — either delegate the scoring to a
weak-tier call, or score the batch once at series-authoring time instead of per spawn.
That change is available whichever way the accuracy question lands, and the skill
already has the surface for it: step 5 of its procedure asks for a per-task batch table,
which is the batched shape. What it lacks is any statement that the *decision itself*
has a price and a cheapest place to be taken.

## What would license a change here

Per the standing rule — nothing is retired or changed on a measurement without power:

1. **Decision cost is measurable now** and is the cheap half. Tranche 1 (54 trials,
   ~$4.73) fits the fixed and marginal decision cost at all three deciding tiers.
2. **Accuracy is not measurable yet.** Its ground truth is `cheapest_adequate_tier` from
   fathom's `model-tier-v2`, which is authored, unrun, and blocked on an expired host
   OAuth session. Until that bank runs, C(m) has one measured term and the rest is
   projection.
3. **An early stop may settle it without the substrate.** If `rubric` and `none` emit
   the same tier on 8 of 9 briefs, the rubric's routing value is bounded by a single
   disagreement and the comparison is already decided on decision cost alone. That
   result costs $4.73 and needs no outcome table.
4. **A 5-point quality non-inferiority will probably not be certifiable** at any
   affordable n on a 9-task bank. If the mechanisms cannot be distinguished on quality,
   the report will say exactly that rather than record a null as equivalence.

Until at least (1) and (3) are in hand, `SKILL.md`, `references/scoring-rubric.md` and
`models.toml` stay exactly as they are.
