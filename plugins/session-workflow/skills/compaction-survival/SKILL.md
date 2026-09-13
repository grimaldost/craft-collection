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

HEAD — bounded, rewritten in place. **The order below is the survival order.**
The injection reserves the cursor, then spends what is left top-down and drops
whole trailing sections, naming them: a section's position is its priority for
everything except the cursor, and putting one above another demotes that other.

1. **Mission** — the goal, the hard constraints, and any user instruction about
   *mechanism*, quoted verbatim with a stable id.
2. **Cursor** — done / in progress / **next action on resume**, rewritten in
   place. The newest two steps; older ones fold into the TAIL at each boundary.
   This is the part that earns the anchor.
3. **Resume steps** — how a cold reader re-orients, in absolute paths.
4. **Invariants** — what a post-compaction turn must not relitigate.
5. **Parallel tracks** — a peer run's anchor path and this track's never-touch
   surface, when the trees are shared.
6. **In-flight work** — background tasks the cursor depends on, with a
   do-not-relaunch guard.
7. **Last-known-good** — commits, branches, PRs, tags, files, checkpoints.
8. **Plan pointer** — where the full plan lives, so the anchor stays a cursor.

TAIL — append-only, read on demand: the decisions log, and closed phases' folded
one-line outcomes.

What each section holds and why, and how to measure a draft against the
injection budget: [`references/anchor-spec.md`](references/anchor-spec.md).

## The protocol

1. **Create the anchor at the start of the run**, before the first irreversible
   step, so there is something to resume from immediately. Arming is also the
   sweep moment — read `anchor_inject.py --list-dormant <anchors dir>` and close
   or adopt any track it names. It reaches what `close --stale` cannot: a track
   abandoned mid-cursor never marks itself done.
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
5. **Keep the HEAD bounded.** As a phase closes, fold its detail into a
   one-line outcome in the TAIL, below the marker. Measure rather than estimate:
   `anchor_inject.py --head-fit <anchor>` prints the head's bytes against the
   budget and the sections a cut would take.
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
   at the moment the cycle ends; a track closed only in prose accumulates. And
   close on the *deliverable*, not the session: if the session carries on into
   new substantive work, arm the next anchor in the same breath — a closed
   anchor beside a live session is an uncovered window. At
   wind-down, `/anchor close --stale` sweeps the dir for anchors marked done
   in-content but never renamed and offers the exact rename for each.

## Explicit surfaces

- Invoked directly (`/compaction-survival`), arm the protocol now: create or
  refresh the anchor immediately from the current conversation state, then
  follow the update-and-re-read cadence for the rest of the run.
- **`/anchor`** (session-workflow command) is the one-off backstop: a single
  snapshot on demand, with or without this protocol armed — the deliberate
  checkpoint before a manual `/compact`. It replaces asking in prose for the
  state to be persisted; it does not replace the cadence, which is what
  protects against *automatic* compactions that arrive unannounced.
- **Automatic re-injection** ships on; `SESSION_WORKFLOW_ANCHOR_HOOKS=0` opts
  out. A SessionStart hook on `compact`, `resume`, `clear`, and `startup`
  re-injects the newest **active** anchor's HEAD (to the tail marker) into fresh
  context mechanically — the re-read step stops depending on the model
  remembering the protocol. Without session-start hooks, the manual re-read at
  each turn start is the whole mechanism. Over budget, the cursor is reserved
  first and the rest is spent top-down on whole sections whose names the drop
  line carries, so the survival order above is a policy the author sets rather
  than wherever the bytes ran out — and the one section a cut cannot take is the
  live cursor. An anchor marked done in-content, or one that does not read as an
  anchor at all, is de-ranked below live tracks, and the injection names any
  other open anchors; the rename to `*.closed.md` remains
  the only signal that stops injection entirely. An anchor untouched for 24h
  injects as a short pointer — path, title, age, close command, and the cursor
  it still asserts, which is the part a reader can check against reality.
  `startup` (crash restart) injects only an anchor updated within 6h.
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

The seven recurring ones and what each costs: [`references/failure-modes.md`](references/failure-modes.md).

## Boundaries

The description names the three neighbours this is not. The discriminator worth
having in hand: a handoff is written once and read by someone else; an anchor is
rewritten continuously and read by the same run.
