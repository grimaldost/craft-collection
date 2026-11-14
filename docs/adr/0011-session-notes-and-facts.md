# ADR-0011 - harness-kit: session notes and per-session facts

- **Status:** Accepted
- **Date:** 2026-11-14

## Context

`docs/adr/0009-harness-kit-outside-the-harness.md` put the policy judge outside
the harness, and `docs/adr/0010-tool-rules-through-the-judge.md` let a tool's own
rule reach it as a checker file. Both describe an act before it happens: the
neutral event carries the act and what the shell observed of its session, and a
checker is called as `check(act, observation)` with no session and no memory.

Two guards of the session-workflow plugin decide an act from something that
happened earlier in the session, and neither can be judged from the act alone.
The series guard denies a second `gh pr create` in one repository and session
unless the command declares a series, and it knows a create is the second
because an earlier create printed a pull-request URL. The owner-acts gate denies
a write to a governed configuration file, a plugin change, an environment
variable or a global git setting unless a sentence of the owner's latest prompt
names the act, and it knows that prompt because it recorded it when the prompt
was submitted. The kit's event, shells and checker call carry nothing of either
kind.

ADR-0003 (`docs/adr/0003-hooks-core-adapter-precommit-floor.md`) keeps such logic
in a pure core behind thin adapters, so the rule exists once and only its envelope belongs
to a harness. That stays true here: the two guards keep their cores, and the kit
adds a way for a core to be told what already happened.

Two facts about the harnesses, measured on Claude Code 2.1.316 and opencode 2.2.5,
decide the shape of the answer. Both deliver a submitted prompt and the outcome
of a finished shell call to the shell they run, and both await the hook for call N
before the hook for call N+1 of a later assistant message, so a note recorded
after one call is visible to the judgement of the next. Neither proves who typed
a prompt: on Claude Code a task notification
arrives as a prompt, and on opencode a child session's first message carries a
harness-written line and no flag. A refused call fires no outcome hook on either
harness, so a note describes only a call that ran.

## Decision

The kit gains a second intake, `kit note`, for what already happened: a submitted
prompt and a finished shell call. A shell forwards each to `kit note` in a note
mode that is separate from its judgement mode. A note asks for no verdict; it is
recorded or dropped, and a receipt of one line says which.

The kit keeps small per-session facts inside a minted run, one for which
`state.is_launched` holds. Only `kit note` writes them. A facts file belongs to
one checker and one session root and lives under the kit's state root, outside
every harness's configuration.

Policy version 3 is version 2 with one more optional key on a checker, `records`,
which lists the kinds of note the checker records, `prompt` and `outcome`. A
checker that declares `records` defines `record(note, facts)`, which returns the
new facts or says nothing changed, and is called as `check(act, observation,
facts)` when it judges. A checker without `records` is called as before.

The session root is one rule, used by notes and judgements alike. The root key is
`session.root_id` when the root is observed and non-empty; else `session.id` when
the session is observed and non-empty; else there is no root key and the session
cannot be observed. A child session on opencode whose root is found is keyed by
that root, so a note recorded in a child is seen by the judgement of its parent
and the reverse; a walk that ends early keys the child by its own id.

`None` is what a checker receives when the session cannot be observed: outside a
minted run, with no root key, or with an unreadable facts file. An empty object
is what it receives when the session is observable and nothing was recorded. The
two are different answers and a checker must not merge them. `None` facts mean the session cannot be observed and a checker answers `cannot-tell` on them. For a governed rule, a `cannot-tell` is `unknown`, which denies, so with no facts an owner act is denied; for a steering rule it passes.

Six invariants bind this change, each stated by its identifier.

1. **note-never-decides.** A note asks for no verdict and never blocks a session.
   `kit note` prints only its receipt and exits 0 whenever its arguments parse. A
   shell's note mode prints nothing to its harness, never denies or throws, and on
   its own deadline or on any failure ends silently. This narrows ADR-0009's rule
   that a kit shell fails closed to the judgement path, since a note mode never
   denies: a shell that cannot get a verdict still denies, and a shell that cannot
   deliver a note is silent.
2. **facts-from-notes-only.** Only `kit note` writes facts. A judgement reads them
   and never writes them, and creates no folder. Facts exist only inside a minted
   run.
3. **facts-bounded.** A facts file is at most 65536 bytes. A recorder's result
   that would pass that is not written, and the facts stay as they were.
4. **note-journal-no-text.** A note's journal line holds its kind, sizes and
   hashes, never a prompt's text, a command, an output or a path. Note lines go to
   `notes.ndjson`, beside the event journal and not in it, so that every reader of
   the event journal counts what it counted before.
5. **v1-v2-unchanged.** A version 1 or version 2 policy loads and judges exactly
   as before this change, with the same refusal texts. Only the message for an
   unknown version changes, to name 1, 2 and 3.
6. **harmless-cells.** Every act scripted in a real-harness cell is harmless if
   it runs, and nothing a test does writes outside its test folder: no `setx`, no
   plugin command, no global git setting, no write to a real governed home and
   no real `gh`.

The invariants of ADR-0010 are kept and extended to `record`: checker-three-valued,
checker-pinned, judge-output-clean, pack-single-source and
no-launch-with-broken-checker. A recorder that raises, returns anything else or
overruns leaves the facts as they were; a recording checker without a callable
`record` is refused by `kit policy build` and by `kit run`; and the standard
output of `kit note` holds exactly one line, its receipt. The invariants of
ADR-0009 are kept: origin-never-owner now also covers notes, whose origin
vocabulary is the event's, and thin-shell, unknown-denies, no-harness-shape (also
over the checker files of the packs), stdlib-runtime, nothing-under-plugins and
no-private-names stand. One bound of thin-shell moves: the shells' line ceiling,
160 non-blank lines in the repository's tests, becomes 240 non-blank lines per
shell file, for the note modes.

Two packs carry the guards through this mechanism, `series` and `owner-acts`. Each
imports its core where it is and changes none of it, and each is proved on both
harnesses in test homes against a stub model.

## Alternatives considered

- **Each pack reads the harness's own transcript or database.** Rejected. It puts
  harness code in a pack, against the thin shells of ADR-0009, and ties each rule
  to a storage format that a harness may change in any release.
- **Rules with no memory.** Every create declares a series; every owner act is
  denied. Rejected as the design, because it changes both guards' behaviour and
  leaves nothing for the next tool that needs to know what happened earlier in the
  session. It is kept as the written degradation for a harness that cannot
  deliver a kind of note: such a harness's contract records the kind as absent
  and `kit run` refuses a policy that records it.

## Consequences

- The facts store holds a prompt's text, up to 20000 code points, and
  pull-request URLs, under the kit's state root and outside every harness's
  configuration. It never appears in a journal.
- A note can be lost: the shell's deadline, a lock not obtained within 1 s, a
  conflict or a failed recorder each lose it. A lost note leaves the facts as they
  were, so the series rule may miss a pull request and the owner-acts rule may
  deny an act the owner named.
- On the allow side, a prompt note that is not recorded leaves the earlier owner prompt in force until the next prompt that is recorded, so an act the earlier prompt named stays allowed meanwhile. A long prompt is never lost for its size: the owner-acts
  recorder keeps the longest prefix whose facts file fits in 65536 bytes.
- The facts store takes a lock of its own, `facts.lock` in the run's `facts/`
  folder. The journal's lock is taken only for the short append to
  `notes.ndjson`, so a note holds the journal's lock only for one short append, as
  a judgement does, and a judgement never waits on `facts.lock`.
- The worst case of a note is stated with its numbers. A process start costs
  about 130 ms, as measured on 2026-11-11. The recorders have at most 500 ms of
  budget in all. Per recorder there are two waits for `facts.lock` of at most 1 s
  each and one replace of at most 2 s, the retry of a Windows sharing error in
  `state.write_json_atomic`; then one wait of at most 1 s for the journal's lock.
  That makes about 5.6 s with one recorder, and each further recorder adds up to
  4 s. On opencode the walk to the session root adds up to 1 s more, inside the
  same deadline. This worst case passes the shells' 3 s note deadline. The shell
  then ends the note and it is lost: a facts file it had not yet replaced stays as
  it was, because the replace is atomic; its journal line and receipt may be
  missing; and nothing is blocked.
- A judgement reads facts without any lock, retrying a Windows sharing error for
  at most 100 ms per recording checker. That is all a judgement adds to the
  arithmetic of ADR-0010.
- Who typed a prompt is not proved. The kit has only what the core's lexical rule
  and the harness's child marker say, and each contract lists the gap as a known
  loss.
- The launcher passes `SESSION_WORKFLOW_GOVERNED_HOME` into a session only when
  the policy records something and the variable points under a test root of the
  policy. It never passes the cores' switches, so both rules are on in a launched
  session.
- Facts exist only inside a minted run. A session started outside one has none,
  so the owner-acts rule denies every owner act there and the series rule never
  denies.
- A note mode prevents nothing and wires the kit into no daily session. As with
  every rule of the kit, a refusal is feedback to the model inside one turn.
