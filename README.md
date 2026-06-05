# craft-collection

A Claude Code plugin marketplace with two plugins:

- **engineering-discipline** — modern Python engineering standards + stack-agnostic
  data-engineering discipline, with mechanical enforcement (ruff/uv hooks),
  runnable scripts, and a self-refreshing toolchain.
- **session-workflow** — capture session knowledge into structured entries, author
  paste-ready hand-off briefs, and keep a live inventory of the installed toolkit.

## Install

```text
/plugin marketplace add grimaldo-stanzani/craft-collection
/plugin install engineering-discipline@craft-collection
/plugin install session-workflow@craft-collection
```

Local development (no marketplace needed):

```text
claude --plugin-dir ./plugins/engineering-discipline --plugin-dir ./plugins/session-workflow
```

## What's inside

**engineering-discipline** — skills `python-engineering`,
`data-engineering-discipline`, and `/refresh-stack`; scripts for scaffolding,
auditing, version-checking, schema-diffing, parity, and contract validation;
hooks for ruff-format and uv enforcement; a `stack.toml`-based freshness loop.

**session-workflow** — skills `journaling-sessions`, `context-handoff`, and
`toolkit-awareness`; a live `scan_toolkit.py` inventory; an optional
session-start inject hook.

## Optional hooks (all off by default)

| Behaviour | Enable with |
|-----------|-------------|
| Toolkit inventory injected at session start | `TOOLKIT_AWARENESS_INJECT=1` |
| Data pre-shipping checklist nudge on Stop | `DATAENG_CHECKLIST_NUDGE=1` |
| Allow one pip/poetry command in a uv project | `CLAUDE_ALLOW_PIP=1` |

## Versioning

Each plugin pins a semantic `version` in its `plugin.json`. **Bump it on every
release** — Claude Code only pulls an update when the version changes. Do not set
`version` in both the manifest and a marketplace entry (the manifest wins).

## Development

```text
uv run --no-project --with pyyaml -- python scripts/validate_plugins.py   # structural checks
cd <script-dir> && python test_<name>.py                                  # run any test (no pytest needed)
```

CI under `.github/workflows/` runs the validator + every `test_*.py` on push/PR
(`validate.yml`) and a monthly toolchain drift check (`currency.yml`).

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
