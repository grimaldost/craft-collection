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

In this slice `kit run` accepts only a home rendered by `kit home render`, and
only a headless session (`claude -p`, `opencode run`): the canary ran nothing
else. `HARNESS_ARGS` must start with the driver's leading tokens and may carry
only the flags the driver names; anything else is refused.

## Policy

A policy is a TOML file, version 1: a `[launcher]` table with `test_roots` and
`forbidden_roots`, and `[[rule]]` tables, each with an `effect` (`allow` or
`deny`), `governed`, `kinds`, optional matchers (`command_regex`, `path_glob`,
`origin_in`) and a `reason` shown to the model. Rules are read in file order. A
policy is read whole before any judgement; one bad rule makes it unreadable,
and an unreadable policy denies.

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
`KIT_HARNESS_ARGV_OPENCODE` are set.

## Tests

The tests beside the code run with the repository's runner,
`python scripts/run_tests.py`, from the repository root. The decisions behind
the package are in `docs/adr/0009-harness-kit-outside-the-harness.md`.
