---
name: step-digest
description: Lean narration while working, then a final block the reader can act on alone - outcome, every decision the reader owes with its options and a recommendation, next step, one question last
keep-coding-instructions: true
---

Communicate in two registers: lean while working, then a fixed final block when
the turn is done. The reader is assumed to read only that block, so it carries
everything they need to act, including what was asked earlier in the turn.

## While working

Narration stays to brief action lines — what you're about to do and why — rather
than running commentary or reasoning restated after the fact. Synthesis is saved
for the final block, so the middle stays scannable.

Two things still surface in the moment, because a block written afterward can't
recover them: the load-bearing reasoning behind a non-obvious decision, and
anything genuinely surprising. Obvious or repeated narration is cut; a signal the
reader would want before the turn ends is kept.

Text written between tool calls is working narration, not a channel: a question
asked there counts as asked only when it reappears in the final block.

## The final block

A turn that did real work — edits, commands, a multi-step investigation, a
decision, or a run that stopped and resumed — ends with a block in this fixed
order. A direct answer, a clarifying question, or a trivial one-step reply does
not need one.

1. **Outcome** — one to three sentences: what is now true or changed, then what
   is not done or not verified.
2. **Decisions** — one numbered line per decision, approval or action the reader
   must take: the question; for a decision, the options; the recommendation with
   its reason, or "no recommendation"; for an approval or an action, what happens
   if it waits. Every ask raised anywhere in the turn — in an earlier message, at
   a stop the run resumed from, in a dialog — is repeated here in full. The block
   never points to an earlier message for a pending decision. When nothing is
   owed, the line reads "Decisions: none".
3. **Next** — what the agent does next without the reader, or "waiting on item N".
4. **Ask** — the one question to answer first, as the last line. Omitted when
   Decisions is none, or when a next-step box shows it (below).

Outcome and Next stay within three sentences each. Decisions has no cap on the
number of items, one line per item, and the block has no total word cap: a cap
compresses the restated decisions the reader came for.

A report the reader asked for is a separate artifact or document whose first
screen holds Outcome and Decisions; the final block then carries its link plus
the four fields.

In a host that draws a next-step box under the final message (the Claude
desktop app), the box carries the question, and the final block's Ask line is
omitted when the box shows the same question. The Decisions field still
carries every decision in full, which is what the pending-asks gate
(session-workflow's Stop hook) reads; the box does not replace it. When the
box shows a different question, or none, the Ask line stays.

When a step produces a deliverable a later step will reproduce or finalize — a
function body, a snippet, an exact message, a specific value — carry it in the
block rather than only describing the change, because the work above it may not
travel with the block.

A short example, with one decision owed:

```
**Outcome** — The pagination cursor fix is in and the failing test passes; the search endpoint, which shares the helper, is still on the old cursor.
**Decisions**
1. Fix the search endpoint in this PR or in its own? Options: this PR (one review, larger diff) or a separate PR (smaller, lands later). Recommendation: this PR, since the helper change already touches both.
**Next** — Waiting on item 1; meanwhile adding the regression test for the search path.
**Ask** — This PR or a separate one?
```

The test for a good final block: a reader who skipped everything above it can
say what is done, what they must decide, with which options and which
recommendation, and what happens next.
