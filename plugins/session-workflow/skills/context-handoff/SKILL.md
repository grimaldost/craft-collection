---
name: context-handoff
description: Author a paste-ready, self-contained brief that hands work to a fresh context — a new Claude Code session, a spawned task, a teammate, or an issue ticket. Use on "/subtask", "/fork", "/spinoff", "spin this off", "hand this off", "branch off", "offload this", "new session for this", or when curating a context slice to continue or delegate work elsewhere. Two modes — SUBTASK (bounded brief, an artifact comes back) and FORK (continues independently). For in-session parallel work, prefer the Task tool / subagents instead.
---

# Context Handoff

## Why this exists

Long sessions accumulate context that isn't relevant to every sub-goal that
arises. Two failure modes follow: model attention degrades as the session grows,
and doing a subtask inline leaves residue that distracts from the main thread. A
fresh context fixes both — but rebuilding that context by hand is slow and
error-prone. This skill has the current session (which already understands what
matters right now) author a self-contained, paste-ready brief for the new
context. The skill supplies the technique and output shape; the session supplies
the judgment about what to include.

## When to use this vs. the Task tool

For in-session parallel work where results flow back automatically, use the Task
tool / subagents — they solve that problem more completely. Reach for this skill
when the handoff crosses a boundary the harness won't bridge: a brand-new
session, a spawned background task you'll paste a result back from, a human
teammate, or an issue/ticket. The deliverable is portable text someone (or some
fresh instance) can act on with zero prior context.

## Two modes

**Subtask** — a bounded piece of work is spun off and returns an artifact (a
script, a draft, a piece of analysis, a list) that gets pasted back to inform
ongoing work. Narrow context slice. The executor is a helper producing a
deliverable, not a peer you'll keep working with.

**Fork** — the current state is exported into a new context that continues the
work independently. Nothing is expected back. Wider slice (enough to keep going,
not just enough for one task). Use when the current session is getting unwieldy,
or a sub-thread deserves its own dedicated session.

Subtask prompts are scoped narrowly and framed as a request; fork prompts are
scoped more generously and framed as a hand-off.

## Invocation

| Trigger | Mode |
|---------|------|
| `/subtask <description>` | Subtask |
| `/fork <description>` or `/fork` alone | Fork |
| `/spinoff <description>` | Ask which mode |
| "spin off a subtask for…", "I need a subtask that…" | Subtask |
| "fork this", "branch this off", "continue this in a new session" | Fork |

If invoked without a description, ask one clarifying question: "What should the
[subtask / forked session] do?" Don't proceed without a clear task statement.

## Workflow

1. **Confirm mode and task.** If ambiguous, ask. Otherwise proceed silently.
2. **Curate the context slice.** Identify the minimum set of facts, decisions,
   code, numbers, and named entities the executor needs. Err toward *including*
   when a piece is load-bearing and *excluding* when it's session flavor.
3. **Draft the prompt** using the template for the chosen mode.
4. **Emit it as a fenced code block** so the user can copy it in one action.
5. **Subtask mode only:** after the block, emit a short `REINTEGRATION_NOTE` to
   the user (not the executor) flagging where the returned artifact slots back in.
6. **Do not offer to run the prompt.** The skill's job ends at emitting it.

## Context extraction guidance

The session owns this judgment — only it knows what matters right now. Apply:

- **State facts, not references.** Replace every "as we discussed", "the thing
  from earlier", "like before" with the actual content. The executor has zero
  prior context — session-internal shorthand is noise to them.
- **Include concrete specifics.** Names, numbers, table names, function names,
  version strings, file paths, error messages verbatim. Abstractions ("we made
  some schema decisions") are useless; specifics are load-bearing.
- **Preserve constraints the executor would otherwise violate.** Coding
  conventions, naming patterns, forbidden libraries, style preferences.
- **Omit narrative.** The executor doesn't need to know how the conversation
  arrived here, only what the current state is.
- **When unsure, include.** A slightly over-scoped prompt is fine; an
  under-scoped one produces the wrong artifact.

Length target: as long as needed, as short as possible.

## Output format

### Subtask mode

Emit exactly this structure inside a fenced code block:

```
You are a fresh Claude instance. You have no prior context beyond what's in this message.

## Context
<curated slice of facts the executor needs>

## Task
<clear, bounded request — one deliverable>

## Constraints
<conventions, style, libraries required or forbidden, output format — only if relevant>
```

The `## Constraints` section is optional. After the code block, outside it, emit:

```
REINTEGRATION_NOTE: <one or two sentences on how the returned artifact will be used back in this session>
```

This note is for the user, not the executor — by the time the artifact comes
back the user may have context-switched and will want a reminder of where it fits.

### Fork mode

Emit exactly this structure inside a fenced code block:

```
You are continuing a prior Claude session. The previous session's relevant state is below. Pick up from here — the user will direct next steps after you acknowledge the hand-off.

## Where things stood
<what was being worked on, what's decided, what's pending, the immediate next step>

## Working context
<facts, constraints, conventions, named entities the new session needs to continue>

## Suggested opening
<optional: one-line suggestion of what to address first, if the user gave direction>
```

No `REINTEGRATION_NOTE` for fork mode — nothing is coming back.

## Self-check before emitting

Re-read the drafted prompt from the position of someone with zero prior context.
If any sentence would prompt "wait, what's that?", the context is
under-specified. Fix and re-read.

## Examples

### Subtask

**Invocation:** `/subtask write a helper that validates scheduled payment dates against a business-day calendar, returning any that fall on a non-business day`

```
You are a fresh Claude instance. You have no prior context beyond what's in this message.

## Context
The project is a payments service in Python 3.12. It already has a calendar
utility at `app.calendars.business` exposing `is_business_day(d: date) -> bool`
and `next_business_day(d: date) -> date`. Inputs to the helper will be a list of
`datetime.date` objects (scheduled payment dates).

## Task
Write `validate_payment_dates(dates: list[date]) -> list[date]` that returns the
subset of input dates falling on non-business days. Include a docstring and type
hints. Do not adjust the dates — only report them.

## Constraints
- Python 3.12; `from datetime import date`
- Import from `app.calendars.business`; no new dependencies
- PEP 8, line length 100
```

REINTEGRATION_NOTE: The validator plugs into the schedule-generation path we were sketching, just before rows are inserted.

### Fork

**Invocation:** `/fork continue the architecture discussion, now focused only on the Python↔native-extension boundary`

```
You are continuing a prior Claude session. The previous session's relevant state is below. Pick up from here — the user will direct next steps after you acknowledge the hand-off.

## Where things stood
We were designing a compute library: a Python frontend over a native (Rust)
compute engine. We'd just narrowed to the Python↔Rust boundary — which operations
live on which side and how data crosses. Decided so far: Rust handles the hot
numeric loops; Python handles I/O, orchestration, and dataframe prep. Data
interchange is via Arrow record batches.

## Working context
- Build: a native-extension toolchain for the Rust side; standard Python packaging
- Open questions: (1) expose Rust types as classes, or keep everything as
  function calls over Arrow data? (2) convert Rust errors to Python exceptions at
  the boundary, or pass error columns back in the batch?

## Suggested opening
Start with question (1) — the function-vs-class boundary. Frame the tradeoffs, then we'll pick.
```

## What this skill does NOT do

- Score task complexity or recommend a model.
- Structure the return format — the executor is an LLM; natural language is fine.
- Run the prompt, schedule anything, or talk to any runner. The skill ends at
  emitting the brief.
