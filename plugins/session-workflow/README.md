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

## Hooks (optional, off by default)

- **SessionStart** — inject the live toolkit inventory each session. Ships wired
  but inert; enable with `TOOLKIT_AWARENESS_INJECT=1`.
- **SessionStart (compact/resume/clear/startup)** — re-inject the newest open
  control anchor's HEAD (`.claude/anchors/*.md`; content above the
  `<!-- anchor:tail -->` marker, whole file when marker-less) so a run survives
  compaction and process restarts; warns and names the others when several
  anchors are open in one directory. Lifecycle gates: an anchor untouched for
  >24h degrades to a one-paragraph pointer (path + title + age +
  confirm-to-expand + close command) instead of the full body; `startup`
  (fresh process — the crash-restart path) injects only when the anchor was
  updated in the last 6h, so ordinary new sessions in a cwd with an old anchor
  pay nothing. Ships wired but inert; enable with
  `SESSION_WORKFLOW_ANCHOR_HOOKS=1`.
  Enabling it in a session whose plugin snapshot predates the hook (or in a
  harness without the plugin surface):
  `skills/compaction-survival/references/cold-start.md` has the manual recipe.
- **PostToolUse (async)** — skill-exercise ledger: one JSONL entry per `Skill`
  or plugin-MCP tool call, under `<CLAUDE_PLUGIN_DATA>/exercise-ledger/`. The
  substrate for real-session activation telemetry and for the Stop nudge below.
  Ships wired but inert; enable with `SESSION_WORKFLOW_EXERCISE_LEDGER=1`.
- **Stop** — feedback-debt nudge: once per session, when the ledger shows
  plugin tools were exercised, no tool-feedback invocation is on record, and
  the session has at least `SESSION_WORKFLOW_NUDGE_MIN_TURNS` (default 8) real
  user turns, a Stop block asks the model to apply the tool-feedback skill (or
  finish if nothing is worth recording). Requires the ledger. Ships wired but
  inert; enable with `SESSION_WORKFLOW_FEEDBACK_NUDGE=1`.
