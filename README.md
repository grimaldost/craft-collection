# craft-collection

A Claude Code plugin marketplace with four plugins:

- **engineering-discipline** — modern Python engineering standards + stack-agnostic
  data-engineering discipline, with mechanical enforcement (ruff/uv hooks),
  runnable scripts, and a self-refreshing toolchain.
- **experiment-discipline** — discipline for evaluation acts: a typed `record.yaml`
  across a probe / measurement / decision tier ladder, with a validator, a derived
  report, small-n statistics that refuse the CLT, and a pre-registration freeze.
- **session-workflow** — capture session knowledge and distill it into durable
  guidance, author paste-ready hand-off briefs, convene fresh-eyes review panels,
  behaviorally evaluate skills, keep a live inventory of the installed toolkit,
  sign agent-assisted work with machine-generated provenance trailers, and run a
  tool-dogfooding feedback loop (capture + triage).
- **humblepowers** — superpowers-derived process disciplines in a calibrated
  register (fit-ranked dispatch, calibration-first skill authoring, TDD,
  root-cause debugging, brainstorming, verification, review reception, midweight
  planned execution) — eval-gated, with a register linter. **Replaces
  superpowers; never install both.**

## Install

**Prerequisites:** [`uv`](https://docs.astral.sh/uv/) must be on your `PATH`. The
plugins' hooks launch via `uv run`, so without uv every Write/Edit/Bash/Stop/
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
a live `scan_toolkit.py` inventory; the headless skill-eval engine in `scripts/`;
a selectable `step-digest` output style; an optional session-start inject hook.

**humblepowers** — skills `choosing-tools`, `skill-authoring`, `brainstorming`,
`test-driven-development`, `systematic-debugging`,
`verification-before-completion`, `receiving-code-review`, and
`planned-execution`; every skill measured (trigger datasets + sealed holdouts +
correct-usage suites under `evals/`); register linter wired into pre-commit;
an optional dispatch-protocol inject hook. Derived from
[obra/superpowers](https://github.com/obra/superpowers) (MIT) — see the
plugin's LICENSE for third-party notices.

## Hooks

Two engineering-discipline hooks are **always on** once that plugin is installed —
they are its mechanical layer, not options: `ruff_format` re-formats a `.py` file
after every edit (PostToolUse, non-blocking), and `uv_enforce` blocks
pip/poetry/virtualenv inside uv-managed projects (PreToolUse; override one command
with `CLAUDE_ALLOW_PIP=1`). Everything else is **off by default**, each behind an
env var:

| Behaviour | Enable with |
|-----------|-------------|
| Toolkit inventory injected at session start | `TOOLKIT_AWARENESS_INJECT=1` |
| Data pre-shipping checklist nudge on Stop | `DATAENG_CHECKLIST_NUDGE=1` |
| Dispatch protocol injected at session start | `HUMBLEPOWERS_DISPATCH_INJECT=1` |
| Control-anchor re-injection on compact/resume | `SESSION_WORKFLOW_ANCHOR_HOOKS=1` |

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
uv run --no-project python scripts/run_tests.py                 # run every test_*.py (no pytest needed)
uv run --no-project --with pyyaml -- python scripts/validate_plugins.py  # structural marketplace checks (PyYAML catches the frontmatter colon-space trap)
```

Formatting and lint are governed by `ruff.toml` (100-column, single quotes). CI
(`.github/workflows/validate.yml`) enforces ruff lint + format, the register
linter, the structural validator, and the full test suite on push/PR;
`currency.yml` runs a monthly toolchain drift check.

## Layout

```text
.claude-plugin/marketplace.json
plugins/
  engineering-discipline/   .claude-plugin/  skills/  hooks/
  experiment-discipline/    .claude-plugin/  skills/
  session-workflow/         .claude-plugin/  skills/  hooks/  output-styles/
  humblepowers/             .claude-plugin/  skills/  hooks/
scripts/                    validate_plugins.py  run_tests.py  lint_register.py
evals/                      harness/  tasks/  trigger/  config.json
```

## License

MIT
