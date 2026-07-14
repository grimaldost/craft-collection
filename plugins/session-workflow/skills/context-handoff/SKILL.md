---
name: context-handoff
description: Author a paste-ready, self-contained brief that hands work to a fresh context — a new Claude Code session, a spawned task, a teammate, or an issue ticket. Use whenever current work must be packaged so a receiver with zero shared context can take it cold — "package this up for a fresh session", "bundle this for another agent", "write a standalone brief / a self-contained handoff", "spin this off", "hand this off", "offload this", "branch off", "new session for this", "author a persisted backlog / worklist doc for a future session", "subtask", "fork", "spinoff" — when curating a context slice to continue or delegate work elsewhere, or running "/context-handoff". Three modes — SUBTASK (bounded brief, an artifact comes back), FORK (continues independently, nothing returns), and BACKLOG (a persisted repo doc a future session opens to pick up any item). For in-session parallel work where results flow back automatically, prefer the Task tool / subagents — this skill is for handoffs that cross a boundary the harness won't bridge (a fresh session, a human, a ticket).
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

## Three modes

**Subtask** — a bounded piece of work is spun off and returns an artifact (a
script, a draft, a piece of analysis, a list) that gets pasted back to inform
ongoing work. Narrow context slice. The executor is a helper producing a
deliverable, not a peer you'll keep working with.

**Fork** — the current state is exported into a new context that continues the
work independently. Nothing is expected back. Wider slice (enough to keep going,
not just enough for one task). Use when the current session is getting unwieldy,
or a sub-thread deserves its own dedicated session.

**Backlog** — the curated slice becomes a persisted repo document (a
findings/worklist file at a named path), not a paste-prompt: it neither returns
nor continues a single thread, it sits in the tree for a future session to open
and pick up *any* item. Structure is findings-with-stable-IDs plus a "how to use"
line and the constraints an executor would otherwise violate; framing is "a
future session opens this file." Subtask and Fork model *who continues*; Backlog
models a deliverable that waits.

Subtask prompts are scoped narrowly and framed as a request; fork prompts are
scoped more generously and framed as a hand-off; a backlog doc is scoped to be
independently actionable item-by-item.

## Invocation

The skill itself is invocable as `/context-handoff`; the words below are trigger
phrases in ordinary requests, not slash commands (none of them ship as one).

| Trigger | Mode |
|---------|------|
| "spin off a subtask for…", "package this up for a fresh session and get the result back", "bundle this for another agent" | Subtask |
| "fork this", "branch this off", "continue this in a new session" | Fork |
| "author a backlog / worklist / findings doc for a future session to pick up", "write these up as a persisted doc for later" | Backlog |
| "write a self-contained handoff someone can take cold" | Subtask or Fork by destination — ask if unclear |
| "spin this off" (destination unclear) | Ask which mode |

If invoked without a description, ask one clarifying question: "What should the
[subtask / forked session] do, or what area should the backlog cover?" Don't
proceed without a clear task statement.

## Workflow

1. **Confirm mode and task.** If ambiguous, ask. Otherwise proceed silently.
2. **Curate the context slice.** Identify the minimum set of facts, decisions,
   code, numbers, and named entities the executor needs. Err toward *including*
   when a piece is load-bearing and *excluding* when it's session flavor.
3. **Draft the brief** using the template for the chosen mode.
4. **Emit it.** Subtask / Fork: a fenced code block the user copies in one
   action. Backlog: write the document to the named repo path (a real file) and
   report the path.
5. **Subtask mode only:** after the block, emit a short `REINTEGRATION_NOTE` to
   the user (not the executor) flagging where the returned artifact slots back in.
6. **Do not offer to run the prompt** (Subtask / Fork). Backlog ends at the
   written file — no paste-prompt and no offer to run.

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
- **State the INTENT behind a step the executor might adapt, not just the
  procedure.** An executor meets situations you didn't enumerate and can resolve
  them in the spirit of a step only if the spirit is on the page. For any
  instruction it might need to deviate from, give the *why* — the gate it protects,
  the invariant it preserves — so a step followed literally into a situation it
  doesn't fit is caught, not silently obeyed. Strongest in FORK mode, where the
  executor continues independently with no one to ask.
- **Omit narrative.** The executor doesn't need to know how the conversation
  arrived here, only what the current state is.
- **Include a fact only if its absence would change the artifact.** This is the
  test for the hard call — what to include. Err toward load-bearing, not toward
  volume: over-scoping dilutes the executor's attention as surely as under-scoping
  derails it (that attention drift is the failure this skill exists to prevent).
  When a fact lives in a file the executor can open, point to it by path rather
  than transcribing it.
- **Strip secrets before emitting.** Remove credentials, tokens, API keys, PII,
  and internal-only names — especially when the destination is a teammate, an
  issue/ticket, or any other external surface.

Length target: as long as needed, as short as possible.

## Output format

Both templates below address a fresh or continuing Claude. **If the recipient is
a human teammate or an issue ticket, drop the "You are a … Claude" opening line
and lead with a one-sentence title** — the rest of the structure still applies.

### Subtask mode

Emit exactly this structure inside a fenced code block:

```
You are a fresh Claude instance. You have no prior context from the originating session beyond what's in this message.

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

### Backlog mode

Write a document (not a paste-block) to a named repo path — e.g.
`docs/design/<area>/<date>-findings-backlog.md`. Emit the file with this shape:

```
# <Area> — findings backlog (<date>)

## How to use
A future session opens this file and picks up any item below. Each finding is
self-contained; take the highest-leverage one first. <constraints an executor
must respect — conventions, forbidden libraries, the invariant each protects>.

## Findings

### F1 — <short title>
<the finding as fact: file:line, versions, the concrete change or open question,
and why it matters — enough that a cold reader acts without this session>.

### F2 — <short title>
…
```

No "You are a … Claude" opening line and no `REINTEGRATION_NOTE` — the reader
finds this file on their own initiative. The extraction guidance above applies
unchanged: state facts not references, concrete specifics, strip secrets.

## Self-check before emitting

Re-read the drafted prompt from the position of someone with zero prior context.
If any sentence would prompt "wait, what's that?", the context is
under-specified. Fix and re-read.

## Examples

### Subtask

**Invocation:** "spin off a subtask: write a helper that validates scheduled payment dates against a business-day calendar, returning any that fall on a non-business day"

```
You are a fresh Claude instance. You have no prior context from the originating session beyond what's in this message.

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

**Invocation:** "fork this — continue the architecture discussion, now focused only on the Python↔native-extension boundary"

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
