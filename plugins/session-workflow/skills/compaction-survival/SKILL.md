---
name: compaction-survival
description: >
  Maintain a persisted, re-readable control anchor so a long autonomous run
  survives context compaction without losing the plot — one file holding the
  mission, a plan pointer, a live cursor (done / in progress / next action),
  invariants, last-known-good state, and exact resume steps, updated after each
  step and re-read at the start of each turn. Use when starting or driving a
  multi-hour or multi-phase autonomous task, a self-driving loop, or any
  unattended run that will cross one or more automatic compactions or
  context-window resets; on asks like "make sure compaction doesn't lose the
  work", "keep state across auto-compact", "persist the current state so a reset
  doesn't disrupt this", "this is a long autonomous run", or "resume cleanly
  after a reset". The anchor is intra-actor state recovery — the same actor
  re-reading its own working state across a discontinuity. Not for handing work
  to a fresh context or a teammate (that is context-handoff's inter-actor
  brief), not for post-hoc capture of what a finished session learned (that is
  journaling-sessions), and not for tracking a short task that fits comfortably
  in one context window.
---

# Compaction Survival

A long autonomous run loses to one thing more than any other — the context that
held the plan gets compacted or reset, and the next turn resumes from a summary
that dropped the load-bearing detail. The defense is an anchor on disk that the
run re-reads and rewrites as it goes, so the plan lives in a file, not only in
the context window.

This is a **flexible** skill: the anchor's schema and update cadence adapt to
the task. What stays firm is small — the anchor is the single source of truth
for run state, it is re-read at the start of each turn, and it is updated before
the state it describes can be lost.

## The anchor

One file, at a stable path the run can find again after a reset. It holds, in
whatever shape fits the work:

- **Mission** — the goal in a sentence or two, and the hard constraints.
- **Plan pointer** — where the full plan lives (a separate doc), so the anchor
  stays a cursor, not a second copy of the plan.
- **Cursor** — what is done, what is in progress, and the single next action.
  This is the part that earns the anchor; keep it current.
- **Invariants** — decisions and constraints that hold across the whole run, so
  a post-compaction turn does not relitigate them.
- **Last-known-good** — the concrete recoverable state: commit hashes, the
  branch, the files written, the checkpoint reached.
- **Resume steps** — how a cold reader re-orients: read this file, check the
  real state (version control log, the artifact on disk), continue from the
  cursor.
- **Decisions log** — append-only; why the non-obvious calls were made.

## The protocol

1. **Create the anchor at the start of the run**, before the first irreversible
   step, so there is something to resume from immediately.
2. **Update the cursor after each step or phase**, before moving on. State that
   lives only in the context window is one compaction away from gone; write it
   down while it is still true.
3. **Re-read the anchor at the start of each turn** — especially when a summary
   has appeared or the context feels thinner than the work already done, the
   visible signs that a compaction happened. Re-read before acting, not after.
4. **Write atomically and keep one anchor.** Overwrite the single file rather
   than scattering state across several; a half-written or duplicated anchor is
   worse than a terse one.
5. **Keep it bounded.** The anchor is a cursor plus pointers, not a transcript.
   As a phase closes, fold its detail into a one-line outcome and point to the
   commit or artifact that carries the rest — an anchor that grows without bound
   becomes the token cost it was meant to avoid.
6. **Make resume idempotent.** The resume steps let a fresh context recover the
   run from the anchor and the real on-disk state alone; re-entering a
   half-finished step checks the artifact before redoing it, so re-reading is
   always safe.

## Finding the anchor again

A reset can also lose the *path* to the anchor. Record that path where the
environment surfaces it on the next turn — a session handoff file, a pinned
note, the run's opening instruction — so the re-read step has somewhere to look.
An anchor that cannot be found is no anchor.

## Common failure modes

| Pattern | What it costs |
|---------|---------------|
| Anchor created, then never updated | Resume reads a stale cursor; work is redone or skipped. |
| State kept only in context | The compaction the anchor exists to survive erases it. |
| Re-read skipped on resume | Acts on the summary's gaps; relitigates settled decisions. |
| Anchor grown into a transcript | Becomes the token hog it was meant to prevent. |
| Non-idempotent resume | Re-runs a finished irreversible step, or stacks a second attempt on a half-done one. |

## Boundaries

- **context-handoff** hands work *across* actors — a brief for a fresh session
  or a teammate who lacks this run's context. This skill is *intra*-actor: the
  same run re-reading its own state across a discontinuity. A handoff is written
  once and read by someone else; an anchor is rewritten continuously and read by
  the same run.
- **journaling-sessions** captures what a finished session learned, for future
  retrieval. The anchor is live working state, discarded once the run completes.
- A short task that fits in one context window needs no anchor — the overhead is
  only worth it once a run will cross a compaction or span several phases.
