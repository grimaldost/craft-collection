# Evidence fabrication and absence-read-as-state

Four failure modes about the *evidence* behind a completion claim. Two are
fabrication — a status event or a cited anchor invented rather than read. Two
are the mirror image — an absence over-read as a verdict: silence on an
unattended run taken as "finished", an empty check result taken as "clean".

They are tool-general. They were catalogued inside
`engineering-discipline:data-engineering-discipline` as Modes 9, 10, 12 and 13
of its LLM failure-mode taxonomy, and moved here in 2026-08 because none of
them is about data: the clearest recorded instance of the fail-open mode
diagnosed a defect in an *eval harness*, and the mode numbers are kept so the
older citations still resolve. Reachable now by anyone about to claim work
done, not only by someone doing data work.

Each mode has four parts: the pattern, detection signals, the mechanical
defense, and a concrete example.

---

## Mode 9 - Fabricated telemetry: async status events treated as system state

**The pattern.** In orchestrated or long-running work, the agent treats
asynchronous status signals - progress notifications, monitor streams,
dry-run callbacks, "approved" / "merged" / "complete" events, cost
summaries - as the system's actual state. They are the agent's (or a
tool's) *narration about* the system, generated from expectation, not
read from it. When the narration runs ahead of reality, the agent acts
on events that never happened: it reports approvals for work not done,
marks runs complete that did not finish, records costs for runs that did
not execute.

**Detection signals.**

- A status claim ("wave approved", "all merged", "5/5 passed") with no
  artifact named - no commit SHA, no log line, no file on disk.
- An outcome reported before the process that produces it could have
  finished; costs and identifiers that are too clean, too fast, or
  suspiciously round.
- Bulk success in progress/dry-run output ("COMPLETE ... SUCCESS" for every
  item at once) rather than one verified result at a time.
- The agent narrates the next step's result while still inside the
  current step.

**Defense - the disk-truth protocol.**

- Every event claim is unconfirmed until verified against an append-only
  source: VCS state (the commit/merge on disk), an append-only run log,
  the process table, the materialized artifact. A notification is a prompt
  to go look, not a fact.
- No state-changing action and no status report on the strength of an
  event alone - read the disk truth first.
- For an orchestrated run, the close step is an independent
  re-verification from disk (git log, tracker file, process exit), never
  a trust of the run's own progress stream.

**Example.** An orchestration run reported two waves of approvals - with
realistic costs and plausible branch names - for changes that had not
been created; a `git log` would have shown nothing. Separately, a dry-run
emitted "COMPLETE ... SUCCESS" for every item in a series it had not
executed. In both, the defense is identical: the commit on disk is the
truth; the event is a claim.

---

## Mode 10 - Confabulated anchors and projected verification

**The pattern.** The agent cites an anchor - a test, a fixture, a file
path, a line range, a symbol - that it never actually read or that does
not exist, and builds on it as if verified. Three shapes recur:

- *Fabricated anchor* - the cited test / fixture / file isn't in the tree.
- *Projected verification* - one part is checked and the whole is recorded
  clean.
- *Partial read* - a `file:lo-hi` slice that ends inside an open
  collection literal, read as complete, producing *higher* false
  confidence than no read at all.

This is the verification-side twin of Mode 9: there the agent invents the
system's state; here it invents the evidence that the state was checked.

**Detection signals.**

- A "verified" / "confirmed clean" claim that doesn't name the exact scope
  checked ("verified the file" rather than "verified the constants table
  only").
- A cited `file:line` range whose end falls inside an unclosed `[`, `{`,
  or `(` - the read was sliced mid-literal.
- A spec or review names a fixture / test / symbol that a grep doesn't
  find.
- A handed-down brief ("X drifted; add Y") applied without reading the
  cited X - and the brief turns out accurate-but-incomplete.

**Defense - the anchor-provenance pass.**

- Every cited anchor traces to a read actually performed. Before shipping
  a spec or a review, grep-verify each cited `file:line` / fixture /
  symbol exists and says what you claim.
- A verified-clean entry names the exact scope read. "Verified clean"
  without a scope is an unverified claim wearing a verified label.
- A cited line range that ends inside an unclosed bracket / brace is
  evidence the read was truncated - re-read to the closing delimiter
  before citing any collection literal.
- A handed-down fix brief is a *claim*, not a contract: when a task
  supplies a root cause AND a fix, verify each cited anchor against the
  source before applying. The brief's own diagnostic step is often the
  tell that a second site needs the same change.

**Example.** A spec cited a parity-baseline fixture that did not exist in
the tree (fabricated anchor). A reviewer verified one table in a config
file and recorded the whole file clean; six other entries had wrong
signatures (projected verification). A `file:0-40` read ended inside a
list literal, so a three-element set was read as two and the truncated
value became the spec's concrete instance (partial read). A handed-down
brief said "the hook drifted; add the missing entry to its exclusion
set"; reading the source showed the *scanner's* exclusion set was
byte-identical and *also* lacked the entry - the one-file fix was a
two-file fix, and the brief's own step-1 diagnostic ("read the scanner;
is it missing too?") was the tell.

---

## Mode 12 - Silence read as status on an unattended run

**The pattern.** On a long unattended job - an overnight migration, a
headless multi-PR run, a backfill left to churn - the agent treats the
*absence* of new output as a fact: a tracker that hasn't moved and a HEAD
that hasn't advanced get read as "it finished" or "it stopped," and the
agent reports done or steps in to take over. But a quiet job is
slow-versus-dead-ambiguous: a still-live writer mid-computation and a
wedged process produce the *same* surface (no new lines, unmoved HEAD).
Acting on the inference corrupts the work - declaring a still-running job
complete reports a result that isn't materialized yet; taking over a
still-live writer collides two processes on the same worktree.

This is the inverse of Mode 9. Mode 9 is a *fabricated* event - narration
ahead of reality. This is a *missing* event read as a terminal state -
silence treated as a status it cannot, on its own, convey.

**Detection signals.**

- A "the run finished / stalled / is stuck" claim with no independent
  observable named - no process-table check, no artifact mtime, no log
  tail, only "nothing new appeared."
- A takeover (kill, branch reset, re-fire) about to start on the strength
  of a frozen tracker alone.
- "No errors, so it must have worked" on a job whose result was never read
  from disk.
- The job's own progress stream is trusted to *stop reporting* as proof of
  termination (a wedged process stops reporting too).

**Defense - disambiguate before acting, verify from disk before reporting.**

- Silence is a prompt to probe, not a status. Disambiguate slow-vs-dead
  with an independent observable: the process tree (is the writer still
  alive?), artifact mtimes (is anything still being written?), an
  append-only run log's tail. Only a dead process *and* quiescent artifacts
  is "stopped."
- A watcher that reports the world gone may be reporting its own instrument
  broken: a git-bash `/c/...` path handed to a Windows interpreter reads as a
  different, empty location, so a live workspace looks absent. Probe the observer
  with a known-present path first - if it cannot see a thing that certainly
  exists, the "gone" verdict is the observer failing, not the target.
- No state-changing takeover - kill, branch reset, re-fire - until
  quiescence is confirmed; a takeover that collides with a live writer
  corrupts the worktree, and that is the irreversible move.
- Completion is read from the materialized result (Mode 9's disk-truth
  protocol), never inferred from quiet. "No new errors" is not "succeeded";
  a job can die silently between log lines.
- When the gates-green output of a stalled run is salvageable, the recovery
  sequence is itself disciplined: confirm quiescence, review the in-diff
  artifact, re-verify it independently from disk, then merge - the same
  observable-source discipline the run itself owed.

**Example.** An overnight multi-PR run went quiet: the tracker file hadn't
advanced in an hour and HEAD was unmoved. Read as "stuck," the safe-looking
move was to take over and re-fire. The independent probe told a different
story each time it was run - a process-tree check plus artifact mtimes
distinguished a writer still mid-PR (do not touch) from a genuinely wedged
orchestrator (safe to salvage). Where the run had genuinely stopped with a
gates-green PR in the tree, the recovery was a quiescence check, an in-diff
review, an independent re-verify, then merge - not a blind re-run.

---

## Mode 13 - Fail-open tooling: a check that passes when it errors

**The pattern.** A gate is written so that *failing to run* and *finding
nothing* produce the same green verdict. The classic shape is
`command | filter` with "no output means pass": if the command itself is
absent from PATH, mis-invoked, or errors out, it prints nothing, the filter
matches nothing, and the gate reports clean - not because the tree is clean
but because the check never executed. A return-code-blind gate (pattern-
matching stdout while ignoring a non-zero exit) and an exception-swallowing
validator (`try: check() except: pass`) have the same defect. A gate that
manufactures false confidence is worse than no gate: no gate at least leaves
you knowing you haven't checked.

This is Mode 12's logic inside the project's own tooling - *absence of
output* read as *found-nothing*, when it may mean *the check didn't run*.
The per-invocation environment is not always sticky across an agent's
shell calls, so a tool present in one step can be missing in the next, and
a fence built on it silently flips from enforcing to vacuous.

**Detection signals.**

- A gate of the form `<tool> ... | grep/Select-String ...` whose pass
  condition is "no matching lines," with no prior check that `<tool>` exists
  and exited zero.
- A check that prints `CLEAN` / `PASS` unconditionally on an empty result,
  including the empty result an error produces.
- Stdout parsed for a success token while the process's exit code is
  discarded.
- A `try/except` around a validation step whose `except` branch lets the
  caller proceed.
- A gate that has never been observed to fail - neither on a planted bad
  input nor when its own tool was removed.

**Defense - distinguish did-not-run from found-nothing.**

- A check is fail-closed only when *tool-missing* is distinguishable from
  *nothing-found*. Assert the command exists and exited zero before trusting
  an empty result; treat a non-zero exit as BLOCKED, not CLEAN.
- Prefer a built-in over a shelled-out external tool for a fence (a
  language built-in or `Select-String` / Python over a PATH-dependent
  binary), so tool-absence can't silently zero the result.
- Let exceptions in a validator propagate, or catch-and-fail - never
  catch-and-pass. The error path defaults to blocked.
- Prove the gate can fail twice: once on a planted violation, and once by
  removing its own tool - a fail-closed gate goes red in both cases.

**Example.** A documentation fence ran `<formatter> --check ... | <filter>`
and treated empty output as pass. In a shell where the formatter binary
wasn't on PATH that invocation, the command errored, printed nothing, and
the fence reported CLEAN over a tree it had never inspected. Rewritten to
assert the tool resolved and exited zero - and to read a non-zero exit as
BLOCKED - the same fence went correctly red the next time the tool was
absent, surfacing the gap instead of hiding it.

---

## The shared root

All four are one Axiom-2 violation with two tells. In 9 and 10 a signal
*about* the system is invented and stood in for the system: an event that
never fired, an anchor that was never read. In 12 and 13 a *missing* signal
is over-read the same way: quiet taken for stopped, empty taken for clean.
Too much asserted as fact, or too little read as a conclusion.

The defenses rhyme. An event, a cited anchor, a "verified" claim and a green
gate each trace to something actually read from an append-only source - VCS
state, logs, the process table, the materialized artifact, the file at the
cited line. And an absence is a prompt to probe, never a verdict: confirm the
process is dead rather than quiet, and that the tool ran rather than stayed
silent, before acting on "nothing happened".
