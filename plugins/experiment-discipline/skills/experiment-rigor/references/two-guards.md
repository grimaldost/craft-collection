# Two guards, and the day they both fired

A worked example of what the freeze buys. Both guards are cheap, both are
pre-committed, and on 2026-07-25 they killed the author's own headline twice in
one day — which is the only reason it is worth writing down, because a guard
that has never vetoed anything is indistinguishable from no guard.

## Guard 1 — a negative control in the bank

A **null bank** is a set of trials where the treatment cannot help by
construction: the arm is inert, the condition it targets is absent, or the two
arms deliver identical treatment over the subset. It answers the question a
primary contrast never can — *what does this metric read when there is nothing
to find?*

**What it caught.** A prescriptive gate scored 1.00 on its primary metric
(footprint) and looked like the wave's winner. The null bank then returned 0.58
`over_scope` on trivial edits: the mechanism fired where nothing needed doing,
so the 1.00 was measuring the arm's willingness to act rather than its judgment
about when to. The primary-metric winner was vetoed by its own control.

**The cheap form.** When two arms deliver identical treatment over any subset,
pre-register that subset's contrast as an A/A calibration and report it beside
the primary. It costs one line in `exploratory_contrasts`. One such calibration
returned a noise floor of +0.0417 against a primary contrast of +0.0417 — which
says what no amount of prose about small effects can.

**Why it must be pre-committed.** A control added after seeing the result is a
subgroup search. Freeze it with the plan or it is not a control.

## Guard 2 — a pre-committed rule for what a finding must survive

State, before the run, what would have to be true for a result to enter a tool
body. Not "we will look at the evidence" — the specific bar: replication across
waves, a null bank that stays null, a minimum n, a cross-distribution check.

**What it caught.** A doctrine promotion had already been drafted off the
vetoed result above. Phase 3's pre-registered replication rule withdrew it: the
follow-up ran 165 trials, prescriptive gates for two other disciplines produced
0.00 `over_scope` in every cell, and the gap came back +0.00. The finding was
plausible, evidenced, single-wave, and wrong. Without the rule it would have
shipped, because nothing else in the loop stops a single-wave finding from
becoming doctrine.

**The loop-side half.** A promotion whose sole evidence is one measured wave
names the replication it is pending and waits for it. Downstream, that is what
`feedback-triage`'s `watch` status is for.

## The shape, stated once

Neither guard tells you what is true. Each one tells you when you are not
entitled to say it yet:

| guard | the question it answers | fails you when |
|---|---|---|
| Null bank | what does this read with nothing to find? | the metric moves on the inert arm |
| Survival rule | what must hold before this enters doctrine? | the evidence is one wave and the rule said two |

The record to keep is the veto, not the win. A wave whose guards never fired is
a wave that has not yet been tested for whether its guards work.
