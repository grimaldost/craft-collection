# The anchor spec, section by section

The skill body carries the section list, because **the order is the survival
order** and a reader has to see it whole. This file carries what each section
holds and why — the part that is reference rather than decision, and that a
session reads once while authoring rather than on every turn.

The HEAD is bounded and rewritten in place. The TAIL, below the literal
`<!-- anchor:tail -->` marker line, is append-only and stays on disk: the
re-injection hook emits the HEAD only.

## Frontmatter

A short block of `key: value` lines above the HEAD sections. `format: anchor/v1` marks
the file as an anchor, `task:` names the work in one line, and `step:` counts the
snapshots. The block opens on line 1 with a `---` line and closes with a `---` line, as
`/anchor` writes it; `--step`, the `--head-fit` step warning and `parked:` read nothing
from frontmatter that is not fenced this way. `parked: <what it waits on>` is optional and
opt-in: it marks a track that is deliberately waiting, such as on a review or an outside
answer, rather than dormant. A
parked anchor ranks below every live one, is injected as a short block naming the wait
instead of its HEAD, and is listed by `--list-dormant` under a `parked:` heading, so the
arm-time sweep does not offer to close it. Remove the line to resume the track; a value of
`false`, `no`, `none` or `0` also counts as not parked. Only
the frontmatter counts: a `parked:` line in the body or the TAIL is prose.

## HEAD

### Mission

The goal in a sentence or two, the hard constraints, and any user instruction
that constrains *mechanism* rather than outcome — quoted in the user's own words
with a stable id.

Paraphrase is where an order dies: once the wording is gone, a substituted
mechanism reads as a design choice rather than a violation. A reversal of a
standing rule is quoted the same way and names what it supersedes; the old rule
lives in other copies and will not overwrite itself.

### Cursor

Done / in progress / **next action on resume**: one imperative step plus the
precondition to verify before it, rewritten in place as it mutates. An
unanswered question or approval is armed here for verbatim re-ask after the
reset. This is the part that earns the anchor, and the part the injection
reserves.

The cursor is the one block guaranteed to survive a cut, so write it to stand
alone: name the next action, its inputs and where to look, with no dependence on
history the cut drops.

It holds the **newest two steps**. Older ones fold into the TAIL at each phase
boundary — the done-list is what actually accumulates, and a cursor that grows
without bound spends the budget its own survival depends on.

Entries are bullets, newest first, each opening with `Step N`. At a step boundary,
`anchor_inject.py --step <anchor> "<text>"` sets the frontmatter `step:` to N+1 and puts
`- Step N+1: <text>` at the top of this section in one atomic edit (it does not fold the
older entries). `--head-fit` prints a line when `step:` is behind the cursor's newest
`Step N`, so a field that nothing bumps does not stay wrong unnoticed.

### Resume steps

How a cold reader re-orients: read this file, check the real state (version
control log, the artifact on disk), continue from the cursor.

They run somewhere they were not authored, so write them in **absolute paths**:
a relative command does not fail after a restart, it succeeds in the wrong
place. Record the anchor's own absolute path where the environment surfaces it
next turn — an anchor that cannot be found is no anchor.

### Invariants

Decisions and constraints that hold across the whole run, so a post-compaction
turn does not relitigate them.

### Parallel tracks

Only when a peer run shares these trees: the other track's anchor path and this
track's never-touch surface, written before any work. Disclose on every commit
that touches shared surface, and route a cross-track lesson into both anchors.

### In-flight work

Background or async tasks the cursor depends on: their ids, log paths, and a "do
not relaunch over the same output" guard. A run that fans out to background work
records them here as first-class cursor state, so each async boundary resumes
idempotently instead of being re-derived.

### Last-known-good

The concrete recoverable state: commit hashes, branches and PRs opened, tags
pushed, the files written, the checkpoint reached.

### Plan pointer

Where the full plan lives (a separate doc), so the anchor stays a cursor rather
than a second copy of the plan.

## TAIL

- **Decisions log** — why the non-obvious calls were made, what was rejected with
  the measurement that rejected it, and what the run got wrong and how it was
  settled.
- **Folded history** — closed phases' one-line outcomes, resolved incidents.

## What the injection does with all this

Over budget, the hook reserves the cursor section and then spends what is left
top-down on whole sections, naming what it dropped. So a section's position is
its priority for everything except the cursor, and putting one section above
another demotes that other.

Measure a draft before it ships:

```
python <plugin>/skills/compaction-survival/scripts/anchor_inject.py --head-fit <anchor>
```

It prints the head's size in characters (the unit the hook spends) against the
budget, the cursor section it would reserve, and the sections that would drop
at the current size. That number is not
countable by hand reliably — three hand-written byte counters in one session
still let a head go out 118 bytes over.

A file in `anchors/` is treated as an anchor when it carries a
`format: anchor/...` frontmatter line or a cursor section. One with neither is
de-ranked below every real anchor and named as "not an anchor" in the warning
line; it is still injected if nothing else is open, because zero useful bytes on
the recovery path is the protocol's cardinal failure.
