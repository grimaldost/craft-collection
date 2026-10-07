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
- **consolidate-knowledge** (`/consolidate-knowledge`) — the downstream pass that
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
  output, synthesis over averaging, a stakes-scaled ladder. Needs fresh-context
  reviewer spawning (sequential clean contexts as the fallback); shows the
  plan + cost and asks before firing.
- **evaluate-skill** (`/evaluate-skill`) — behaviorally evaluate a skill by running
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
- **feedback-triage** (`/feedback-triage`) — the downstream pass: cluster a
  tool's accumulated feedback reports by underlying cause, reconcile what
  already shipped, assign dispositions (ATTACK / ROUTE OUT / DECLINE), apply a
  promotion gate (reinforced · specific · actionable), and emit a
  leverage-ordered, status-tracked backlog doc. Defers to a tool-registered
  triage template (e.g. keel's reflection-triage) when one exists.
- **compaction-survival** — maintain a persisted, re-readable control anchor
  (mission, plan pointer, live cursor, invariants, exact resume steps) so a
  long autonomous run survives context compaction without losing the plot —
  updated after each step, re-read at the start of each turn.
- **corpus-review** — audit a large file corpus (dozens to hundreds of files)
  by fanning out blind reviewers over partitions, adversarially verifying
  high-severity findings, fixing in disjoint partitions, and re-auditing with
  fresh eyes until findings converge.

## Command

- **/anchor** (`close` | `close --stale`) — snapshot the run's control anchor to
  `.claude/anchors/` right now; a one-off backstop before a manual `/compact`,
  usable whether or not the `compaction-survival` protocol is armed.

## Output style

- **step-digest** — lean narration while working, then a fixed-field digest at
  the end of each substantive turn. Off by default; select it under `/config` or
  set `"outputStyle": "session-workflow:step-digest"`.

## Hooks

The rule across this collection: **a hook ships on with a documented opt-out, or
it does not ship.** A hook whose gate nobody sets has never run, which is worse
than an honest line of prose — it looks like enforcement in the manifest and is
absent in the session. Opt-outs go in the `env` block of your settings file
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
  tie), and names both when they differ. When it
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
  write-time half of the SessionStart behaviour above. It costs one Python start per
  Write, Edit or MultiEdit, with the path filter first. **On by default**; opt out with
  `SESSION_WORKFLOW_ANCHOR_HOOKS=0` (the same switch as the SessionStart hook).
- **Stop** — feedback-debt nudge: once per session, when the transcript shows
  plugin tools were exercised, no tool-feedback invocation is on record, and
  the session has at least `SESSION_WORKFLOW_NUDGE_MIN_TURNS` (default 8) real
  user turns, a Stop block asks the model to apply the tool-feedback skill (or
  finish if nothing is worth recording). **On by default**; opt out with
  `SESSION_WORKFLOW_FEEDBACK_NUDGE=0`.
  What makes default-on safe is the binding check: it stays silent unless a
  feedback-targets file resolves (`$FEEDBACK_TARGETS_FILE`, else
  `~/.claude/feedback-targets.toml`), so an install with no registered tools
  never sees it.
  There is no skill-exercise ledger hook. It wrote one JSONL entry per `Skill` or
  plugin-MCP call so this nudge had something to read; the transcript already
  carried that, so the nudge reads it directly and the second write path is
  gone.
