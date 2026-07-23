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
  in one context window. The /anchor command is the one-off snapshot entry
  point; when the running session lacks the plugin surface entirely (stale
  snapshot, harness without the skill menu), references/cold-start.md has the
  by-hand recipe.
---

# Compaction Survival

A long autonomous run loses most often to this — the context that
held the plan gets compacted or reset, and the next turn resumes from a summary
that dropped the load-bearing detail. The defense is an anchor on disk that the
run re-reads and rewrites as it goes, so the plan lives in a file, not only in
the context window.

This is a **flexible** skill: the anchor's schema and update cadence adapt to
the task. What stays firm is small — the anchor is the single source of truth
for run state, re-read at the start of each turn and updated before the state
it describes can be lost.

## The anchor

One file, at a stable path the run can find again after a reset. It has two
tiers, split by a literal `<!-- anchor:tail -->` marker line: above it the live
**HEAD** — the only part the re-injection hook emits — and below it the
**TAIL**, which stays on disk. A marker-less anchor still injects whole, but
then a long run's live state is whatever the 8K bound keeps.

HEAD — bounded, rewritten in place:

- **Mission** — the goal in a sentence or two, and the hard constraints.
- **Plan pointer** — where the full plan lives (a separate doc), so the anchor
  stays a cursor, not a second copy of the plan.
- **Cursor** — done / in progress / **next action on resume**: one imperative
  step plus the precondition to verify before it, rewritten in place as it
  mutates. An unanswered question or approval is armed here for verbatim
  re-ask after the reset. This is the part that earns the anchor.
- **In-flight work** — background or async tasks the cursor depends on: their
  ids, log paths, and a "do not relaunch over the same output" guard. A run that
  fans out to background work records them here as first-class cursor state, so
  each async boundary resumes idempotently instead of being re-derived.
- **Invariants** — decisions and constraints that hold across the whole run, so
  a post-compaction turn does not relitigate them.
- **Last-known-good** — the concrete recoverable state: commit hashes, the
  branch, the files written, the checkpoint reached.
- **Resume steps** — how a cold reader re-orients: read this file, check the
  real state (version control log, the artifact on disk), continue from the
  cursor.

TAIL — append-only, read on demand:

- **Decisions log** — why the non-obvious calls were made.
- **Folded history** — closed phases' one-line outcomes, resolved incidents.

## The protocol

1. **Create the anchor at the start of the run**, before the first irreversible
   step, so there is something to resume from immediately.
2. **Update the cursor after each step or phase**, before moving on. State that
   lives only in the context window is one compaction away from gone; write it
   down while it is still true.
3. **Re-read the anchor at the start of each turn** — especially when a summary
   has appeared or the context feels thinner than the work already done — the
   signs of a compaction. Re-read before acting, not after. A
   cursor is an Edit, so during tool outages it can lag reality by a phase; when
   it disagrees with durable state (the version-control log, run ledgers), trust
   the durable state.
4. **Write atomically and keep one anchor.** Overwrite the single file rather
   than scattering state across several; a half-written or duplicated anchor is
   worse than a terse one.
5. **Keep the HEAD bounded.** The anchor is a cursor plus pointers, not a
   transcript. As a phase closes, fold its detail into a one-line outcome in
   the TAIL, below the marker — growth goes below the fold, never into the
   injected HEAD.
6. **Make resume idempotent.** The resume steps let a fresh context recover the
   run from the anchor and the real on-disk state alone; re-entering a
   half-finished step checks the artifact before redoing it, so re-reading is
   always safe. A stored recovery command (a ledger-count grep, a resume key)
   is validated against the live artifact before the run goes unattended —
   unchecked, it is a fabricated inference waiting to misfire.
7. **Close by stubbing, then renaming.** When the run ends, rewrite the anchor
   to a minimal landed stub — status, a one-line outcome, resume: none — and
   rename it `<name>.closed.md`. The rename is the only close signal the hook
   honors: a prose "status: CLOSED" line does not stop re-injection, and a
   full-ledger close overflows the injection budget on the next session. Close
   at the moment the cycle ends; a track closed only in prose accumulates. At
   wind-down, `/anchor close --stale` sweeps the dir for anchors marked done
   in-content but never renamed and offers the exact rename for each.

## Finding the anchor again

A reset can also lose the *path* to the anchor. Record that path where the
environment surfaces it on the next turn — a session handoff file, a pinned
note, the run's opening instruction — so the re-read step has somewhere to look.
An anchor that cannot be found is no anchor.

## Explicit surfaces

- Invoked directly (`/compaction-survival`), arm the protocol now: create or
  refresh the anchor immediately from the current conversation state, then
  follow the update-and-re-read cadence for the rest of the run.
- **`/anchor`** (session-workflow command) is the one-off backstop: a single
  snapshot on demand, with or without this protocol armed — the deliberate
  checkpoint before a manual `/compact`. It replaces asking in prose for the
  state to be persisted; it does not replace the cadence, which is what
  protects against *automatic* compactions that arrive unannounced.
- **Automatic re-injection** (env-gated, off by default): with
  `SESSION_WORKFLOW_ANCHOR_HOOKS=1`, a SessionStart hook on `compact`,
  `resume`, `clear`, and `startup` re-injects the newest **active** anchor's
  HEAD (to the tail marker) into fresh context mechanically — the re-read step
  stops depending on the model remembering the protocol. Without session-start
  hooks, the cadence's manual re-read at each turn start is the whole
  mechanism. An anchor marked done in-content is de-ranked below live
  tracks, so a stray closed-but-unrenamed track no longer shadows the live one;
  the rename to `*.closed.md` remains the only signal that stops injection
  entirely. An anchor untouched for 24h injects as a short pointer (path,
  title, age, close command), not its body; `startup` (crash restart) injects
  only an anchor updated within 6h. When several anchors are open
  in one directory (concurrent tracks), the injection names the others and
  emits the exact `mv` rename for any that read as closed in-content.
  Anchor-less sessions pay nothing.
- **Cold start without the plugin surface** — a session whose plugin snapshot
  predates the skill, or a harness whose menu omits it, arms everything by hand:
  `references/cold-start.md` has the full recipe (the anchor file by hand, manual
  hook registration, a verify-by-piping step). Because that recipe is unreachable
  exactly when the skill is absent, keep the compact minimal contract — anchor
  path, the `<!-- anchor:tail -->` split, a cursor with a next action, the
  `.closed.md` rename — in the CLAUDE.md protocol snippet, where a menu-less
  session still has it.

## Common failure modes

| Pattern | What it costs |
|---------|---------------|
| Anchor created, then never updated | Resume reads a stale cursor; work is redone or skipped. |
| State kept only in context | The compaction the anchor exists to survive erases it. |
| Re-read skipped on resume | Acts on the summary's gaps; relitigates settled decisions. |
| Anchor grown into a transcript | Becomes the token hog it was meant to prevent. |
| Non-idempotent resume | Re-runs a finished irreversible step, or stacks a second attempt on a half-done one. |
| Closed in prose, never renamed | Injection de-ranks it and offers the rename, but strays accumulate until renamed — sweep at wind-down. |

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
