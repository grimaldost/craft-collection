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
  `parity_check.py`, `contract_check.py` (stdlib-first, pandas optional).

All scripts ship with stdlib-runnable tests (`python test_<name>.py`).

## Hooks

- **PostToolUse** — `ruff format` + `ruff check --fix` on `.py` edits via `uvx`.
  Non-blocking.
- **PreToolUse** — blocks `pip install` / `poetry` / `virtualenv` / `venv` inside
  a uv project (`uv.lock` or `[tool.uv]`/`uv_build`). Override one command with
  `CLAUDE_ALLOW_PIP=1`; never fires outside a uv project.
- **Stop** — inert nudge to run the data pre-shipping checklist; enable with
  `DATAENG_CHECKLIST_NUDGE=1`.

## Freshness loop

`check_versions.py` reads `stack.toml` and exits non-zero on drift; the monthly
`currency` workflow opens a `stack-drift` issue; `/refresh-stack` does the
LLM-assisted review and proposes updates (mechanical bumps on approval, guidance
edits never auto-applied).
