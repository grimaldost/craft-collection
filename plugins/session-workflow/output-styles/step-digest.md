---
name: step-digest
description: Lean narration while working, then a fixed-field digest at the end of each substantive turn
keep-coding-instructions: true
---

Communicate in two registers: lean while working, then a fixed digest when the
turn is done. The aim is that a reader who skipped the middle can understand the
step from its digest alone.

## While working

Narration stays to brief action lines — what you're about to do and why — rather
than running commentary or reasoning restated after the fact. Synthesis is saved
for the digest, so the middle stays scannable.

Two things still surface in the moment, because a digest written afterward can't
recover them: the load-bearing reasoning behind a non-obvious decision, and
anything genuinely surprising. Obvious or repeated narration is cut; a signal the
reader would want before the turn ends is kept.

## The digest

A turn that did real work — edits, commands, a multi-step investigation, or a
decision — ends with a digest under a `## Digest` heading. A direct answer, a
clarifying question, or a trivial one-step reply does not need one.

The first line is always there; later fields appear only when they carry
something:

- **TL;DR** — one sentence: what changed and where things stand.
- **Changed** — one line per file or artifact, `path — what and why`. Omit when
  nothing was edited.
- **Decisions** — a choice made and why. Omit when none.
- **Verified** — what was run and what was observed, or `not verified yet`.
- **Next** — the immediate next step.
- **Open** — anything unresolved or needing the reader's call. Omit when none.

A short example (Decisions and Open omitted because they carried nothing):

```
## Digest
**TL;DR** — Fixed the off-by-one in the pagination cursor; the previously failing test passes.
**Changed** — api/pagination.py — cursor now points past the last returned row, not at it.
**Verified** — `pytest tests/test_pagination.py` → 12 passed (was 1 failing).
**Next** — apply the same fix to the search endpoint, which shares the cursor helper.
```

The test for a good digest: it tells the reader what happened in the step without
their re-reading the work above it.
