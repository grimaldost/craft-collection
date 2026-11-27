# ADR-0012 - harness-kit: daily use on opencode

- **Status:** Accepted
- **Date:** 2026-11-18

## Context

`docs/adr/0009-harness-kit-outside-the-harness.md` put the policy judge outside
the harness, `docs/adr/0010-tool-rules-through-the-judge.md` let a tool's rule
reach it as a checker, and `docs/adr/0011-session-notes-and-facts.md` let it
know what happened earlier in a session. All three are proved on test homes
against a stub model, in headless sessions that take one prompt each, and
`kit run` accepts only a headless argument list: `run` with `--standalone` on
opencode, `-p` on Claude Code. So the kit judges only headless test sessions.
Daily work outside Claude Code is interactive, and is to run on opencode under
the kit.

Four facts about the harnesses decide the shape of the answer.

- **opencode's interactive interface runs its sessions on a server.** In
  opencode 2.2.5 the bare `opencode` command connects to one shared background
  server per account, and a server in service mode loads a saved environment of
  its own, so variables set on the client do not reach its plugins (read in the
  2.2.5 source). With `` `--standalone` `` the interface runs a private server
  instead. Measured on 2.2.5, under a pseudo console: the private server loaded
  the kit plugin, the guard's verdicts were journaled under the run that kit
  minted, every isolation variable the launcher sets reached the plugin's shell
  calls with its value, but `NO_PROXY`, which opencode extends with the IPv6
  loopback at every start, and every process of the session, the server
  included, stayed in a Job Object put around the interface.
- **A configuration write drops the guard in the running process.** On opencode
  2.2.5 a write tool's write of the home's `opencode.jsonc` without the kit
  plugin left later calls of the same session unjudged, from the call after the
  write or one call later, and a restoring write left the file's hash unchanged,
  in 3 of 3 runs (measured 2026-11-11). opencode reloads every configuration
  source live, and with both of its file-watcher variables set, every call after
  such a write was judged (measured on 2.2.5).
- **opencode offers tools that the shell does not translate.** Besides the shell,
  the edit tools and the read-only tools, 2.2.5 enables tools that run code,
  write files or move the session, among them `execute` (Code Mode),
  `opencode_worktree_create`, `opencode_session_move` and
  `opencode_worktree_remove`. The opencode shell gives each the kind `other`,
  with no command and no paths, which no rule reads, and a judgement that no
  rule matches allows. In 2.2.5 a tool is switched off by a permission rule on
  its permission name, which refuses all but one of them. That one is
  `opencode_worktree_remove`: it removes a worktree of the project, with `force`
  one holding modified or untracked files, and its permission is `edit`, which
  `edit`, `write` and `patch` share, so no statement or switch of opencode
  refuses it alone. Measured on 2.2.5, it removes a linked worktree made by
  `git worktree add` once a session of the same home has started in it. The
  opencode shell itself is full: 238 non-blank lines against the ceiling of 240,
  and it maps `patch` to a write whose paths are unavailable, so the owner-acts
  rule refuses every patch.
- **A desktop app that runs its own copy of a harness cannot be launched.** The
  Claude desktop app starts each session from its own bundled copy of Claude
  Code, of another version than the command line's 2.1.316, with its own
  arguments and settings (measured 2026-11-16). `kit run` cannot start such a
  session, and since facts exist only inside a run that kit minted, the
  owner-acts rule would deny every owner act in it.

## Decision

The kit gains daily use on opencode 2.2.5 under `kit run`, in seven parts.

- **An interactive mode, for opencode only.** `kit run --mode interactive`
  starts opencode's interface through its private server: the argument list
  carries `--standalone` exactly once and may carry `--continue` (`-c`),
  `--session` (`-s`) and `--prompt`; every other token is refused, the project
  folder positional, a subcommand, `--server`, `--auto` and the flags that skip
  permissions among them. The mode runs on Windows only. Its proof is in three
  parts: the headless canary still runs before every start, on the home bytes
  the session starts with; a cell under a pseudo console proves the guard in an
  interactive session once per harness version, and the contract records the
  mode from those cells; and the check during the run, below, holds for the
  whole session. The session's process tree joins a Job Object that ends it
  when `kit run` ends. The built-in rule `launcher.workdir` binds a session's
  tool calls to the folder `kit run` launched.
- **A daily home whose provider is a local relay holding the key.** `kit home
  render --daily FILE` renders an opencode home whose one provider is a relay:
  a child of `kit run`, written in the standard library, that listens on the
  loopback only, receives the provider key on its standard input, accepts only
  requests that carry a capability minted for the run, reserves each request's
  worst cost against a run, a day and a month ceiling in an append-only ledger
  under the kit's state root before it forwards, and refuses proxy requests.
  The session sees a loopback endpoint and never the key. A daily home carries a
  git identity (a name and an email) and no push credential or `gh` login, and
  it carries the note mode and the packs as a test home does.
- **opencode's configuration governed by built-in rules, a check during the
  run and rendered statements.** The built-in rule `config.protected` denies,
  ahead of the policy's rules, a write tool's write under the home's
  configuration, the state root, the policy file, the judge's import surface,
  the project and system configuration of opencode, and the account's own
  Claude Code home and opencode configuration folder; a judgement under a policy
  whose bytes changed after `kit run` read them is `unknown`. A check during the
  run reads the watched files and the judge's import surface every 2 s; a
  difference ends the session's process tree, records `config-changed` and
  marks the home so that it starts no session until a new one is rendered. Every
  opencode home's configuration carries statements that load no plugin but the
  kit's, no MCP server and no provider but the home's own, and switches that
  take `execute`, `opencode_worktree_create`, `opencode_session_move` and
  `experimental_image_generate` out of the session. The session's file watcher
  is switched off. `kit run` refuses a system opencode configuration folder,
  and, in interactive mode or for a daily home, a project configuration in the
  working folder.
- **Native permissions rendered from policy version 4.** A version 4 policy may
  hold a `[permissions]` section, read as Claude Code reads its rules (a deny
  beats an ask, an ask beats an allow, whatever their order). The opencode
  driver renders it into opencode's ordered permission rules, with a `tool.use`
  deny beside each deny rule so that no saved approval lifts it. The judge
  ignores the section.
- **The version pin with `--accept-version`.** `kit run` starts only the harness
  version its contract names, or the version that the person starting it names
  exactly with `--accept-version`. A re-pin runs every conformance cell at the
  new version before the contract changes.
- **The translation of opencode events in the driver.** The opencode shell sends
  the hook's event whole, in an envelope, to `kit judge --from opencode` and
  `kit note --from opencode`, and the opencode driver translates it into the
  neutral event and note of the earlier records; the driver also reads the
  paths of a `patch` call from the headers of its text. The driver holds a list
  of refused tools: a tool opencode cannot refuse alone, by any statement or
  switch. For 2.2.5 the list holds `opencode_worktree_remove`. The judge denies
  a call of a listed tool with the rule `opencode.refused-tool`, ahead of every
  policy, and a worktree is removed with git in the shell, which the kit judges.
- **Claude Code kept to headless and conformance runs.** The Claude Code driver
  offers no interactive mode, and this record wires the kit into no Claude Code
  settings of the account. Sessions of a desktop app that runs its own copy of a
  harness are outside the kit's scope: this record decides so, since `kit run`
  cannot start them and the kit cannot prove its guard in them.

Ten new invariants bind this decision, each stated by its identifier.

1. **interactive-proven.** `kit run --mode interactive` starts a harness only
   when its driver offers that mode, its contract does not record the mode
   `absent`, and the headless canary passed on the home bytes the session starts
   with.
2. **home-unchanged.** The home's watched files hash the same right before the
   session starts as at the mint; a difference refuses the start, and a
   difference during the run ends the session's process tree and records
   `config-changed`. A daily home, and any home in interactive mode, also holds
   exactly the files its render recorded; a home whose run ended
   `config-changed` starts no session until a new home is rendered; a daily home
   whose last run did not record its end starts no session, and no home starts
   an interactive session while it holds `run-open.json`.
3. **workdir-bound.** A launched act of a harness that `launcher.required`
   covers (every harness but Claude Code), whose working folder lies outside the
   run's working folder, its work tree's top and the canary's folder, is denied
   by the built-in rule `launcher.workdir`.
4. **config-protected.** A launched file write whose path lies under a protected
   path recorded in the run is denied by the built-in rule `config.protected`,
   ahead of the policy's rules; a write whose paths are unavailable is
   `unknown`; a launched event judged under a policy file whose bytes no longer
   hash to the run's recorded `policy_sha256` is `unknown`. The protected paths
   are the harness's configuration sources and the part of the judge's import
   surface that the run's `protected` list names.
5. **kit-only-plugins.** An opencode home's configuration carries statements
   that load no plugin but the kit's, no MCP server and no provider but the
   home's own, and that deny every enabled tool that runs code, writes files or
   moves the session outside the tools the driver translates, save a tool
   opencode cannot refuse alone, which the driver's refused list holds and the
   judge refuses; `kit run` refuses a system opencode layer, and in interactive
   mode or for a daily home a project layer in the working folder.
6. **key-outside-session.** No provider key enters a session's environment,
   home, working folder or any record of the kit, nor the environment of any
   child of `kit run` but the relay, which receives it on its standard input;
   `kit run` removes it from its own environment once read. The terminal that
   started `kit run` still holds it, and a process of the owner's account can
   read that terminal, `kit run` and the relay
   (loss `account-stores-reachable`).
7. **spend-reserved.** The relay forwards a request only after appending a
   reservation of its worst cost that keeps the run, day and month totals within
   their ceilings. The run's total lives in the relay's memory; the day and
   month totals hold only while the ledger is intact, since a shell command of
   the session can truncate it and so reset them at the next relay start.
8. **permissions-from-policy.** A home's native permission statements are
   rendered from the policy's `[permissions]` section only, besides the switches
   that end every opencode home's permissions; `kit run` refuses a home whose
   rendered statements differ from what its policy renders now, and a section
   that would refuse either of the canary's calls before the kit's hook sees it.
9. **pinned-or-named.** `kit run` starts only the harness version its contract
   names, or the version that the person starting it names exactly with
   `--accept-version`, which the run records.
10. **no-paid-call.** No test, cell or gate of the kit forwards a model request
    beyond the machine: the relay forwards to a non-loopback upstream only for a
    daily file whose `test` is false, such a daily file is refused while the
    state root lies under the system's temporary folder, and no file under
    `harness-kit/tests/` or `harness-kit/conformance/` holds one.

The eleventh, pending-before-record, amends ADR-0011 below.

The invariants of the earlier records are kept, some of them extended:
thin-shell (the ceiling stays 240 non-blank lines, and the opencode shell drops
to at most 210), unknown-denies, origin-never-owner, no-harness-shape (the
translation lives in the driver, under `harnesses/`), state-outside-harness,
marker-proof, no-launch-without-guard, stdlib-runtime, nothing-under-plugins,
no-private-names (extended: nothing committed carries a personal path, a
private name or a credit line for a tool that wrote it, in files, commit
messages or branch names), harmless-cells (extended: no paid call, no real
`gh`, no write to the account's opencode configuration or Claude Code home, and
no opencode service or autostart entry left behind), note-never-decides,
facts-from-notes-only (the pending stamp is written by `kit note` only),
facts-bounded, note-journal-no-text (extended to the relay's log) and
v1-v2-unchanged (extended: a version 1, 2 or 3 policy loads and its rules judge
as before; the built-in rules `launcher.workdir` and `config.protected` stand
ahead of every policy, as `launcher.required` does, and read only run records
that carry their keys; `opencode.refused-tool` stands ahead of every policy too
and reads no run record).

### Amendment to ADR-0011

ADR-0011 states two consequences that this record replaces.

- It says that a prompt note that is not recorded leaves the earlier owner
  prompt in force until the next prompt that is recorded. That is replaced by
  the eleventh invariant. **pending-before-record.** `kit note` writes a pending
  stamp for a prompt note before any recorder runs and removes it only when
  every prompt recorder answered; while a stamp stands, a judgement gives each
  checker that records prompts `None` facts. So a prompt note lost after its
  pending stamp is written leaves the owner-acts rule denying an owner act until
  a later prompt note is recorded by every recorder; only a note lost before its
  stamp is written leaves the earlier owner prompt in force.
- It says that a note mode prevents nothing and wires the kit into no daily
  session. The daily home of this record carries the note mode and its packs, so
  that part is replaced; a note mode still prevents nothing.

ADR-0010 states as a consequence that its change does not wire the kit into a
daily session. The daily home supersedes that for rules in the same way: a rule
through the judge reaches a daily session, and is still feedback inside one turn
that prevents nothing.

Both records keep their text unedited. This record is the amendment, as ADR-0010
amended ADR-0009.

## Alternatives considered

- **An interactive canary per launch.** Rejected: it needs a pseudo console at
  every start, which is slower and more fragile than a cell per harness version,
  while the headless canary still proves the home's bytes before every start.
- **A key file or the operating system's credential store for the relay.**
  Rejected: either is readable by the same account, and a key file sits on
  disk. The key goes from the environment of `kit run` to the relay's standard
  input and nowhere else.
- **Widening the owner-acts families to opencode's files.** Rejected: it needs a
  change under `plugins/`. The built-in rule `config.protected` covers those
  files instead.
- **Refusing every version change with no override.** Rejected: the re-pin cells
  could not run on a new version, so a re-pin could never be measured.
- **Wiring the kit into the account's Claude Code settings.** Rejected: the
  model can rewrite those settings, Claude Code reloads hooks live, and every
  owner act would be denied in desktop sessions, which carry no facts.

## Consequences

- The canary still runs before every start, within 60 s. An interactive session
  is proved by the cell of its harness version and by the canary on the bytes
  it starts with, not by a canary of its own.
- The check during the run reads the watched files every 2 s, so a shell write
  to opencode's configuration is found within about 2 s and the session ended
  with `config-changed`, and the calls in between may go unjudged. A write that
  restores the file's bytes and resets its times within one poll is not found,
  and neither is a session that, within one poll, removes the home's
  `run-open.json` and ends `kit run`.
- The judge's import surface (the folder that holds the kit's package, each
  folder a checker puts first on `sys.path`, the files the checkers load and the
  interpreter's startup files) is protected from the session's tools and read
  by that check, but a shell write into the interpreter's own installation or
  into a `__pycache__` folder is not seen.
- The shells' deadline stays 3 s, and the CLI reads an envelope of at most
  16 MiB.
- The opencode shell drops to at most 210 non-blank lines, since the
  translation moves to the driver.
- The relay forwards only after a reservation. One relay runs per state root,
  and the ceilings hold per state root: another state root keeps totals of its
  own. The run's total lives in the relay's memory; the day and month totals
  hold only while the ledger is intact, since a shell command of the session
  can truncate it.
- A session continued in a new run starts with no facts, so the owner-acts rule
  denies an owner act until the owner's next prompt is recorded.
- Last, the session runs as the owner's own account, so nothing here is
  prevention. Credential stores, an SSH agent, the terminal that started
  `kit run`, the memory of `kit run` and of the relay, which hold the key, and
  the kit's state root are reachable by a shell command of the session, and the
  contracts keep `prevention` `absent`.
