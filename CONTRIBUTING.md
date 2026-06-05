# Contributing to craft-collection

Thanks for your interest in improving this collection. It's a Claude Code plugin
marketplace, so most contributions touch a **skill** (`SKILL.md` + references +
scripts), a **hook**, the **eval harness**, or repo tooling. This guide covers how
to get set up and what a mergeable change looks like.

By participating you agree to keep things respectful and constructive, and that
your contributions are licensed under the project's [MIT License](LICENSE).

## Ways to contribute

- **Report a bug or suggest an idea** — open an issue. Include the skill/plugin
  involved and, for misfires, the prompt that did (or didn't) trigger it.
- **Improve a skill, script, hook, or doc** — open a pull request (see below).
- **Security issues** — please follow [SECURITY.md](SECURITY.md) instead of opening
  a public issue.

## Getting set up

Prerequisites: **Python 3.13+** and **[uv](https://docs.astral.sh/uv/)** (used to
run the pinned tooling without polluting your environment).

```bash
git clone https://github.com/grimaldost/craft-collection
cd craft-collection
uv tool run pre-commit install   # installs the pre-commit + pre-push gates
```

To try the plugins locally without publishing a marketplace:

```bash
claude --plugin-dir ./plugins/engineering-discipline \
       --plugin-dir ./plugins/session-workflow
```

See the [README](README.md) for the full layout.

## Running the checks locally

The same gates run in pre-commit, pre-push, and CI — running them before you push
avoids round-trips:

```bash
uv tool run pre-commit run --all-files   # ruff lint + format, JSON/YAML, validator
python scripts/run_tests.py              # every test_*.py (no pytest needed)
python scripts/validate_plugins.py       # structural marketplace checks (needs pyyaml)
```

The `validate` workflow re-runs all of these on every PR; it must be green to merge.

## Conventions

- **Python style** is governed by [`ruff.toml`](ruff.toml): 100-column lines, single
  quotes. `ruff format` + `ruff check --fix` run automatically on commit.
- **Stdlib-first.** Scripts avoid third-party dependencies where practical (heavier
  libs like pandas stay optional). This keeps the harness and scripts runnable with
  nothing to install.
- **Tests live beside code.** Every `script.py` ships a `test_script.py` that runs
  under plain `python` (no pytest). `scripts/run_tests.py` discovers them.
- **Skills** follow the existing shape: `plugins/<plugin>/skills/<skill>/SKILL.md`
  with a trigger-focused `description` in the frontmatter, plus `references/` for
  on-demand depth and `scripts/` for runnable tools. Use a sibling skill as a model.
- **Don't hand-edit `version` in two places.** A plugin's version lives in its
  `plugin.json` manifest, not in the marketplace entry.

## Commits & pull requests

- **Branch off `main`.** Direct pushes to `main` are blocked — all changes land via
  pull request with the `validate` check passing.
- **Use [Conventional Commits](https://www.conventionalcommits.org/).** This repo's
  history uses them, e.g.:
  - `feat(session-workflow): add review-panel personas`
  - `fix(python-engineering): correct ruff pin in scaffold`
  - `docs(evals): clarify scorecard columns`
  - `build:` / `ci:` / `chore:` for tooling, CI, and housekeeping.
- **Open a PR** and fill in the template. Keep changes focused; unrelated cleanups
  belong in their own PR.
- PRs are **squash-merged**, so the PR title becomes the commit — make it a good
  Conventional Commit line.

## Releasing

Claude Code only pulls a plugin update when its version changes. For a
release-worthy change, **bump the semantic `version` in the affected plugin's
`plugin.json`** as part of the PR, and note it in that plugin's `CHANGELOG.md`.
