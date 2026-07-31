# engineering-discipline

Modern Python engineering standards and stack-agnostic data-engineering
discipline, with mechanical enforcement and a self-refreshing toolchain.

## Skills

- **python-engineering** — uv / ruff / ty, src layout, `typing.Protocol`,
  pydantic-settings, structlog + OpenTelemetry, pytest + hypothesis, supply-chain
  security. Version pins live in `skills/python-engineering/stack.toml`.
- **data-engineering-discipline** — the four non-negotiables (output is the
  contract; source of truth is observable; real data finds what fixtures can't;
  all change is traceable), LLM failure modes, scenario playbooks, parity recipes,
  and contract templates.
- **/refresh-stack** (manual-only) — review changelogs for any drifted tool and
  propose a reviewable `stack.toml` + guidance update.

## Scripts

- `skills/python-engineering/scripts/` — `scaffold.py` (new project to standard),
  `doctor.py` (audit an existing project), `check_versions.py` (compare pins to
  PyPI; `--json` for CI).
- `skills/data-engineering-discipline/scripts/` — `schema_diff.py`,
  `parity_check.py`, `contract_check.py`, `freshness_check.py` (stdlib-first,
  pandas optional).

All scripts ship with stdlib-runnable tests (`python test_<name>.py`).

## Hooks

The PostToolBatch and PreToolUse hooks are **active as soon as the plugin is
installed** in Claude Code (no env gate — they are the mechanical layer); only
the Stop nudge is opt-in. On a harness without act-time hooks the same rules
degrade down the enforcement ladder: commit-time via the exported pre-commit
floor (`adapters/pre-commit/craft-floor.yaml`, hook id `check-uv-hygiene`),
else advisory text in the generated `AGENTS.md`. The decision cores are
importable for other harnesses' hook systems via `hooks/harness_adapters.py`.

- **PostToolBatch** — one `uvx ruff format` run at the end of each assistant turn
  over every `.py` file that turn's Write/Edit calls touched. Non-blocking;
  requires Claude Code >= 2.1.218.
  `ruff check --fix` is deliberately excluded here (it strips an import added
  in one edit before a later edit uses it) and runs at the pre-commit/CI gate
  instead, where the file is complete; `test_ruff_format.py` guards the exclusion.
- **PreToolUse** — blocks `pip install` / `poetry` / `virtualenv` / `venv` inside
  a uv project (`uv.lock` or `[tool.uv]`/`uv_build`). Override one command with
  `CLAUDE_ALLOW_PIP=1`; never fires outside a uv project.
- **Stop** — inert nudge to run the data pre-shipping checklist; enable with
  `DATAENG_CHECKLIST_NUDGE=1`. It fires only when the session's git diff touched
  pipeline-ish paths — by default `*.sql`, `*dbt*`, `*pipeline*`, `*etl*`,
  `models/*`, `*/models/*`; override that list with a comma-separated
  `DATAENG_PIPELINE_GLOBS`.

## Freshness loop

`check_versions.py` reads `stack.toml` and exits non-zero on drift; the monthly
`currency` workflow opens a `stack-drift` issue; `/refresh-stack` does the
LLM-assisted review and proposes updates (mechanical bumps on approval, guidance
edits never auto-applied).
