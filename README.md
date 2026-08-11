<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/craft-hero-dark.svg">
  <img alt="craft" src="assets/craft-hero-light.svg" width="100%">
</picture>

[![validate](https://img.shields.io/github/actions/workflow/status/grimaldost/craft-collection/validate.yml?branch=main&style=flat-square&labelColor=2A3238&label=validate)](https://github.com/grimaldost/craft-collection/actions/workflows/validate.yml)
[![license](https://img.shields.io/badge/license-MIT-39621C?style=flat-square&labelColor=2A3238)](LICENSE)

craft-collection is a Claude Code plugin marketplace with four plugins:

- **[engineering-discipline](plugins/engineering-discipline/README.md)** — modern
  Python engineering standards + stack-agnostic data-engineering discipline, with
  mechanical enforcement (ruff/uv hooks), runnable scripts, and a self-refreshing
  toolchain.
- **[experiment-discipline](plugins/experiment-discipline/README.md)** — discipline
  for evaluation acts: a typed `record.yaml` across a probe / measurement /
  decision tier ladder, with a validator, a derived report, small-n statistics
  that refuse the CLT, and a pre-registration freeze.
- **[session-workflow](plugins/session-workflow/README.md)** — capture session
  knowledge and distill it into durable guidance, author paste-ready hand-off
  briefs, convene fresh-eyes review panels, behaviorally evaluate skills, keep a
  live inventory of the installed toolkit, sign agent-assisted work with
  machine-generated provenance trailers, and run a tool-dogfooding feedback loop
  (capture + triage).
- **[humblepowers](plugins/humblepowers/README.md)** — superpowers-derived process
  disciplines in a calibrated register (fit-ranked dispatch, calibration-first
  skill authoring, TDD, root-cause debugging, brainstorming, verification, review
  reception, midweight planned execution, model/effort dispatch) — eval-gated,
  with a register linter. **Replaces superpowers; never install both.**

## Install

**Prerequisites:** [`uv`](https://docs.astral.sh/uv/) must be on your `PATH`. The
plugins' hooks launch via `uv run`, so without uv every Write/Edit/Bash/Stop and
session-start hook fails to spawn.

```text
/plugin marketplace add grimaldost/craft-collection
/plugin install engineering-discipline@craft-collection
/plugin install experiment-discipline@craft-collection
/plugin install session-workflow@craft-collection
/plugin install humblepowers@craft-collection
```

Local development (no marketplace needed):

```text
claude --plugin-dir ./plugins/engineering-discipline --plugin-dir ./plugins/experiment-discipline --plugin-dir ./plugins/session-workflow --plugin-dir ./plugins/humblepowers
```

**Other agents (Codex, Gemini CLI, Cursor, any agents.md reader):** clone this
repo and point the agent at the generated `AGENTS.md` index — see
[`docs/portability.md`](docs/portability.md) for the installation matrix, the
enforcement ladder, and what is (and is not) measured off Claude Code.

## What's inside

**engineering-discipline** — skills `python-engineering`,
`data-engineering-discipline`, and `/refresh-stack`; scripts for scaffolding,
auditing, version-checking, schema-diffing, parity, and contract validation;
hooks for ruff-format and uv enforcement; a `stack.toml`-based freshness loop.

**experiment-discipline** — skill `experiment-rigor` (rigid); the mechanism spine
in `skills/experiment-rigor/scripts/` (`validate.py` central gate with stable
`ER-*` codes, `render.py` report/schema generator and drift gate, `stats.py`
small-n intervals, `from_fathom.py` ledger adapter); tier templates plus a
machine-readable `schema.json` and its generated field guide; the founding RG-2x2
dogfood record and its freeze choreography. Two repo pre-commit hooks gate every
travelling `record.yaml` / `report.md` pair.

**session-workflow** — skills `journaling-sessions`, `consolidate-knowledge`,
`context-handoff`, `review-panel`, `evaluate-skill`, `toolkit-awareness`,
`llm-signature`, `tool-feedback`, `feedback-triage`, `compaction-survival`, and
`corpus-review`;
the `/anchor` command; a live `scan_toolkit.py` inventory; the headless
skill-eval engine in `scripts/`; a selectable `step-digest` output style; the
control-anchor re-injection hook (on by default) plus two opt-in ones (see the
plugin README).

**humblepowers** — skills `choosing-tools`, `skill-authoring`, `brainstorming`,
`test-driven-development`, `systematic-debugging`,
`verification-before-completion`, `receiving-code-review`,
`planned-execution`, `choosing-models`, and `/refresh-models`; every
auto-triggering skill carries a trigger dataset and a sealed holdout under
`evals/`, and four of them — `test-driven-development`, `systematic-debugging`,
`verification-before-completion`, `planned-execution` — additionally carry
correct-usage suites; register linter wired into pre-commit;
a per-prompt dispatch-router hint hook, on by default. Derived from
[obra/superpowers](https://github.com/obra/superpowers) (MIT) — see the
plugin's LICENSE for third-party notices.

## Hooks

Two engineering-discipline hooks are **always on** once that plugin is installed —
they are its mechanical layer, not options: `ruff_format` re-formats every `.py`
file edited in a turn, once at the end of that turn (PostToolBatch,
non-blocking; needs Claude Code >= 2.1.218), and `uv_enforce` blocks
pip/poetry/virtualenv inside uv-managed projects (PreToolUse; override one command
with `CLAUDE_ALLOW_PIP=1`).

The rule for every other hook here: **it ships on with a documented opt-out, or
it does not ship.** A hook behind a variable nobody sets has never run, which
reads as enforcement in the manifest and is absent in the session. Opt-outs go in
the `env` block of `~/.claude/settings.json` (every project) or
`<repo>/.claude/settings.json` (one), e.g.
`{ "env": { "SESSION_WORKFLOW_ANCHOR_HOOKS": "0" } }`.

| Behaviour | Default | Opt out with |
|-----------|---------|--------------|
| Dispatch router hint injected on each prompt (UserPromptSubmit, not session start) | on | `HUMBLEPOWERS_DISPATCH_PROMPT_INJECT=0`, or `HUMBLEPOWERS_DISPATCH_ROUTER=0` to disable the router itself |
| Control-anchor re-injection on compact/resume | on | `SESSION_WORKFLOW_ANCHOR_HOOKS=0` |
| Skill-exercise ledger (one JSONL entry per Skill / plugin-MCP call) | off | enable with `SESSION_WORKFLOW_EXERCISE_LEDGER=1` |
| Feedback-debt nudge on Stop (requires the ledger) | off | enable with `SESSION_WORKFLOW_FEEDBACK_NUDGE=1` |

Two hooks were retired rather than defaulted on: the toolkit-inventory session
start inject (the harness already lists skills and descriptions in the system
prompt) and the data pre-shipping checklist Stop nudge (exhortation through a
hook, against four runnable checks already in the gates that reject rather than
remind).

## Optional output style

`step-digest` (session-workflow) keeps working narration lean and ends each
substantive turn with a fixed-field digest, so a long agent-driven run reads back
from its digests instead of its full transcript. Off by default — pick it under
`/config`, or set `"outputStyle": "session-workflow:step-digest"` in your user or
project settings. (The plugin ships it under that namespaced name; the bare
`step-digest` resolves only for a project-local `.claude/output-styles/` file.)

## Versioning

Each plugin pins a semantic `version` in its `plugin.json`. **Bump it on every
release** — Claude Code only pulls an update when the version changes. Do not set
`version` in both the manifest and a marketplace entry (the manifest wins).

## Development

```text
uv tool run pre-commit install         # enable commit gates: ruff, validator, hygiene
uv tool run pre-commit run --all-files # run every gate now
uv run --no-project --with pyyaml -- python scripts/run_tests.py    # run every test_*.py (no pytest needed)
uv run --no-project --with pyyaml -- python scripts/validate_plugins.py  # structural marketplace checks (PyYAML catches the frontmatter colon-space trap)
```

`AGENTS.md` is generated from skill / command / output-style frontmatter by
`scripts/gen_agents_md.py` and is freshness-gated in pre-commit and CI — never
hand-edit it; change the frontmatter and re-run
`uv run --no-project -- python scripts/gen_agents_md.py`.

Formatting and lint are governed by `ruff.toml` (100-column, single quotes). CI
(`.github/workflows/validate.yml`) enforces ruff lint + format, the register
linter, the structural validator, the `AGENTS.md` freshness gate, and the full
test suite on push/PR; `currency.yml` runs a monthly toolchain drift check.

## Layout

```text
.claude-plugin/marketplace.json
plugins/
  engineering-discipline/   .claude-plugin/  skills/  hooks/
  experiment-discipline/    .claude-plugin/  skills/
  session-workflow/         .claude-plugin/  skills/  hooks/  commands/  output-styles/
  humblepowers/             .claude-plugin/  skills/  hooks/
scripts/                    repo gates (see CONTRIBUTING)
evals/                      harness/  tasks/  trigger/  config.json
assets/                     brand assets (see assets/README.md)
```

## License

MIT
