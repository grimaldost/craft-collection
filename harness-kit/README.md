# harness-kit

`kit` is a command line that judges what a coding-agent harness is about to do,
starts a harness only when its guard is in place, and reports what was tested.
It runs outside the harness, in standard-library Python, and has thin shells for
Claude Code 2.1.316 and opencode 2.2.5. It also takes notes of what already
happened in a session, a submitted prompt or a finished shell call, and keeps
small facts from them, so that rules that decide from an earlier event can run
through it.

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

The third slice, which adds session notes, facts and the series and owner-acts packs, has these limits:

- It prevents nothing: as with every rule of the kit, a refusal is feedback to the model inside one turn.
- It does not wire the kit into the owner's daily sessions.
- It changes nothing under `plugins/`; the cores stay as they are, and the packs use some of their private names until `plugins/` can change.
- It does not prove who typed a prompt.
- It does not treat opencode's own configuration files as governed files: the four families are the core's, which speak of the owner's Claude Code home.
- It does not check that the note hooks are present at launch: the canary judges the PreToolUse guard only, and a home rendered without note hooks is refused only by the static check of the rendered home that `kit run` makes.
- It does not keep every prompt note: a prompt note that is not recorded (the shell's deadline, a lock not obtained, a conflict, a failed recorder) leaves the earlier owner prompt in force until the next prompt that is recorded, so an act the earlier prompt named stays allowed meanwhile.
- It does not tell a script written by a Bash heredoc from a command: the owner-acts rule reads every command in both dialects, so a heredoc body whose lines name an owner act (a script written to a file) is denied, where the core allows it.
- It does not survive a shell file removed during a session on Claude Code: the interpreter then exits 2 for every hook, which blocks each prompt as well as each tool call (inferred; at launch the canary refuses such a home).
- Facts exist only inside a minted run, one that `kit run`, `kit state new-run` or `kit doctor --live` made; a session started outside one has none, so the owner-acts rule denies every owner act there and the series rule never denies.
- In a launched session the cores' switches (`SESSION_WORKFLOW_SERIES_GUARD`, `SESSION_WORKFLOW_OWNER_ACTS_GATE`) are absent, so both rules are on.
- A refused call leaves no outcome note on either harness (measured): the series rule counts only pull requests whose create ran and printed a URL.
- It does not tie a child session's notes and judgements to one root on opencode when the walk to the root ends early in one hook and not in another: each hook walks on its own, and a walk that ends early keys the child by its own id, so the series rule may miss a pull request and the owner-acts rule may deny an act the owner named.
- It does not order calls that run in parallel: Claude Code can run the calls of one assistant message in parallel (measured for two read-only calls), so a create issued beside the first one is not seen by the series rule.
- With the owner-acts pack in the policy, opencode's `patch` tool is refused: the shell does not observe its paths, the governed rule cannot tell, and the verdict is `unknown`.
- The owner-acts refusal does not carry the core's per-family side effects and example sentence: the rule's reason is one fixed text, and the detail names the denied acts.

What the slice does do:

- It judges a neutral event with a three-state verdict. `unknown` has the same
  effect as `deny`, so a guard that cannot tell refuses.
- It refuses to start a harness whose guard is missing or broken, before the
  first request reaches the session's model endpoint (the presence canary).
- It records each run and each judgement under a state root of its own.
- It reports, per harness and per objective, what was tested, with the losses
  that apply.
- It takes notes of what a session already did and keeps per-session facts, so
  that the series rule and the owner-acts rule decide from earlier events.

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
| `kit note [--policy PATH]` | Read one session note as JSON on stdin, let the policy's recording checkers keep facts from it, and print one receipt as one line of JSON; it always exits 0 once its arguments parse. See "Notes and facts". |
| `kit state path` | Print the state root. |
| `kit state new-run --harness NAME` | Mint a run id and its folder; print them as JSON. |
| `kit stub --log FILE --script FILE [--port N]` | Serve a scripted model endpoint on 127.0.0.1 for tests; the first stdout line is `{"port": N}`. |
| `kit home render --harness NAME --dir DIR --endpoint URL [--policy FILE]` | Render a test home for `claude-code` or `opencode` into an absent or empty folder; print its `home.json`. With `--policy`, a policy whose checkers record notes also gets `note_config.json` and the note hooks, and an opencode home renders the policy's `[permissions]` section (see "Permissions"); an unreadable policy exits 64. |
| `kit run --harness NAME --home DIR --workdir DIR --policy FILE -- HARNESS_ARGS...` | Check the session, run the presence canary, then start the harness and return its exit code. |
| `kit doctor [--json] [--live --live-root DIR]` | Report what was tested, the runs and the sessions that were not launched. |
| `kit policy build --base FILE --pack DIR [--pack DIR ...] --out FILE [--force]` | Write a version 2 policy from a base policy and rule packs, or a version 3 policy when a checker records notes, or a version 4 policy when the base has a `[permissions]` section, with `<out>.packs.json` beside it; a refused input exits 64 and writes nothing. |
| `kit relay serve --config FILE --state-root ROOT --run-id ID`, `kit relay summary [--json]` | Serve one daily run's chat requests on 127.0.0.1 with the provider key and the run's capability read from the first line of stdin, forwarding a request only after its worst cost is reserved within the run, day and month ceilings of the daily file's `[relay]` table in `relay/ledger.ndjson` under the state root; print that ledger's totals. |

In this slice `kit run` accepts only a home rendered by `kit home render`, and
only a headless session (`claude -p`, `opencode run`): the canary ran nothing
else. `HARNESS_ARGS` must start with the driver's leading tokens and may carry
only the flags the driver names; anything else is refused. `kit run` accepts a
version 1, 2, 3 or 4 policy and loads its checkers first; see "Version 2 and
checkers", "Version 3 and `records`" and "Permissions". For a policy with a recording checker
it makes three more checks, each a refusal with exit 64 before the canary and
before any harness process: a recorded kind whose `[notes]` entry in the
harness's contract is `absent`; a home without `note_config.json` for each
recorded kind (and, on Claude Code, without the matching hook entries), which
asks for `kit home render --policy`; and a `SESSION_WORKFLOW_GOVERNED_HOME` in
`kit run`'s environment that lies under no `test_roots` entry of the policy.
A contract with no `[notes]` entry for a kind launches, with one line on
standard error.

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

### Version 3 and `records`

Policy version 3 is version 2 with one more optional key on a `[[checker]]`
table, `records`: a non-empty array of distinct kinds of note, each `prompt` or
`outcome`. A checker that has it is a recording checker. Under version 1 and
version 2 `records` is an unknown key, and a version other than 1, 2, 3 or 4
makes the policy unreadable (version 4 is under "Permissions"). The id of a recording checker names its facts file, so it
matches `[a-z0-9][a-z0-9-]{0,62}` and is not a reserved Windows device name
(`con`, `nul`, `com1` and the like); any other id makes the whole policy
unreadable.

A recording checker defines two functions beside each other. `record(note, facts)`
is called by `kit note` with a copy of the note and of the facts read so far, and
returns either `{"result": "unchanged"}` or `{"facts": OBJECT}`, the session's new
facts. `check(act, observation, facts)` takes the facts as a third argument when
the kit judges. A checker without `records` keeps `check(act, observation)`. A
recording checker without a callable `record` is refused by `kit policy build`
and by `kit run`, with exit 64, as a checker without `check` is.

## Permissions

Policy version 4 is version 3 with one more optional top-level table,
`[permissions]`, which a harness renders as its own permission rules. The judge
ignores it. The table holds `default` (required: `allow`, `ask` or `deny`), the
effect of an action no rule names, and any number of `[[permissions.rule]]`
tables, each with exactly `action` (one of `read`, `edit`, `glob`, `grep`,
`shell`, `subagent`, `skill`, `question`, `webfetch`, `websearch`,
`external_directory`), `resource` (a non-empty string in opencode's wildcard
syntax, `*` and `?`) and `effect` (`allow`, `ask` or `deny`). Any other key or
value makes the policy unreadable, and under versions 1 to 3 `permissions` is an
unknown key. The section reads as Claude Code's rules do: a deny beats an ask,
and an ask beats an allow, whatever their order. A section that asks before every
action but a `git status` in the shell holds `default = "ask"` and one rule with
`action = "shell"`, `resource = "git status*"` and `effect = "allow"`. opencode
2.2.5 matches a `shell` rule against each command its scanner extracts, and an
`edit` or `read` rule against the file's path relative to the session's folder
when the file lies inside it and against its absolute path, with forward
slashes, outside it: in the session's folder `locked/*` covers `locked/x.txt`,
and `*/locked/*` does not.

An opencode home rendered with such a policy (`kit home render --policy FILE`)
gets, in `opencode.jsonc`, `permissions` that start with `* * DEFAULT`, then the
section's allow rules, then its ask rules, then its deny rules, each in the
section's order, so that opencode's last matching rule gives deny over ask over
allow; then the rules that switch off the tools kit does not let a session use,
last, so no rule of the section lifts one. Its `policies` gain one `tool.use`
deny `ACTION:RESOURCE` per deny rule, which holds after an approval saved in the
interface. A policy without the section renders those switches alone, and
opencode's own base applies to every other action. `home.json` records
`permissions_sha256`, the SHA-256 of the rendered `permissions` and `policies` as
canonical JSON (sorted keys, no spaces). The Claude Code driver renders nothing
from the section.

The canary's two shell calls must reach kit's hook: a section under which
`echo probe > deny-0123456789abcdef.marker` or
`echo probe > allow-0123456789abcdef.marker` resolves to deny for `shell` (a deny
rule that matches it, or a default `deny` with no allow for it) is refused by the
render and by `kit run` with exit 64, naming the rule. A default `deny` with
allows for both commands renders. On an opencode home, `kit run` renders both
lists again from its policy and refuses with exit 64 a home whose
`permissions_sha256` differs (a policy changed after the render) and a home whose
`opencode.jsonc` does not parse or holds other `permissions` or `policies`, a
headless test home included; render the home again with the policy.

How the rules map:

| Claude Code | opencode 2.2.5 | the kit's section |
|---|---|---|
| `Bash(cmd *)`, `PowerShell(...)` | `shell`, matched per command the scanner extracts | `shell` |
| `Read(path)` | `read` | `read` |
| `Glob`, `Grep` | `glob` (the pattern), `grep` (the expression, not the path) | `glob`, `grep` |
| `Edit`, `Write`, `MultiEdit`, `NotebookEdit` | `edit` (edit, write and patch) | `edit` |
| `WebFetch(domain:host)` | `webfetch`, matched on the URL | `webfetch` with `https://host/*` |
| `WebSearch` | `websearch`, matched on the query | `websearch` |
| `Task(agent)` | `subagent` | `subagent` |
| `Skill(name)` | `skill` | `skill` |
| `additionalDirectories` | `external_directory` (allowed by default) | `external_directory` |
| `mcp__server__tool` | `server_tool`; servers by `mcp.use` | not offered: every MCP server is denied |
| none | `execute` (Code Mode) and any other tool that runs code or writes files besides `shell` and `edit` | not offered when a `permissions` rule rendered last switches it off; offered and refused when called when the driver's list holds it |
| deny over ask over allow, any order | ordered, last match wins | deny over ask over allow; the renderer orders |
| default mode asks, read-only tools excepted | base `* * allow` | `default`, with allow rules for read-only actions |
| `--dangerously-skip-permissions`, bypass mode | `--auto`, `--yolo`, `--dangerously-skip-permissions` | refused flags in interactive mode |
| a hook's deny holds in every mode | a `tool.use` deny holds after saved approvals | each deny also rendered as `tool.use` |
| "don't ask again" written to settings | "Allow always" saved in opencode's database (inferred), never over a configured deny | not rendered; the owner's choice in the interface |
| subagent permissions inherit the session's | a configuration's rules come after each shipped agent's own rules | the section's rules hold for every shipped agent |


## Packs and `kit policy build`

A pack is a folder with a `pack.toml` and the checker files it names. It is how
a tool hands the kit a rule. A checker in a pack calls the tool's own core and
restates none of its logic, so the rule is written once.

```toml
pack = 1
name = "series"

[[checker]]
id = "series-check"
file = "series_rule.py"
budget_ms = 250
records = ["outcome"]

[[rule]]
id = "series-second-pr-declared"
effect = "deny"
governed = false
kinds = ["shell"]
check = "series-check"
reason = "The owner's rule: name the series that governs this change in the command, or say why there is none with `KEEL_SERIES=none:<reason>`."
```

This is the series pack's `pack.toml`, with a shortened `reason`. A pack may also
carry a `prevention` table with a `rule` and a `layer`, the layer that really
prevents what the rule only steers; the uv pack declares pip's own setting, and
the doctor shows the declaration, which the kit does not check. The series pack
declares none.

`kit policy build` composes a policy from a base policy and packs: the base's
`launcher` table, the base's rules, then each pack's rules in argument order,
with every checker's `file` made absolute and its `sha256` computed from its
bytes at that moment. The result is version 2, or version 3 when any checker of
the base or of the packs has `records`, or version 4, with the base's section
after the rules, when the base has a `[permissions]` section; the base may be
version 1, 2, 3 or 4. It
writes `<out>.packs.json` beside the policy, which the doctor reads. The same
inputs give the same bytes. The uv pack, which records nothing, is built into a
version 2 policy like this:

```
kit policy build --base base-policy.toml --pack harness-kit/packs/uv --out kit-policy.toml
```

The checker files stay where they are, so moving a pack folder after the build
makes the policy unreadable; build again. The uv pack reads the
`engineering-discipline` plugin's own core from where it sits in this
repository, and its tests compare the checker's answers against that core as it
runs.

### The series and owner-acts packs

Two packs in `harness-kit/packs/` carry guards of the session-workflow plugin
that decide from an earlier event. Each one reads its core where it sits in this
repository and changes nothing under `plugins/`; a core that has moved fails
`kit policy build` and `kit run`. They are built into a version 3 policy, which
is how a home learns to register the note hooks.

- `series` has the rule `series-second-pr-declared`, from the series guard. The
  guard denies a second `gh pr create` in one repository and session unless the
  command carries `KEEL_SERIES`, a path of the series that governs the change or
  `none:<reason>`. Its checker `series-check` records `outcome` notes: when a
  finished create printed a pull-request URL, the repository and the URL are kept
  as the session's facts, and the next create in that repository is judged from
  them. The rule is guidance (`governed = false`), so a checker that cannot tell
  lets the act pass. It reads a command in the bash and in the PowerShell
  dialect and answers `match` only when both readings find an unsatisfied create,
  so every difference from the core lets an act pass that the core denies.
- `owner-acts` has the rule `owner-acts-named-by-owner`, from the owner-acts
  gate. The gate denies a write to the governed `CLAUDE.md` or settings files, a
  `claude plugin` change, a user or machine environment variable and a
  write to the global git configuration, unless one sentence of the owner's latest prompt
  names the act. Its checker `owner-acts-check` records `prompt` notes: the latest
  prompt the core's lexical rule accepts as typed by the owner, cut to what fits
  the facts file, and never one from a child or synthetic origin. The rule is
  governed (`governed = true`), so a checker that cannot tell denies: with no
  facts, an owner act is denied. The governed home is the core's:
  `SESSION_WORKFLOW_GOVERNED_HOME`, else `CLAUDE_CONFIG_DIR`, else `~/.claude`,
  read in the environment of the judge.

Each core has a switch that turns it off or to observe, `SESSION_WORKFLOW_SERIES_GUARD`
and `SESSION_WORKFLOW_OWNER_ACTS_GATE`; the packs read them in the environment of
the judge. A launched session does not receive them, so both rules are on there.
For a policy that records something, `kit run` passes one more variable into the
session, `SESSION_WORKFLOW_GOVERNED_HOME`, and only when its value lies under a
`test_roots` entry of the policy, resolved and compared up to a separator; a value
outside every test root is refused with exit 64, and a policy that records
nothing launches without it.

## Notes and facts

`kit judge` decides an act before it happens. `kit note` is the second intake,
for what already happened. A shell tells the kit that a prompt was submitted or a
shell call finished, and a recording checker keeps small facts from it for the
next judgement. A note asks for no verdict and never blocks a session.

A note is one JSON document, read as an event is: UTF-8 with an optional BOM,
no duplicate keys, no `NaN` or `Infinity`. Its keys are exactly `kit_note` (the
integer 1), `run_id`, `harness`, `session`, `origin`, `observation` and `note`.
`run_id`, `harness`, `session`, `origin` and `observation` have the event's types
and vocabularies, except that `origin` has no value meaning the owner. `note.kind`
is `prompt` or `outcome`. A prompt note holds `text` and `truncated`; an outcome
note holds the `act` of the finished call, its `status` (`completed`, `failed`,
`background` or `unknown`), its `output` (a string or null) and `truncated`. A
missing or extra key at any level, a value of the wrong type or a value outside
its vocabulary makes the note invalid. A prompt note:

```json
{"kit_note": 1, "run_id": "20261113T120000Z-0123456789ab",
 "harness": {"name": "claude-code", "version": "2.1.316"},
 "session": {"id": "1caa8e5d-eaa7-421e-9fed-3c9ae823d2cd", "parent_id": null, "root_id": null},
 "origin": "unknown",
 "observation": {"session": "observed", "parent": "unavailable", "root": "unavailable", "origin": "unavailable",
                 "command": "not_applicable", "paths": "not_applicable"},
 "note": {"kind": "prompt", "text": "Run the scripted tool call. Pode editar o CLAUDE.md.", "truncated": false}}
```

An outcome note, from an opencode child session whose root was found:

```json
{"kit_note": 1, "run_id": "20261113T120000Z-0123456789ab",
 "harness": {"name": "opencode", "version": "2.2.5"},
 "session": {"id": "ses_child", "parent_id": "ses_root", "root_id": "ses_root"},
 "origin": "child",
 "observation": {"session": "observed", "parent": "observed", "root": "observed", "origin": "observed",
                 "command": "observed", "paths": "not_applicable"},
 "note": {"kind": "outcome",
          "act": {"kind": "shell", "command": "gh pr create -R kit-probe/guard-cell -t kit-cell -b kit-cell",
                  "argv": null, "paths": [], "cwd": "C:/scratch/work",
                  "payload_sha256": "0000000000000000000000000000000000000000000000000000000000000000"},
          "status": "completed", "output": "https://github.com/kit-probe/guard-cell/pull/1\r\n", "truncated": false}}
```

The caps count Unicode code points. A shell cuts before it sends: a prompt keeps
its first 20000 code points and an output its last 65536 (a `gh pr create` prints
its URL last), and `truncated` is then true. A note longer than a cap is invalid;
`kit note` never cuts.

**The receipt.** `kit note` prints exactly one line, ASCII JSON with the keys
`kit_note_receipt` (1), `outcome`, `reason` and `recorders`, and exits 0 whenever
its arguments parse, whatever the note. The `outcome` is one of:

- `recorded`: the note reached its recorders, and `recorders` lists each one with
  its result, `facts`, `unchanged`, `failed`, `skipped`, `too-large` or
  `conflict`;
- `dropped`, with the reason `policy-unreadable`, `no-recorder` (no checker
  records this kind) or `no-root` (the session cannot be observed);
- `invalid`: the note broke the contract;
- `outside-run`: `KIT_RUN_ID` names no minted run, so nothing is read or loaded;
- `failed`: the state root was refused, or the journal line could not be written.

**Where things live.** One line per note goes to `notes.ndjson`, a file of its own
beside the event journal: `runs/<run_id>/notes.ndjson` for a note in a minted run,
`not-launched/<16 hex or no-session>/notes.ndjson` for a valid note outside one,
and `not-launched/invalid/notes.ndjson` for an invalid note outside one. The line
holds the kind, sizes and hashes, never a prompt, a command, an output or a path,
and it is a separate file so that the doctor's count of judged events is what it
was. Facts live in `runs/<run_id>/facts/<16 hex>/<checker id>.json`, one file per
recording checker and session, written only by `kit note`, at most 65536 bytes,
by compare-and-replace under `facts.lock` in the run's `facts/` folder. A
judgement reads them without any lock and writes none.

**The root rule.** Notes and judgements find a session's facts by one key: the
`session.root_id` when `observation.root` is `observed` and the id is a non-empty
string, else the `session.id` when `observation.session` is `observed` and the id
is a non-empty string. With neither there is no key and the session cannot be
observed.

**`{}` against `None`.** A recording checker's `check(act, observation, facts)`
gets `{}` when the session can be observed and nothing was recorded, and `None`
when the event is not launched, has no root key or has an unreadable facts file.
`None` means the session cannot be observed, and a checker answers `cannot-tell`
on it; `{}` means it can be observed and nothing happened yet.

Facts exist only inside a minted run, one that `kit run`, `kit state new-run` or
`kit doctor --live` made. A note can be lost (the shell's deadline of 3 seconds,
a lock not obtained, a conflict, a failed recorder), and a lost note leaves the
facts as they were. The recorders of a note share 500 ms of `record` time. The
decisions are in `docs/adr/0011-session-notes-and-facts.md`.

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
`journal.ndjson`, `notes.ndjson`, the `facts/` folder, the canary's folder) and
`not-launched/` for judgements and notes made outside `kit run`. A journal line
names the kind of act and its hash and the verdict, never the command text or a
path; a note line follows the same rule, as "Notes and facts" says.

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
section is absent and the report is as before. A version 3 policy is read as a
version 2 one. The doctor runs no checker and starts no program for this section.

### The `notes` section

When `KIT_POLICY` names a readable policy with at least one recording checker, the
report gains a `notes` section after `rules` and before the line `runs:`. Per
recording checker, in the order of the policy, it gives one line with the checker's
id, the word `records` and its kinds, and under it one line per harness and kind
with the harness name, the kind and a state:

```
notes:
  series-check records outcome
    claude-code outcome tested (evidence from the contract)
    opencode outcome unknown
```

The state is `unknown` when the harness binary is absent, its version differs from
the contract's or the contract's `[notes]` table has no entry for the kind;
otherwise it is the entry's own `tested` or `absent`, and a `tested` state carries
the contract's evidence in parentheses. With `--json` the same list is under the
key `notes`, each item holding `checker`, `records`, `states` and `evidence` per
harness and kind. With any other policy the key and the section are absent, and a
version 3 policy that records nothing gives the report of the same policy with its
version line set to 2. The doctor runs no checker and starts no program for this
section.

## Shells and contracts

The shells are in `src/harness_kit/shells/`: `claude_code/kit_hook.py` and
`opencode/index.js`. Each one only calls `kit judge` and translates the verdict
into the harness's convention; it holds no policy, and it denies when it cannot
get a verdict. They are registered in the settings or config of a home rendered
by `kit home render`, not in a harness's real installation.

Each shell also has a note mode, on when the home was rendered with a policy
that records. `note_config.json`, beside `shell_config.json`, holds the command
that runs `kit note` (`note_argv`), the deadline in seconds (`timeout_s`, 3) and
the recorded kinds (`records`). Claude Code registers its hook file with the
note argument for `UserPromptSubmit` (a prompt note) and for `PostToolUse` and
`PostToolUseFailure` (an outcome note, for the Bash and PowerShell tools). opencode
registers the `prompt` hook and `execute.after` for the shell tool, and walks from
a session up to four parents to find its root. A note mode prints nothing to its
harness, never denies or throws, and ends silently on its own deadline or any
failure.

The contracts are in `src/harness_kit/contracts/`. They are read by the doctor
and updated by hand from the conformance results in `conformance/`, which run
the real harnesses against a local stub model and print `skip:` unless
`KIT_CONFORMANCE_BASE`, `KIT_HARNESS_ARGV_CLAUDE_CODE` and
`KIT_HARNESS_ARGV_OPENCODE` are set. The rule cells, in `conformance/test_rules.py`,
build a policy from the conformance base policy and `packs/uv`, run each harness
against the stub model, and write `rules-results.json`; the `[rules]` table of a
contract is written by hand from that file. The guard cells, in
`conformance/test_guards.py`, build a policy from the conformance base policy,
`packs/series` and `packs/owner-acts`, run each harness against the stub model
with a stand-in `gh`, and write `guards-results.json`; the `[notes]` table and
the two `[rules]` entries of a contract are written by hand from that file. The
`[notes]` table has an entry per kind, `prompt` and `outcome`, with a `state`
(`tested` or `absent`), a `mark` and the evidence.

## Tests

The tests beside the code run with the repository's runner,
`python scripts/run_tests.py`, from the repository root. The decisions behind
the package are in `docs/adr/0009-harness-kit-outside-the-harness.md`,
`docs/adr/0010-tool-rules-through-the-judge.md` and
`docs/adr/0011-session-notes-and-facts.md`.
