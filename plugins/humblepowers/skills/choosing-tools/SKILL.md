---
name: choosing-tools
description: Decide which installed skill or tool, if any, should own a task — a fit-ranking dispatch step at task starts and direction changes, not a per-message ritual. Use when starting substantive work that more than one installed capability could plausibly own, when unsure whether a discipline skill (TDD, debugging, data-contract guardrails) applies to the work at hand, when two skills seem to claim the same job, or when the user asks "which tool/skill should handle this". Ranks candidates against their descriptions' positive and negative triggers and loads one only when its expected benefit clearly exceeds its context and anchoring cost; exits in one line when nothing fits, and sets aside a loaded skill plainly when it turns out wrong. Pairs with toolkit-awareness, which answers what is installed — this skill decides whether and when to load it. Not for inventory questions (that is toolkit-awareness) and not for authoring or tuning skill descriptions (that is skill-authoring).
---

# Choosing Tools

Tool selection runs on fit, not volume. This skill states the dispatch policy
once, centrally, so no individual skill has to argue for its own attention —
descriptions describe, and this protocol ranks them.

This is a **flexible** skill: the procedure below is the default shape of the
decision, and the judgment inside each step is yours.

## When this runs

At task starts and direction changes — the moments where work could take a
shape: build, fix, migrate, refactor, review, plan, audit. It does not run on
conversational turns, follow-up messages inside an active task, or questions
answerable directly. A dispatch check on "hang on" is ceremony, not selection.

## The dispatch procedure

1. **Name the task in one phrase.** "Schema change with downstream consumers",
   "unexplained test failure", "new feature, shape unclear". The phrase is
   what candidates get ranked against.
2. **Shortlist candidates.** Installed skills whose triggers plausibly match.
   When unsure what is installed, get the live inventory (toolkit-awareness)
   rather than recalling from memory.
3. **Check positive and negative triggers.** A candidate that matches the
   phrase but sits in another skill's declared territory ("not for X — that
   is Y") loses to the owner. Negative space decides ties.
4. **Load when the bar is met.** Load the best fit when its expected benefit —
   risk averted, rework avoided, discipline the task genuinely needs — clearly
   exceeds its cost: the context it occupies and the way a loaded skill
   anchors the plan. When a process discipline and an implementation skill
   both apply, load the process discipline first; it shapes how the
   implementation runs.
5. **Exit in one line when nothing clears the bar.** "No installed skill owns
   this; proceeding directly" is a complete, correct outcome. Record it and
   move on.
6. **Set aside misfires plainly.** A loaded skill that turns out not to fit is
   abandoned explicitly — "loaded X; it assumes Y, which doesn't hold here;
   continuing without it." Following a misfit skill to completion because it
   was loaded is anchoring, not diligence.

## The loading bar

The threshold is deliberately qualitative — "clearly exceeds" — because a
numeric cutoff in prose would be fake precision. What calibrates the bar over
time is measurement: the trigger evals and their gates, not adjectives. Two
rules of thumb hold:

- Cheap, scoped reference skills (a schema, a config convention) clear the bar
  easily; heavyweight process skills that restructure the whole turn need a
  task that actually has the failure modes they prevent.
- Keyword overlap alone never clears the bar. "Test" appearing in the task
  does not load a TDD skill; implementing behavior does.

## Boundaries

- **toolkit-awareness** owns the inventory — what is installed and who owns
  which concern. This skill consumes that answer; it does not produce it.
- **skill-authoring** owns descriptions — when a skill keeps winning or losing
  dispatch wrongly, fix its trigger surface there. Never compensate by
  inflating register; selection quality depends on descriptions staying
  honest.

## Optional session-start reminder

The plugin ships a SessionStart hook that injects a compact version of the
procedure above. It is inert by default: set `HUMBLEPOWERS_DISPATCH_INJECT=1`
to enable it. The hook is the mechanical home for "always consider the
toolkit" — a reminder the harness re-issues each session beats prose asking to
be remembered.
