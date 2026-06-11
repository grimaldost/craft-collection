# craft-collection

A Claude Code plugin marketplace with three plugins:

- **engineering-discipline** — modern Python engineering standards + stack-agnostic
  data-engineering discipline, with mechanical enforcement (ruff/uv hooks),
  runnable scripts, and a self-refreshing toolchain.
- **session-workflow** — capture session knowledge and distill it into durable
  guidance, author paste-ready hand-off briefs, convene fresh-eyes review panels,
  behaviorally evaluate skills, keep a live inventory of the installed toolkit,
  and run a tool-dogfooding feedback loop (capture + triage).
- **humblepowers** — superpowers-derived process disciplines in a calibrated
  register (fit-ranked dispatch, calibration-first skill authoring, TDD,
  root-cause debugging, brainstorming, verification, review reception, midweight
  planned execution) — eval-gated, with a register linter. **Replaces
  superpowers; never install both.**

## Install

```text
/plugin marketplace add grimaldost/craft-collection
/plugin install engineering-discipline@craft-collection
/plugin install session-workflow@craft-collection
/plugin install humblepowers@craft-collection
```

Local development (no marketplace needed):

```text
claude --plugin-dir ./plugins/engineering-discipline --plugin-dir ./plugins/session-workflow --plugin-dir ./plugins/humblepowers
```

## What's inside

**engineering-discipline** — skills `python-engineering`,
`data-engineering-discipline`, and `/refresh-stack`; scripts for scaffolding,
auditing, version-checking, schema-diffing, parity, and contract validation;
hooks for ruff-format and uv enforcement; a `stack.toml`-based freshness loop.

**session-workflow** — skills `journaling-sessions`, `consolidate-knowledge`,
`context-handoff`, `review-panel`, `evaluate-skill`, `toolkit-awareness`,
`tool-feedback`, and `feedback-triage`; a live `scan_toolkit.py` inventory; the
headless skill-eval engine in `scripts/`; an optional session-start inject hook.

**humblepowers** — skills `choosing-tools`, `skill-authoring`, `brainstorming`,
`test-driven-development`, `systematic-debugging`,
`verification-before-completion`, `receiving-code-review`, and
`planned-execution`; every skill measured (trigger datasets + sealed holdouts +
correct-usage suites under `evals/`); register linter wired into pre-commit;
an optional dispatch-protocol inject hook. Derived from
[obra/superpowers](https://github.com/obra/superpowers) (MIT) — see the
plugin's LICENSE for third-party notices.

## Optional hooks (all off by default)

| Behaviour | Enable with |
|-----------|-------------|
| Toolkit inventory injected at session start | `TOOLKIT_AWARENESS_INJECT=1` |
| Data pre-shipping checklist nudge on Stop | `DATAENG_CHECKLIST_NUDGE=1` |
| Allow one pip/poetry command in a uv project | `CLAUDE_ALLOW_PIP=1` |
| Dispatch protocol injected at session start | `HUMBLEPOWERS_DISPATCH_INJECT=1` |

## Versioning

Each plugin pins a semantic `version` in its `plugin.json`. **Bump it on every
release** — Claude Code only pulls an update when the version changes. Do not set
`version` in both the manifest and a marketplace entry (the manifest wins).

## Development

```text
uv tool run pre-commit install         # enable commit gates: ruff, validator, hygiene
uv tool run pre-commit run --all-files # run every gate now
python scripts/run_tests.py            # run every test_*.py (no pytest needed)
python scripts/validate_plugins.py     # structural marketplace checks (needs pyyaml)
```

Formatting and lint are governed by `ruff.toml` (100-column, single quotes). CI
(`.github/workflows/validate.yml`) enforces ruff lint + format, the structural
validator, and the full test suite on push/PR; `currency.yml` runs a monthly
toolchain drift check.

## Layout

```text
.claude-plugin/marketplace.json
plugins/
  engineering-discipline/   .claude-plugin/  skills/  hooks/  evals/
  session-workflow/         .claude-plugin/  skills/  hooks/  evals/
scripts/validate_plugins.py
```

## License

MIT
