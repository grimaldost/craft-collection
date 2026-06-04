# session-workflow

Capture session knowledge, hand work off cleanly, and stay aware of your toolkit.

## Skills

- **journaling-sessions** — capture a work or reference-reading session into
  structured, separable, retrieval-ready entries for a long-term memory store.
  Runs an automatic internal multi-pass (capture → coverage self-check → fill
  gaps), so a single invocation produces thorough output — no need to ask for
  "multiple passes." Generic core + on-demand references (output format,
  reference-ingestion taxonomy, coverage check, writing-for-retrieval).
- **context-handoff** — author a paste-ready, self-contained brief for a fresh
  context: a new Claude Code session, a spawned task, a teammate, or an issue.
  SUBTASK mode (an artifact comes back) and FORK mode (continues independently).
  For in-session parallel work, prefer the Task tool / subagents.
- **toolkit-awareness** — `scripts/scan_toolkit.py` produces a live inventory of
  installed skills / commands / agents / hooks (no hand-maintained list); the
  skill adds durable guidance on referencing the toolkit in prompts and specs.

## Hook (optional, off by default)

- **SessionStart** — inject the live toolkit inventory each session. Ships wired
  but inert; enable with `TOOLKIT_AWARENESS_INJECT=1`.
