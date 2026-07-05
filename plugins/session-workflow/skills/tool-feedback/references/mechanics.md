# tool-feedback mechanics — folded detail

Edge-case mechanics behind the SKILL.md rules. The body carries the rules; this
file carries the why and the rare-path detail.

## Copy skew — which copy did you actually exercise?

When the tool is a skill in a repo you are also developing, the `Skill` loader
serves the **installed/cached** copy, which can diverge from the working tree in
*either* direction:

- **Cache behind the tree** (a stale install): the session exercised older
  behavior than the repo shows. Common right after landing PRs.
- **Cache ahead of the manifest** (a newer install over an older checked-out
  manifest): the executed version can be *newer* than the working tree claims.

So the manifest version and the executed version can disagree both ways. Read
the working-tree `SKILL.md` before reporting on, or reconciling against, the
skill's current behavior — and record in the report which copy you ran, flagging
any skew. (`toolkit-awareness`'s scan flags installed-vs-source version skew
mechanically.)

## Destination precedence — the fine print

Each report's destination, in precedence:

1. a dir the user named *this session* ("save them in `<dir>`"); a consolidated
   sink with per-tool subdirs maps to `<sink>/<tool>/`;
2. the registered feedback dir from the bindings table;
3. the tool's own repo.

Resolve only a **named or registered** dir, never an inferred one. A redirected
destination moves the *write* only: when a registered binding exists, the
recurrence check still reads **the registered dir's** `INDEX.md`, so a one-off
sink can't sever the recurrence baseline. State in the report which baseline you
used.

## Why the INDEX, not greps

The recurrence check reads one current `INDEX.md` (one entry per prior report
with its numbered proposals and §-stubs) instead of N speculative greps, because
grep-by-phrasing is fragile: a finding restated in different words is invisible
to it, and a missed recurrence breaks the `extends` chain triage depends on for
reinforcement counts.
