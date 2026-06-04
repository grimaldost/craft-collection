# Design panel — round 2 synthesis

A blind 4-lens Opus panel (MINIMALIST / AUDITOR / ADVOCATE / DOMAIN-EXPERT) over
all 7 skills, each lens a fresh subagent blind to the eval results and to the other
lenses, synthesized per-skill by divergence. Run as a workflow (~35 agents); the
review-panel synthesis was recovered on a resume.

## Meta-result

The lenses split in a revealing way: **MINIMALIST consistently found no bugs** (it
scored the prose for redundancy), while **AUDITOR and DOMAIN-EXPERT found the real,
reproduced defects** (they ran the scripts and checked against live docs/CLI). The
behavioral eval rated every skill as working; the panel surfaced ~20 concrete
correctness bugs it structurally could not see. Verdicts: journaling /
context-handoff / python-eng / refresh-stack / review-panel = **minor-tweaks**;
**toolkit-awareness = significant-revision**; data-eng = sound-but-correctness-blocked.

Recurring shape of the divergences: MINIMALIST wants to cut restated prose;
ADVOCATE/DOMAIN-EXPERT want to add concrete artifacts. They target different lines
and reconcile cleanly — *cut the abstract restatement to fund inlining the
load-bearing bits; fix the scripts, then promote them.* No skill needs a rewrite.

## Fixed — verified correctness bugs (commits ebdfc13 scripts, 019f0c0 docs)

**Scripts** (`ebdfc13`, all bundled tests pass, a case added per fix):
- toolkit `scan_toolkit`: `claude plugin list --json` returns `id`-keyed objects
  with no `name`, so every plugin rendered as `? (0.1.0, True)`. Derive the name
  from `id`, drop the leaked `enabled` bool, pull descriptions from each plugin
  manifest; extracted a pure `_plugins_from_json` and fixed the now-5-key self-test.
- data-eng `contract_check`: dtype `int` did `int('1.0')` and rejected
  integer-valued floats (normal CSV/warehouse rendering) → `float(v).is_integer()`.
- data-eng `parity_check`: print the failing null-rate deltas (a null-rate failure
  printed PARITY FAILED with no reason) + caveat that aggregate parity passes a
  sum-preserving row swap.
- python-eng `check_versions`: `is_behind` truncated to (major,minor) so ty's 0.0.x
  drift was invisible; compare the patch too for true 0ver pins (also unblocks
  refresh-stack, which consumes this).
- python-eng `scaffold`: reject digit-leading names that resolve to an unimportable
  package (`3d-tool` → `3d_tool`).

**Docs** (`019f0c0`):
- journaling: removed the phantom `/journal` command (it has no `commands/` entry —
  a regression from this session's offer-routing edit); Qdrant `ef_construct`
  128 → 100 (the real default, and it sat in the "capture defaults correctly"
  section); defined the undefined "layer breakdown" as a breakdown by entry type.
- review-panel: the verdict scale + score axes are fixed once per panel and pasted
  identically into every reviewer, so the promised comparison matrix is buildable.
- context-handoff: reversed "when unsure, include" to a load-bearing-relevance test
  (it contradicted the skill's own attention-degradation thesis — the panel's
  highest-confidence single edit); added a secrets/PII redaction rule; noted the
  human/ticket recipient variant; softened the false "blank slate" line.
- data-eng: corrected the flat-wrong dbt claim ("validates the others in the build
  step regardless") in two files — dbt validates only column names+types at build
  and delegates constraint enforcement to the warehouse; ODCS apiVersion → v3.1.0.
- python-eng: added `foreign_pre_chain` to the structlog `ProcessorFormatter` so
  third-party logs are actually formatted.
- refresh-stack: stamp the review date into the human-visible SKILL.md stamps too,
  from `checked_at`; disclaimed that pre-commit revs are not auto-detected.
- toolkit: run `scan_toolkit.py` via `${CLAUDE_PLUGIN_ROOT}` so it works from cwd.

## Panel corrections (verified false / out of scope)

- **`.pyc` "committed into the distributable"** — false. `git ls-files` shows zero
  tracked `.pyc`/`__pycache__`; `.gitignore` already covers them. They are local
  build cruft, never shipped. (A subagent conflated on-disk with committed.)
- **`setup-uv@v5` / `uv:latest` pinning** — deferred as a judgment call, not a bug:
  `currency_review.md` already records the `uv:latest` Docker-copy pattern as
  deliberately recommended. This is a DOMAIN-EXPERT divergence to weigh, not a
  clear defect, and the exact pin is a currency target (refresh-stack's job).
- **refresh-stack ty 0.0.x carve-out** — made moot by the `is_behind` patch fix,
  which now makes ty drift visible at the source.

## Deferred — editorial / scope divergences (backlog)

Per the agreed scope (fix correctness, defer subjective trim/expand). All are
quality improvements, none are bugs:

- **journaling:** reconcile the pass-1-under-captures provenance stats (promote a
  hedged firm version into SKILL.md step 4, drop the unsourced integers, delete the
  reference-file restatement); inline the loop's mechanical trip-wires + the
  anti-pattern four-question scaffold into SKILL.md; qualify embedder-specific
  mechanics as bi-encoder heuristics; trim the opening thesis/offer-section to fund
  the inlining; 2026-stack hand-off notes (forgetting/decay, graph-extractability,
  PII boundary).
- **context-handoff:** add a `## Done when` acceptance-criteria block + an
  escalation line to both templates; promote the zero-context self-check into a
  numbered workflow gate; harvest MINIMALIST's non-conflicting cuts.
- **toolkit:** resolve the `--session-start` hook half-state (wire+document or
  delete); add MCP/LSP servers + plugin token-cost to the toolkit model; trim the
  4×-restated ownership axiom and ground the prompt-authoring rules with one example.
- **data-eng:** surface the scripts early + wire them to the done-gate (after the
  script fixes, which shipped); halve `principles.md` (delete the 22 per-scenario /
  22 LLM-gotcha blocks); dedupe war-stories to one canonical file; trim
  `community-practices.md` to a currency-delta sheet; fix the two unsound parity
  recipes (non-unique-key sort; Recipe 5 return annotation); column-level
  `deprecation_date`; empty-dataset row-count floor.
- **python-eng:** lead the scaffolding protocol with the scripts; pin `setup-uv` /
  `uv:latest`; reconcile the two pyproject sources of truth; right-size async
  (`asyncio_mode='strict'`) and per-module `ignore_missing_imports`; ty-as-local /
  mypy-as-gate; money `float` → `Decimal` in observability; enforce the Google
  docstring convention the config mandates; trim `ecosystem_rationale.md` sales
  pitch (keep the architecture sections).
- **refresh-stack:** relocate-and-compress the Guardrails framing to an opening
  hook; add a freshness severity gradient (the 14-of-18 day-one wall); align the
  `context7` reference with `allowed-tools`; fix the stale "TOOLS dict" line.
- **review-panel:** add a before/after neutral-brief example + a pre-fire
  self-check; make the cost gate executable with a heuristic; give the default
  quartet (Auditor / Domain-Expert) inline stances or rename to a pack; name the
  Task tool + a subagent-availability pre-flight; require each reviewer to quote a
  line from the artifact; collapse the redundant guard-rail prose.

## Workflow notes

35 agents, two runs (first run + a resume) needed to get all 7 syntheses: the
schema-bound synthesis agents intermittently failed to call StructuredOutput under
load (one synth failed the first run, four failed the resume). Between the two runs
all 7 skills are covered. Lesson for the harness: schema-forced synthesis agents
want a retry/fallback, and a resume re-runs more than the single failed call.
