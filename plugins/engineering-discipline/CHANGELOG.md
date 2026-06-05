# Changelog — engineering-discipline

All notable changes to this plugin are documented here. Bump the `version` in
`.claude-plugin/plugin.json` with each release.

## 0.1.1 — 2026-06-05

- Fixed: corrected the `repository` URL to `grimaldost/craft-collection` (the
  previous `grimaldo-stanzani` owner did not resolve).

## 0.1.0 — 2026-06-04

Initial release.

- `python-engineering` skill with `stack.toml` as the single source of truth for
  version pins.
- `data-engineering-discipline` skill (relocated, examples genericized).
- Scripts: `scaffold.py`, `doctor.py`, `check_versions.py`, `schema_diff.py`,
  `parity_check.py`, `contract_check.py` — all with stdlib-runnable tests.
- Hooks: ruff-format (PostToolUse), uv-enforce (PreToolUse), optional data
  checklist nudge (Stop, off by default).
- Tier-3 freshness loop: drift detection + monthly `currency` cron +
  `/refresh-stack` review command.
