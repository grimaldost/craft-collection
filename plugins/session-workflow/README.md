# session-workflow

Manage the work *around* the work: capture session knowledge and distill it into
durable guidance, hand work off to a fresh context, convene fresh-eyes review
panels, behaviorally evaluate your skills, stay aware of your toolkit, sign
agent-assisted work with machine-generated provenance trailers, and run the
tool-dogfooding feedback loop (capture + triage).

## Skills

- **journaling-sessions** — capture a work or reference-reading session into
  structured, separable, retrieval-ready entries for a long-term memory store.
  Runs an automatic internal multi-pass (capture → coverage self-check → fill
  gaps), so a single invocation produces thorough output — no need to ask for
  "multiple passes." Generic core + on-demand references (output format,
  reference-ingestion taxonomy, coverage check, writing-for-retrieval).
- **consolidate-knowledge** (`/consolidate-knowledge`, manual-only) — the downstream pass that
  distills many `journaling-sessions` entries across sessions into durable,
  higher-level guidance: cluster related entries → synthesize one generalization
  each → a strict promotion gate (reinforced · specific · non-reconstructable ·
  actionable) → reconcile supersession. Under-promotes by design.
- **context-handoff** — author a paste-ready, self-contained brief for a fresh
  context: a new Claude Code session, a spawned task, a teammate, or an issue.
  Auto-triggers on phrasing like "spin this off", "hand this off", or "new session
  for this". SUBTASK mode (an artifact comes back) and FORK mode (continues
  independently). For in-session parallel work, prefer the Task tool / subagents.
- **review-panel** (`/review-panel`) — convene fresh reviewer subagents that are
  blind to the conversation and to each other, pointed at an artifact you've
  anchored on from adversarial angles. Neutral brief, structured comparable
  output, synthesis over averaging, a stakes-scaled ladder that starts at one
  reviewer. Needs fresh-context reviewer spawning (sequential clean contexts as
  the fallback); shows the plan + cost and asks before firing.
- **evaluate-skill** (`/evaluate-skill`, manual-only) — behaviorally evaluate a skill by running
  it headless many times: triggering (recall / specificity), correct-usage (rubric
  judge), and a with/without baseline, each with Wilson 95% CIs. Ships the eval
  engine in `scripts/`. Spawn backend: headless Claude Code today; cost-gated.
- **toolkit-awareness** — `scripts/scan_toolkit.py` produces a live inventory of
  installed skills / commands / agents / hooks (no hand-maintained list); the
  skill adds durable guidance on referencing the toolkit in prompts and specs.
- **llm-signature** — sign agent-assisted work with a machine-generated
  provenance signature: an `Assisted-By` git trailer naming the exact model that
  wrote and orchestrated the change (its only appearance — never a commit
  co-author), and an `Agent-Stack` trailer naming the harness and enabled plugin
  versions, each with its marketplace as a lookup key. Rendered by
  `scripts/render_signature.py` from live sources (session transcript,
  `claude plugin list`, `claude --version`) — never typed from memory; `--apply`
  doubles as a `prepare-commit-msg` hook that also scrubs
  `Co-Authored-By: Claude` / "Generated with Claude Code" boilerplate. Trailer
  grammar in `references/spec.md` (`llm-signature/v1`).
- **tool-feedback** — write a per-session dogfooding feedback report for each
  registered in-development tool the session exercised, into that tool's own
  feedback directory: what worked, severity-tagged friction, misses with the
  phase that should have caught them, vacuous gates, and proposals with stable
  finding IDs (`<file-stem>#<n>`). Targets come from a user-supplied
  `feedback-targets` table — the skill never hunts the filesystem. Offer-first
  when self-activated.
- **feedback-triage** (`/feedback-triage`, manual-only) — the downstream pass: cluster a
  tool's accumulated feedback reports by underlying cause, reconcile what
  already shipped, assign dispositions (ATTACK / ROUTE OUT / DECLINE), apply a
  promotion gate (reinforced · specific · actionable), and emit a
  leverage-ordered, status-tracked backlog doc. Defers to a tool-registered
  triage template (e.g. keel's reflection-triage) when one exists.
- **compaction-survival** — maintain a persisted, re-readable control anchor
  (mission, plan pointer, live cursor, invariants, exact resume steps) so a
  long autonomous run survives context compaction without losing the plot —
  updated after each step, re-read at the start of each turn.

## Command

- **/anchor** (`close` | `close --stale`; manual-only) — snapshot the run's control anchor to
  `.claude/anchors/` right now; a one-off backstop before a manual `/compact`,
  usable whether or not the `compaction-survival` protocol is armed.

Entries marked manual-only set `disable-model-invocation: true`: the owner runs
them as slash commands, and the model does not invoke them on its own.

## Output style

- **step-digest** — lean narration while working, then a final block the reader
  can act on alone: outcome, every decision the reader owes with its options and
  a recommendation, next step, one question last. Off by default; select it
  under `/config` or set `"outputStyle": "session-workflow:step-digest"` in your
  user or project settings.

## Hooks

The rule across this collection: **a hook ships on with a documented opt-out, or
in observe mode, or it does not ship.** A hook whose gate nobody sets has never
run, which is worse than an honest line of prose — it looks like enforcement in
the manifest and is absent in the session. Observe mode is for a heuristic
trigger: by default it records what it would have done and prints nothing (the
pending-asks gate below). Opt-outs, and `=on` for an observe-mode hook, go in the `env` block of your settings file
(`~/.claude/settings.json` for every project, `<repo>/.claude/settings.json` for
one):

```json
{ "env": { "SESSION_WORKFLOW_ANCHOR_HOOKS": "0" } }
```

There is no toolkit-inventory SessionStart inject. It was retired in 0.21.0: the
harness already places skill names and descriptions in the system prompt in
progressive-disclosure shape, and dropping the inject removed the fingerprint
cache layer that existed only to make it affordable. The serving-snapshot diff it
carried survives as the on-demand `scan_toolkit.py --check-serving <transcript>`.

- **SessionStart (compact/resume/clear/startup)** — re-inject the newest open
  control anchor's HEAD (`.claude/anchors/*.md`; content above the
  `<!-- anchor:tail -->` marker, whole file when marker-less) so a run survives
  compaction and process restarts; warns and names the others when several
  anchors are open in one directory. On `compact`, `resume` and `clear` it looks
  in both the directory the session started in (the first `cwd` in its
  transcript) and the current one, uses the better-ranked anchor (a live track
  beats a stale, parked, finished or non-anchor file; the start directory wins a
  tie), and names both when they differ. Among live anchors, one the starting
  session last wrote (`.claude/anchors/.owners.json`, kept by the PostToolUse arm
  below) ranks first even when another is newer; a session that wrote none of them
  gets the usual injection plus one line naming the session that did. When it
  finds open anchors it creates `.claude/anchors/.gitignore` (content `*`) if that
  file is missing, so the anchors and the hook's log never show as untracked; an
  existing `.gitignore` is never touched.
  Lifecycle gates: an anchor untouched for
  >24h degrades to a one-paragraph pointer (path + title + age +
  confirm-to-expand + close command) instead of the full body; `startup`
  (fresh process — the crash-restart path) injects only when the anchor was
  updated in the last 6h, so ordinary new sessions in a cwd with an old anchor
  pay nothing. **On by default**; opt out with
  `SESSION_WORKFLOW_ANCHOR_HOOKS=0`.
  Enabling it in a session whose plugin snapshot predates the hook (or in a
  harness without the plugin surface):
  `skills/compaction-survival/references/cold-start.md` has the manual recipe.
- **SessionStart (resume/compact)** — stale skill-body check: a skill body stays
  in context after the plugin that served it is updated, so a resumed or
  compacted session can keep working from a release-old copy without knowing
  it. The hook reads the transcript's skill loads (the `Base directory for this
  skill:` line in front of each served body, the last load per skill winning)
  and compares each body served from a plugin cache directory with the versions
  `installed_plugins.json` beside that cache lists. For each plugin with an
  older body it adds one line naming both versions and the fix: invoke the
  skill again to load the current body, or restart and resume from the anchor.
  Silent when every body is current, for a body served from outside a cache (a
  `--plugin-dir` checkout), for a plugin the registry does not list, and when
  the transcript or the registry cannot be read. **On by default**; opt out
  with `SESSION_WORKFLOW_STALE_BODY_CHECK=0`.
- **PostToolUse (Write/Edit/MultiEdit)** — anchor size warning: after a write to an
  open anchor (`.claude/anchors/*.md`, not `*.closed.md`) whose HEAD is over the
  8000-character injection budget or within 10% of it (7,200 characters and up), adds
  the head-fit lines (characters, budget, `OVER by X` or `headroom Y`, the sections
  that would drop) and the Cursor's oldest entries as candidates to fold below
  `<!-- anchor:tail -->`, so the overrun is seen at the write rather than at the next
  injection. It is silent for every other path and for a HEAD with room, and it
  creates `.claude/anchors/.gitignore` (content `*`) when that file is missing, the
  write-time half of the SessionStart behaviour above. Every write to an open anchor
  also records the writing session as its owner in `.claude/anchors/.owners.json`,
  replaced atomically; `--step` leaves the record alone, and an entry whose anchor was
  renamed to `*.closed.md` is dropped. It costs one Python start per
  Write, Edit or MultiEdit, with the path filter first. **On by default**; opt out with
  `SESSION_WORKFLOW_ANCHOR_HOOKS=0` (the same switch as the SessionStart hook).
- **UserPromptSubmit** — feedback-debt nudge: once per session, when the
  transcript shows registered plugin tools were exercised, no tool-feedback
  invocation is on record, and it holds at least
  `SESSION_WORKFLOW_NUDGE_MIN_TURNS` (default 8) owner turns, the next
  owner-typed prompt carries one line of additional context asking the model to
  apply the tool-feedback skill at a natural stopping point (or carry on if
  nothing is worth recording). It never blocks: it used to be a Stop block, which
  forced one more turn out of every session that owed a report. A hand-back,
  task notification or peer message gets nothing and does not use up the
  session's one nudge (`hooks/prompt_kind.py` is the rule), and skill bodies and
  compaction summaries are not owner turns. The cheap exits come before the
  transcript is opened, and the read resumes from where the previous prompt
  stopped. **On by default**; opt out with `SESSION_WORKFLOW_FEEDBACK_NUDGE=0`.
  What makes default-on safe is the binding check: it stays silent unless a
  feedback-targets file resolves (`$FEEDBACK_TARGETS_FILE`, else
  `~/.claude/feedback-targets.toml`), so an install with no registered tools
  never sees it.
  There is no skill-exercise ledger hook. It wrote one JSONL entry per `Skill` or
  plugin-MCP call so this nudge had something to read; the transcript already
  carried that, so the nudge reads it directly and the second write path is
  gone.
- **UserPromptSubmit / Stop** — pending-asks gate: the asks a turn raised reach its
  final block. At every stop the hook reads `last_assistant_message` (never the
  transcript, which may lag) and records the sentences that ask the operator for a
  decision, approval, answer or action in a per-session ledger under
  `CLAUDE_PLUGIN_DATA/final-block-gate/`. An owner-typed prompt empties it; a task
  notification, a subagent hand-back or a peer message does not, because it wakes the
  session inside the same turn (`hooks/prompt_kind.py` is the rule). At a stop with
  nothing in flight (`background_tasks` empty or absent) whose message does not restate
  an earlier ask of the same turn, it records the dropped asks, once per ask, as an
  `observed` event; with `SESSION_WORKFLOW_FINAL_BLOCK_GATE=on` it also returns them as
  `additionalContext` (UTF-8, whatever the console codepage), so the model restates
  each with its options and a recommendation or says it is resolved, and an ask counts
  as advised only once that advice was written; it never blocks. Measured cause
  (2026-10-25, 499 turns): 36% of the asks first raised before the final block were
  absent from it. **Observe by default** (it records and prints nothing): the ask
  detector is a heuristic, and a heuristic trigger ships in observe mode.
  `SESSION_WORKFLOW_FINAL_BLOCK_GATE=on` turns the advice on and
  `SESSION_WORKFLOW_FINAL_BLOCK_GATE=0` turns the hook off;
  `python hooks/final_block_gate.py --health` prints the counts. There is no hook on
  the desktop next-step box (`mcp__ccd_turn__wrap_up`): the collection hooks none of
  the desktop app's own tools, and the final block's Decisions field carries every
  ask in text, so a question shown only in the box does not count as carried.
- **PostToolUse / PreToolUse (Bash/PowerShell)** — series guard: the owner's rule that a
  series of two or more PR-sized changes goes through keel's Definition of Ready and runs
  with convoy's gate as the judge of each change, enforced at the moment a session turns
  into a series, its second pull request in one repository. `gh pr create` is matched at
  program position (heredoc bodies, comments and quoted arguments are data). The
  PostToolUse arm records, per session, the repository of each PR whose
  `github.com/<owner>/<repo>/pull/<n>` URL is on the command's stdout; a failed or
  backgrounded command is not recorded. The PreToolUse arm keys each create by lowercase
  `owner/repo`, from `-R`/`--repo`, else from the `origin` URL in the git config of the
  command's working directory (the payload's `cwd`, or the directory of an opening `cd` or
  `Set-Location`, also inside a `bash -c` or `powershell`/`pwsh -Command` wrapper), and
  denies a create in a repository that already holds a recorded PR of the session unless
  the command carries `KEEL_SERIES=<path>` naming an existing series file or spec, or
  `KEEL_SERIES=none:<reason>`: in Bash as a prefix (`KEEL_SERIES=v gh pr create ...`), in
  PowerShell as `$env:KEEL_SERIES='v'; gh pr create ...`. Each decision appends one line,
  without the command text, to `series-guard/log.ndjson` in `CLAUDE_PLUGIN_DATA`. A
  subagent counts with its parent session; a separate `claude -p` process counts on its
  own. **On by default**; opt out with `SESSION_WORKFLOW_SERIES_GUARD=0`;
  `SESSION_WORKFLOW_SERIES_GUARD=observe` logs the would-be deny and prints nothing.
- **SessionStart / UserPromptSubmit** — governance-change notice: a running session
  hears once that the owner's global `CLAUDE.md` changed. A session reads that file at
  its start, and the supervising session edits it while others keep running, many of
  them woken only by task notifications and hand-backs. At SessionStart, only when
  the session has no baseline yet, the hook records the file's SHA-256 and
  modification time (the governed home: `$SESSION_WORKFLOW_GOVERNED_HOME`, else
  `$CLAUDE_CONFIG_DIR`, else `~/.claude`, resolved by `hooks/governed_home.py`), so a
  compact or resume cannot absorb a change silently. On every prompt, owner-typed or
  synthetic, it hashes the file again and, when the hash changed, adds one line of
  `additionalContext` naming the file, the time it changed and the instruction to
  re-read it before the next act; the new hash is recorded once that line was
  written, so each change is announced once. A created or removed file counts; a
  touch that leaves the content alone does not. Baselines live under
  `CLAUDE_PLUGIN_DATA/governance-notice/`. **On by default** (an exact trigger: a
  resolved path and its hash); opt out with `SESSION_WORKFLOW_GOVERNANCE_NOTICE=0`.
