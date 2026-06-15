---
name: planned-execution
description: "Turn an agreed design or spec into a complete implementation plan and execute it task by task with fresh subagents and two-stage review — the midweight lane between direct implementation and a governed PR series. Use when a feature needs a multi-step plan with review checkpoints but not series machinery: 'write the implementation plan for this spec', 'execute this plan task by task', 'plan then build this', 'run docs/plans/<file>', or when work has outgrown a single TDD loop but doesn't warrant keel or pr-pilot. The plan contract is firm: bite-sized steps with exact paths, complete code, exact commands with expected output, and no placeholders — a zero-context engineer could execute it cold. The loop is firm too: per task, a fresh implementer subagent, then spec-compliance review, then code-quality review, re-reviewing after each fix. Not for deciding what to build (brainstorming comes first), not for governed multi-PR series with gates and dependency DAGs (keel and pr-pilot own that), and not for small single-loop fixes (test-driven-development directly)."
---

# Planned Execution

The midweight lane: a spec becomes a plan an engineer with zero context could
execute cold, and the plan becomes working software through a loop of fresh
implementer subagents and two-stage review. Below this lane, implement
directly with test-driven-development; above it, a governed series (keel,
pr-pilot) owns the work.

This is a **rigid** skill: the plan contract and the review-loop order are
bright lines, because the failure mode of plan-then-execute work is
self-granted shortcuts — placeholder steps, skipped re-reviews, "close
enough" spec compliance.

## The plan contract

Write the plan assuming a skilled engineer who knows nothing about this
codebase or problem domain. Save it where the project keeps plans (user
preference wins; a dated file under the repo's plans convention is a sensible
default).

1. **Map the file structure first.** Which files are created or modified and
   what each is responsible for — decomposition gets locked in here. One
   clear responsibility per file; follow existing codebase patterns.
2. **Bite-sized steps, one action each** (2–5 minutes): write the failing
   test — run it and watch it fail — write the minimal implementation — run
   to green — commit. The task granularity of test-driven-development,
   written down.
3. **Exact everything.** Exact file paths (`src/path/file.py:123-145` for
   modifications), complete code in every code step, exact commands with
   their expected output.
4. **No placeholders.** These are plan failures, not shorthand: "TBD",
   "implement later", "add appropriate error handling", "write tests for the
   above" without the test code, "similar to Task N" instead of repeating
   the code, references to types or functions no task defines.
5. **Header**: goal in one sentence, architecture in two or three,
   tech stack, and the execution mode (this skill's loop, or inline).
6. **Self-review before execution**: every spec requirement maps to a task;
   no placeholder patterns survive; names and signatures used in later tasks
   match their definitions in earlier tasks; every config field, limit, or
   flag the plan introduces is consumed by a task, not merely declared. Fix
   inline and move on.

## The execution loop

Read the plan once, extract every task with its full text and context, and
track them (one tracked item per task). Then, per task:

1. **Dispatch a fresh implementer subagent** with the complete task text and
   scene-setting context — where this task fits, what came before. Never
   make a subagent read the plan file; the controller curates exactly what
   it needs. Answer its questions before it starts, not after it guesses.
2. The implementer implements, tests, commits, and self-reviews, then
   reports a status:
   - **DONE** → proceed to review.
   - **DONE_WITH_CONCERNS** → read the concerns; correctness or scope
     concerns get addressed before review, observations get noted.
   - **NEEDS_CONTEXT** → provide the missing context, re-dispatch.
   - **BLOCKED** → change something before re-dispatching: more context, a
     more capable model, a smaller task split — or escalate to the user if
     the plan itself is wrong. Re-dispatching unchanged is not a strategy.
3. **Spec-compliance review** by a fresh subagent: does the code match the
   task's requirements — nothing missing, nothing extra? Issues go back to
   the implementer, then re-review. "Close enough" is a finding, not a pass.
4. **Code-quality review** by a fresh subagent, only after spec compliance
   passes: is it well built? Same fix-and-re-review loop.
5. Mark the task complete; next task. Don't pause to ask "should I
   continue?" between tasks — the user asked for the plan to be executed.
   Stop only for BLOCKED-beyond-recovery, genuine ambiguity, or completion.

After the last task: one final review subagent over the whole implementation
against the whole plan — including an **integration trace**: follow every
config field, limit, flag, or option the plan introduced (task fields,
scenario fields, CLI options) to a consumer, confirming each is actually
read end-to-end, not merely declared. Plan-fidelity review is blind here by
construction — a declared-but-unconsumed limit passes both code-matches-plan
and code-is-well-built while doing nothing, surfacing only at runtime. Then
hand the completion claim to
verification-before-completion — its evidence rules govern the "done".

## Authoring and dispatch notes

**Strip-on-save hooks.** If the project runs a format-on-save hook that strips
unused imports or symbols, author each import in the *same* step that first
references it. An "add the import now, use it later" sequence breaks: the hook
removes the still-unused import the instant it lands, and the later step hits
an undefined name. It bites fresh implementers and the controller identically —
sequence the edit so the symbol is introduced and used together.

**Task granularity vs dispatch economics.** "Bite-sized" means one clear action
per step, not one subagent per step. When several small steps form one
tightly-coupled responsibility, batching them into a single coherent *unit* —
still running the full implementer + two-stage review loop — is a valid reading,
and often the right one: a dozen two-line steps don't each need three subagents.
Batch by responsibility, never to skip a review.

## Model selection per role

Mechanical implementation with a complete spec → the cheapest capable model;
multi-file integration → a standard model; design judgment and review → the
most capable available. When a registered model-tier policy is installed
(e.g. pr-pilot's model-tiers), its thresholds win over these heuristics.

## Without subagents

In a context without subagent support, the same plan executes inline:
tracked tasks, steps followed exactly, verification at every checkpoint the
plan specifies, and a stop — not a guess — at the first blocker or unclear
instruction.

## Dispatch prompts

[subagent-prompts.md](subagent-prompts.md) carries condensed templates for
the implementer, spec reviewer, and code-quality reviewer, including the
status protocol.

## Boundaries

- **brainstorming** owns the step before this one — if what to build isn't
  agreed yet, no plan contract can fix that.
- **keel / pr-pilot** own governed work: multi-PR series, dependency DAGs,
  Definition-of-Ready gates, deterministic quality gates. The moment the
  work wants those, hand it off — this skill is deliberately lighter.
- **test-driven-development** alone covers a single-loop change; a plan
  document for a one-test fix is ceremony.
- Harness plan mode complements this skill: its approved plan is a valid
  input; the contract above is what makes the artifact executable cold.
