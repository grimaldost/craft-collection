# Skill design review — 4-reviewer Opus 4.8 panel (synthesis)

Four independent Opus 4.8 reviewers, each a distinct critical lens (MINIMALIST,
AUDITOR, ADVOCATE, DOMAIN-EXPERT), reviewed all six skills blind to each other and
to the behavioral eval. Prompt: `evals/review/skill-design-review-prompt.md`.
Agent ids: ad1393caca397db5b · a1d31dfb259ee8f9b · af1719ef20478824b · a1d33c271a0960e63.

## Verdict matrix (Worth-it / Design, out of 10)

| Skill | MINIMALIST | AUDITOR | ADVOCATE | DOMAIN-EXPERT | Consensus |
|---|---|---|---|---|---|
| journaling-sessions | KEEP 8/8 | KEEP 8/7 | KEEP 8/7 | KEEP 9/9 | **KEEP (unanimous, top-3 all)** |
| data-engineering-discipline | KEEP 8/6 | REVISE 7/6 | KEEP 9/8 | KEEP 9/8 | **KEEP — ranked #1 by 3 of 4** |
| python-engineering | REVISE 6/6 | KEEP 6/8 | KEEP 8/8 | KEEP 8/8 | KEEP — currency verified |
| refresh-stack | KEEP 7/8 | KEEP 7/9 | KEEP 7/9 | KEEP 7/9 | **KEEP (unanimous)** |
| context-handoff | REVISE 5/7 | KEEP 7/9 | KEEP 7/9 | KEEP 7/9 | KEEP — best-designed, thinnest value |
| toolkit-awareness | KEEP 7/9 | REVISE 5/7 | REVISE 5/6 | REVISE 5/7 | **REVISE — real bug (3 of 4)** |

**Headline: zero outright CUTs from any reviewer — including the ruthless
minimalist** ("every skill clears the bar once, which is rare"). The collection's
existence is validated; the work is REVISE-in-place.

## Where the panel agreed (act on these)

1. **toolkit-awareness has a real bug, not just a design nit.** The scan script
   only reads `.claude/` dirs and is blind to *plugin-provided* components — three
   reviewers independently ran `scan_toolkit.py` against this repo and got empty
   results, even though everything here ships as a plugin. Its headline "live
   inventory" reports nothing in exactly the packaging model it targets. Fix: merge
   `claude plugin list --json`, or narrow the description to "scans `.claude/` dirs".
2. **data-engineering-discipline has a concrete code bug** (DOMAIN-EXPERT, verified):
   `references/parity-recipes.md` Recipe 6 calls `assert_frame_equal(check_dtype=…,
   rel_tol=…)` — `check_dtype` was renamed `check_dtypes` (Polars 0.20.31) and
   `rel_tol` only exists ≥1.32.3, so it runs on *no* Polars version. Worse, it
   contradicts Principle 8, which uses that exact signature as the canonical
   "verify, don't infer" example. Also `COUNT(DISTINCT (tuple))` isn't portable
   (BigQuery/Postgres reject it).
3. **The two big bodies are bloated** — data-eng states the four non-negotiables
   ~3× (axioms → "Make the discipline visible" → pre-shipping checklist); python-eng
   has reconstructable snippets, a "Senior Python Developer" roleplay preamble, and
   two duplicated `uv` command lists. Trim toward progressive disclosure.
4. **A downstream consumer is missing.** Three reviewers independently flagged that
   journaling-sessions writes a precise envelope for a "cluster → promote"
   consolidation pass that **no skill in the collection performs** — so the
   collection captures knowledge it has no companion skill to compound. The most-
   cited candidate for a 7th skill.

## Where they disagreed (the interesting splits)

- **toolkit-awareness** is the most polarized: MINIMALIST loves it (tiny body, work
  delegated to a script, inert hook) while the other three dock it for the
  plugin-blind scan. Both are right — good *shape*, broken *reach*.
- **context-handoff**: MINIMALIST would demote/merge it (thinnest reconstruction
  case — "the closest to things Opus already does when asked"); the other three rate
  it the **best-designed** skill (9/10 design) and keep it. Tension between "elegant"
  and "necessary."
- **python-engineering** value: MINIMALIST sees ~40% reconstructable filler; the
  DOMAIN-EXPERT verified the currency claims are *correct and current* (uv_build
  default since Jul 2025, ruff 0.15 / PEP 758, ty Dec-2025 beta) and rates it 8/10.

## Triangulation with the behavioral eval

The two methods are complementary — each caught what the other can't:

- **Confirms:** the panel ranks journaling #1–3 with the highest worth scores, which
  *validates* the eval's "journaling usage is under-measured" conclusion — its true
  quality is high.
- **Counters:** the panel worries descriptions are over-broad (false-fire risk), but
  the eval measured **specificity 1.00 on all five** — i.e. no false fires actually
  occur. Measured evidence tempers that worry.
- **Tension:** the round-2 "Make the discipline visible" edit *lifted* data-eng's
  measured correct-usage 0.33→0.67, yet two reviewers flag it as redundant bloat and
  the ADVOCATE warns "name the non-negotiable as you apply it" makes routine answers
  performative. Eval-optimal ≠ design-optimal here — a genuine judgment call.
- **Only the panel found:** the toolkit plugin-blindness bug and the Polars kwargs
  bug — content-correctness issues invisible to a trigger/usage harness.

## Prioritized actions (from both methods)

1. **Fix toolkit-awareness scan** (plugin discovery) or narrow its promise — bug.
2. **Fix data-eng Recipe 6** Polars kwargs + reconcile with Principle 8 — bug.
3. **Trim data-eng SKILL.md** (state axioms once; reconsider/condense "Make the
   discipline visible") and python-eng (drop roleplay preamble + dup uv lists).
4. **Hedge unsourced multipliers** in python-eng ("50× mutations", "10-100×").
5. **Decide on the 7th skill**: a consolidation/recall step that consumes journaling
   entries — closes the memory loop.
6. **Minor**: refresh-stack `allowed-tools` delimiter + `${CLAUDE_PLUGIN_ROOT}` path;
   consider folding it into python-engineering.
