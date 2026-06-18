---
name: verification-before-completion
description: "Evidence before completion claims: identify the command that would prove the claim, run it fresh in this session, read the full output including exit code, and only then state the result — with the evidence. Use when about to report work as done, fixed, passing, or ready; before committing, opening a PR, or moving to the next task; when relaying a subagent's result (verify the diff, not the report); and when adding a regression test (red-green it: revert the fix, watch it fail, restore, watch it pass). Claims match their evidence — 'tests pass' means this session's run with zero failures, not a previous run or an expectation; if verification fails, the deliverable is the actual state with output. Prefer wiring recurring checks into pre-commit or CI over re-remembering them. Not for designing what to verify (a test-strategy concern) — this skill governs the moment of claiming, not the shape of the suite."
---

# Verification Before Completion

Evidence before claims. This is a **rigid** skill. The bright line: **a
completion claim is made only after the command that proves it has run in
this session and its output has been read.**

## The gate

Before stating any status — done, fixed, passing, ready, complete:

1. **Identify** the command that would prove the claim.
2. **Run it**, fresh and in full — not a remembered result, not a partial
   check.
3. **Read** the output: exit code, counts, failures, warnings.
4. **State the result that the output supports.** Confirmed → the claim, with
   the evidence. Refuted → the actual state, with the output. A true "still
   failing" is a better deliverable than a false "done".

## What claims require

| Claim | Requires | Not sufficient |
|-------|----------|----------------|
| Tests pass | This session's run: zero failures | A previous run, "should pass" |
| Linter clean | Linter output: zero errors | A partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs looking fine |
| Bug fixed | Symptom re-tested gone **and** a regression test that red-greens | Symptom gone, no test left behind |
| Regression test works | Red-green verified (below) | The test passing once |
| Delegated work done | The diff inspected, checks re-run | The agent's success report |
| Requirements met | Line-by-line check against the plan | Tests passing |
| Artifact ships right (wheel, image, bundle) | The built artifact inspected directly | A green editable/CI run — it may never build the artifact |

## Regression tests are red-green verified

Write the test → it passes → revert the fix → the test fails → restore the
fix → it passes again. A regression test that was never seen failing against
the bug proves nothing about the bug.

**A bug fix is not done until that test exists** — even a one-line fix, even when
you judged the full test-driven-development cycle not worth loading for the change
(its exceptions still hold: throwaway spikes, generated code, pure config — agreed
with the user, not self-granted). The regression test costs seconds and is the only
thing that keeps the bug from returning; "the fix is obvious" is how a fixed bug
comes back a month later. Shipping a fix without one is an unverified durability
claim, not a smaller scope.

## Delegated work

A subagent's "success" is a claim, not evidence. Inspect the diff, run the
verification yourself, and report the state you observed — including any gap
between the report and the diff.

## Finishing a change

Before committing, opening a PR, or moving on: the full test command ran this
session with zero failures; the requirements were re-read and checked off
individually; the output is pristine — no stray errors or warnings riding
along. Recurring checks belong in pre-commit or CI rather than in memory —
mechanism outlasts intention.

## Wording that signals an unverified claim

"Should work", "probably passes", "seems fixed", and satisfaction expressed
before the verification ran — each marks a claim outrunning its evidence.
Either run the proving command or state plainly that verification hasn't
happened yet.

## Boundaries

Designing what to verify — suite shape, coverage strategy — is test-strategy
work. This skill governs the moment of claiming. The reproducing-test cycle
for a fix belongs to test-driven-development; this skill takes the evidence from
there — and, when that cycle wasn't loaded, still refuses a fix's completion claim
without its cheap core, a red-green regression test.
