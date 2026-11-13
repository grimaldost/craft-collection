# harness-kit

`kit` is a command line that judges what a coding-agent harness is about to do,
starts a harness only when its guard is in place, and reports what was tested.
It runs outside the harness, in standard-library Python, and has thin shells for
Claude Code 2.1.316 and opencode 2.2.5.

## What this slice does not do

A shell's refusal is feedback to the model inside one turn. It is not
prevention. The objective `prevention` is `absent` on both harnesses, in the
contract files and in the report of `kit doctor`, and nothing in this package
changes that.

A model that wants past the guard has routes this slice does not close: a
`python -c` write to a settings file, a config write that drops an opencode
plugin in-process, a rewrite after approval, shell prefixes the guard does not
judge. They wait for a resource boundary that this package does not have. The
ledger of known losses is in `src/harness_kit/contracts/`, one file per harness.

The second slice, which lets a tool's own rule reach the judge, has four more limits:

- a rule's refusal is feedback: a rule through the judge steers the model inside one turn and prevents nothing;
- the uv rule's preventing layer is pip's own setting and is not installed or checked by the kit, and the uv pack only declares that layer;
- the kit is not wired into a daily session, and every harness run here is a test home against a stub model;
- the doctor's `tested` for a rule comes from the contract and does not see a core that has gone missing since, so a checker that cannot load its core reads `cannot-tell` and a `governed = false` rule lets the act pass until the next build or launch refuses it.

What the slice does do:

- It judges a neutral event with a three-state verdict. `unknown` has the same
  effect as `deny`, so a guard that cannot tell refuses.
- It refuses to start a harness whose guard is missing or broken, before the
  first request reaches the session's model endpoint (the presence canary).
- It records each run and each judgement under a state root of its own.
- It reports, per harness and per objective, what was tested, with the losses
  that apply.

## Install

From a clone of this repository, with [uv](https://docs.astral.sh/uv/):

```
uv run --project harness-kit kit --version
```

prints `kit 0.1.0`. `uv tool install ./harness-kit` puts `kit` on `PATH`;
`python -m harness_kit` is the same command once the package is installed.
Python 3.11 or later, no dependencies.

## Subcommands

| Command | What it does |
|---|---|
| `kit --version` | Print the version. |
| `kit judge [--policy PATH]` | Read one neutral event as JSON on stdin, print one verdict as one line of JSON, exit 0 whenever a verdict was printed. The policy is `--policy`, else `KIT_POLICY`. |
| `kit state path` | Print the state root. |
| `kit state new-run --harness NAME` | Mint a run id and its folder; print them as JSON. |
| `kit stub --log FILE --script FILE [--port N]` | Serve a scripted model endpoint on 127.0.0.1 for tests; the first stdout line is `{"port": N}`. |
| `kit home render --harness NAME --dir DIR --endpoint URL` | Render a test home for `claude-code` or `opencode` into an absent or empty folder; print its `home.json`. |
| `kit run --harness NAME --home DIR --workdir DIR --policy FILE -- HARNESS_ARGS...` | Check the session, run the presence canary, then start the harness and return its exit code. |
| `kit doctor [--json] [--live --live-root DIR]` | Report what was tested, the runs and the sessions that were not launched. |
| `kit policy build --base FILE --pack DIR [--pack DIR ...] --out FILE [--force]` | Write a version 2 policy from a base policy and rule packs, with `<out>.packs.json` beside it; a refused input exits 64 and writes nothing. |

In this slice `kit run` accepts only a home rendered by `kit home render`, and
only a headless session (`claude -p`, `opencode run`): the canary ran nothing
else. `HARNESS_ARGS` must start with the driver's leading tokens and may carry
only the flags the driver names; anything else is refused. `kit run` accepts a
version 2 policy and loads its checkers first; see "Version 2 and checkers".

## Policy

A policy is a TOML file, version 1: a `[launcher]` table with `test_roots` and
`forbidden_roots`, and `[[rule]]` tables, each with an `effect` (`allow` or
`deny`), `governed`, `kinds`, optional matchers (`command_regex`, `path_glob`,
`origin_in`) and a `reason` shown to the model. Rules are read in file order. A
policy is read whole before any judgement; one bad rule makes it unreadable,
and an unreadable policy denies.

### Version 2 and checkers

Policy version 2 reads everything version 1 does, and adds a `[[checker]]` array
and one more rule matcher, `check`. A version 1 policy is loaded and judged as
before, and in it `checker` and `check` are unknown keys.

```toml
version = 2

[[checker]]
id = "uv-rule"
file = "packs/uv/uv_rule.py"
sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
budget_ms = 250

[[rule]]
id = "uv-project-uses-uv"
effect = "deny"
governed = false
kinds = ["shell"]
check = "uv-rule"
reason = "Use uv for dependencies in this project."
```

A checker is a Python file that a tool owns and that defines
`check(act, observation)`. Its `file` is absolute or relative to the folder of
the policy file. The judge calls it with copies of the event's `act` and
`observation`, and the checker returns a dict whose `result` is one of three
values, with an optional `detail` string:

- `match`: the rule's matcher holds.
- `no-match`: it does not.
- `cannot-tell`: the checker could not decide. An exception, any other return,
  a file that does not execute and a call still running when its budget ends
  all read `cannot-tell`.

A `check` is evaluated after `kinds` and the rule's other matchers, and only
when none of them gave no-match. Its result joins the others as in version 1:
any no-match gives no-match, else any `cannot-tell` gives `cannot-tell`, else
`match`. A rule that is `governed = false` passes on `cannot-tell`; a governed
one denies. A deny from a rule whose checker returned a `detail` carries the
detail, one space, then the rule's `reason`.

The rules of the contract, each a refusal when broken:

- The `sha256` pins the bytes of the checker file. A file that is missing,
  unreadable or different makes the whole policy unreadable, and the judge runs
  the very bytes it hashed. The hash pins that file only, not what the file loads.
- `budget_ms` is an integer from 50 to 500 and defaults to 250. One judgement
  has a total checker budget of 500 ms: each wait is cut to what is left, and a
  checker is not called once less than 50 ms is left. The budget is cooperative,
  so a call that never yields is bounded only by the shell's deadline.
- The judge's standard output holds exactly one line, the verdict, whatever a
  checker writes to descriptors 1 and 2.
- `kit run` loads every checker before the canary and refuses, with exit 64, a
  policy whose checker does not load or defines no callable `check`.

## Packs and `kit policy build`

A pack is a folder with a `pack.toml` and the checker files it names. It is how
a tool hands the kit a rule. A checker in a pack calls the tool's own core and
restates none of its logic, so the rule is written once.

```toml
pack = 1
name = "uv"

[[checker]]
id = "uv-rule"
file = "uv_rule.py"
budget_ms = 250

[[rule]]
id = "uv-project-uses-uv"
effect = "deny"
governed = false
kinds = ["shell"]
check = "uv-rule"
reason = "Use uv for dependencies in this project."

[prevention]
rule = "uv-project-uses-uv"
layer = "pip's require-virtualenv setting in the user's pip configuration"
```

`kit policy build` composes a version 2 policy from a base policy and packs: the
base's `launcher` table, the base's rules, then each pack's rules in argument
order, with every checker's `file` made absolute and its `sha256` computed from
its bytes at that moment. It writes `<out>.packs.json` beside the policy, which
the doctor reads. The same inputs give the same bytes. The uv pack is built into
a policy like this:

```
kit policy build --base base-policy.toml --pack harness-kit/packs/uv --out kit-policy.toml
```

The checker files stay where they are, so moving a pack folder after the build
makes the policy unreadable; build again. The uv pack reads the
`engineering-discipline` plugin's own core from where it sits in this
repository, and its tests compare the checker's answers against that core as it
runs.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. For `kit judge`, a verdict was printed, whatever it was. |
| 2 | Usage error from the argument parser. |
| 64 | A refusal: an argument, a state root, a home or a policy was refused, or a preflight check failed. Nothing was started. |
| 65 | The presence canary failed. The session was not started. |
| 70 | An internal error. |

`kit run` otherwise returns the harness's own exit code. A denied tool call
exits 0 on every harness tested, so the exit code says nothing about a denial:
the proof is a marker on disk, and `run.json` in the run's folder is the
authority on what happened.

## State root

The state root is `KIT_STATE_ROOT` when set, else `%LOCALAPPDATA%\harness-kit`
on Windows, else `$XDG_STATE_HOME/harness-kit`, else
`~/.local/state/harness-kit`. A root inside a harness's configuration folder is
refused with exit 64. It holds `runs/<id>/` (`run.json`, `heartbeat.json`,
`journal.ndjson`, the canary's folder) and `not-launched/` for judgements made
outside `kit run`. A journal line names the kind of act and its hash and the
verdict, never the command text or a path.

The run id reaches the harness's children through `KIT_RUN_ID`.

## Reading `kit doctor`

`kit doctor` prints one report: per harness, the version found and one state per
objective (`guard_loaded`, `refusal_in_turn`, `allow_passes`, `run_identity`,
`launcher_checks`, `hung_guard`, `heartbeat`, `prevention`), the known losses,
the runs (`running`, `stale`, `ended`, `refused`) and the sessions that were
not launched. `--json` prints it as one line of JSON.

The states are exactly these four:

- `tested`: the objective held in the conformance cells that measured it, and no
  loss is known for it.
- `degraded`: it held, and the contract lists at least one loss that applies.
- `absent`: there is no mechanism for it, or the live canary failed.
- `unknown`: nothing was measured, or the harness version found differs from the
  version the contract was measured on.

Without `--live` the states come from the contract files. With `--live
--live-root DIR` the doctor also renders a scratch home under `DIR` (which must
lie under a `test_roots` entry of `KIT_POLICY`), runs the canary per harness
found, and never reads cleaner than the contract. A session that did not go
through `kit run` reads "not launched, guarantees unknown": on Claude Code it is
judged and journaled, and what it was not given (the canary, the run identity)
is not claimed.

### The `rules` section

When `KIT_POLICY` names a readable version 2 policy and a `<policy>.packs.json`
beside it records that policy's `sha256`, the report gains a `rules` section.
For each rule that has a checker it gives the rule's id, `governed`, the pack's
name (`-` for a rule from the base), a state per harness and `prevention`: the
layer the pack declares, followed by `declared by the pack, not checked by the
kit`, or `none declared`. With `--json` the same list is under the key `rules`.

The state per harness is `unknown` when the harness binary is absent or its
version differs from the contract's; otherwise `tested`, with the contract's
evidence text, when the contract's `[rules]` table has the rule; otherwise
`unknown`. A policy that does not load gives the one line `rules: policy unreadable`
followed by its reason, and a sidecar that does not record the policy's hash gives
`rules: sidecar stale`. With a version 1 policy, no `KIT_POLICY` or no sidecar, the
section is absent and the report is as before. The doctor runs no checker and
starts no program for this section.

## Shells and contracts

The shells are in `src/harness_kit/shells/`: `claude_code/kit_hook.py` and
`opencode/index.js`. Each one only calls `kit judge` and translates the verdict
into the harness's convention; it holds no policy, and it denies when it cannot
get a verdict. They are registered in the settings or config of a home rendered
by `kit home render`, not in a harness's real installation.

The contracts are in `src/harness_kit/contracts/`. They are read by the doctor
and updated by hand from the conformance results in `conformance/`, which run
the real harnesses against a local stub model and print `skip:` unless
`KIT_CONFORMANCE_BASE`, `KIT_HARNESS_ARGV_CLAUDE_CODE` and
`KIT_HARNESS_ARGV_OPENCODE` are set. The rule cells, in `conformance/test_rules.py`,
build a policy from the conformance base policy and `packs/uv`, run each harness
against the stub model, and write `rules-results.json`; the `[rules]` table of a
contract is written by hand from that file.

## Tests

The tests beside the code run with the repository's runner,
`python scripts/run_tests.py`, from the repository root. The decisions behind
the package are in `docs/adr/0009-harness-kit-outside-the-harness.md`.
