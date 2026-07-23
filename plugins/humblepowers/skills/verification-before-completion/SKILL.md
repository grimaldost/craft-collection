---
name: verification-before-completion
description: "Evidence before completion claims: identify the command that would prove the claim, run it fresh in this session, read the full output including exit code, and only then state the result — with the evidence. Use when about to report work as done, fixed, passing, or ready; before committing, opening a PR, or moving to the next task; when relaying a subagent's result (verify the diff, not the report); and when adding a regression test (red-green it: revert the fix, watch it fail, restore, watch it pass). Claims match their evidence — 'tests pass' means this session's run with zero failures, not a previous run or an expectation; if verification fails, the deliverable is the actual state with output. Prefer wiring recurring checks into pre-commit or CI over re-remembering them. Not for designing what to verify (a test-strategy concern) — this skill governs the moment of claiming, not the shape of the suite."
---

# Verification Before Completion

Evidence before claims — a **rigid** skill. The bright line: **a
completion claim is made only after the command that proves it has run in
this session and its output has been read.**

## The gate

Before stating any status — done, fixed, passing, ready, complete:

1. **Identify** the command that would prove the claim.
2. **Run it**, fresh and in full — not a remembered result or partial check.
3. **Read** the output: exit code, counts, failures, warnings. (`$?` is the
   LAST command's exit code — read it right after the bare command, never
   after a pipe; capture output to a file instead.)
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
| Artifact ships right (wheel, image, bundle) | The built artifact inspected directly | A green editable/CI run — it may never build it |

## Regression tests are red-green verified

Write the test → it passes → revert the fix → the test fails → restore the
fix → it passes again. A regression test never seen failing against the bug
proves nothing about it.

**A bug fix is not done until that test exists** — even a one-line fix, even when
you judged the full test-driven-development cycle not worth loading for the change
(its exceptions still hold: throwaway spikes, generated code, pure config — agreed
with the user, not self-granted). The regression test costs seconds and keeps the
bug from returning; "the fix is obvious" is how a fixed bug comes back later.
Shipping a fix without one is an unverified durability claim, not a smaller scope.

## A verifier is trusted green only after it has been seen red

The regression-test rule above is one case of a principle that governs *any*
verifier — a gate, a parity diff, a contract check, an eval assertion: a check
seen only green is indistinguishable from one that tests nothing (a typo'd join
key, a tolerance so wide nothing trips, a fixture that hits a fallback). Before
trusting a green, watch it go red — plant a known violation, confirm the catch,
remove the plant. test-driven-development's "verify red" is this for tests; for
an enforcement gate, prove it can fail before trusting it green. (A
data-engineering skill states this canonically for gates when installed — e.g.
`data-engineering-discipline`'s prove-the-gate-can-fail non-vacuity matrix.)
Same discipline, named here.

## Delegated work

A subagent's "success" is a claim, not evidence. Inspect the diff, run the
verification yourself, and report the state you observed, including any gap
between report and diff.

## Finishing a change

Before committing, opening a PR, or moving on: the full test command ran this
session with zero failures; requirements re-read and checked off
individually; the output is pristine — no stray errors or warnings riding
along. Recurring checks belong in pre-commit or CI, not memory — mechanism
outlasts intention. When the suite carries irreducible pre-existing
failures, the honest gate is "zero net regression" against a baseline, not an
absolute zero: diff this run's failure set against the baseline's and require
the difference to be empty — capture the baseline by stashing the change and
running the suite, or by running it at the base commit. (A data-engineering
skill, when one is installed, carries these as concrete parity recipes — e.g.
`data-engineering-discipline`'s differential-baseline: the stash-test and the
base-commit set-diff.)

## Wording that signals an unverified claim

"Should work", "probably passes", "seems fixed", and satisfaction expressed
before the verification ran — each marks a claim outrunning its evidence: run
the proving command or say plainly that verification hasn't happened.

## Boundaries

Designing what to verify — suite shape, coverage strategy — is test-strategy
work. This skill governs the moment of claiming. The reproducing-test cycle
for a fix belongs to test-driven-development; this skill takes the evidence from
there — and, when that cycle wasn't loaded, still refuses a fix's completion claim
without its cheap core, a red-green regression test.
