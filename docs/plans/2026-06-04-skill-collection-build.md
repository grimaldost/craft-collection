# Skill-collection Plugin Marketplace — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended here — the skill refactors are judgment-heavy and benefit from accumulated context) or superpowers:subagent-driven-development for the isolated code tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn five loose skill folders into a git-distributed Claude Code marketplace (`grimaldo-stanzani/skill-collection`) holding two plugins — `engineering-discipline` and `session-workflow` — each at current best practice.

**Architecture:** Monorepo marketplace (`.claude-plugin/marketplace.json`) → two plugins under `plugins/`. Mechanical work (format, scaffold, version-check, schema-diff, validate) → scripts/hooks; reasoning (journaling passes, engineering judgment) → skill bodies. Perishable version pins isolated in `stack.toml` behind a detect→update→deliver freshness loop.

**Tech Stack:** Markdown skills + references, Python 3.10+ stdlib scripts, PEP-723 `uv run` single-file hooks, GitHub Actions, `claude plugin validate`.

**Source of content:** the existing folders (`chat-session-journal/`, `session-spinoff/`, `code-toolkit-awareness/`, `python-engineering/`, `data-engineering-discipline/`) are the raw material. Refactor **relocates and condenses; it must not dilute** the craft (anti-pattern template, reconstruction test, confidence calibration, embedding-aware rules, the four data non-negotiables stay verbatim in their new homes).

**Reference:** [docs/specs/2026-06-04-skill-plugin-design.md](../specs/2026-06-04-skill-plugin-design.md) — the approved design and decisions log.

---

## Conventions

- After each task: run its **validation gate**, then **commit** with a Conventional-Commits message.
- Validation gate `VALIDATE` = `claude plugin validate ./plugins/<plugin>` if the CLI is available; else fall back to: JSON parses, frontmatter present, references resolve, SKILL.md ≤ 250 lines, combined description ≤ 1536 chars.
- Python scripts: stdlib-only unless noted; `from __future__ import annotations`; single quotes; handle their own errors (no bare failures); justify every constant in a comment.
- Keep the original folders in place until Phase 9 deletes them, so nothing is lost mid-refactor.

---

## Phase 0 — Marketplace scaffold

### Task 0.1: Marketplace manifest

**Files:** Create `.claude-plugin/marketplace.json`

- [ ] Write the manifest:

```json
{
  "$schema": "https://raw.githubusercontent.com/hesreallyhim/claude-code-json-schema/main/marketplace.schema.json",
  "name": "skill-collection",
  "owner": { "name": "Grimaldo Stanzani", "email": "grimaldosj93@gmail.com" },
  "metadata": { "pluginRoot": "./plugins" },
  "plugins": [
    { "name": "engineering-discipline", "source": "engineering-discipline", "category": "development",
      "description": "Modern Python + stack-agnostic data-engineering discipline, with mechanical enforcement and a self-refreshing toolchain.",
      "keywords": ["python", "uv", "ruff", "data-engineering", "data-contract", "pipeline"] },
    { "name": "session-workflow", "source": "session-workflow", "category": "productivity",
      "description": "Session journaling, context hand-off briefs, and live toolkit awareness for Claude Code.",
      "keywords": ["journal", "handoff", "session", "knowledge-capture", "toolkit"] }
  ]
}
```

- [ ] **VALIDATE:** `python -c "import json,sys; json.load(open('.claude-plugin/marketplace.json'))"` → no error.
- [ ] **Commit:** `chore: add marketplace manifest`

### Task 0.2: Plugin manifests

**Files:** Create `plugins/engineering-discipline/.claude-plugin/plugin.json` and `plugins/session-workflow/.claude-plugin/plugin.json`

- [ ] engineering-discipline manifest (version starts at `0.1.0`):

```json
{
  "$schema": "https://raw.githubusercontent.com/hesreallyhim/claude-code-json-schema/main/plugin.schema.json",
  "name": "engineering-discipline",
  "displayName": "Engineering Discipline",
  "version": "0.1.0",
  "description": "Modern Python engineering standards and stack-agnostic data-engineering discipline, with ruff/uv enforcement hooks and a self-refreshing toolchain manifest.",
  "author": { "name": "Grimaldo Stanzani", "email": "grimaldosj93@gmail.com" },
  "repository": "https://github.com/grimaldo-stanzani/skill-collection",
  "license": "MIT",
  "keywords": ["python", "uv", "ruff", "ty", "data-engineering", "data-contract"],
  "hooks": "./hooks/hooks.json"
}
```

- [ ] session-workflow manifest (mirror, `hooks` included but file ships with hooks disabled-by-default — see Task 3.3):

```json
{
  "$schema": "https://raw.githubusercontent.com/hesreallyhim/claude-code-json-schema/main/plugin.schema.json",
  "name": "session-workflow",
  "displayName": "Session Workflow",
  "version": "0.1.0",
  "description": "Capture session knowledge into structured entries, author paste-ready hand-off briefs, and keep live awareness of the installed toolkit.",
  "author": { "name": "Grimaldo Stanzani", "email": "grimaldosj93@gmail.com" },
  "repository": "https://github.com/grimaldo-stanzani/skill-collection",
  "license": "MIT",
  "keywords": ["journal", "handoff", "session", "knowledge-capture", "toolkit"]
}
```

- [ ] **VALIDATE:** both files parse as JSON.
- [ ] **Commit:** `chore: add plugin manifests`

### Task 0.3: Preserve research

**Files:** Create `docs/research/plugin-best-practices.md`, `docs/research/top-tier-patterns.md`

- [ ] Save the two research reports (already produced this session) verbatim, fixing HTML entities (`&amp;`→`&`, `&lt;`→`<`, `&gt;`→`>`) and stripping agent preambles.
- [ ] **Commit:** `docs: save plugin research reports`

---

## Phase 1 — session-workflow / journaling-sessions (highest value)

Content-map source: `chat-session-journal/SKILL.md` (1207 lines). Split per spec §3.1. **Preserve verbatim:** the ANTI_PATTERN four-question template + example, the confidence-calibration table, the reconstruction test, the embedding-aware writing rules, the eight-category taxonomy.

### Task 1.1: Create skill dir + references skeleton

**Files:** Create `plugins/session-workflow/skills/journaling-sessions/references/` (empty dir placeholder)

- [ ] No commit yet (empty dirs); proceed to 1.2.

### Task 1.2: `references/output-format.md`

**Files:** Create `plugins/session-workflow/skills/journaling-sessions/references/output-format.md`

- [ ] Content (relocate, generic — drop cogmem framing): the `--- ENTRY_START ---`/`--- ENTRY_END ---` envelope + "why explicit markers" rationale; the **lean** metadata block (`type, author, timestamp, occurred_at?, area, domains, confidence, refs?, summary?`); the eight entry-type definitions; the ANTI_PATTERN four-question template + worked example **verbatim**; area/domains guidance.
- [ ] Add a TOC (file > 100 lines).
- [ ] **VALIDATE:** TOC present; no `cogmem`/`meditation`/`visibility` tokens (those belong in the adapter).

### Task 1.3: `references/reference-ingestion.md`

**Files:** Create `.../references/reference-ingestion.md`

- [ ] Relocate verbatim: the reference-ingestion mode signals, the **eight-category taxonomy** with all cross-domain examples, downstream-use detection (implementation/teaching/cross-project/positioning) and the per-use required entry shapes.
- [ ] Add TOC.

### Task 1.4: `references/coverage-check.md`

**Files:** Create `.../references/coverage-check.md`

- [ ] Relocate: the three-axis coverage check (source / downstream-use / measurability) with all signals, the reconstruction test, scale guidance, multi-arc/checkpoint guidance. Reframe the user-facing "offer a second pass" into the **internal-loop self-check criteria** (the SKILL.md drives the loop; this file is the checklist it runs).
- [ ] Add TOC.

### Task 1.5: `references/writing-for-retrieval.md`

**Files:** Create `.../references/writing-for-retrieval.md`

- [ ] Relocate verbatim the "Writing for the embedder" + "Writing guidance" rules, generalized to "any vector-retrieval store" (keep MiniLM/BM25 as concrete examples, not as the only target).
- [ ] Add TOC.

### Task 1.6: `references/cogmem-adapter.md` (the mantis layer)

**Files:** Create `.../references/cogmem-adapter.md`

- [ ] Content (everything mantis-specific): experience/hypothesis/wisdom layer model; the full cogmem field semantics (`visibility`, `origin` taxonomy incl. `meditation`, `occurred_at`, `language`, `author` privacy rule); the **confidence-as-promotion-rules** table verbatim; the VALIDATED and SUPERSEDES markers + who-applies rules; cogmem-specific coverage weightings; the "meditation will cluster this against future sessions" quality framing.
- [ ] Header note: "Load this only when journaling for mantis/cognitive-memory. The generic core + output-format.md is sufficient for any other use."
- [ ] Add TOC.

### Task 1.7: `SKILL.md` (the lean core, ~200 lines)

**Files:** Create `plugins/session-workflow/skills/journaling-sessions/SKILL.md`

- [ ] Frontmatter — rewritten description (what + when + triggers ONLY, third person, ≤ 1536 chars, **no workflow summary**). Draft:

```yaml
---
name: journaling-sessions
description: Capture knowledge from a work or reference-reading session into structured, separable, retrieval-ready entries. Use when the user says "journal", "log this", "wrap up", "session summary", "capture what we learned", or "create registries for everything", and proactively when a substantive session is ending after 3+ decisions, findings, or ingested reference items. Covers implementation/decision sessions and end-to-end reference ingestion. For mantis/cognitive-memory output, also load references/cogmem-adapter.md. Not for quick Q&A or sessions with no novel knowledge; not for consolidating prior journals (that is meditation).
---
```

- [ ] Body sections (condensed, each pointing to its reference):
  1. What this captures and why (generalized quality bar: "useful to a future session/reader/retrieval"); the three knowledge kinds (conclusions / process / perceptions).
  2. When to produce.
  3. Pick the mode (implementation vs reference-ingestion) + detect downstream use → `reference-ingestion.md`.
  4. **The automatic multi-pass workflow** (the spec §3.1 loop), stated as the default behaviour: capture → silent self-check vs `coverage-check.md` → add missing → repeat to clean or cap 3 → present once ("ran K passes; coverage clean") → single targeted offer only if a *declared* downstream use stays thin.
  5. How to produce (implementation mode): the Conclusions/Process/Perceptions questions (kept inline — they're the core).
  6. How to produce (reference-ingestion mode): one paragraph + pointer to `reference-ingestion.md`.
  7. Output: pointer to `output-format.md`; "for mantis, also `cogmem-adapter.md`".
  8. Writing quality: 4-5 load-bearing rules inline (concrete, reasoning-inline, one-idea-per-entry, anti-patterns-are-gold, reconstruction test) + pointer to `writing-for-retrieval.md`.

- [ ] **VALIDATE:** SKILL.md ≤ 250 lines; description ≤ 1536 chars (`python -c "print(len(open(...).read()))"` on the description block); all five `references/*.md` linked exactly once and one level deep.
- [ ] **Commit:** `feat(session-workflow): add journaling-sessions skill (generic core + mantis adapter, auto multi-pass)`

---

## Phase 2 — session-workflow / context-handoff

Content-map source: `session-spinoff/SKILL.md`. Generalize off Claude.ai-web (spec §3.2).

### Task 2.1: `SKILL.md`

**Files:** Create `plugins/session-workflow/skills/context-handoff/SKILL.md`

- [ ] Rewritten description (triggers only):

```yaml
---
name: context-handoff
description: Author a paste-ready, self-contained brief that hands work to a fresh context — a new Claude Code session, a spawned task, a teammate, or an issue ticket. Use on "/subtask", "/fork", "/spinoff", "spin this off", "hand this off", "branch off", "offload this", "new session for this", or when curating a context slice to continue or delegate work elsewhere. Two modes: SUBTASK (bounded brief, an artifact comes back) and FORK (continues independently). For in-session parallel work, prefer Task/subagents instead.
---
```

- [ ] Body: keep the two-mode model, the context-extraction craft (state facts not references, concrete specifics, preserve constraints, omit narrative, when-unsure-include), the self-check, and both output templates — with Claude.ai phrasing removed and "fresh Claude Code session / teammate / issue" substituted. Keep the worked examples (retarget wording). Add the positioning note (Task/subagents for in-session; this for portable cross-session/person briefs).
- [ ] **VALIDATE:** SKILL.md ≤ 250 lines; description ≤ 1536 chars; no "Claude.ai web chat only" claims remain.
- [ ] **Commit:** `feat(session-workflow): add context-handoff skill (generalized off web-chat)`

---

## Phase 3 — session-workflow / toolkit-awareness

### Task 3.1: `scripts/scan_toolkit.py` (TDD)

**Files:** Create `plugins/session-workflow/skills/toolkit-awareness/scripts/scan_toolkit.py` and `.../scripts/test_scan_toolkit.py`

- [ ] **Step 1 — failing test:** create a temp dir tree mimicking `.claude/skills/<x>/SKILL.md`, `.claude/commands/<y>.md`, `.claude/agents/<z>.md`, `.claude/hooks/`; assert `scan(root)` returns a dict with those names.

```python
def test_scan_enumerates_components(tmp_path):
    (tmp_path / '.claude/skills/foo').mkdir(parents=True)
    (tmp_path / '.claude/skills/foo/SKILL.md').write_text('---\nname: foo\n---\n')
    (tmp_path / '.claude/commands').mkdir(parents=True)
    (tmp_path / '.claude/commands/bar.md').write_text('# bar')
    out = scan([tmp_path])
    assert 'foo' in {s['name'] for s in out['skills']}
    assert 'bar' in {c['name'] for c in out['commands']}
```

- [ ] **Step 2:** run, expect FAIL (no `scan`).
- [ ] **Step 3 — implement:** `scan(roots)` walks each root's `.claude/{skills,commands,agents,hooks}`; for skills, read the `name:` from frontmatter (fallback to dir name) + first line of `description`; return `{skills, commands, agents, hooks}` lists. Missing dirs → empty, never raise. CLI: default roots = `~/.claude` and `<cwd>/.claude`; `--json` prints machine-readable, else a grouped table.
- [ ] **Step 4:** run tests → PASS.
- [ ] **VALIDATE:** `python scan_toolkit.py` prints a table without error on the real machine; `--json` parses.

### Task 3.2: `SKILL.md` (thin)

**Files:** Create `plugins/session-workflow/skills/toolkit-awareness/SKILL.md`

- [ ] Content (durable only, from `code-toolkit-awareness/SKILL.md`): the **skill-ownership / routing map**, "How to reference the toolkit in PR prompts," the source-of-truth hierarchy. **Delete** the hand-typed inventory tables; replace with: "Run `scripts/scan_toolkit.py` for the live inventory of installed skills/commands/agents/hooks."
- [ ] Rewritten description (triggers only — "what tools/agents/commands/hooks do I have", planning Claude Code work, referencing quality gates in specs).

### Task 3.3: Optional SessionStart hook (default-off)

**Files:** Create `plugins/session-workflow/hooks/hooks.json`

- [ ] Ship the hook **commented in the README as opt-in**; the `hooks.json` contains the wiring but the entry is gated behind an env flag so it is inert unless the user sets it:

```json
{
  "description": "Optional: inject a live toolkit inventory at session start. Inert unless TOOLKIT_AWARENESS_INJECT=1.",
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command",
        "command": "python",
        "args": ["${CLAUDE_PLUGIN_ROOT}/skills/toolkit-awareness/scripts/scan_toolkit.py", "--session-start"] } ] }
    ]
  }
}
```

- [ ] `scan_toolkit.py --session-start`: if `TOOLKIT_AWARENESS_INJECT` unset → exit 0 silently; else print a compact inventory to stdout (becomes injected context).
- [ ] **VALIDATE:** `VALIDATE` on session-workflow passes; hook is inert by default.
- [ ] **Commit:** `feat(session-workflow): add toolkit-awareness (live scan + thin routing skill)`

---

## Phase 4 — engineering-discipline / python-engineering

### Task 4.1: Relocate existing content

**Files:** Move `python-engineering/{SKILL.md,references/,scripts/}` → `plugins/engineering-discipline/skills/python-engineering/`

- [ ] `git mv` the folder contents into the new path. Commit: `refactor: relocate python-engineering into engineering-discipline plugin`

### Task 4.2: `stack.toml` (single source of truth)

**Files:** Create `plugins/engineering-discipline/skills/python-engineering/stack.toml`

- [ ] Encode the pins currently hardcoded in `check_versions.py` `TOOLS` + the pre-commit revs + a `[python]` EOL section:

```toml
[meta]
last_reviewed = "2026-06-04"

[tools.ruff]
pypi = "ruff"
pinned_min = "0.15"
category = "lint"
note = "single-quote formatter+linter must stay aligned"
# ... one block per tool from check_versions TOOLS ...

[precommit]
"pre-commit-hooks" = "v5.0.0"
"ruff-pre-commit" = "v0.15.7"

[python]
supported = ["3.12", "3.13", "3.14"]
eol_watch = "3.12"
```

### Task 4.3: Refactor `check_versions.py` to read `stack.toml` (TDD)

**Files:** Modify `.../scripts/check_versions.py`; create `.../scripts/test_check_versions.py`

- [ ] **Step 1 — failing test:** write `stack.toml` fixture; assert `load_tools(path)` returns `{'ruff': '0.15', ...}` (replaces the inline `TOOLS` dict).
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** add `tomllib` (3.11+) loader; replace `TOOLS`/`PRECOMMIT_HOOKS` constants with reads from `stack.toml`; keep PyPI fetch + table/`--json` unchanged. Network call stays out of the unit test (test only the loader + the stale-comparison logic on a stubbed result).
- [ ] **Step 4:** tests PASS.
- [ ] **VALIDATE:** `python check_versions.py` still prints the table.

### Task 4.4: `scaffold.py` (TDD on the pure parts)

**Files:** Create `.../scripts/scaffold.py` and `test_scaffold.py`

- [ ] **Step 1 — failing test:** `render_pyproject(name='my-cool-tool')` returns a string containing `name = "my-cool-tool"` and `known-first-party = ["my_cool_tool"]` (the mandatory substitutions).
- [ ] **Step 2/3/4:** implement name resolution (kebab/snake/Pascal) + `render_pyproject()` from the canonical template; the side-effecting part (`uv init --lib`, write files, `pre-commit install`) lives behind a `main()` that calls the pure renderer. Test only the pure renderer.
- [ ] **VALIDATE:** unit tests pass.

### Task 4.5: `doctor.py` (TDD)

**Files:** Create `.../scripts/doctor.py` and `test_doctor.py`

- [ ] **Step 1 — failing test:** build a temp project dir (src layout, a `pyproject.toml` missing `[tool.ruff.format] quote-style`), assert `audit(dir)` returns a failing check `ruff-single-quote` and a passing `src-layout`.
- [ ] **Step 2/3/4:** implement checks: src-layout present, `[tool.uv]`/`uv.lock` present, ruff single-quote config, `[dependency-groups]` (not optional-deps for dev), pip-audit referenced in CI. Each check returns `(id, ok, detail)`. CLI prints a pass/fail table; exit 1 if any fail.
- [ ] **VALIDATE:** unit tests pass.

### Task 4.6: Trim `SKILL.md`

**Files:** Modify `.../skills/python-engineering/SKILL.md`; extend `references/`

- [ ] Move the inline `structlog` config, `pydantic-settings` block, and `.pre-commit-config.yaml` into their reference files (observability.md / a new config snippet ref); leave a 3-line pointer each.
- [ ] Replace hardcoded version numbers in prose with "see `stack.toml`" where listing pins.
- [ ] Add `last-reviewed` note + the point-of-use live-verify instruction (verify exact versions vs PyPI/context7 when precision matters).
- [ ] Tighten the description if needed (already a good folded block; confirm ≤ 1536 chars).
- [ ] **VALIDATE:** SKILL.md ≤ 250 lines; references resolve.
- [ ] **Commit:** `feat(engineering-discipline): stack.toml SoT + scaffold/doctor scripts + trimmed python-engineering`

---

## Phase 5 — engineering-discipline / hooks

### Task 5.1: `ruff_format` hook (PostToolUse, non-blocking) — TDD

**Files:** Create `plugins/engineering-discipline/hooks/ruff_format.py` (PEP-723) and `test_ruff_format.py`

- [ ] **Step 1 — failing test:** feed a fake PostToolUse stdin JSON with `tool_input.file_path` ending `.py`; assert the script *selects* that file (test the `target_file(payload)` pure function), and ignores non-`.py`.
- [ ] **Step 2/3/4:** PEP-723 header (`# /// script` … `dependencies = []` `# ///` — calls `uv run ruff` via subprocess, ruff not a py dep). Read stdin JSON; if `.py`, run `ruff format <f>` then `ruff check --fix <f>`; always `exit 0` (non-blocking). Errors print to stderr, never block.
- [ ] **VALIDATE:** `echo '<payload>' | uv run hooks/ruff_format.py` formats a scratch `.py`.

### Task 5.2: `uv_enforce` hook (PreToolUse, blocking) — TDD

**Files:** Create `plugins/engineering-discipline/hooks/uv_enforce.py` and `test_uv_enforce.py`

- [ ] **Step 1 — failing test:** the pure `verdict(command, cwd_has_uv, allow_env)` function:
  - `verdict('pip install x', True, False)` → `block`
  - `verdict('pip install x', False, False)` → `allow` (not a uv project)
  - `verdict('pip install x', True, True)` → `allow` (`CLAUDE_ALLOW_PIP=1`)
  - `verdict('uv add x', True, False)` → `allow`
- [ ] **Step 2/3/4:** match `pip install`, `pip3 install`, `poetry add|install`, `virtualenv`, `python -m venv`; "uv project" = `uv.lock` or `[tool.uv]` in `pyproject.toml` at cwd. On block: print guidance to stderr (`use 'uv add' / 'uv venv'`) and `exit 2`; else `exit 0`. Read `CLAUDE_ALLOW_PIP` from env.
- [ ] **VALIDATE:** unit tests pass; a manual `pip install` payload in a uv-project fixture exits 2.

### Task 5.3: `hooks.json` wiring

**Files:** Create `plugins/engineering-discipline/hooks/hooks.json`

- [ ] Wire PostToolUse `Write|Edit` → `ruff_format.py`; PreToolUse `Bash` → `uv_enforce.py`, both via `uv run` + `${CLAUDE_PLUGIN_ROOT}` paths.
- [ ] **VALIDATE:** `VALIDATE` on engineering-discipline passes.
- [ ] **Commit:** `feat(engineering-discipline): ruff-format + uv-enforce hooks`

---

## Phase 6 — engineering-discipline / data-engineering-discipline

### Task 6.1: Relocate

**Files:** `git mv data-engineering-discipline/{SKILL.md,references/}` → `plugins/engineering-discipline/skills/data-engineering-discipline/`. Commit: `refactor: relocate data-engineering-discipline into plugin`

### Task 6.2–6.4: Scripts (TDD each)

**Files:** Create `.../scripts/{schema_diff.py,parity_check.py,contract_check.py}` + tests

- [ ] `schema_diff.py` — `diff(schema_a, schema_b)` returns added/removed/retyped columns. Test with two dict schemas. CLI reads two CSV/parquet headers (pandas optional; degrade to CSV header compare if pandas absent).
- [ ] `parity_check.py` — `compare(df_a, df_b, keys, tol)` returns row-count delta, group-cardinality delta, per-column null-rate delta, numeric aggregate-sum delta within `tol`. Test on two small in-memory tables (list-of-dicts; pandas if available). Exit 1 if any out of tolerance.
- [ ] `contract_check.py` — `validate(rows, contract)` where contract = `{column: {dtype, nullable, enum?, unique?}}`; returns violations. Test pass + fail fixtures.
- [ ] Each: stdlib-first, pandas/polars optional with graceful degrade; justify tolerances in comments.

### Task 6.5: Stamps + optional nudge + description

**Files:** Modify `.../data-engineering-discipline/SKILL.md`, `references/community-practices.md`; extend `plugins/engineering-discipline/hooks/hooks.json`

- [ ] Add `last-reviewed: 2026-06-04`; add a one-line "tool survey may drift; principles are stable" note to `community-practices.md`.
- [ ] Add the **optional, default-off** Stop-hook nudge to `hooks.json`: a `stop_nudge.py` that, only if `DATAENG_CHECKLIST_NUDGE=1` and the session diff touched files matching pipeline globs, prints a reminder to run the pre-shipping checklist (else exit 0 silently).
- [ ] Tighten the description (already strong).
- [ ] **VALIDATE:** `VALIDATE` passes; nudge inert by default.
- [ ] **Commit:** `feat(engineering-discipline): data-engineering scripts (schema-diff/parity/contract) + stamps`

---

## Phase 7 — Freshness loop (Tier 3)

### Task 7.1: `/refresh-stack` skill (manual-only)

**Files:** Create `plugins/engineering-discipline/skills/refresh-stack/SKILL.md`

- [ ] Frontmatter: `disable-model-invocation: true`, `user-invocable: true`, `allowed-tools: Bash Read Edit WebFetch`.
- [ ] Body — the detect→classify→propose→deliver workflow from spec §5: run `check_versions.py --json`; for each moved tool fetch changelog (WebFetch/context7) between pinned↔latest; classify each delta (version-only / guidance-affecting / needs-human); emit a reviewable changeset (a `stack.toml` diff + proposed prose edits with cited rationale + a needs-human list); on approval apply **only** the mechanical `stack.toml` bumps; update `[meta] last_reviewed`. **Never auto-apply guidance edits.**
- [ ] **VALIDATE:** description ≤ 1536; skill is manual-only.

### Task 7.2: Currency cron

**Files:** Create `.github/workflows/currency.yml`

- [ ] Monthly `schedule` cron + `workflow_dispatch`. Steps: checkout; setup Python; `python plugins/engineering-discipline/skills/python-engineering/scripts/check_versions.py --json > drift.json`; a small inline step that opens/updates a GitHub issue via `gh` if any tool is behind or past EOL. Use `GITHUB_TOKEN`.
- [ ] **Commit:** `feat(engineering-discipline): Tier-3 freshness loop (/refresh-stack + monthly currency cron)`

---

## Phase 8 — Cross-cutting

### Task 8.1: Description-tuning pass (all five)

**Files:** the five `SKILL.md` frontmatters

- [ ] For each: confirm what+when+triggers, third person, no workflow summary, combined ≤ 1536 chars. Fix any that miss.

### Task 8.2: Trigger evals

**Files:** Create `plugins/session-workflow/evals/*.json`, `plugins/engineering-discipline/evals/*.json`

- [ ] Anthropic-format JSON eval files (≥3 should-trigger + ≥3 should-not-trigger queries) for `journaling-sessions`, `context-handoff`, `data-engineering-discipline`. Each: `{ "skills": [...], "query": "...", "expected_behavior": ["triggers <skill>" | "does not trigger <skill>"] }`.

### Task 8.3: Validate CI

**Files:** Create `.github/workflows/validate.yml`

- [ ] On PR/push: checkout, setup, run `claude plugin validate ./plugins/engineering-discipline --strict` and `./plugins/session-workflow --strict` (if the CLI is installable in CI; else a Python structural validator script as fallback).

### Task 8.4: Docs

**Files:** Create root `README.md`, `plugins/*/README.md`, `plugins/*/CHANGELOG.md`

- [ ] Root README: what's inside, the install one-liner (`/plugin marketplace add grimaldo-stanzani/skill-collection` then `/plugin install <plugin>@skill-collection`), the version-bump gotcha, how to enable the optional hooks.
- [ ] Per-plugin README: purpose, skills list, scripts, hooks (+ how to enable optional ones), how to run `/refresh-stack`.
- [ ] CHANGELOGs seeded at `0.1.0`.

### Task 8.5: Final verify + cleanup

- [ ] Delete the five original top-level folders (content now lives under `plugins/`): `chat-session-journal/`, `session-spinoff/`, `code-toolkit-awareness/`, `python-engineering/`, `data-engineering-discipline/`. (They were relocated via `git mv` in Phases 4/6; journaling/handoff/toolkit were rewritten fresh, so remove their originals now.)
- [ ] Run `claude plugin validate ./plugins/<each> --strict` (or fallback validator). Smoke-test: `claude --plugin-dir ./plugins/session-workflow --plugin-dir ./plugins/engineering-discipline`, confirm skills appear and `/refresh-stack` is manual-only.
- [ ] **Commit:** `docs: READMEs, changelogs, evals, validate CI; remove relocated originals`

---

## Self-Review (run after writing, before execution)

**Spec coverage** — every spec section maps to a task:
- §2 layout → Phase 0 + relocations (4.1, 6.1). §3.1 journaling split → Phase 1 (1.2–1.7). §3.2 handoff → Phase 2. §3.3 toolkit → Phase 3. §4.1 python (stack.toml/trim/scripts/hooks) → Phases 4–5. §4.2 data (scripts/stamp/nudge) → Phase 6. §5 freshness → Phase 7. §6.1 descriptions → 8.1. §6.2 evals/CI → 8.2/8.3. §6.3 docs → 8.4. §6.4 git → throughout. §7 non-goals → respected (no auto-merge, no full promptfoo, no multi-harness). §8 decisions ①–⑦ → 1.7(①), 3.3(②), 5.2(③), 6.5(④), 8.2/8.3(⑤), commits(⑥), Phase 7(⑦). **No gaps.**

**Placeholder scan:** code tasks carry real test assertions + implementation specs; markdown tasks carry content-maps + mechanical validation gates (the honest substitute for TDD on prose, flagged up front).

**Type consistency:** `scan()`, `load_tools()`, `render_pyproject()`, `audit()`, `target_file()`, `verdict()`, `diff()`, `compare()`, `validate()` each defined once in their task and referenced consistently.
```
