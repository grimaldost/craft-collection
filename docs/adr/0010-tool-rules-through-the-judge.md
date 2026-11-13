# ADR-0010 - harness-kit: a tool's rule reaches the judge through a checker the tool owns

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

`docs/adr/0009-harness-kit-outside-the-harness.md` put the policy judge outside
the harness, and its policy, version 1, matches an act with data: a command
regular expression, a path glob and an origin set. A tool's own rule is often
logic that no pattern holds. The uv rule of `engineering-discipline` is the
example: it finds `pip install` and its relatives at a command position, with
quoted spans, comments and data heredoc bodies masked, and fires only when the
working directory is a uv project. A regular expression over the command either
misses those cases or fires on a quoted mention.

`docs/adr/0003-hooks-core-adapter-precommit-floor.md` already keeps such logic
in a pure core behind thin adapters, so the rule exists once, as a function of
plain arguments, and only its envelope belongs to a harness. The hooks that
carry these rules reach one harness. A second harness needs the same decision
and the same guidance text from the same source, and the kit must not grow a
second implementation of the rule to give it.

## Decision

A rule in policy version 2 may name a checker: a Python file owned by the tool,
declared in the policy with an identifier, a path and a `sha256`. The judge
loads the file, calls its `check(act, observation)` and folds the answer
(`match`, `no-match` or `cannot-tell`) into the rule's result like any other
optional matcher. A pack is the unit that carries a tool's rule: it holds the
checker, a thin adapter that calls the tool's own core, and the rule's text;
`kit policy build` composes a policy from packs. Version 1 policies stay valid.

Six invariants bind this change. Each is stated here so that no later change
has to rediscover it.

1. **checker-three-valued.** A checker answers `match`, `no-match` or
   `cannot-tell`. An exception, any other return value, or a call that has not
   returned when its budget ends is `cannot-tell`.
2. **checker-pinned.** A checker file that is missing, unreadable or whose bytes
   differ from the `sha256` the policy carries makes the whole policy
   unreadable. The judge executes the very bytes it hashed, with no second read
   of the file.
3. **judge-output-clean.** Whatever a checker writes to file descriptors 1 and 2,
   by any route short of ending the process, the judge's standard output holds
   exactly one line: the verdict.
4. **pack-single-source.** A pack calls the tool's own core and restates none of
   its logic. Its tests compare its answers against that core as it runs.
5. **v1-unchanged.** A version 1 policy is loaded and judged exactly as before
   this change, with the same refusal texts. Only the message for a version that
   is neither 1 nor 2 changes, to name both.
6. **no-launch-with-broken-checker.** `kit run` refuses, before the canary, a
   policy one of whose checkers does not load or defines no callable `check`.

The invariants of ADR-0009 are kept: thin-shell, unknown-denies,
no-harness-shape (now also over the checker files of the packs), stdlib-runtime
(amended below), nothing-under-plugins and no-private-names.

### Amendment to ADR-0009, stdlib-runtime

ADR-0009 gives, as its reason for stdlib-runtime, that the judge has no
environment to break. That reason no longer covers the whole case, because the
judge now holds a tool's core in its own process. The invariant stays and its
reason is widened: the kit's own code imports the standard library only, and a
checker file imports the standard library and the tool core it adapts, nothing
else. A checker that needs a third-party package is outside the rule. ADR-0009
itself is not edited; this record is the amendment.

## Alternatives considered

- **Rules as data, with a shell reader inside the kit.** Rejected: the kit would
  parse shell syntax and carry a second implementation of every rule that a tool
  already implements, and the two would drift. The kit reads no shell syntax; a
  pack does, through the tool's core.
- **One adapter per tool per harness, with no common judge.** Rejected by
  ADR-0009: it is the design whose guard disappears without a sound, and each
  rule would be written once per harness.

## Consequences

- The judge runs tool code, so a hash, a budget and a clean output are rules of
  the judge and not conventions of the checker.
- The `sha256` pins the checker file only, not what that file loads. A core
  removed while a session runs makes a steering rule read `cannot-tell` and pass,
  until the next build or launch refuses it.
- The budget is cooperative. A checker runs in a thread that the judge stops
  waiting for, so a call that never yields the interpreter is bounded only by
  the shell's deadline, which ends in a deny.
- A steering rule must not turn into a shell's deny by being slow. The budget
  arithmetic has four numbers, and names the
  judge's own start beside them:
  - at most 500 ms of checker budget in one judgement;
  - at most 1 s of journal lock;
  - at most 1 s of session lookup in the opencode shell;
  - the shells' 3 s, against which the others are held;
  - about 130 ms for the judge's own start, as measured on 2026-11-11.

  The first three bounds plus the judge's own start add up to about 2.63 s, which
  leaves the shells' 3 s a margin.
- A steering rule is `governed = false` and never blocks when it cannot tell. It
  stands outside the invariant no-launch-without-guard of ADR-0009, which speaks
  of the guard and not of each rule.
- The kit shell still denies when it gets no verdict, so this change does not
  wire the kit into a daily session: a rule through the judge is feedback inside
  one turn and prevents nothing.
