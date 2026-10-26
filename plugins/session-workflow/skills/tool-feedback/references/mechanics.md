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
skill's current behavior — and record in the report which copy you ran.
`plugin_version.py` renders the version, its resolved install path, and any
cache-versus-tree skew into the field for you.

**Equal versions license reporting, not editing.** The two copies can differ in
*bytes at the same version* — observed as line wrapping: same words, different
line breaks. A body read from the cache and edited by literal match against the
tree failed `NOT FOUND` three times before a byte comparison found it, and the
first failure read as a charset fault because the console renders an em dash as
`?`. So anything that patches a skill body matches on collapsed whitespace, or
re-reads the target from the working tree first. Checking versions and finding
them equal is not evidence that the text is identical.

## Destination precedence — the fine print

Each report's destination, in precedence:

1. a dir the user named *this session* ("save them in `<dir>`"); a consolidated
   sink with per-tool subdirs maps to `<sink>/<tool>/`;
2. the registered feedback dir from the bindings table;
3. the tool's own repo.

Resolve only a **named or registered** dir, never an inferred one. A redirected
destination moves the *write* only: when a registered binding exists, the
recurrence check still reads **the registered dir** (its rebuilt `INDEX.md` and
`--grep` over its reports), so a one-off sink can't sever the recurrence baseline. State in the report which baseline you
used.

## Why the rebuilt index and `--grep`, not hand greps

The recurrence check rebuilds `INDEX.md` (one entry per prior report with its
numbered proposals and §-stubs) and then asks the builder for
`--grep <term> [<term> ...]`, instead of N speculative greps over the directory.
A hand grep matches one phrasing and returns a line out of its finding; the
builder's `--grep` reads the same reports the index covers (no triage doc, digest,
README or BACKLOG), matches any of several terms, and prints each matching finding
whole: its numbered line or §-stub bullet, its indented body, and its `<stem>#<n>`.
The index alone is not enough to judge "same cause?": it caps each title at 140
characters, so the deciding clause of a long finding is often the clipped part.
Pass several terms (the cause, the component, the symptom), because a finding
restated in other words still escapes a single term, and a missed recurrence
breaks the `extends` chain triage depends on for reinforcement counts.

Each digest line carries the fields the "same cause?" question needs, in fixed
positions — severity, the phase a miss names, and the `extends` referent:

    - `2026-08-01-wave#2` [HIGH] extends `2026-07-20-prior#3` — only the new evidence.
    - `2026-08-01-wave §Misses` [MED] (phase: gate) — the gate passed on a hollow record

so a first pass over the whole corpus is one read of the index; `--grep` is the
read of the candidates it turns up. A field is omitted when the source report did not supply it.

## When the builder refuses to write

Two install surfaces can serve different plugin versions at once, so an older
cached builder can meet an index a newer one wrote. It now refuses rather than
overwriting: exit 3, naming both versions and the file. Re-run from the newer
copy. `--force` writes anyway and is for a deliberate rollback, not for getting
past the message. Every successful write prints the report and finding delta
(`209 report(s) (+0), 1082 finding(s) (-14)`) — read it, because a parser change
can drop findings while the version stamp stays identical.
