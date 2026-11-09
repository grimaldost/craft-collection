# ADR-0009 — harness-kit: the policy core lives outside the harness

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

`docs/adr/0003-hooks-core-adapter-precommit-floor.md` keeps each hook's logic in
a pure core behind a thin per-harness adapter, and ranks enforcement from a block
at act time down to advice in `AGENTS.md`. It stops there. Nothing in it says
what happens when the adapter itself is missing, malformed or hung, and the
repository's existing hooks answer that in one way: they fail open (the class
named under "fail-open hooks" in `CONTRIBUTING.md`, where a hook that errors is
exempt from the proof that a check can fail).

That answer is wrong for a guard. On the harnesses tested so far, a guard that
fails to load is lost without a sound:

- **Claude Code.** A malformed `settings.json` or a hook entry with the wrong
  schema leaves the tool running, with nothing on stderr. A hook that crashes,
  times out or has no interpreter lets the tool run and tells the model nothing,
  unless the entry sets `onFailure: "block"`.
- **opencode.** A plugin that throws at load, has a syntax error, exports
  nothing or sits in a missing folder leaves the process exiting 0 and the tool
  running, with one warning line in a log file.
- **Every harness.** A denied run exits 0, so only a marker written to disk tells
  a denial from a success.
- **Payloads.** On the harnesses examined, no payload says who wrote a prompt
  (measured on opencode and goose, read on Claude Code), so a policy that reads
  an "owner" origin from a payload reads something nobody supplied.

A hook inside the harness is therefore feedback to the model, not governance.
Governance needs a judge that runs outside the harness, a launcher that will not
start a harness whose guard is missing or broken, and a record of what was
tested on which harness.

## Decision

Add a top-level package, `harness-kit/`, outside `plugins/`: a standard-library
Python command line, `kit`, with a policy judge, a launcher, a presence canary
and a doctor, and thin shells for the harnesses that need them. The package is a
separate distribution (`harness-kit`, backend `uv_build`, Python 3.11 or later,
no dependencies) and the repository's test runner and two encoding lints now
read it.

Ten invariants bind the package. Each is stated here so that no later change has
to rediscover it.

1. **thin-shell.** A shell only calls the CLI and translates its verdict into
   the harness's own convention. It holds no policy. This extends the adapter
   thinness of ADR-0003. ADR-0003 states no failure rule, so this ADR states one
   on its own authority: a kit shell **fails closed**. A shell that cannot get a
   verdict (CLI missing, crash, timeout, empty or unparsable output) denies.
   This differs on purpose from the fail-open class in `CONTRIBUTING.md`, which
   covers formatters and advisory hooks, not guards.
2. **unknown-denies.** A verdict has three states, `allow`, `deny` and
   `unknown`. `unknown` has effect `deny`, and so does invalid input to the
   judge.
3. **origin-never-owner.** The event's origin vocabulary (`interactive`,
   `child`, `synthetic`, `unknown`) has no value meaning the owner. An event that
   claims one is invalid.
4. **no-harness-shape.** The core, meaning every `.py` file of the package
   outside `shells/` and `harnesses/`, names no key of any harness's payload.
   Only a shell or a driver knows a harness's shape. A contract's prose may name
   one, because a loss is a fact about a harness.
5. **state-outside-harness.** The kit's state root (run records, journals,
   heartbeats) lies outside every harness's configuration, so a harness's own
   settings cannot reach it by accident.
6. **marker-proof.** A canary's proof is a marker on disk. No exit code is read
   as proof, since a denied run and a successful one both exit 0.
7. **no-launch-without-guard.** A missing or broken guard ends `kit run` before
   any request reaches the session's model endpoint.
8. **stdlib-runtime.** Nothing under `harness_kit/` imports outside the
   standard library, so the judge has no environment to break.
9. **nothing-under-plugins.** This work changes nothing under `plugins/`.
   `docs/adr/0001-single-source-portable-core.md` keeps the plugins as the single
   source of what they ship, and the package neither duplicates nor edits it.
10. **no-private-names.** Nothing committed names a private project, machine,
    personal path or private decision record.

The kit prevents nothing against a model that wants past it: a write to a
configuration file by another route, an in-process change that drops a plugin,
or a rewrite after approval all remain open. Those need a boundary at the
resource, which this decision does not provide. The doctor reports that
objective as `absent` so that the kit is not read as protection.

## Alternatives considered

- **Keep the policy inside each harness's hooks, as ADR-0003 does.** Rejected: it
  is the design whose guard is lost silently, and the policy would be written
  once per harness. The hooks stay, as feedback that names the verdict to the
  model in the turn.
- **Rely on each harness's native permission tables alone.** Rejected as the
  core: each harness's table has its own shape, so the policy would be written
  once per harness, and each table is unproved until a deny-and-allow test
  passes on it; what happens when one fails to load is unmeasured. They remain
  usable as defence in depth, each switched on only after such a test passes.
- **A resource boundary first (file ownership or a separate account).** Not
  chosen for this slice: its measurements are incomplete and where the protection
  should live is still an open choice, and claiming prevention before both are
  settled would be worse than stating the limit. It is the next layer, not a
  replacement for this one.
- **A broker that holds credentials and mediates writes.** Deferred: no broker
  has been measured, and it solves a different problem (who may write) than the
  one measured here (a guard that disappears without notice).
- **Translate the verdict into one harness's shape and have the others imitate
  it.** Rejected: the neutral event and verdict keep the core free of any
  harness's keys (invariant 4), and each shell does its own translation.

## Consequences

- New decisions about enforcement are made in the kit's judge and tested there;
  shells stay short enough to read at a glance, and a change to one is a change
  to a translation only.
- `kit run` proves the guard live with a canary before the first model request.
  Outside Claude Code the launcher is required by the judge, not by the harness:
  the rule `launcher.required` denies a governed act from an event that `kit run`
  did not launch. A bare opencode start with the shell plugin loaded still
  starts, and its first governed tool call is denied. A bare start with no
  plugin, or with one that fails to load, never reaches the judge: it runs
  unguarded and nothing journals it. That loss is out of reach of this slice and
  is recorded in the harness's contract. Claude Code without the launcher stays
  possible; its events are judged by the policy and recorded as not launched.
- `kit doctor` reports, per objective and per harness, what was tested. A loss
  that is known and cannot be closed is listed in the harness's contract rather
  than left implicit.
- The package adds one more test root and one more lint root:
  `scripts/run_tests.py` and `scripts/ascii_runtime_lint.py` read `harness-kit/`,
  `scripts/subprocess_encoding_lint.py` follows through the ASCII lint's file
  list, and the test runner skips any folder named `.venv`.
- The kit adds a failure mode of its own: a judge that is down denies governed
  acts. That is the intended trade, and the doctor and the launcher are the
  places that make it visible.
