# Using craft-collection from any agent

The skills are plain Agent Skills (`SKILL.md` + `references/` + `scripts/`);
Claude Code is one consumer, not a requirement. This page is the map for every
other harness. Decisions behind it: `docs/adr/0001`–`0006`.

## Installation matrix

| Harness | Install | Discovery | Updates |
|---|---|---|---|
| Claude Code | `/plugin marketplace add grimaldost/craft-collection` + `/plugin install <plugin>` | plugin skill dispatch | version bump per `plugin.json` |
| Any agents.md-reading harness (Codex CLI, Gemini CLI, Cursor, Copilot, custom agents) | `git clone https://github.com/grimaldost/craft-collection` | repo-root `AGENTS.md` (generated index: name + trigger + path per skill) | `git pull` |
| Harness with its own skills directory | clone, then point/symlink `plugins/*/skills/*` into its skills location | its native dispatch + `AGENTS.md` | `git pull` |
| Any repo's pre-commit (no agent at all) | reference this repo in `.pre-commit-config.yaml` | n/a | bump the pinned `rev` |

`AGENTS.md` is generated (`scripts/gen_agents_md.py`) and freshness-gated —
never hand-edit it. Off Claude Code there is no per-plugin update granularity:
you track the repo (pin a SHA if you need reproducibility).

## Enforcement ladder

The mechanical layer degrades explicitly; each tier states what it does and
does not guarantee.

| Tier | Mechanism | Guarantees | Does NOT guarantee |
|---|---|---|---|
| Act-time | Claude Code hooks (`ruff_format` PostToolBatch, `uv_enforce` PreToolUse); other hook-capable harnesses via `plugins/engineering-discipline/hooks/harness_adapters.py` | a bad command is blocked before it runs; every `.py` file edited in a turn is formatted at the end of that turn | anything on a harness without hooks |
| Commit-time | the pre-commit floor: `adapters/pre-commit/craft-floor.yaml` (ruff + the `check-uv-hygiene` hook this repo exports via `.pre-commit-hooks.yaml`), plus `experiment-rigor-validate` / `experiment-rigor-render-check` from the same file for projects keeping experiment records | residue and format drift cannot be committed; an experiment record cannot be committed out of sync with its report or its frozen pre-registration | that the mistake never happened — it is caught after the fact |
| Advisory | the rules stated in `AGENTS.md` and the skill bodies | the agent read the rule | that the agent followed it |

## Commands and output styles, by hand

Both are plain markdown an agent can be pointed at — no command/output-style
runtime needed:

- **anchor** (`plugins/session-workflow/commands/anchor.md`) — say "follow the
  instructions in that file" (optionally with `close` / `close --stale` as the
  argument). It snapshots the run's control anchor to `.claude/anchors/`.
- **step-digest** (`plugins/session-workflow/output-styles/step-digest.md`) —
  paste or reference it as a standing instruction ("communicate per this
  file"); it defines the lean-narration + end-of-turn digest contract.

## Measurement scope (read before claiming parity)

The toolkit is designed for any agents.md-reading harness; **trigger behavior
is measured on Claude Code only** (trigger datasets, sealed holdouts, and
correct-usage suites under `evals/`, spawned through the `AgentRunner` seam's
single backend, headless `claude -p`). Until a second runner backend exists
and the suites have run on it, "works on harness X" is a design claim, not a
measured one — phrase it that way.

## MCP (deferred, with a named trigger)

An MCP server exposing the utility scripts as tools and the skills as
resources is deliberately not built (ADR-0004). Revisit when a concrete
consumer that cannot read files — or a user request — demands it; nothing in
the current layout blocks adding it as a complement.
