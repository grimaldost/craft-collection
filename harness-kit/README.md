# harness-kit

`kit` is a command line that judges what a coding-agent harness is about to do,
starts a harness only when its guard is in place, and reports what was tested.
It runs outside the harness, in standard-library Python, and has thin shells for
Claude Code 2.1.316 and opencode 2.2.5. It also takes notes of what already
happened in a session, a submitted prompt or a finished shell call, and keeps
small facts from them, so that rules that decide from an earlier event can run
through it. On opencode it also starts daily sessions, interactive ones included, in
a home whose model provider it reaches only through a local relay that holds the key.

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

Daily use on opencode lifts three of the items above: that the kit is not wired into a daily session, since a daily home now carries it; that opencode's `patch` tool is refused under the owner-acts pack, since every patch form is now read and the rule sees its paths; and that a prompt note not recorded leaves the earlier owner prompt in force, which now holds only for a note lost before its pending stamp is written. Its own limits:

- It prevents nothing a process of the session can do as the owner's account.
- It does not keep the account's own stores out of reach: a credential manager, an SSH agent, the terminal that started `kit run`, the relay's memory and the kit's state root are reachable by a shell command of the session (inferred).
- It does not stop a shell write to opencode's configuration before it happens: the check during the run finds it within about 2 seconds and ends the session, and calls made in between may go unjudged. A write that restores the file's bytes and resets its times within one 2 s poll is not found, and neither is a session that, within one poll, removes the home's `run-open.json` and ends `kit run`.
- It does not see a shell write into the interpreter's own installation, its standard library among them, or into a `__pycache__` folder the judge loads from. The check during the run reads the rest of the judge's import surface, and the write tools are denied in the part of it that `protected` lists.
- It does not bind a `cd` inside a command: `launcher.workdir` reads only the folder a tool call starts in, and a shell command can change folder after it starts.
- It does not judge a project the owner switches to in the interface when that project's file removes the kit plugin, and a tool the home switches off is offered again there when that file allows it. opencode reads each project's configuration anew.
- It does not block network connections that ignore the proxy variables: the relay refuses proxy requests, and nothing else stands between the session and the network.
- It does not carry session facts across runs: a session continued in a new run starts with none, so the owner-acts rule denies an owner act until the owner's next prompt is recorded.
- It does not run interactive sessions on Claude Code or on POSIX systems.
- It does not judge sessions of a desktop app that runs its own copy of a harness.
- It does not measure the relay against a real provider: every relay test forwards to a local stub.
- It does not keep a prompt note lost before its pending stamp: a note that never reaches `kit note` leaves the earlier owner prompt in force until the next prompt that is recorded.
- It does not guard a bare opencode start beyond the wired plugin's own judgement: a configuration layer the bare start reads may remove the plugin before it loads.
- It does not apply the wiring of the kit plugin to the owner's configuration: that is the owner's act.
- It does not run two daily sessions on one state root at once: the relay holds its ledger's lock.

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
- On opencode it starts interactive sessions and daily homes whose provider is a
  local relay that holds the key, and it keeps opencode's configuration, plugins
  and native permissions as it rendered them.

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
| `kit judge [--policy PATH] [--from NAME]` | Read one neutral event as JSON on stdin, print one verdict as one line of JSON, exit 0 whenever a verdict was printed. The policy is `--policy`, else `KIT_POLICY`. With `--from NAME`, read instead one envelope from the shell of harness `NAME`, which its driver translates (the opencode shell sends one). |
| `kit note [--policy PATH] [--from NAME]` | Read one session note as JSON on stdin, or with `--from NAME` one envelope that harness's driver translates, let the policy's recording checkers keep facts from it, and print one receipt as one line of JSON; it always exits 0 once its arguments parse. See "Notes and facts". |
| `kit state path` | Print the state root. |
| `kit state new-run --harness NAME` | Mint a run id and its folder; print them as JSON. |
| `kit stub --log FILE --script FILE [--port N]` | Serve a scripted model endpoint on 127.0.0.1 for tests; the first stdout line is `{"port": N}`. |
| `kit home render --harness NAME --dir DIR --endpoint URL [--policy FILE]`, `kit home render --harness opencode --dir DIR --daily FILE [--policy FILE]` | Render a test home for `claude-code` or `opencode`, or with `--daily` an opencode daily home whose provider is the relay (see "Daily homes and the relay"), into an absent or empty folder; print its `home.json`. With `--policy`, a policy whose checkers record notes also gets `note_config.json` and the note hooks, and an opencode home renders the policy's `[permissions]` section (see "Permissions"); an unreadable policy exits 64. |
| `kit home wire --harness opencode --config FILE --shell-dir DIR --out FILE`, `kit home wire --check --config FILE --shell-dir DIR` | Write to `--out` a copy of an opencode global configuration that loads the kit shell, materialized into `DIR`, and never write the configuration itself; with `--check`, say whether a configuration is wired. See "Wiring the kit plugin into an opencode configuration". |
| `kit run --harness NAME --home DIR --workdir DIR --policy FILE [--mode MODE] [--accept-version VERSION] -- HARNESS_ARGS...` | Check the session, run the presence canary, then start the harness and return its exit code. `MODE` is `headless`, the default, or `interactive`, opencode's own interface on Windows (see "Interactive mode"); `--accept-version` starts a harness whose version the contract does not name when it is exactly `VERSION` (see "Re-pinning a harness version"). |
| `kit doctor [--json] [--live --live-root DIR] [--home DIR]` | Report what was tested, the runs and the sessions that were not launched; with `--home DIR`, one more line: which ripgrep opencode's `grep` and `glob` would run in that home, from the absolute `PATH` entries and the home's `bin` folder (see "Reading `kit doctor`"). |
| `kit policy build --base FILE --pack DIR [--pack DIR ...] --out FILE [--force]` | Write a version 2 policy from a base policy and rule packs, or a version 3 policy when a checker records notes, or a version 4 policy when the base has a `[permissions]` section, with `<out>.packs.json` beside it; a refused input exits 64 and writes nothing. |
| `kit relay serve --config FILE --state-root ROOT --run-id ID`, `kit relay summary [--json]` | Serve one daily run's chat requests on 127.0.0.1 with the provider key and the run's capability read from the first line of stdin, forwarding a request only after its worst cost is reserved within the run, day and month ceilings of the daily file's `[relay]` table in `relay/ledger.ndjson` under the state root; print that ledger's totals. See "Daily homes and the relay". |

`kit run` accepts only a home rendered by `kit home render`. A session is
headless by default (`claude -p`, `opencode run`): `HARNESS_ARGS` must start
with the driver's leading tokens and may carry only the flags the driver names,
and anything else is refused. On Windows, `--mode interactive` starts
opencode's own interface instead, under a grammar of its own (see "Interactive
mode"). `kit run` accepts a
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

opencode asks the kit's hook before its own permission check. In the permission
cells, run on opencode 2.2.5, the kit's journal held a verdict for every call that
the native layer then refused, so a call such a rule refuses is still judged and
journaled.

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
| 1 | For `kit home wire --check`: the configuration is not wired. |
| 2 | Usage error from the argument parser. |
| 64 | A refusal: an argument, a state root, a home or a policy was refused, or a preflight check failed. Nothing was started. |
| 65 | The presence canary failed, or the home's watched files changed between the mint and the session's start. The session was not started. |
| 66 | A watched file changed during the session: kit ended the session's process tree, recorded `config-changed` and wrote `config-changed.json` beside the home's `home.json` (see "Governance of opencode's configuration"). |
| 70 | An internal error, or a relay that did not get ready. |
| 130 | An interrupt (Ctrl+C or Ctrl+Break) before the session started: during preflight no run is minted, and after it the run records `interrupted`. During the session kit ignores it. |

`kit run` otherwise returns the harness's own exit code. A denied tool call
exits 0 on every harness tested, so the exit code says nothing about a denial:
the proof is a marker on disk, and `run.json` in the run's folder is the
authority on what happened.

## State root

The state root is `KIT_STATE_ROOT` when set, else `%LOCALAPPDATA%\harness-kit`
on Windows, else `$XDG_STATE_HOME/harness-kit`, else
`~/.local/state/harness-kit`. A root inside a harness's configuration folder is
refused with exit 64. It holds `runs/<id>/` (`run.json`, `heartbeat.json`,
`journal.ndjson`, `notes.ndjson`, `home-hashes.json`, the `facts/` folder, the
canary's folder and, for a daily run, `relay-log.ndjson`), `not-launched/` for
judgements and notes made outside `kit run`, and `relay/`, the relay's ledger and
its lock. A journal line
names the kind of act and its hash and the verdict, never the command text or a
path; a note line follows the same rule, as "Notes and facts" says.

The run id reaches the harness's children through `KIT_RUN_ID`.

## Reading `kit doctor`

`kit doctor` prints one report: per harness, the version found and one state per
objective (`guard_loaded`, `refusal_in_turn`, `allow_passes`, `run_identity`,
`launcher_checks`, `hung_guard`, `heartbeat`, `prevention`), then one line for
the interactive mode, `mode interactive` with the state of the contract's
`[modes.interactive]` entry (`unknown` when the binary is absent or its version
differs, as for the objectives), the known losses, the runs (`running`, `stale`,
`ended`, `refused`, `config-changed`, `interrupted`) and the sessions that were
not launched. A run reads `config-changed` when the check during the run ended
it, `refused` when its canary failed, its home changed before the session or its
relay did not get ready, and `interrupted` when an interrupt ended it before the
session. `--json` prints it as one line of JSON, with the mode under each
harness's `modes`.

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

### The `--home` line

`kit doctor --home DIR` adds one line after the harness entries, starting
`ripgrep: `, and with `--json` the key `home`, with `dir` and `ripgrep`
(`state`, `path`, `shadowed_by`). For the home in `DIR` the line reads
`home unreadable` with the reason; `not a daily opencode home`; for a daily home
whose daily file names no ripgrep, `not named in the daily file;` then that its
`xdg/cache/opencode/bin/rg.exe` differs from its render (a hand copy, which
`kit run` refuses whatever `PATH` holds), that opencode's grep and glob fail in
this home, or which file runs, unguarded; and for one that names a ripgrep,
`named,` then whether the copy matches its render, differs from it or is absent,
then `no rg.exe earlier on PATH` or `shadowed by` the file that would run first.
The line reads absolute `PATH` entries of kit's own environment, which the
session inherits, and the home's `bin` folder only: no working folder, and no
empty or relative entry. On Windows it takes `PATHEXT` as the system holds it,
the value the session gets, and reads `the system values could not be read` when
it cannot read them. It reads files and the registry, starts no program and
exits 0. Without `--home` the report is as before.

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

The opencode shell sends each hook's event whole, in an envelope, to
`kit judge --from opencode` or `kit note --from opencode`, and the opencode driver
translates it into the neutral event or note; that is where a `patch` call's paths
are read, from every header form opencode 2.2.5 applies. A contract's
`[modes.interactive]` entry records the interactive mode: `tested` on opencode, from
`conformance/test_interactive.py`, and `absent` on Claude Code, whose driver offers
none. The other conformance files of daily use, `test_patch.py`,
`test_daily_home.py`, `test_config_governance.py`, `test_permissions.py` and
`test_wiring.py`, run on opencode only, and the contract names their cells in the
evidence of the objectives and losses they measured.

## Interactive mode

`kit run --mode interactive` starts opencode's own interface, where the owner works, instead of
one headless prompt. Only the opencode driver offers it, on Windows only: it is refused with exit
64 for Claude Code, on any other platform, and for a harness whose contract records the mode
`absent`. The opencode contract records it `tested`, from the cells of
`conformance/test_interactive.py`. The interface runs its session on a private server, which
`--standalone` asks for:

```
kit run --harness opencode --mode interactive --home HOME --workdir DIR --policy POLICY -- --standalone
```

The interactive grammar has no leading token: `--standalone` exactly once, and the flags
`--continue` (or `-c`), `--session ID` (or `-s ID`) and `--prompt TEXT`. Every other token is
refused with exit 64, naming it: a project-folder argument, a subcommand, a flag joined to its
value by `=`, and the flags that skip opencode's permissions (`--auto`, `--yolo`,
`--dangerously-skip-permissions`) among them.

The proof is the one every launch has. The presence canary runs headless on the home before
every start, whatever the mode, and the session starts only when it passed and the home's watched
files still hash as they did at the mint (`runs/<id>/home-hashes.json`); a home changed in between
is refused with exit 65. Where it was measured, the canary's median was 3.1 s over five launches.

In interactive mode the session also gets the terminal's names from kit's environment, those that
are set: `TERM`, `COLORTERM`, `TERM_PROGRAM`, `TERM_PROGRAM_VERSION`, `WT_SESSION`,
`WT_PROFILE_ID`, `LANG`, `LC_ALL`, `LC_CTYPE`, `TZ` and `NO_COLOR`; `run.json` lists the names
passed under `terminal_names`. A home started in interactive mode must hold exactly the files its
render recorded in `home.json` (`rendered_sha256`), else it is refused with exit 64 and a request
to render it again into an empty folder. Right before the session starts, kit writes
`run-open.json` beside `home.json`, and it removes the file once it has recorded the session's
end. A home that still holds one, from a run whose end kit did not record (kit was ended, or its
terminal closed), is refused until a new home is rendered, so end a session from the interface
(Ctrl+C), not by closing the terminal.

The session's tool calls start only in the folder `kit run` launched: the built-in rule
`launcher.workdir` denies an act whose folder lies outside the run's `--workdir`, its work tree's
top and the canary's folder, with a reason that says to start another `kit run` for another
folder. opencode's location follows a project switch made in the interface (Ctrl+O), so a call in
the folder switched to is denied. The session runs in a Job Object that ends every process of it
with kit. A Ctrl+C or Ctrl+Break before the session starts exits 130; during the session kit
ignores it and the interface keeps the terminal.

## Daily homes and the relay

A daily home is an opencode home for work outside the test homes: its model provider is a relay
that `kit run` starts for the run on 127.0.0.1, and only the relay holds the provider key. It is
rendered from a daily file, TOML with exactly `daily = 1`, a `[relay]` table and a `[git]` table
with `name` and `email`:

```text
daily = 1

[relay]
listen_port = 47801
upstream_base = "https://api.example.com"
route = "/v1/chat/completions"
key_env = "PROVIDER_API_KEY"
test = false
usage_include = true
default_model = "vendor/model-a"
upstream_timeout_s = 600

[relay.ceilings]
run_usd = 3.0
day_usd = 10.0
month_usd = 30.0

[[relay.model]]
id = "vendor/model-a"
input_usd_per_mtok = 3.0
output_usd_per_mtok = 15.0
max_output_tokens = 16000

[git]
name = "Your Name"
email = "you@example.com"

[tools]
ripgrep = "C:/Users/me/tools/rg.exe"
ripgrep_sha256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
```

The numbers are an example only, and so are the names, the path and the hash. An optional
`[relay.provider]` table is forwarded as the request's `provider` object (`order`,
`allow_fallbacks`, `data_collection`). `listen_port` is bound on 127.0.0.1 only. `upstream_base` is
an `https` URL; with `test = true` it can only be `http://127.0.0.1:PORT`, and a daily file whose
`test` is false is refused while the state root lies under the system's temporary folder, where
every test keeps its own. `key_env` names the variable of kit's own environment that holds the key,
never the key itself: set it in the terminal that runs `kit run`, for that terminal only, typed at a
masked prompt rather than on a command line.

`kit home render --harness opencode --dir DIR --daily FILE [--policy FILE]` renders the home: one
provider, `relay`, at `http://127.0.0.1:LISTEN_PORT/v1` with one model per `[[relay.model]]`,
`model` and `small_model` set to the default model, the kit plugin, and a `gitconfig` with the
identity and an empty `credential.helper`. A session gets that identity and no push credential.
Each model whose id starts with `anthropic/` carries `compatibility.cacheFormat` `"anthropic"`,
so opencode marks the prompt for the provider's cache, with its default 5-minute lifetime; every
other model carries its name only. A daily home rendered by an earlier kit keeps working without
those marks until it is rendered again into an empty folder, and the relay settles its requests
by the rule below at once.

opencode's `grep` and `glob` tools run a ripgrep binary. opencode looks for `rg.exe` (`rg` off
Windows) as the `which` package finds a program: on Windows in the working folder first, then in
each `PATH` folder, then in the home's `xdg/cache/opencode/bin`; with none, it downloads ripgrep
from github.com, a proxy request the relay refuses, so both tools fail. The daily file's optional
`tools` table names one existing binary by its absolute path, `ripgrep`, and its SHA-256,
`ripgrep_sha256`, both or neither, the hash in lowercase hex (PowerShell's `Get-FileHash` prints
uppercase hex, so lowercase its output before writing it). The file is refused at load for one key
without the other, a relative path, or a hash that is not 64 lowercase hex characters. The render
refuses a missing file, or one of another hash, before it writes anything; otherwise it copies the
file's bytes to the home's `xdg/cache/opencode/bin/rg.exe` (`rg` off Windows). `kit run` refuses a
copy that no longer matches the daily file, and an `rg.exe` that resolves earlier on the session's
`PATH` or, on Windows, in the working folder, found as opencode finds it. The copy is watched in
every opencode home, like the home's configuration, and protected only in a home that names one; a
hand-copied `rg.exe` is refused as a difference from the render in a daily home, and in any home in
interactive mode, so a home rendered before gets the copy only from a new render into an empty
folder. The gap: in a daily home that names no ripgrep, a program where opencode looks for `rg` runs
unjudged inside a judged `grep` or `glob` call, in four places: on Windows the working folder (a
repository's own `rg.exe` included, which needs no act of the session; off Windows the working
folder is searched only through an empty or relative `PATH` entry), a `PATH` folder, the home's
`bin` folder under a `PATHEXT` variant such as `rg.exe.CMD`, and the home's `bin/rg.exe` itself
until the next poll of the check during the run, where it is watched and not protected. Earlier kits
leave the same gap. A session places such a program only by a write or a shell command, each judged
by the kit. The relay's proxy refusal and the proxy variables are unchanged, and nothing downloads a
binary. Installing ripgrep, or reusing one already on the machine, is the owner's choice. A ripgrep
installed the usual way (winget, scoop or choco put `rg.exe` on `PATH`) makes every run of a home
that names a ripgrep refuse while it is on the `PATH` that `kit run` starts from, so the owner then
names none, or starts `kit run` without it on `PATH`.

`kit run` on a daily home, in either mode, reads the key from the `key_env` variable before any
child starts, keeps it only for the relay and removes it from its own environment, so no other
child gets it. It mints a capability for the run, which the session carries as
`KIT_RELAY_CAPABILITY`; the relay serves only requests that bear it, and the canary gets another.
Preflight refuses with exit 64 a daily file that is absent or changed since the render (naming
each key whose value differs), an invalid `[relay]`, an absent or empty key variable, a listen
port already bound, a relay lock already held, and a day or month total already at its ceiling.
The canary runs against its own stub, never the relay. Then the relay starts (`kit relay serve`,
with the key and the capability on its first line of standard input) and must print its ready
line within 10 seconds, else the run records `refused-relay` and exits 70. However the session
ends, the relay is stopped after it, and `run.json` records its `requests`, `refused`,
`settled_usd` and `stopped`.

The relay forwards only a `POST` to `/v1/chat/completions` that bears the capability. It refuses
a proxy request, a request whose line, headers or body carry the key (and every request after
that one), the request fields that would let the upstream pick other models or tools, and a model
the daily file does not price; it caps the output at the model's `max_output_tokens`. It forwards
a request only after appending to `relay/ledger.ndjson`, under the state root, a reservation of
the request's worst cost that keeps the run's, the UTC day's and the UTC month's totals within
`[relay.ceilings]`, and it settles each request from the reported cost or usage. A
bring-your-own-key answer (`usage.is_byok` true) settles at the upstream cost the provider
reports, `cost_details.upstream_inference_cost` or else its prompt and completion parts, plus
`usage.cost` as the fee, with no floor and no cap at the reservation; any other answer settles at
the larger of `usage.cost` and its tokens priced at the daily file's prices, else at the
reservation. The ceilings hold per state root: one relay runs per state root, holding the
ledger's lock, and another state root keeps totals of its own. The run's total lives in the
relay's memory; the day and month totals hold only while the ledger is intact.
`runs/<id>/relay-log.ndjson` holds one line per request, with its sizes, tokens and amounts, and
never a body, a header value or the key.
`kit relay summary` prints the ledger's totals (with `--json`: `run`, `day`, `month`, `all`,
`open` and `stops`) and starts nothing.

## Governance of opencode's configuration

A session does not change what governs it. Every opencode home's `opencode.jsonc` carries
rendered statements: `plugin.use` loads no plugin but the kit's, `mcp.use` denies every MCP
server, and `provider.use` and the `integration.*` statements allow the home's own provider only.
The tools that run code or move the session, outside what the kit translates, are switched off by
a `tool.use` deny and a `permissions` rule rendered last, so they are not offered: `execute` (Code
Mode), `opencode_worktree_create`, `opencode_session_move` and `experimental_image_generate`.
`opencode_worktree_remove`, which no statement or switch refuses alone, is refused by the kit:
it is on the opencode driver's list of refused tools, so the judge denies it with rule
`opencode.refused-tool`, and the reason says to remove a worktree with git in the shell, which
the kit judges.

A write tool's write to a protected path is denied by the built-in rule `config.protected`, ahead
of the policy's rules. The protected paths are the home's configuration and shell folders,
`home.json` and `run-open.json`, a daily home's `gitconfig` and daily file, the state root, the
policy file, the judge's import surface (the folder of the kit's package, each folder a checker
puts on the path, the files they load and the interpreter's own trees), the project-config names
in the working folder and in the folders of the project walk, opencode's system configuration
folder, and the account's Claude Code home and opencode configuration folder. `run.json` records
them under `protected`, with `protected_except` (the run's `tmp` folder) and `policy_sha256`; a
judgement under a policy file that no longer has that hash is `unknown`.

A shell write cannot be denied by its path, so a thread of `kit run` reads every 2 seconds, from
the session's start to its end and once more after it, the names, sizes and modification times
of those files. A difference ends the session's process tree, records `config-changed` with the
changed names, writes `config-changed.json` beside `home.json` and exits 66. Each changed path
outside the home and the run's folder carries into a new home and is named on exit; `kit run`
refuses a home that holds `config-changed.json`, and a new home is rendered once those paths are
read or restored. The interface's own settings file is watched too, so a setting changed in the
interface during a governed session writes `conf/cli.json` and ends the session with
`config-changed`: change settings before or after a session, not during one.

Every opencode session runs with the file watcher off (`OPENCODE_DISABLE_FILEWATCHER` and
`OPENCODE_FILEWATCHER_DISABLE` set to `1`). With it off, a rewrite of the configuration that
drops the kit plugin does not take effect in the running process: in the cell that measured it,
the calls after the rewrite were judged. Other live edits wait too: with the file watcher off, an
edit of the home's global `AGENTS.md` reached neither of the next two requests of the running
session, while with it on the second request carried the edit.

A project configuration (`opencode.json`, `opencode.jsonc` or `.opencode`) in an ancestor of the
working folder is refused, and one in the working folder is refused too in interactive mode and
for a daily home (exit 64); a headless test home records it. opencode's system configuration
folder (`opencode` under `PROGRAMDATA` on Windows, `/etc/opencode` on Linux) is refused in every
mode. A `.agents` root feeds opencode's skills only; one in the working folder is protected from
the write tools.

## Re-pinning a harness version

Each contract names the harness version its cells measured, `[harness] version`,
and that is the version the driver pins: `kit run` reads the version the binary
reports and refuses another one, or none, with exit 64 and no run, naming both
versions and the two ways on. One is a re-pin, below. The other is
`kit run --accept-version VERSION`, which starts the harness only when VERSION is
exactly the version found; the run then records `accepted_version` in
`run.json`, and one line on standard error says that it is not covered by the
contract. `kit doctor` keeps reading `unknown` for a harness whose version
differs from its contract's. Auto-update is off in every home (`update`
`disable` and `OPENCODE_DISABLE_AUTOUPDATE` on opencode, `DISABLE_AUTOUPDATER` on
Claude Code), so a version changes only when someone installs another.

A re-pin moves a contract to a new version once the cells have run on it:

1. Install the new version beside the pinned one, and name it in the harness's
   `KIT_HARNESS_ARGV_*` variable.
2. Run every conformance file in `conformance/` against it, each with a base of
   its own, with `KIT_CONFORMANCE_ACCEPT_VERSION` set to the new version. Every
   cell that a file starts with `kit run` then passes `--accept-version` with
   that value; a cell started without `kit run` needs nothing. Every row records
   in `harness_version` the version that the driver reads for the binary the
   cell ran.
3. Edit a copy of the contract to the new version, and run
   `conformance/repin_check.py` with the harness's name, the folder that holds
   the bases and that copy. It reads every `*-results.json` under the folder and
   exits 0 only when every cell that each conformance file declares for the
   harness in `CELLS_BY_HARNESS` has a row, every row passed or failed with
   `accepted_failure` `loopback-fetch-refused` (opencode refusing a loopback
   fetch by itself in the webfetch control cell, the one failure accepted by
   name), and every row holds the copy's version. Otherwise it prints one line
   per missing cell, failed cell or version, and exits 1.
4. On a clean check, change in one pull request the contract's version and the
   evidence the cells measured. A failed cell keeps its objective or loss as the
   cell showed it, written by hand in that pull request.

A version that offers a tool the list in `conformance/test_config_governance.py`
does not hold fails the cell `offered-tools`. The re-pin pull request decides
each new tool: it switches the tool off in every opencode home's rendered
statements, adds it to the driver's list of refused tools, or records it as a
loss in the contract, and it updates the list.

## Wiring the kit plugin into an opencode configuration

A session started with `kit run` gets the kit shell from its home. An opencode started
without `kit run` (a bare start) loads only what its own global configuration lists.
`kit home wire` prepares that configuration; it does not apply it, since replacing the
account's configuration file is the owner's act:

```
kit home wire --harness opencode --config FILE --shell-dir DIR --out FILE
```

It reads the configuration (JSON or JSONC), materializes the opencode shell into `DIR`, an
absent or empty folder (`index.js` and a `shell_config.json` whose `cli_argv` ends in
`judge --from opencode`, the files `kit home render` writes, with no note mode), and writes
to `--out` the configuration's text with two edits and every other byte kept, comments
included: `DIR` (absolute, with forward slashes) added to `plugins`, and
`"update": "disable"` when `update` is absent. An absent key is inserted as the first key
after the opening brace; an existing `plugins` array gets the entry appended when it lies on
one line. A configuration that holds no `plugins` and no `update` comes out as:

```jsonc
{
  "plugins": ["C:/Users/me/kit-shell"],
  "update": "disable",
  // the rest of the file, byte for byte
  "model": "provider/model"
}
```

Refused with exit 64: a `plugins` array spread over lines, a nested form (an element that is
not a string, a value that is not an array, `plugins` named twice or inside another value),
a text that does not parse, an `--out` that names the configuration, and a non-empty `DIR`.
A refusal over the configuration's form still materializes the shell and names the entry to
add to `plugins` by hand. The command never writes the file `--config` names; the scanner
that reads JSONC blanks comments and trailing commas outside strings and keeps every offset.

`kit home wire --check --config FILE --shell-dir DIR` prints one line:
`wired: CONFIG lists SHELL_DIR`, exit 0, when the configuration's `plugins` lists `DIR` (and
no later `-harness-kit` entry removes it) and the files in `DIR` are the ones this kit
renders; `not wired: REASON`, exit 1, otherwise; and it exits 64 for a configuration that
cannot be read or does not parse.

A bare start of a wired opencode has no run, so its first tool call is denied: by
`launcher.required` when `KIT_POLICY` names a policy, and as `unknown` when no policy is set,
as in a terminal that does not set `KIT_POLICY`. A project file in the
working folder can still remove the plugin: with `"plugins": ["-harness-kit"]` in its
`opencode.jsonc`, the call runs unjudged. `conformance/test_wiring.py` runs the three bare
starts on a wired copy of a test configuration and writes `wiring-results.json`.

## Tests

The tests beside the code run with the repository's runner,
`python scripts/run_tests.py`, from the repository root. The decisions behind
the package are in `docs/adr/0009-harness-kit-outside-the-harness.md`,
`docs/adr/0010-tool-rules-through-the-judge.md`,
`docs/adr/0011-session-notes-and-facts.md` and
`docs/adr/0012-kit-daily-use-on-opencode.md`.
