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
run the pinned tooling without polluting your environment). 3.13 is the CI and uv
baseline; the scripts are stdlib-first and `ruff` targets 3.10, so they also run on
older interpreters.

```bash
git clone https://github.com/grimaldost/craft-collection
cd craft-collection
uv tool run pre-commit install   # installs the pre-commit + pre-push gates
```

To try the plugins locally without publishing a marketplace:

```bash
claude --plugin-dir ./plugins/engineering-discipline \
       --plugin-dir ./plugins/experiment-discipline \
       --plugin-dir ./plugins/session-workflow \
       --plugin-dir ./plugins/humblepowers
```

See the [README](README.md) for the full layout.

## Running the checks locally

The same gates run in pre-commit, pre-push, and CI — running them before you push
avoids round-trips:

```bash
uv tool run pre-commit run --all-files   # ruff lint + format, JSON/YAML, validator
uv run --no-project --with pyyaml -- python scripts/run_tests.py    # every test_*.py (no pytest needed)
uv run --no-project --with pyyaml -- python scripts/validate_plugins.py  # structural marketplace checks (PyYAML catches the frontmatter colon-space trap)
```

The `validate` workflow re-runs the register linter, the plugin validator, the
`AGENTS.md` freshness check, the env-gate claims check, the release-discipline
gate (PRs only), ruff, and the test suite on every PR; it must be green to
merge. It does **not** run the pre-commit-only hooks — `check-json`,
`check-yaml`, `check-merge-conflict`, `check-added-large-files`, the ASCII runtime
ratchet, or the two `experiment-rigor` record gates. Those exist at commit time
only, which is what makes the exemptions below worth writing down.

## Gate exemptions on a Windows application-control machine

This is the suite's shared record of local gate constraints, kept here because
sibling repositories plan commit-time gates against it rather than rediscovering
it. It is a log of observations, not a standing instruction — check the
re-verification line before copying anything from it.

**Observed (2026-07-23 to 2026-07-26).** On the maintainer's Windows machine,
`pre-commit`'s bare `.exe` shims were refused by the OS application-control policy
(`WinError 4551`). Three hooks that run through those shims — `check-json`,
`check-merge-conflict`, `check-added-large-files` — were skipped for the duration
with `SKIP=check-merge-conflict,check-added-large-files,check-json git commit …`.
Only the first two were written down at the time; `check-json` rode along
undocumented for eight consecutive commits, which is the reason this section
exists. Hooks **git itself invoked** ran normally throughout; only direct
invocation of the binary was refused.

**Compensating controls while those three were skipped.** `check-json` is
substantially covered by `scripts/validate_plugins.py`, which parses every plugin
manifest, `marketplace.json`, and `hooks.json` in pre-commit and in CI — but not
by the eval and router data files, which nothing else parses at commit time.
`check-merge-conflict` is covered indirectly: a conflict marker in a `.py`, `.json`
or `.yaml` file fails ruff, the validator, or the test suite. `check-added-large-files`
had **no** compensating control; a large file added in that window would have gone in.

**The installation form that works under the restriction.** A checked-in hooks
directory git executes itself, rather than a shim:

```bash
git config core.hooksPath .githooks
# .githooks/pre-commit
#!/bin/sh
exec uv run --no-project --with pre-commit -- python -m pre_commit \
  hook-impl --config=.pre-commit-config.yaml --hook-type=pre-commit -- "$@"
```

The module form (`python -m pre_commit`) is the load-bearing part: it is an
interpreter invocation, not a shim launch. Verified 2026-08-11 in a throwaway
repository, both directions: a clean commit ran `check-json` green, and a commit
carrying malformed JSON was rejected with the hook's own diagnostic — the form is
not merely present, it blocks. Sibling repositories adding commit-time gates
should reach for it only if the plain `uv tool run pre-commit install` path is
actually refused; installing it pre-emptively buys a config that looks present and
is harder to debug.

**A second, live constraint on the same machine class: exported `language: script`
hooks are unusable.** pre-commit resolves such a hook through its entry's shebang,
and `#!/usr/bin/env python3` resolves to the Windows Store app-execution alias,
which exits 9009 with an install advert. Measured 2026-08-11 in a throwaway
consumer repository against every hook this repository exports — `check-uv-hygiene`
included, despite `adapters/pre-commit/craft-floor.yaml` recording it as verified
by a by-URL consumer run — on both the `pre-commit run --all-files` path and the
git-invoked commit path. Resolution census on that machine: `python3` -> the Store
alias (9009); `python` -> a real interpreter; `py` -> a real interpreter;
`/bin/sh` -> not found. The hooks fail closed, so nothing passes hollow. Until the
repository is made pip-installable and the exports move to `language: python`,
Windows consumers should use the local `repo: local` + `language: system` form
that pins the interpreter (recipe in `plugins/experiment-discipline/README.md`).

**Re-verified 2026-08-11 and it did not reproduce.** On the same machine,
`uv tool run pre-commit --version`, `uv run --no-project --with pre-commit --
python -m pre_commit --version`, and each of the three hooks run over the whole
tree (`uv tool run pre-commit run <hook> --all-files`) all succeeded, and a real
commit ran the full pre-commit set green with no `SKIP`. So the skip list is
**not** standing: do not carry `SKIP=…` forward on a new commit without first
reproducing the block. The one skip that remains legitimate is per-commit and
unrelated to application control — the `experiment-rigor-validate` freeze
bootstrap documented in
[`FREEZE.md`](plugins/experiment-discipline/skills/experiment-rigor/examples/rg-2x2/FREEZE.md),
where a frozen record cannot name its own commit sha before that commit exists.

## Conventions

- **Python style** is governed by [`ruff.toml`](ruff.toml): 100-column lines, single
  quotes. `ruff format` + `ruff check --fix` run automatically on commit.
- **Register discipline (all markdown).** `scripts/lint_register.py` gates every
  plugin's markdown in pre-commit and CI. It flags coercive phrasing — commands
  ordering the reader to invoke a skill, importance banners, and runs of three or
  more consecutive all-caps words outside code. One counter-intuitive rule: the word
  "non-negotiable" is flagged only inside a skill's frontmatter `description` (where
  it buys salience), and is fine in body prose. Full doctrine in
  [`skill-authoring`](plugins/humblepowers/skills/skill-authoring/SKILL.md).
- **The end-of-turn format hook is format-only and won't remove your imports.**
  `engineering-discipline`'s PostToolBatch hook runs `ruff format` only; the
  import-removing autofix (`ruff check --fix`) runs at the pre-commit/CI gate, where
  the file is complete — so adding an import in one edit and using it in a later one
  is safe within a session. (If you run `ruff check --fix` *manually* mid-sequence it
  will still strip the not-yet-used import; introduce the symbol and its first use
  together. Do not re-add `check --fix` to the format hook — `test_ruff_format.py`
  guards against it.)
- **Stdlib-first.** Scripts avoid third-party dependencies where practical (heavier
  libs like pandas stay optional). This keeps the harness and scripts runnable with
  nothing to install.
- **ASCII runtime output — any bundled script, not just hooks.** Text a script
  emits at runtime (print, stderr, argparse messages, hook payloads) is ASCII:
  Windows consoles run cp1252, and a cp1252-encoding child meeting a
  utf-8-decoding parent mojibakes even encodable chars (an em dash in one stderr
  message once failed a test environment-dependently and blocked every push).
  Docstrings and comments are exempt; content written to explicitly-UTF-8 files
  takes an `# ascii-ok` comment. Enforced as a ratchet by
  `scripts/ascii_runtime_lint.py` in pre-commit (baseline burn-down tracked).
  When fixing findings, rewrite the line — never round-trip via `untokenize`,
  which reflows the whole file.
- **Tests live beside code.** Every `script.py` ships a `test_script.py` that runs
  under plain `python` (no pytest). `scripts/run_tests.py` discovers them.
- **Every shipped check declares how it was proved able to fail.**
  `scripts/red_proofs.json` classifies every script under `scripts/`,
  `plugins/*/skills/*/scripts/`, `plugins/*/hooks/` and `evals/harness/` as
  **proved** (naming the test function that reddens it), a declared **gap**
  (with why it has none yet), or **exempt** (with why it is not a reject check —
  formatters, fail-open hooks, pure libraries). A script in none of the three
  fails `evals/harness/test_red_proofs.py`, so a new check cannot ship without
  that decision being made. A proof must name a function that actually runs
  under bare `python`: a `def test_x` no runner block reaches is dead code that
  reads as coverage. Three reddening shapes count — a non-zero exit, a non-empty
  findings list from a pure core, and a hook's `decision: block` payload.
  **A new or re-seeded entry is reviewed as evidence, not as configuration** —
  the reviewer opens the named test and confirms it asserts the reject path. The
  gate is a registry, not a detector, by design, so nothing in the mechanism can
  tell a true entry from a plausible one; the first seeding is where a wrong
  entry is cheapest to make and hardest to see, and one shipped in the seeding
  pass itself (a proof that ran, and did not exercise the branch it claimed).
- **A documented env-gate default must match its guard.**
  `scripts/check_gate_claims.py` reads each hook's polarity from the guard
  itself — `os.environ.get(GATE) == '0'` ships on, `== '1'` ships off — and fails
  when a plugin's prose says otherwise, by wrong control value or by an
  "off by default" phrase in the same paragraph. Fenced code is exempt (a
  verification recipe legitimately sets the variable) and so is `CHANGELOG.md`
  (a dated record of what was true then). It exists because
  `compaction-survival`'s body and its cold-start recipe both described the
  re-injection hook as off by default for a full release after it shipped on,
  while the manifest, the script, the tests, the README and the CHANGELOG all
  said otherwise — and a reader who believes a mechanism is inert does not
  reason about what it does.
- **Skills** follow the existing shape: `plugins/<plugin>/skills/<skill>/SKILL.md`
  with a trigger-focused `description` in the frontmatter, plus `references/` for
  on-demand depth and `scripts/` for runnable tools. Use a sibling skill as a model.
- **`AGENTS.md` is generated — never hand-edit it.** It is rendered from
  `SKILL.md` / command / output-style frontmatter by `scripts/gen_agents_md.py`;
  change the frontmatter and re-run
  `uv run --no-project -- python scripts/gen_agents_md.py`. A pre-commit hook and
  CI both run `--check` and fail on a stale or hand-edited file.
- **Trigger datasets live in exactly one place.** `evals/trigger/<skill>.json`, with
  the sealed sets under `evals/trigger/holdout/` and the registration in
  `evals/config.json`. Do not add a per-plugin copy: three such copies existed
  under `plugins/*/evals/` until 2026-08, used a schema the shipped runner rejects
  (no `should_trigger` key), were read by nothing, and could only mislead a reader
  into thinking they were the evidence.
- **A new skill needs a word-budget baseline.** `scripts/validate_plugins.py`
  fails a `SKILL.md` body with no entry in `scripts/word_budget.json`; add the
  one entry by hand. Read current headroom with
  `uv run --no-project -- python scripts/word_budget.py --report` (tightest
  first) rather than counting by hand — there is exactly one counter in this
  repo, and an audit that compared a hand count against the gate's ceiling once
  reported 78 words of headroom where there were zero. (`scripts/word_budget.py --seed` exists, but it rewrites
  *every* baseline from the current tree, so it resets the ratchet — don't use it
  to add a single entry.) Growing an existing body means bumping its baseline in
  the same reviewed diff and naming what the growth displaces.
- **The evaluate-skill engine is mirrored.**
  `evals/harness/{aggregate,claude_runner,grade_tasks,judge,run_all,run_triggers,stats}.py`
  must stay identical to
  `plugins/session-workflow/skills/evaluate-skill/scripts/` — the check compares
  the two line-ending-normalised, so CRLF vs LF is the one difference it lets
  through. Edit the harness copy, then re-copy;
  `evals/harness/test_scripts_in_sync.py` fails the pre-push suite otherwise.
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
- PRs land via a **merge commit**, so your branch's own commits are preserved on
  `main` as authored — write each commit as a clean Conventional Commit line, not
  just the PR title.
- **Stacked PRs:** push the base branch *before* `gh pr create --base <base>` (an
  unpushed base gives `Base sha can't be blank`). Once the base merges, GitHub
  retargets the stacked PR to `main` and its diff narrows to its own commits — no
  rebase dance needed under merge-commit merges.

## Releasing

Claude Code only pulls a plugin update when its version changes. For a
release-worthy change, **bump the semantic `version` in the affected plugin's
`plugin.json`** as part of the PR, and record it in that plugin's
`CHANGELOG.md` under a `## [X.Y.Z] - YYYY-MM-DD` heading. That is the one
heading grammar (adopted 2026-08-29; the older `## X.Y.Z — date` headings were
reformatted in place), so a single parser serves every plugin's changelog.

CI enforces this on every PR: `scripts/check_release_discipline.py` fails a PR
that touches `plugins/<p>/` (that plugin's `CHANGELOG.md`/`README.md` aside)
unless the version is bumped **and** sits as the changelog's top heading. A
change that genuinely ships nothing an installed copy could notice — a
comment-only edit, a test-only refactor — declares itself instead with a
commit-message trailer: `Release-note: none (<reason>)`. The reviewer judges
the reason; the gate only checks that the decision was made.
