---
description: Snapshot the run's control anchor to disk now — a one-off backstop before a manual /compact, with or without the compaction-survival protocol armed
argument-hint: "[close | close --stale]"
disable-model-invocation: true
---

# /anchor — one-off control-anchor snapshot

Write the current run's control state to disk, right now, in one pass. This is
the manual backstop: it works whether or not the `compaction-survival` protocol
is armed, and it is safe to run repeatedly — each run overwrites the anchor
with a fresher snapshot.

## If the argument is `close`

1. Find the current anchor: the newest `*.md` under `.claude/anchors/` whose
   name does not end in `.closed.md`. If none exists, say so in one line; done.
   **If more than one is open** (concurrent tracks), close the one whose
   `task:` line matches this session's work — never stub-close another track's
   anchor; if none matches, ask which one in one line.
2. Rewrite it as a minimal landed stub — status, a one-line outcome pointing
   at the commits/PRs that carry the detail, `resume: none`. A full-ledger
   close overflows the injection budget if the file is ever injected again.
3. Rename it to `<name>.closed.md` — the rename is what stops re-injection; a
   prose "status: CLOSED" line alone does not.
4. Append to `.claude/anchors/log.ndjson`:
   `{"event":"anchor-close","source":"command","date":"<YYYY-MM-DD HH:MM>","file":"<basename>"}`
5. Report the archived path in one line. Do **not** also snapshot.

## If the argument is `close --stale`

A cycle-end sweep for the accumulation failure mode: rename every anchor that
already reads as done in-content but was never renamed, so terminal anchors do
not pile up and shadow the live one (seven stranded across ~8 tracks is what
motivated this).

1. List the strays mechanically — run the same helper the re-injection hook uses:
   `python <this-plugin>/skills/compaction-survival/scripts/anchor_inject.py --list-stale .claude/anchors`.
   It emits one `mv <name>.md <name>.closed.md` per anchor whose content marks it
   closed/landed but whose filename is still open. If the helper is not locatable,
   scan `.claude/anchors/*.md` for a top-level `Status:` line reading closed or
   landed and emit the same renames. An empty list means the dir is clean — say
   so and stop.
2. Show the commands and rename only on a go-ahead — never force, and skip any
   anchor still marked active or belonging to another live track. The rename
   mutates no content, so it is safe and reversible.
3. Append one `{"event":"anchor-close","source":"command --stale","date":"<YYYY-MM-DD HH:MM>","file":"<basename>"}`
   line per renamed file to `.claude/anchors/log.ndjson`, and report the count in
   one line. Do not also snapshot.

## Otherwise: snapshot

1. **Nothing to anchor?** If the session holds no meaningful run state — fresh
   session, purely conversational so far — say so in one line and write
   nothing. An empty anchor is noise, not insurance.
2. **Make the directory self-ignoring.** Ensure `.claude/anchors/` exists and
   contains a `.gitignore` whose content is exactly `*`. The anchor is local
   working state, never commit material.
3. **Locate or create the anchor file.** Reuse the newest non-closed `*.md` in
   `.claude/anchors/` when its task line matches the current work; otherwise
   create `<YYYY-MM-DD>-<short-run-slug>.md`.
4. **Write the snapshot** — one full-file Write: every HEAD section in survival
   order, then the tail, each at task-appropriate depth. The order matters: the
   re-injection hook spends its budget top-down, so a section's position is its
   priority.
   - Frontmatter: `format: anchor/v1`, `date`, `task:` (one line), `step:`
     (prior step + 1, or 1), `source: /anchor`. The block opens and closes with
     a `---` line (line 1 and after the last field); `--step` and `parked:` read
     only a block fenced this way.
   - **Mission** — the goal, plus the owner's authorizations and instructions
     about mechanism (not outcome) as dated, literal quotes with a stable id: a
     record of what the owner said and when, never a grant the anchor makes
     itself. The anchor has authority over task position only, the cursor. A
     rule that must never be broken belongs in a hook that enforces it, not in
     the anchor.
   - **Cursor** — done / in progress / the single next action. This is the
     load-bearing section; make it current, not aspirational. Number the
     entries `- Step N: ...`, newest first: the fold-candidate warning offers
     only numbered entries.
   - **Resume steps** — how a cold reader re-orients: read this file, verify
     the real state, continue from the cursor. Keep them idempotent, in
     absolute paths.
   - **Invariants** — decisions about the task that a post-reset turn must not
     relitigate; not inviolable rules, which belong in a hook.
   - **Parallel tracks** — only when a peer run shares these trees: the other
     track's anchor path and this track's never-touch surface.
   - **In-flight work** — background or async tasks the cursor depends on: ids,
     log paths, and a do-not-relaunch guard.
   - **Last-known-good** — branch and commit SHA, artifacts written,
     checkpoints reached. Check the real state (`git log --oneline -1`,
     the files on disk) rather than recalling it.
   - **Plan pointer** — where the full plan lives. Point, don't copy.
   - `<!-- anchor:tail -->` on its own line — the re-injection hook emits only
     what is above this marker; everything below stays on disk.
   - **Decisions log** — append-only; why the non-obvious calls were made.
   Keep the HEAD bounded: cursor plus pointers, not a transcript. Fold closed
   phases into one-line outcomes below the marker, pointing at the commit or
   artifact that carries the detail. Then measure it rather than eyeballing it —
   `python <this-plugin>/skills/compaction-survival/scripts/anchor_inject.py --head-fit <the anchor>`
   prints the head's size in characters against the injection budget, the
   cursor it would reserve, and the sections a cut would take. A hand-counted head went out 118 bytes
   over.
5. **Append telemetry** to `.claude/anchors/log.ndjson`:
   `{"event":"anchor-write","source":"command","date":"<YYYY-MM-DD HH:MM>","step":<N>,"file":"<basename>"}`
6. **Confirm in one line:** path, step number, and — when the user is about to
   compact — that `/compact` is now safe to run.

## Boundary

This command is the backstop, not the discipline. A one-off snapshot ages the
moment work continues; for a long or autonomous run, arm `compaction-survival`
— create the anchor at the start, update it whenever durable state moves, re-read it each
turn. Use `/anchor` for the deliberate checkpoint: before a manual `/compact`,
before stepping away, before an irreversible move.

Between snapshots, when only a step boundary moved, one edit does both halves of it:
`python <this-plugin>/skills/compaction-survival/scripts/anchor_inject.py --step <the anchor> "<what moved>"`
sets the frontmatter `step:` to the next number and puts `- Step N: <what moved>` first in the
Cursor section, atomically, then prints the head's size. It does not fold older entries; do that
at the phase boundary. `--head-fit` also says when `step:` is behind the newest cursor entry.
