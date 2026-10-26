# Phase briefs

A brief that hands one phase of work to a fresh context names the disciplines
that govern that phase, in the order the receiver loads them, and ends with the
closing block at the end of this file. Work that grows inside a session tends to
lose the method that an owner-written brief would have named; writing the
disciplines into the brief carries them across the boundary.

The lists below are for the installed toolkit: humblepowers, session-workflow,
engineering-discipline, experiment-discipline, keel and convoy. Each name is
written as the plugin, a colon and the skill, the form the receiver loads it
by. When the
receiver's environment may differ, it checks what is installed with
`session-workflow:toolkit-awareness` before loading anything.

How a brief uses a phase:

- Copy the phase's list into the brief's constraints, in order, with the line
  that says what each one governs there. A discipline marked "when" is listed
  only when its condition holds for this work.
- A brief that spans two phases (design, then specification) lists both, and
  the receiver loads each list at its phase boundary, not all at the start.
- At a direction change inside the phase, the receiver ranks the installed
  skills again with `humblepowers:choosing-tools`; a loaded discipline that
  turns out not to fit is set aside plainly.
- A run that will cross a compaction or restart also loads
  `session-workflow:compaction-survival` first, and its anchor's invariants
  repeat the list.

## Design

1. `humblepowers:brainstorming`: the design is agreed before code, with two or
   three approaches, their trade-offs and a recommendation.
2. `session-workflow:review-panel`, when the design is high-stakes or hard to
   reverse: a reviewer blind to the session reads it before it is handed on.

The brief also states the decision the design serves, the constraints already
fixed, and who approves the design.

## Specification

1. `keel:apply-method`: the spec follows the project's bound format, passes the
   Definition of Ready (`keel check-ready`), and gets a pre-mortem from a
   reviewer who did not write it. A series of two or more PR-sized changes goes
   through this before it is built.
2. `engineering-discipline:data-engineering-discipline`, when the spec changes a
   dataset or payload that something else reads: the contract is pinned in the
   spec.
3. `humblepowers:choosing-models`, when the spec carries a series file or
   per-task tiers.

The brief also states the spec path, the method bindings file, and the gate
each change will be judged by.

## Implementation

1. `humblepowers:test-driven-development`: each acceptance case is a test
   watched failing for the expected reason before the code that passes it.
2. `engineering-discipline:python-engineering`, when the code is Python: the
   project's tooling and layout.
3. `humblepowers:systematic-debugging`, when a failure has no proven cause.
4. `humblepowers:verification-before-completion`: before the hand-back, every
   claim of done or passing carries this run's command and output.

The orchestration follows the size of the work: one change is a direct turn; a
multi-step plan without series machinery runs under
`humblepowers:planned-execution`; two or more PR-sized changes run under
`convoy:convoy`, or at least with its gate as the judge of each change. The
brief also states the worktree and branch, the gate the implementer cannot
edit, and the repository's commit and release conventions.

## Data-contract change

1. `engineering-discipline:data-engineering-discipline`, at the start, before
   any code: pin the contract, verify the observable source, and check parity
   on real data.
2. `humblepowers:test-driven-development`: the contract's cases are tests first.
3. `humblepowers:verification-before-completion`: the parity result is shown
   with its command, not summarized.

The brief also states the consumers, the contract (columns, types, row
cardinality, null behavior, freshness), and the dataset the parity check runs
on.

## Measurement

1. `experiment-discipline:experiment-rigor`: the plan is frozen before the run,
   rates carry their numerator and denominator, and small samples get exact
   intervals.
2. `session-workflow:evaluate-skill`, when what is measured is a skill's
   triggering or its output.
3. `humblepowers:verification-before-completion`: every number in the result
   comes from a counting command read whole.

The brief also states the decision the measurement informs, the spend ceiling,
and who approves the spend.

## Release

1. `keel:apply-method`: the Definition of Done for the change, including the
   generated and mirrored artifacts it lists.
2. `humblepowers:verification-before-completion`: the gates pass on the release
   head, the version agrees at every site, and after the merge the tag is
   checked to resolve to the merge commit.

The brief also states the version, the repository's release steps (its
contributing guide), and where the tag goes. Publishing, installing or updating
the release on the owner's machine are owner questions in the closing block.

## Review

1. `session-workflow:review-panel`: the reviewer did not see the session and is
   briefed to refute.
2. `convoy:convoy`, for its gate run standalone: the verdict's checks are run
   by the reviewer, not taken from the author's report.
3. `humblepowers:verification-before-completion`: a verdict names the commands
   run and their output, an adversarial mutation that turned a test red, and any
   number recomputed independently.
4. `humblepowers:receiving-code-review`, for the author who receives the
   findings: each one is checked against the code before it is acted on.

The brief also states that the reviewer is read-only and the conditions a
passing verdict requires.

## The closing block

Every brief ends with this block, filled in for its phase:

```
## When you are done

Write the hand-back file at <absolute path>, and return the same content:

- done: what was finished, with its identifiers (PR URL, head commit, file paths)
- artifacts: every file or object produced, by absolute path or URL
- leaves: what is left, and why
- blocked on: what stops the next step, or "nothing"

Facts: mark each fact in the hand-back as measured (a command run in this
context, its output read whole) or relayed (taken from this brief, another
session, a subagent or a document), and name its source.

Owner questions: the questions only the owner decides, each framed with its
options and a recommendation. Do not act on them.
```

The questions only the owner decides are the ones the receiver puts to the
owner instead of acting on: spending money or usage headroom, credentials,
deletions, public or irreversible acts (a publish, a push to a shared branch, a
release install), the owner's governance files (the global agent instructions
and harness settings), plugin installs and updates, user or machine environment
variables, and standing rules such as hooks. A generic go-ahead in the brief
does not cover them; the brief names any of them the owner has already
approved, one by one.
