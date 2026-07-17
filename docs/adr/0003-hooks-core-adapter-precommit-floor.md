# ADR-0003 — Hooks: pure core + per-harness adapters, pre-commit as the universal floor

- **Status:** Accepted
- **Date:** 2026-07-16

## Context

The engineering-discipline hooks are the toolkit's mechanical layer:
`ruff_format` (PostToolUse, non-blocking) and `uv_enforce` (PreToolUse,
blocking). Their decision logic is already pure and unit-tested
(`ruff_commands`, `target_file`, `verdict`, `cwd_is_uv_project`); only the
envelope — Claude Code's stdin JSON payload, exit-code semantics,
`${CLAUDE_PLUGIN_ROOT}` paths — is harness-specific. Other harnesses vary:
some have hook systems with different payload schemas, most have none.
Blocking-before-execution semantics do not exist universally.

## Decision

Each hook is split into a harness-agnostic core (the existing pure functions,
moved behind a stable seam that takes plain arguments: file path, command
string, cwd) and a thin per-harness adapter that parses that harness's event
payload and maps the core's verdict to that harness's blocking convention. The
CC adapter is the current `main()` and stays the default. Enforcement degrades
down an explicit ladder: **block at act time** (harness with hooks) → **block
at commit time** (a consumer-facing pre-commit floor: ruff format/lint plus a
uv-hygiene check) → **advisory** (the same rules stated in the generated
AGENTS.md). Hook behavior tests target the core, so every adapter inherits the
same tested semantics.

## Alternatives considered

- **Keep hooks CC-only and document their absence elsewhere** — rejected: the
  mechanical layer is the plugin's differentiator ("enforced discipline beats
  intended discipline"); losing it entirely off-CC guts the plugin.
- **Ship full adapters for every known harness now** — rejected: speculative
  maintenance surface; adapters are cheap (~20 lines) and written on demand
  when a target harness is actually used.
- **Re-implement blocking via shell wrappers around the agent's tools** —
  rejected: fragile, harness-internal, and impossible to support generically.

## Consequences

- New invariant: **adapter thinness** — adapters translate payloads only;
  any logic change lands in the core, where the tests are.
- The degradation ladder is honest and documented: off-CC consumers know they
  get commit-time or advisory enforcement, not act-time blocking.
- The pre-commit floor duplicates intent (not code) with the CC hooks; the
  ladder documentation keeps the two in one place to review together.
