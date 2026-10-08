# engineering-discipline

Modern Python engineering standards and stack-agnostic data-engineering
discipline, with mechanical enforcement and a self-refreshing toolchain.

## Skills

- **python-engineering** — uv / ruff / ty, src layout, `typing.Protocol`,
  pydantic-settings, structlog + OpenTelemetry, pytest + hypothesis, supply-chain
  security. Version pins live in `skills/python-engineering/stack.toml`.
- **data-engineering-discipline** — the four non-negotiables (output is the
  contract; source of truth is observable; real data finds what fixtures can't;
  all change is traceable), the cross-producer contract, grain and time
  semantics, two plain rails (the oracle is not edited in the change it judges;
  irreversible operations are proposed, not executed), scenario playbooks,
  parity recipes, and a contract template.
- **/refresh-stack** (manual-only) — review changelogs for any drifted tool and
  propose a reviewable `stack.toml` + guidance update.

## Scripts

- `skills/python-engineering/scripts/` — `scaffold.py` (new project to standard),
  `doctor.py` (audit an existing project), `check_versions.py` (compare pins to
  PyPI; `--json` for CI).
- `skills/data-engineering-discipline/scripts/` — `schema_diff.py`,
  `parity_check.py` (aggregate diff, null placement, per-column tolerance,
  residual-zero, and a two-producer join asserted before any value),
  `contract_check.py`, `freshness_check.py`, `producer_census.py`,
  `which_copy.py`, and `mutate_check.py`, which proves a check can fail —
  `parity` and `schema` through its own CLI, `contract_check`,
  `freshness_check` and `producer_census` through `test_mutate_check.py`
  (stdlib-first, pandas optional).

All scripts ship with stdlib-runnable tests (`python test_<name>.py`).

## Hooks

Both hooks are **active as soon as the plugin is installed** in Claude Code — no
env gate, because they are the mechanical layer, not options. On a harness
without act-time hooks the same rules
degrade down the enforcement ladder: commit-time via the exported pre-commit
floor (`adapters/pre-commit/craft-floor.yaml`, hook id `check-uv-hygiene`),
else advisory text in the generated `AGENTS.md`. The decision cores are
importable for other harnesses' hook systems via `hooks/harness_adapters.py`.

- **PostToolBatch** — one `uvx ruff format` run at the end of each assistant turn
  over every `.py` file that turn's Write/Edit calls touched, in a project that
  declares ruff: a `ruff.toml`, `.ruff.toml` or `[tool.ruff]` table in a
  `pyproject.toml`, found walking up from the file to the repository root (the
  directory holding `.git`). Files outside any project, or in a repository with
  no ruff config, keep their bytes; a project that uses ruff with no config
  file adds a `[tool.ruff]` table to opt in. Non-blocking;
  requires Claude Code >= 2.1.218.
  `ruff check --fix` is deliberately excluded here (it strips an import added
  in one edit before a later edit uses it) and runs at the pre-commit/CI gate
  instead, where the file is complete; `test_ruff_format.py` guards the exclusion.
- **PreToolUse** — blocks `pip install` / `poetry` / `virtualenv` / `venv` inside
  a uv project (`uv.lock` or `[tool.uv]`/`uv_build`). Override one command with
  `CLAUDE_ALLOW_PIP=1`; never fires outside a uv project. Quoted text, comments
  and heredoc bodies are data and are not scanned, except a heredoc body fed to a
  shell (`bash <<EOF`, `ssh host <<EOF`), which runs. The block message names the
  matched words.

Both hooks append one JSON line per firing to a local log, `hook-log.ndjson`:
`uv_enforce` on each block (`ts`, `hook`, `verdict`, `matched` for the blocked
words, `session`), `ruff_format` on each format run it starts (`ts`, `hook`,
`files` for the file count, `session`). No command text, file path or file
content is written, and nothing is sent over the network. The directory is
`ENGINEERING_DISCIPLINE_STATE_DIR` when set, else `CLAUDE_PLUGIN_DATA` (the
per-plugin data directory Claude Code gives a plugin's hooks), else
`engineering-discipline` under the system temp directory. Appending stops at
1,000,000 bytes, and a failed write never changes a hook's verdict or exit code.
To read it, run `uv run --no-project -- python hooks/hook_log.py` with one of
those two variables set to the directory the hooks write to; it prints the path
it read and the firings per hook.

There is no third hook. A Stop nudge to run the data pre-shipping checklist was
retired in 0.4.0: it was exhortation delivered through a hook, it sat behind an
unset variable and had therefore never fired, and its path globs (`models/*`)
would have matched ORM and ML model directories the moment it did. The seven
data scripts above reject rather than remind: each exits non-zero on a finding.
This repository's own gates run only their unit tests, not the checks on any
data; a project wires the checks into its own CI (Recipe 10 in
`skills/data-engineering-discipline/references/parity-recipes.md` shows a CI job).

## Freshness loop

`check_versions.py` reads `stack.toml` and exits non-zero on drift; the monthly
`currency` workflow opens a `stack-drift` issue; `/refresh-stack` does the
LLM-assisted review and proposes updates (mechanical bumps on approval, guidance
edits never auto-applied).
