---
description: Snapshot the run's control anchor to disk now — a one-off backstop before a manual /compact, with or without the compaction-survival protocol armed
argument-hint: "[close]"
---

# /anchor — one-off control-anchor snapshot

Write the current run's control state to disk, right now, in one pass. This is
the manual backstop: it works whether or not the `compaction-survival` protocol
is armed, and it is safe to run repeatedly — each run overwrites the anchor
with a fresher snapshot.

## If the argument is `close`

1. Find the current anchor: the newest `*.md` under `.claude/anchors/` whose
   name does not end in `.closed.md`. If none exists, say so in one line; done.
2. Rename it to `<name>.closed.md`.
3. Append to `.claude/anchors/log.ndjson`:
   `{"event":"anchor-close","source":"command","date":"<YYYY-MM-DD HH:MM>","file":"<basename>"}`
4. Report the archived path in one line. Do **not** also snapshot.

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
4. **Write the snapshot** — one full-file Write, all seven categories, each at
   task-appropriate depth:
   - Frontmatter: `format: anchor/v0`, `date`, `task:` (one line), `step:`
     (prior step + 1, or 1), `source: /anchor`.
   - **Mission** — the goal and its hard constraints, 1–3 sentences.
   - **Plan pointer** — where the full plan lives. Point, don't copy.
   - **Cursor** — done / in progress / the single next action. This is the
     load-bearing section; make it current, not aspirational.
   - **Invariants** — decisions and constraints a post-reset turn must not
     relitigate.
   - **Last-known-good** — branch and commit SHA, artifacts written,
     checkpoints reached. Check the real state (`git log --oneline -1`,
     the files on disk) rather than recalling it.
   - **Resume steps** — how a cold reader re-orients: read this file, verify
     the real state, continue from the cursor. Keep them idempotent.
   - **Decisions log** — append-only; why the non-obvious calls were made.
   Keep it bounded: cursor plus pointers, not a transcript. Fold closed phases
   into one-line outcomes pointing at the commit or artifact that carries the
   detail.
5. **Append telemetry** to `.claude/anchors/log.ndjson`:
   `{"event":"anchor-write","source":"command","date":"<YYYY-MM-DD HH:MM>","step":<N>,"file":"<basename>"}`
6. **Confirm in one line:** path, step number, and — when the user is about to
   compact — that `/compact` is now safe to run.

## Boundary

This command is the backstop, not the discipline. A one-off snapshot ages the
moment work continues; for a long or autonomous run, arm `compaction-survival`
— create the anchor at the start, update it after each step, re-read it each
turn. Use `/anchor` for the deliberate checkpoint: before a manual `/compact`,
before stepping away, before an irreversible move.
