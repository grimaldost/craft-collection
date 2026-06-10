# session-workflow

Manage the work *around* the work: capture session knowledge and distill it into
durable guidance, hand work off to a fresh context, convene fresh-eyes review
panels, behaviorally evaluate your skills, stay aware of your toolkit, and run the
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
- **context-handoff** (`/subtask`, `/fork`) — author a paste-ready, self-contained
  brief for a fresh context: a new Claude Code session, a spawned task, a teammate,
  or an issue. SUBTASK mode (an artifact comes back) and FORK mode (continues
  independently). For in-session parallel work, prefer the Task tool / subagents.
- **review-panel** (`/review-panel`) — convene fresh reviewer subagents that are
  blind to the conversation and to each other, pointed at an artifact you've
  anchored on from adversarial angles. Neutral brief, structured comparable
  output, synthesis over averaging, a stakes-scaled ladder. Claude Code only;
  shows the plan + cost and asks before firing.
- **evaluate-skill** (`/evaluate-skill`) — behaviorally evaluate a skill by running
  it headless many times: triggering (recall / specificity), correct-usage (rubric
  judge), and a with/without baseline, each with Wilson 95% CIs. Ships the eval
  engine in `scripts/`. Claude Code only; cost-gated.
- **toolkit-awareness** — `scripts/scan_toolkit.py` produces a live inventory of
  installed skills / commands / agents / hooks (no hand-maintained list); the
  skill adds durable guidance on referencing the toolkit in prompts and specs.
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

## Hook (optional, off by default)

- **SessionStart** — inject the live toolkit inventory each session. Ships wired
  but inert; enable with `TOOLKIT_AWARENESS_INJECT=1`.
