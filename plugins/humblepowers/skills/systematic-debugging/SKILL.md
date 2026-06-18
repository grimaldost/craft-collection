---
name: systematic-debugging
description: "Root-cause-first debugging in four phases — investigate (read the full error, reproduce, check recent changes, instrument component boundaries), pattern-match against working examples, test one hypothesis at a time, then fix the cause with a failing test. Use when any bug, test failure, or unexpected behavior lacks a proven cause, when a fix is being proposed before the data flow was traced, when the previous fix didn't work, especially under time pressure (guessing is slower than the protocol), and when three or more fixes have failed — treat that as an architecture signal and raise it with the user instead of attempting a fourth. The bright line: no fix before the root cause is identified with evidence; in multi-component systems, log what enters and exits each boundary before theorizing. Hands the reproducing test to test-driven-development and the resolution claim to verification-before-completion. Not for changes whose cause is already proven (just fix them) and not for performance tuning without a defect (profile first)."
---

# Systematic Debugging

Random fixes waste time and breed new bugs; symptom patches mask the cause
until it resurfaces somewhere worse. The protocol: prove the cause, then fix
it once.

This is a **rigid** skill. The bright line: **no fix is proposed before the
root cause is identified with evidence.** It holds hardest under time
pressure — guess-and-check thrashes for hours where the four phases take
minutes — and it applies to simple-looking bugs too, which have root causes
like any other.

## Phase 1 — investigate

1. **Read the error completely.** The full stack trace, line numbers, error
   codes. The exact answer is often already in it.
2. **Reproduce reliably — observe before you theorize.** Exact steps, every
   time; not reproducible yet means gather more data, not guess. For a behavior
   or regression question, run the failing path and read its real output (logs,
   stack, emitted query) *before* forming hypotheses from source — dynamic
   observation precedes static theory. (Exception: when running the path is
   destructive, irreversible, or not yet buildable, read and instrument first —
   don't trigger a payment or drop a table to "observe" it.) And **confirm the
   code that ran is the code you read** — resolve the imported module's
   `__file__` and installed version; an editable checkout and an installed
   release of the same library diverge silently (the data form is
   `data-engineering-discipline` Axiom 2).
3. **Check recent changes.** Diff, recent commits, new dependencies, config
   and environment differences.
4. **Instrument boundaries in multi-component systems.** Before theorizing
   about a chain (CI → build → signing; API → service → database), log what
   enters and exits each component and whether config propagates; run once;
   read off which layer breaks. Then investigate that layer.
5. **Trace bad values to their origin.** Where does the value come from, what
   called this with it, all the way up — see
   [root-cause-tracing.md](root-cause-tracing.md). Fix at the source, not
   where the error surfaced.

## Phase 2 — pattern-match

Find working code of the same shape in the codebase and compare. Read
reference implementations completely rather than skimming — partial
understanding of a pattern produces partial copies of it. List every
difference between working and broken, including the ones that look like they
can't matter, and pin down the dependencies and assumptions the working
version relies on.

## Phase 3 — hypothesize and test

State one hypothesis precisely: "X is the root cause because Y." Test it with
the smallest change that could confirm it — one variable at a time. If it
fails, form a new hypothesis; stacking a second fix on top of an unconfirmed
first one destroys your ability to attribute anything. When something is not
understood, say so and investigate it — pretending to understand blocks the
protocol exactly where it's needed.

## Phase 4 — fix

1. **Failing test that reproduces the bug** — test-driven-development owns
   the cycle from here.
2. **One fix, addressing the proven cause.** No bundled refactoring, no
   "while I'm here."
3. **Verify**: the new test passes, nothing else broke, and the original
   symptom is actually gone. Hand the claim to verification-before-completion
   before reporting it fixed.
4. **Three failed fixes mean the architecture is in question, not the next
   patch.** The telltale pattern: each fix reveals new coupling or shared
   state somewhere else, or needs a rewrite to land. Stop and raise the
   pattern with the user before a fourth attempt — that conversation is about
   the design, not the symptom.

## Common shortcuts and what they miss

| Shortcut | What it misses |
|----------|----------------|
| "Quick fix now, investigate later" | The patch masks the cause; later never comes. |
| "Just try changing X and see" | Untraced changes can't be attributed; thrashing begins. |
| "It's probably X" | Recognizing a symptom is not understanding a cause. |
| "Several fixes at once saves time" | Nothing can be isolated; regressions ride along. |
| "Emergency — no time for process" | The protocol is the fast path; thrashing is the slow one. |
| "One more attempt" (after two failures) | The third failure is an architecture signal, not bad luck. |
| "I read the code, so I know what it does" | The code you read may not be the code that runs — resolve `module.__file__` + version. |
| "I'm pretty sure it's X" (no run yet) | A causal claim with zero confirming observation is a guess; produce the observation first. |

## When investigation finds no root cause

Genuinely environmental, timing-dependent, or external issues exist. Having
completed the phases: document what was ruled out, implement appropriate
handling (retry, timeout, clear error message), and add the monitoring that
would catch the next occurrence. Most "no root cause" conclusions, though,
are incomplete investigation — check that each phase actually ran before
settling for one.

## Quick reference

| Phase | Activity | Done when |
|-------|----------|-----------|
| 1 Investigate | Read, reproduce, recent changes, instrument | The failing layer is known, with evidence |
| 2 Pattern | Compare against working examples | The differences are listed |
| 3 Hypothesis | One precise theory, smallest test | Confirmed, or replaced |
| 4 Fix | Failing test, single fix, verify | Symptom gone, tests green |

## Supporting references

- [root-cause-tracing.md](root-cause-tracing.md) — backward tracing to the original trigger
- [defense-in-depth.md](defense-in-depth.md) — validation at every layer once the cause is fixed
- [condition-based-waiting.md](condition-based-waiting.md) — replacing arbitrary timeouts with condition polling
