# Design: Skill-collection → marketplace + two plugins

**Date:** 2026-06-04
**Author:** Grimaldo Stanzani
**Status:** Approved design — pending spec review, then implementation plan

---

## 1. Goal

Package five hand-built skills into a maintainable, distributable Claude Code
**plugin marketplace**, raising each skill to current best practice (progressive
disclosure, scripts/hooks where deterministic, evals, a freshness loop), while
**preserving the craft already invested** in them. The refactor relocates and
condenses content; it must not dilute discipline.

### Operating principles

1. **Claude Code primary** target environment. Web-chat-only framing is dropped
   or generalized.
2. **Mechanical → mechanical, reasoning → LLM.** Deterministic work (format,
   scaffold, version-check, schema-diff, validate) becomes scripts/hooks.
   Judgment (journaling passes, engineering decisions, discipline) stays in the
   skill body for the model to execute.
3. **Progressive disclosure.** SKILL.md bodies stay lean (target <250 lines,
   hard ceiling 500); bulky/perishable material moves to `references/` one level
   deep, with a table-of-contents in any reference >100 lines.
4. **Preserve load-bearing guidance verbatim** when relocating it: the
   anti-pattern four-question template, the reconstruction test, confidence
   calibration, embedding-aware writing rules, the four data non-negotiables.
5. **Isolate the perishable layer** so freshness mechanisms target a thin
   surface (version pins) and never the durable judgment.

---

## 2. Repository layout

```
skill-collection/                          # the marketplace repo (git)
├── .claude-plugin/
│   └── marketplace.json                   # $schema, owner, 2 plugin entries, categories
├── plugins/
│   ├── engineering-discipline/
│   │   ├── .claude-plugin/plugin.json
│   │   ├── skills/
│   │   │   ├── python-engineering/
│   │   │   │   ├── SKILL.md
│   │   │   │   ├── references/            # existing 8 + trimmed inline blocks
│   │   │   │   ├── scripts/               # scaffold.py, doctor.py, check_versions.py
│   │   │   │   └── stack.toml             # SINGLE SOURCE OF TRUTH for version pins
│   │   │   ├── data-engineering-discipline/
│   │   │   │   ├── SKILL.md
│   │   │   │   ├── references/            # existing 7 (unchanged structure)
│   │   │   │   └── scripts/               # schema_diff.py, parity_check.py, contract_check.py
│   │   │   └── refresh-stack/             # /refresh-stack command (manual-only skill)
│   │   │       └── SKILL.md
│   │   ├── hooks/hooks.json               # ruff-format (PostToolUse), uv-enforce (PreToolUse)
│   │   ├── evals/
│   │   ├── README.md
│   │   └── CHANGELOG.md
│   └── session-workflow/
│       ├── .claude-plugin/plugin.json
│       ├── skills/
│       │   ├── journaling-sessions/
│       │   │   ├── SKILL.md
│       │   │   └── references/            # output-format, reference-ingestion,
│       │   │                              #   coverage-check, writing-for-retrieval,
│       │   │                              #   cogmem-adapter
│       │   ├── context-handoff/
│       │   │   └── SKILL.md
│       │   └── toolkit-awareness/
│       │       ├── SKILL.md
│       │       └── scripts/scan_toolkit.py
│       ├── hooks/hooks.json               # (optional, default-off) SessionStart inventory inject
│       ├── evals/
│       ├── README.md
│       └── CHANGELOG.md
├── .github/workflows/
│   ├── validate.yml                       # PR: claude plugin validate --strict
│   └── currency.yml                       # monthly cron: check_versions → open drift issue
├── docs/
│   ├── specs/2026-06-04-skill-plugin-design.md
│   └── research/                          # the two research reports, kept as reference
│       ├── plugin-best-practices.md
│       └── top-tier-patterns.md
├── README.md                              # what's inside + install one-liner + versioning note
└── .gitignore
```

Both JSON files carry `$schema` (hesreallyhim's unofficial schemas) for editor
validation. `version` is pinned in each `plugin.json` and **bumped every
release** (documented gotcha: an unbumped version means users never receive
updates; never set `version` in both manifest and marketplace entry).

`marketplace.json` categories: `engineering-discipline` → `development`;
`session-workflow` → `productivity`.

**Naming (resolved):** marketplace `name: skill-collection`; repo
`grimaldo-stanzani/skill-collection`. Install one-liner:
`/plugin marketplace add grimaldo-stanzani/skill-collection` then
`/plugin install <plugin>@skill-collection`.

---

## 3. Plugin: `session-workflow`

### 3.1 `journaling-sessions` (was `chat-session-journal`, 1207 lines)

The headline refactor: generalize off mantis, shrink the body ~6×, and make
multi-pass automatic.

**Core/adapter split — file map:**

| File | Contents (generic vs mantis) |
|---|---|
| `SKILL.md` (~200 ln) | Purpose + quality bar (generalized to "useful to a future session/reader"), when-to-produce, **mode selection**, condensed capture frameworks with pointers, the **internal multi-pass loop**, output pointer. |
| `references/output-format.md` | Generic structured envelope: `ENTRY_START/END` markers (separability is a general retrieval principle), entry types (DECISION/FINDING/OBSERVATION/TRADEOFF/HYPOTHESIS/CONTRADICTION/CONNECTION/ANTI_PATTERN), and a **lean metadata set** (type, author, timestamp, area, domains, confidence, refs, summary). Includes the ANTI_PATTERN four-question template **verbatim**. |
| `references/reference-ingestion.md` | The eight-category taxonomy + downstream-use detection (implementation / teaching / cross-project / positioning) + the teaching/positioning entry shapes. Verbatim relocation. |
| `references/coverage-check.md` | The three-axis coverage machinery (source / downstream-use / measurability), scale guidance, the reconstruction test. Generic capture-QA. |
| `references/writing-for-retrieval.md` | Embedding-aware writing rules (front-load distinctive concept, discriminative terms, vary leads, self-contained, prose-over-bullets, substrate similarity, condition-qualify, flag tensions). Generic to any vector store. |
| `references/cogmem-adapter.md` | **Mantis-specific layer:** experience/hypothesis/wisdom model, full cogmem field semantics (visibility, origin taxonomy, occurred_at, language), confidence-**as-promotion-rules** table, VALIDATED/SUPERSEDES markers, "meditation will cluster this," cogmem-specific coverage weightings. |

A non-mantis user gets clean, separable, retrieval-ready entries from the core +
`output-format.md`. A mantis user loads `cogmem-adapter.md` for the full
envelope — **keeping it fully useful for mantis** as required.

**Internal multi-pass loop (replaces the manual "offer a second pass"):**

```
1. Identify mode (implementation vs reference-ingestion);
   if reference-ingestion, detect any declared downstream use.
2. PASS 1 — produce all entries for the chosen framework.
3. SELF-CHECK (silent) against the three coverage axes.
4. If gaps: PASS N+1 adds ONLY the missing entries. Repeat until the
   coverage signals are clean OR a pass cap (3) is reached.
5. Present ONCE: entry count + layer breakdown + "ran K passes; coverage clean."
6. ESCAPE HATCH (Decision ①): the only user-facing offer. If a downstream
   use was declared AND remains thin after the cap, surface ONE targeted
   offer naming the specific axis. Otherwise stop silently.
```

This makes `journaling-sessions` (or `/journal`) do the multiple passes
automatically — the user no longer phrases "do multiple passes focusing on what
needs attention."

**Triggers/description:** rewritten to *what + when + trigger-phrases only*, no
workflow summary, third person, <1536 chars. The skill stays auto- **and**
user-invocable (so `/session-workflow:journaling-sessions` works for manual
runs); an optional short `/journal` command wrapper can be added if desired.

### 3.2 `context-handoff` (was `session-spinoff`)

Generalize off Claude.ai-web. Keep both modes and all context-curation craft
(state facts not references, concrete specifics, omit narrative, self-check),
retargeted at **any fresh context: a new Claude Code session, `spawn_task`, a
teammate, an issue ticket.**

- **SUBTASK** mode — bounded brief, executor returns an artifact, includes a
  `REINTEGRATION_NOTE`.
- **FORK** mode — hand-off that continues independently.
- Output templates: drop Claude.ai phrasing; keep the fenced paste-ready block.
- **Positioning note:** for *in-session* parallel work use Task/subagents; this
  skill is for *portable, cross-session/cross-person* briefs that need
  copy-paste self-containment.
- Auto- and user-invocable; optional short `/subtask` and `/fork` command
  wrappers.
- Description rewritten to triggers-only.

Note: `/refresh-stack` (§5) is the one skill that *is* manual-only
(`disable-model-invocation: true`), since it should never auto-fire.

### 3.3 `toolkit-awareness`

Replace the perishable inventory tables with a live scan; keep only the durable
guidance.

- **`SKILL.md` (thin):** the skill-ownership/routing map, "how to reference the
  toolkit in PR prompts," and the source-of-truth hierarchy. No hand-typed
  inventory tables.
- **`scripts/scan_toolkit.py`:** enumerates `~/.claude/` and `{repo}/.claude/`
  for skills, commands, agents, hooks; prints a table and `--json`. Stdlib only,
  handles missing dirs gracefully.
- **Optional SessionStart hook (Decision ②, default-off):** injects the live
  inventory each session, eliminating staleness for a few hundred tokens.
  Shipped but disabled by default; enabling documented in the plugin README.

---

## 4. Plugin: `engineering-discipline`

### 4.1 `python-engineering`

- **`stack.toml` — single source of truth** for version pins:
  `{ tool = { pypi = "...", pinned_min = "...", category = "...", note = "..." } }`,
  plus pre-commit hook revs and Python EOL targets. SKILL.md/reference prose
  references this rather than hardcoding numbers in multiple places.
- **Trim SKILL.md (~330 → ~250):** move the inline structlog config,
  pydantic-settings block, and `.pre-commit-config.yaml` into references
  (extend existing ones); SKILL.md stays the decision/routing layer.
- **Scripts:**
  - `scaffold.py` — `uv init --lib` + canonical `pyproject.toml` substitutions +
    pre-commit + src layout, with the mandatory name substitutions from the
    Scaffolding Protocol.
  - `doctor.py` — audit an existing project against the standards (src layout,
    ruff single-quote config, uv usage, pip-audit in CI, dependency groups) and
    report pass/fail per check.
  - `check_versions.py` — refactored to read `stack.toml` (currently hardcodes
    its own `TOOLS` dict); keep the PyPI compare + `--json`.
- **Hooks (PEP-723 `uv run` single-file scripts, `${CLAUDE_PLUGIN_ROOT}` paths):**
  - **PostToolUse** matcher `Write|Edit` → `ruff format` + `ruff check --fix` on
    `.py` files. **Non-blocking** (formatting is mechanical, must not halt work).
  - **PreToolUse** matcher `Bash` → **block** `pip install` / `poetry add` /
    `virtualenv` / `python -m venv` (exit 2, "use `uv add` / `uv venv`").
    **Decision ③:** gated to uv projects — fires only when a `uv.lock` or
    `[tool.uv]` is present in the cwd/project; escape hatch `CLAUDE_ALLOW_PIP=1`.
    Never nags in non-uv repos.
- **Point-of-use live verification note:** SKILL.md instructs the model to
  confirm exact current versions against PyPI / context7 when precision matters,
  so a slightly-stale pin never produces wrong output.
- `last-reviewed: YYYY-MM-DD` stamp in the skill.

### 4.2 `data-engineering-discipline`

Structure is already the reference model — keep it. Add the mechanical layer.

- **Scripts (turn `parity-recipes.md` into runnable tools):**
  - `schema_diff.py` — compare columns + dtypes of two tables/frames, report
    additions/removals/retypes.
  - `parity_check.py` — row-count, group-cardinality, null-rate, and aggregate-sum
    diff within tolerance (Polars/pandas; SQL EXCEPT helper).
  - `contract_check.py` — validate a frame against a contract spec
    (schema.yml / Pydantic / JSON Schema shapes from `contract-templates.md`).
- **Hooks (Decision ④):** **scripts-only by default.** Ship an *optional,
  default-off* `Stop`-hook nudge that, when enabled, reminds to run the
  pre-shipping checklist if the turn's diff touched files matching pipeline
  globs. The discipline itself is reasoning and stays in the skill.
- `last-reviewed: YYYY-MM-DD` stamp; light "tool survey may drift" note in
  `community-practices.md`.
- Description: minor tighten (already strong).

---

## 5. Freshness loop (Decision ⑦ — Tier 3)

`engineering-discipline` constantly evolves; SemVer is only the *delivery* leg.
The loop adds detection + LLM-assisted update in front of it. Mostly a
`python-engineering` concern (data-eng principles are durable).

1. **Detect (mechanical):** `check_versions.py` reads `stack.toml`;
   `.github/workflows/currency.yml` runs it on a **monthly cron** and opens a
   GitHub **issue/PR** listing any pin behind latest or any tool past EOL.
   Drift cannot hide.
2. **Update (LLM-assisted):** **`/refresh-stack`** — a manual-only skill
   (`disable-model-invocation: true`, `user-invocable: true`) in
   `engineering-discipline` that:
   - runs `check_versions.py --json`;
   - for each moved tool, fetches changelog/release notes (WebFetch / context7)
     between pinned and latest;
   - classifies each delta: **(a)** version-only bump, **(b)** guidance-affecting
     (proposes a specific prose edit + cites the changelog entry), **(c)**
     ecosystem shift needing human judgment;
   - emits a **reviewable changeset**: a `stack.toml` diff + proposed prose edits
     with rationale + a "needs human decision" list;
   - on approval, applies the **mechanical** `stack.toml` bumps only — **never
     auto-applies guidance edits**;
   - updates `last-reviewed`.
3. **Deliver:** user approves, bumps the plugin `version`, users receive it.

Internal coherence: this *is* `data-engineering-discipline` applied to itself —
"source of truth is observable, not inferred" (verify against PyPI) and "all
change is intentional and traceable" (reviewed changelog diff, never a silent
edit).

---

## 6. Cross-cutting

### 6.1 Descriptions standard (all five)

Rewrite every `description` to **what it does + when to use it + concrete
trigger phrases**, third person, **no workflow summary**, combined
`description`+`when_to_use` **< 1536 chars**. The journaling description is the
worst current offender (embeds workflow, near the cap).

### 6.2 Evals & CI (Decision ⑤ — pragmatic subset now)

- **Trigger evals** (Anthropic JSON format, should-trigger / should-not-trigger)
  for the three skills whose firing is ambiguous: `journaling-sessions`,
  `context-handoff`, `data-engineering-discipline`. Stored in each plugin's
  `evals/`.
- **Description-tuning pass** on all five (skill-creator-style).
- **CI `validate.yml`:** run `claude plugin validate --strict` on every PR.
- **Follow-up (documented, not now):** full `promptfoo` trigger suite + old-vs-new
  regression diff wired into CI.

### 6.3 Distribution & docs

- Per-plugin `README.md` (purpose / skills / install / enable optional hooks) +
  `CHANGELOG.md`.
- Root `README.md`: what's inside, the install one-liner
  (`/plugin marketplace add <owner>/<repo>` then
  `/plugin install <plugin>@<marketplace>`), and the versioning-bump gotcha.
- `docs/research/` holds both research reports.

### 6.4 Git (Decision ⑥)

`git init` done. Commit the spec and subsequent work as we go (needed for
git-based plugin distribution). `.gitignore` excludes `.remember/`, env, caches.

---

## 7. Non-goals (YAGNI)

- No auto-merge of guidance edits — `/refresh-stack` proposes, human approves.
- No full promptfoo CI in the first pass (documented follow-up).
- No runtime fetch of entire skills (only point-of-use *version* verification).
- No multi-harness packaging (Codex/Cursor/Gemini) — Claude Code only.
- No per-skill plugin explosion — two thematic plugins.

---

## 8. Decisions log

| # | Decision | Resolution |
|---|---|---|
| Arch | Packaging | Two thematic plugins under one marketplace repo |
| Env | Target | Claude Code primary |
| Hooks | Philosophy | Mechanical → hooks/scripts; reasoning → skill |
| ① | Journal multi-pass | Internal loop, silent; single targeted offer only if a *declared* downstream use stays thin after cap |
| ② | Toolkit SessionStart hook | Shipped, **default-off**, enable documented |
| ③ | Python installer-block hook | Gated to uv projects; hard block (exit 2) + `CLAUDE_ALLOW_PIP=1` escape hatch |
| ④ | Data-eng hooks | Scripts-only; optional default-off Stop-hook checklist nudge |
| ⑤ | Evals | Pragmatic subset now (3 trigger-eval skills + description tuning + validate CI); full promptfoo follow-up |
| ⑥ | Git | init + commit as we go |
| ⑦ | Freshness | Tier 3 — stack.toml SoT + check_versions + monthly cron + `/refresh-stack` + live-verify note |

---

## 9. Build sequence

1. **Scaffold** — marketplace.json, two plugin.json, `$schema`, README/CHANGELOG
   skeletons, `docs/research/` reports.
2. **`journaling-sessions`** — core/adapter split, references, internal multi-pass
   loop, description. (Highest value.)
3. **`engineering-discipline`** — `python-engineering` (stack.toml, trim, scripts,
   hooks, description) + `data-engineering-discipline` (scripts, stamp, optional
   nudge).
4. **Freshness Tier 3** — `/refresh-stack` skill + `currency.yml` cron.
5. **`toolkit-awareness`** — thin skill + `scan_toolkit.py` + optional hook.
6. **`context-handoff`** — generalize + templates + triggers.
7. **Cross-cutting** — description tuning, eval subset, `validate.yml`, READMEs,
   CHANGELOGs.
8. **Verify** — `claude plugin validate --strict`; smoke-test via
   `claude --plugin-dir`.
```
