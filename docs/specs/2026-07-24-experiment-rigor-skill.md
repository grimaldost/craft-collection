# Spec — the experiment-rigor skill (humblepowers)

- **Date:** 2026-07-24
- **Status:** ready (DoR passed)
- **Audience:** implementing agents + reviewer
- **Output artifact(s):** `plugins/humblepowers/skills/experiment-rigor/SKILL.md`; `scripts/{stats,validate,render,from_fathom}.py` and their `test_*.py` under that skill (plus `test_mantis_fallback.py`); `templates/{probe,measurement,decision}.yaml`, `templates/schema.json`, and `templates/SCHEMA.md`; `references/{threats-catalog,small-n-stats}.md`; `examples/rg-2x2/{record.yaml,report.md}`; `evals/trigger/experiment-rigor.json`; `evals/trigger/holdout/experiment-rigor.json` and a baseline row in `evals/trigger/holdout/BASELINES.md`; the regenerated `AGENTS.md` index; one row in `plugins/humblepowers/skills/choosing-tools/scripts/router_rules.json`; a baseline in `scripts/word_budget.json`; and a local hook in `.pre-commit-config.yaml`.

## Context

An agent explained a small A/B (the RG-2×2 register/gate factorial) in prose, and
three fresh, isolated frontier readers each reconstructed the narrative but flagged
the same methods holes — the arithmetic did not close (96 stated where the eight
factor-level cells at 12 planned each was never spelled out; the two waves were never
named), the outcome was never operationalized, the rate figures (36/48 with the gate,
18/48 without) carried no denominators, the comparison behind them was inferred, a
post-hoc finding was presented as pre-registered, and no uncertainty was reported.
Methods uncertainty is disqualifying; effect uncertainty is declarable. This spec
builds the discipline that gates the first and structures the second. It implements
the delivery-form decision and invariants recorded in
`docs/adr/0007-experiment-rigor-delivery.md`, and rests on the two research records
`docs/research/2026-07-24-experimental-rigor-and-comprehension-case.md` (the founding
case, Parts 1–3) and `docs/research/2026-07-24-four-traditions-survey.md` (the
transversal synthesis and the role-separation addendum). Those two records are
gitignored (local-only); for grounding portability their sha256 hashes at authoring
time are `654d2ff12482795400b5d5ca1c51014df721214ae0f980f4e883757c2ae32ffe` (the case)
and `07467bb4adb6cabeaf0422ac3f4534114e366b4fadf1ea0da92117484e122dc7` (the survey).
The design is fixed by the synthesis brief; this spec does not reopen it.

## Goal

Ship one rigid skill, `experiment-rigor`, in humblepowers, whose four stdlib-plus-PyYAML
scripts turn a typed `record.yaml` into a validated, derived report across a probe /
measurement / decision tier ladder — every load-bearing rule a gate that exits
non-zero — with the founding RG-2×2 case as both the first chain node and the
acceptance fixture.

## Gate commands

- `uv run --no-project --with pyyaml -- python scripts/run_tests.py` — runs every
  `test_*.py` under `plugins/` and `evals/` (`scripts/run_tests.py:24` `SEARCH_DIRS = ('plugins', 'evals')`).
  This wave changes the canonical test command and the `run-tests` pre-commit hook
  (`.pre-commit-config.yaml:60` `run_tests.py`) to carry `--with pyyaml`, because
  `validate.py`, `render.py`, and `from_fathom.py` parse nested `record.yaml` and depend
  on PyYAML. Each record-parsing test module hard-fails (it never emits the `skip:`
  sentinel that `scripts/run_tests.py:45` `has_sentinel` accepts) when PyYAML is absent,
  so the mechanism spine cannot go green-via-skip.
- `uv run --no-project --with pyyaml -- python scripts/validate_plugins.py` —
  marketplace structure, frontmatter, description cap, line cap, reference resolution,
  and the word-budget ratchet (`scripts/validate_plugins.py:181` `check_budgets`).
- `uv run --no-project python scripts/lint_register.py` — register doctrine over its
  default plugin scope (`scripts/lint_register.py:34` `DEFAULT_SCOPE = ROOT / 'plugins'`);
  this spec's prose is kept plain but sits outside that default scope.
- `uv run --no-project python scripts/word_budget.py` — the per-body ratchet against
  `scripts/word_budget.json`.
- The `agents-md-fresh` pre-commit and CI gate (`.pre-commit-config.yaml:42` `gen_agents_md.py --check`)
  requires `AGENTS.md` to be regenerated in the PR that adds the skill (§4).
- The record-level gates `validate.py` and `render.py --check` run in pre-commit over
  staged `record.yaml` paths (travelling records only), wired in §2.
- The pre-commit hooks `check-merge-conflict` and `check-added-large-files` are
  **skipped on this machine** (Windows Application Control, WinError 4551) with the
  user's standing agreement; every other hook runs.

## Non-goals

- No fathom rebuild in this delivery — a fathom-side run-derived emitter is a possible
  future fathom PR; this spec's bridge reads the fathom ledger directly, so no cross-repo
  edit is part of this series.
- No JSON-LD / RO-Crate / PROV ontology stack — at most ~6 PROV terms adopted as field names.
- No hosted anything — no renderer server, MkDocs site, or tracking DB; a flat file plus one script.
- No second skill — one rigid skill; tier is a field, not a second trigger surface that poaches at report time.
- No auto-comprehension-spawner inside the plugin — the validator enforces the block and its evidence trail; the spawning tooling binds role-generically, and the genuineness of the reads is ceded to review.
- No cross-experiment Beta-Binomial pooling — the posterior is within-experiment only; the cross-experiment chain carries a linked qualitative GRADE update, not arithmetic pooling.

## Invariants touched

All invariants below are recorded in `docs/adr/0007-experiment-rigor-delivery.md`:
record-is-single-source-of-truth (report derived, never hand-edited); a loud-failing
gate per load-bearing rule; schema+tier well-formedness (a rate without both numerator
and denominator fails); declared-cells design-reconciliation; the temporal anchor (a
chronology check whose residual is named); run cross-check equality with a per-tier hand
policy; the small-n CI refusal; threat-coverage over a closed enum; probe refusal; the
`schema_version` freeze read from a machine-readable schema; the decision-tier
comprehension gate (a block-plus-evidence-trail check whose residual is named); the
standing deletion rule for degraded gates; the mantis journal-envelope superset-tolerance
constraint; and the sealed-holdout-before-tuning trigger-dataset discipline. This work
also touches four existing, already-enforced invariants: register doctrine, the
word-budget ratchet, structural marketplace validity, and `AGENTS.md` derived-artifact
integrity.

## Enforcement status

| Invariant | Status | Gate/mechanism |
|---|---|---|
| record.yaml single source of truth (report.md derived, never hand-edited) | planned | `render.py --check` semantic-digest drift gate joins `validate.py` in pre-commit (§2, §3), on committed pairs |
| a loud-failing gate per load-bearing rule (exit 1, itemised, stable error codes) | planned | `validate.py` (§2) |
| schema+tier well-formedness (a rate without numerator and denominator fails) | planned | `validate.py` schema branch reading `templates/schema.json` (§2, §3) |
| declared-cells design-reconciliation (N_expected = Σ cells' planned n == disposition == Σ denominators) | planned | `validate.py` (§2) |
| temporal anchor (chronology check: commit in history, predates earliest run; cannot detect a backdated commit — residual named) | planned | `validate.py` (§2) |
| run cross-check equality with a per-tier hand policy | planned | `validate.py` + `from_fathom.py` (§2, §3) |
| small-n CI refusal (no CLT/normal below cell denominator 30) | planned | `stats.py` + `validate.py` (§1, §2) |
| threat-coverage over the closed enum (silence fails) | planned | `validate.py` + `threats-catalog.md` (§2, §4) |
| probe refusal (hard exit 1 on a `confirmatory_*` verdict or a posterior) | planned | `validate.py` probe branch (§2) |
| pre-registration consistency (frozen-plan drift; a confirmatory verdict only on a confirmatory frozen outcome) | planned | `validate.py` `ER-PREREG` via a `git show` diff of the frozen record (§2, §3) |
| schema_version freeze (unknown versions rejected, message names known versions) | planned | `validate.py` reading `templates/schema.json` (§2, §3) |
| comprehension gate before decision tier (block + resolving transcript paths; genuineness ceded to review) | planned | `validate.py` decision branch (§5) |
| machine-readable schema sync (`schema.json` ↔ `SCHEMA.md`) | planned | sync gate under `run_tests.py` (§3) |
| mantis journal-envelope superset tolerance (with a defined strict fallback) | planned | `test_mantis_fallback.py` parser-rejection fixture (§5) |
| standing deletion rule (a degraded gate is deleted, not tolerated) | review-only | governance (ADR-0007); review checklist |
| sealed-holdout-before-tuning (trigger-dataset discipline) | review-only | skill-authoring doctrine; the `BASELINES.md` record (§4) |
| register doctrine (calibrated skill text) | enforced | `scripts/lint_register.py` in pre-commit + CI |
| word budget (skill body vs baseline) | enforced | `scripts/validate_plugins.py` reading `scripts/word_budget.json` |
| structural marketplace validity | enforced | `scripts/validate_plugins.py` in pre-commit + CI |
| AGENTS.md index freshness (derived-artifact integrity) | enforced | `scripts/gen_agents_md.py --check` in pre-commit + CI |

## Concept → module map

| Concept introduced/changed | Module / file it lives in |
|---|---|
| Exact CIs, within-experiment Beta-Binomial, paired/clustered SE | `plugins/humblepowers/skills/experiment-rigor/scripts/stats.py` (to be created) |
| The central gate (schema+tier, reconciliation, anchor, cross-check, stats-integrity, parity, links, threats, probe refusal, comprehension) | `plugins/humblepowers/skills/experiment-rigor/scripts/validate.py` (to be created) |
| Report derivation, semantic-digest drift check, chain walk, mantis envelope emit | `plugins/humblepowers/skills/experiment-rigor/scripts/render.py` (to be created) |
| Fathom ledger bridge — run-derived fields, craft side | `plugins/humblepowers/skills/experiment-rigor/scripts/from_fathom.py` (to be created) |
| Tier skeleton | `plugins/humblepowers/skills/experiment-rigor/templates/probe.yaml` (to be created) |
| Machine-readable canonical schema (types, per-tier required fields, enums, versions) | `plugins/humblepowers/skills/experiment-rigor/templates/schema.json` (to be created) |
| Human field guide generated from the schema, with the rounding/tolerance policy | `plugins/humblepowers/skills/experiment-rigor/templates/SCHEMA.md` (to be created) |
| The thin rigid skill body and its trigger surface | `plugins/humblepowers/skills/experiment-rigor/SKILL.md` (to be created) |
| Closed threat-enum catalog | `plugins/humblepowers/skills/experiment-rigor/references/threats-catalog.md` (to be created) |
| Small-n statistics reference (Miller's rules, Beta-Binomial recipe, prior sensitivity) | `plugins/humblepowers/skills/experiment-rigor/references/small-n-stats.md` (to be created) |
| Founding case: first chain node and acceptance fixture | `plugins/humblepowers/skills/experiment-rigor/examples/rg-2x2/record.yaml` (to be created) |
| Trigger dev set | `evals/trigger/experiment-rigor.json` (to be created) |
| Sealed holdout | `evals/trigger/holdout/experiment-rigor.json` (to be created) |
| Holdout birth-baseline record | `evals/trigger/holdout/BASELINES.md` |
| choosing-tools registration row | `plugins/humblepowers/skills/choosing-tools/scripts/router_rules.json` |
| Word-budget baseline for the new body | `scripts/word_budget.json` |
| Pre-commit gate over travelling records | `.pre-commit-config.yaml` |
| AGENTS.md index regeneration | `AGENTS.md` |

## Settled decisions (Q1–Q9 + round-2 partition, bound)

These close the brief's open questions and are bound as-is; they are not reopened here.

- **Q1 — threat enum.** Closed core enum: `contamination_familiarity`,
  `prompt_format_sensitivity`, `judge_bias`, `model_version_drift`, `nondeterminism`,
  `construct_validity_proxy`, `token_length_confound`, `selection_exclusion`,
  `generalization`. Extension is allowed only as `custom_<slug>`, and the validator then
  requires a non-empty statement and a status like any row; because core-enum coverage is
  unconditional, an extension cannot skip a core threat, and statement substance is ceded
  to review. The catalog lives in `references/threats-catalog.md`; the enum lives in
  `templates/schema.json`. (Bound in §2, §3, §4.)
- **Q2 — CI gate.** CLT/normal methods are refused whenever any cell denominator is
  below 30; allowed methods are `wilson` (default), `clopper_pearson`, and
  `beta_binomial`. Every between-arm comparison declares `paired: true` or
  `paired: false`; when the design shares tasks across arms and `paired: false`, the
  validator requires either a clustered-SE declaration or an explicit `unclustered_reason`.
  `stats.py` computes; `validate.py` recomputes and asserts equality within `ATOL = 1e-9`
  and `RTOL = 1e-6`, against record-level values rounded to 4 decimal places. (Bound in §1, §2.)
- **Q3 — comprehension gate (decision tier).** At least 2 fresh-context readers (3
  recommended, recorded), each answering the four fixed Methods-reconstruction questions
  — what was manipulated; where the intervention text was placed; how each outcome was
  operationalized; whether execution was real. Block fields: `readers[]` (identity,
  family, `context: fresh`, the four answers recorded verbatim, and a `transcript_path`),
  per-reader per-question correct booleans, and `pass`. The validator checks the block is
  present, that every `transcript_path` resolves to a file, and that `pass` holds only on
  unanimous four-question reconstruction; `SCHEMA.md` carries the per-question correctness
  rubric. The genuineness and freshness of the reads are ceded to review, residual named —
  the same posture as keel's B2. (Bound in §5.)
- **Q4 — prereg field set (measurement tier).** The eight AsPredicted content questions
  mapped to record fields: `prior_data_collected` (must be `no`, or `secondary` with a
  declared reason), `question_hypothesis`, `dv_operationalization` (plus verifier path
  and hash), `conditions_factors`, `analysis_plan` (`ci_method` + `comparison` +
  `decision_rule`, where `decision_rule` is a structured object with `metric`,
  `comparison`, `threshold`, and `direction`), `exclusion_rules`, `n_and_rationale`, and
  `other` (optional). (Bound in §3, §2.)
- **Q5 — run cross-check tolerance and hand policy.** Integers and version strings match
  exactly; `cost_usd_est` (the real fathom key — never `cost_usd`, which the CLI does not
  emit) within `max(1%, $0.01)`. The `source: hand` path is tier-graded: allowed at probe;
  at measurement it is a WARN with a declared reason and the frozen plan commit must
  include the task and verifier fixtures so the run is reconstructible; at decision it is a
  FAIL without a ledger or a named second-party attestation row. (Bound in §2, §3.)
- **Q6 — record naming and commit policy.** One directory per experiment holding
  `record.yaml` plus a generated `report.md`. Committed ("travelling") records live under
  a skill example or eval path; the pre-commit hook selects them with a `files:` regex on
  `record.yaml` paths and `pass_filenames: true`, so only staged, tracked files reach it —
  gitignored `docs/design/**` records never do, satisfying Q6 by construction. This
  diverges deliberately from the repo's `always_run: true` local-hook convention, and the
  hook config carries a comment saying so. For a travelling record, `report.md` is
  generated and committed, and the drift gate (`render.py --check`) runs on the committed
  pair. (Bound in §2, §5.)
- **Q7 — probe refusal.** Hard refuse (exit 1) when a probe carries a `results.*.verdict`
  in the `confirmatory_*` class or any `updates.posterior`; the message names the
  graduation path to measurement. (Bound in §2, §3.)
- **Q8 — mantis envelope.** §5 adds `test_mantis_fallback.py` against the mantis
  journal-ingestion parser contract; if the parser does not tolerate superset keys, the
  emitter falls back to a strict envelope of a defined shape (the mantis-required keys plus
  a `record_ref` path and a `record_sha256`, no superset). The standing journal-contract
  constraint applies — field, enum, and required-key mismatches fail silently, so the
  fixture mocks a parser rejection and asserts the fallback envelope is well-formed and
  resolvable. (Bound in §5.)
- **Q9 — schema_version.** Integer, starts at 1. `templates/schema.json` is the canonical,
  machine-readable field list; `SCHEMA.md` is generated from it and carries a sync note,
  and a gate asserts the two are in sync. `validate.py` reads the known versions from the
  schema and rejects an unknown `schema_version` with exit 1 and a message naming the
  versions it knows; the migration policy is v1-only, and a future bump ships an explicit
  migration note. (Bound in §2, §3.)
- **Partition and `ER-PREREG` (round-2, bound).** `outcomes[].role` is `confirmatory`
  or `exploratory` and belongs to the frozen pre-registration; a new outcome added after
  the freeze must carry `added_after_freeze: true` and `role: exploratory` — that is the
  quarantine, friction-free. A `results.<outcome>.verdict` in the `confirmatory_*` class is
  legal only when that outcome is `role: confirmatory` in the frozen plan; exploratory and
  post-freeze outcomes may carry only `exploratory_signal` or `inconclusive`. Sequential
  designs declare `analysis_plan.amendments[]` (each `{commit, timestamp, scope}`), every
  amendment commit in history and predating the first run of the wave it governs. The
  mechanical detector is the `ER-PREREG` gate (§2). (Bound in §2, §3, §5.)

## Numbered sections

### §1 Statistics core
Create `plugins/humblepowers/skills/experiment-rigor/scripts/stats.py` and its
`scripts/test_stats.py`. Stdlib only, self-contained. `stats.py` exposes exact binomial
CIs — `wilson` in closed form, and `clopper_pearson` plus the `beta_binomial` credible
interval computed exactly for integer parameters via binomial tail sums (`math.comb`)
inverted by bisection to a fixed tolerance. The signature is
`beta_binomial(numerator, denominator, prior_alpha=1, prior_beta=1, paired=False, cluster_ids=None)`,
with the prior pinned to `Beta(1, 1)` and a one-line sensitivity note in `small-n-stats.md`.
It also exposes paired / clustered standard errors for a shared-task structure; it exposes
no CLT/`normal` path, so a small-n record cannot request one. Q2's method set, the small-n
boundary, and the `ATOL = 1e-9` / `RTOL = 1e-6` recomputation tolerances are pinned here;
`validate.py` (§2) recomputes and asserts equality against 4-decimal record values. The
within-experiment-only boundary is stated in `small-n-stats.md` (§4): cross-experiment
belief moves are qualitative GRADE links, never pooled counts.
**Acceptance criterion:** `uv run --no-project --with pyyaml -- python scripts/run_tests.py`
discovers and passes `test_stats.py` (it prints an `ok:` sentinel); the test pins `wilson`,
`clopper_pearson`, and `beta_binomial` against known reference intervals within the stated
tolerances, reproduces the RG-2×2 footprint move (36/48 vs 18/48, paired across the 6
tasks) as a within-experiment Beta-Binomial update, asserts the clustered SE exceeds the
naive SE on that shared-task structure, and asserts that requesting a `normal` method
raises rather than returns a number.

### §2 The validator and the travelling-record pre-commit gate
Create `plugins/humblepowers/skills/experiment-rigor/scripts/validate.py` and
`scripts/test_validate.py`, and add local hooks to `.pre-commit-config.yaml` running
`validate.py` and `render.py --check` over staged `record.yaml` paths (a `files:` regex
with `pass_filenames: true`, deliberately diverging from the `always_run` convention and
commented as such — the FM-6 fix). `validate.py` depends on PyYAML, is the mechanism spine
and the home of the standing deletion rule, and emits a stable per-gate error code with
each itemised failure. It exits 1 on schema+tier violations (`ER-SCHEMA`: a rate without
both numerator and denominator; a missing required field for the declared tier; an unknown
`schema_version`, the message naming known versions, read from `templates/schema.json`),
declared-cells reconciliation (`ER-RECON`: `N_expected` = the sum over `design.cells[]` of
each cell's planned n, asserted equal to the disposition total and to the per-outcome
denominator sums — RG-2×2 is 8 cells × 12 = 96; the model tier is one named factor level,
not a separate multiplier, removing the factors/tiers overload), the temporal anchor
(`ER-ANCHOR`: a `plan_frozen_at.commit` absent from history or postdating the earliest run
— a chronology check that raises the cost of goalpost-moving but cannot detect a backdated
commit, residual named, with push-to-remote recommended at decision tier), run cross-check
(`ER-XCHECK`: a hand field diverging from the ledger beyond the Q5 tolerance; the per-tier
`source: hand` policy of Q5), stats-integrity (`ER-STATS`: a stated CI not equal to the
`stats.py` recomputation within tolerance; a `normal`/CLT method at any cell denominator
below 30), parity (`ER-PARITY`: the typed blocks embedded in a committed `report.md`
re-parse and equal the record — the byte-independent half; `render.py --check` in §3 is the
semantic-digest half), link-resolution (`ER-LINK`: an `updates.prior.source_id` that does
not resolve to a record), threat-coverage (`ER-THREAT`: a silent enum key), and probe
refusal (`ER-PROBE`: Q7's `confirmatory_*` verdict or a posterior on a probe), and
pre-registration consistency (`ER-PREREG`: `validate.py` reconstructs the frozen
pre-registration with `git show` on `plan_frozen_at.commit` for this record's path and diffs
the prereg subset — `design.cells`, `outcomes[].{name,role,operationalization,verifier.hash}`,
and `analysis_plan` — against the analyzed record; any drift in that subset, any
`confirmatory_*` verdict on an outcome whose frozen `role` is not `confirmatory`, or any
`role` change exits 1 naming the drifted field; when the record is not in history at the
frozen SHA it downgrades per the Q5 hand ladder — measurement WARN + reason, decision FAIL).
`validate.py --schema-only` runs the schema/tier shape checks alone — the context gates
(anchor, ledger cross-check, transcript existence, `ER-PREREG`) are skipped and listed as
skipped — as the documented authoring-time check for templates and drafts.
**Acceptance criterion:** `test_validate.py` feeds one minimal defect fixture per gate
branch plus one clean fixture, and `uv run --no-project --with pyyaml -- python scripts/run_tests.py`
passes it (the module hard-fails, never `skip:`, when PyYAML is absent); each defect makes
`validate.py` exit 1 with its named error code while the clean fixture exits 0, and a test
asserts the hook config selects a staged travelling `record.yaml` and excludes a
`docs/design/**` record.

### §3 Renderer, fathom bridge, templates, and schema
Create `scripts/render.py`, `scripts/from_fathom.py`, their `test_render.py` and
`test_from_fathom.py`, the three tier skeletons `probe.yaml`, `measurement.yaml`, and
`decision.yaml` under `templates/`, the machine-readable `templates/schema.json`, and the
generated `templates/SCHEMA.md`. `render.py` derives `report.md` from `record.yaml` under a
canonical serialization (sorted keys, LF line endings, a pinned float format), embedding
the canonical typed blocks as fenced YAML; `render.py --check` is the drift gate — a
semantic re-parse and digest of the embedded blocks against a fresh render, not a
whole-file byte diff — and joins `validate.py` in the pre-commit hook over committed pairs.
`render.py --chain` walks `updates.prior.source_id` links into a lineage view, and
`render.py` emits the mantis journal envelope. `from_fathom.py` reads a fathom
`ledger/<bank>.jsonl` located by the `run.ledger_path` schema field and maps it to the real
ledger schema: `n` as a row count, disposition derived from each graded `trial`
row's `verifier_results` (the rows fathom grades) via the same pass predicate, `cost_usd_est`
from the `run` row (there is no `cost_usd`, `disposition`, or `model_versions` field, and
from_fathom joins across run and trial rows), and the model tier from `pin_level`
or the bank-scenario config (a model-version string is `source: hand` unless the config
carries it). `schema.json` carries the per-tier required/optional fields, the
`schema_version: 1` pin, the Q4 prereg set with `decision_rule` as a structured object, the
confirmatory/exploratory partition (`outcomes[].role` of `confirmatory` or `exploratory`,
`added_after_freeze` for a post-freeze outcome, and `analysis_plan.amendments[]` of
`{commit, timestamp, scope}` for sequential designs), the
Q1 threat enum, the closed verdict enum (`confirmatory_supported`, `confirmatory_null`,
`exploratory_signal`, `inconclusive` — probe refusal keys on the `confirmatory_*` class),
and the cross-experiment GRADE update shape (`certainty` four-level enum,
`downgrade_reasons[]`, `source_id`); `SCHEMA.md` is generated from it with the
rounding/tolerance policy and a two-node GRADE worked example.
**Acceptance criterion:** `run_tests.py` passes `test_render.py`, `test_from_fathom.py`,
and the `schema.json` ↔ `SCHEMA.md` sync test; `render.py` derives a `report.md` whose
embedded blocks equal the record, `render.py --check` exits 1 on a hand-edited report and 0
on a fresh render, `render.py --chain` resolves a two-node fixture chain; `from_fathom.py`
maps a fixture `ledger/rg-2x2.jsonl` that is a verbatim excerpt of a real fathom ledger to
`cost_usd_est`, row-count n, and verifier-derived disposition matching its rows; each
of the three templates passes `validate.py --schema-only` at its declared tier, and the full
`validate.py` on the decision template fails listing exactly the expected context-gate codes
(`ER-ANCHOR`, `ER-XCHECK`, `ER-PREREG`, and `ER-COMPREHEND`), proving those gates fire on a
skeleton.

### §4 The skill, references, and the ship gates
Create `SKILL.md` (rigid, thin), the two references `threats-catalog.md` and
`small-n-stats.md` under `references/`, the trigger dev set `evals/trigger/experiment-rigor.json`,
the sealed holdout `evals/trigger/holdout/experiment-rigor.json`, and a correct-usage
rubric; add one row to `router_rules.json`, a word-budget baseline to `scripts/word_budget.json`,
and regenerate `AGENTS.md` (the `agents-md-fresh` gate fails the moment the new SKILL.md
lands unless the index is regenerated in this same PR, so `AGENTS.md` is in PR04's touched
files). `SKILL.md` declares itself rigid (bright lines: the freeze, the arithmetic
reconciliation, the confirmatory/exploratory partition, the CLT refusal), leads with dense
before-spend lexical triggers, and binds keel's DoR and the fresh-context reader tooling
role-generically. `threats-catalog.md` enumerates the Q1 closed enum, matching `schema.json`.
The dev set and holdout are authored at one sitting; the holdout is run once at seal with
its birth baseline recorded before any description tuning, per
`plugins/humblepowers/skills/skill-authoring/SKILL.md:91` `Sealed holdout, with a birth baseline`
and the seal-with-baseline record at `evals/trigger/holdout/BASELINES.md:1` `seal-with-baseline`;
the row is added to the skills array at `plugins/humblepowers/skills/choosing-tools/scripts/router_rules.json:5` `"skills"`.
The router row must be a narrow, conservative regex, and `test_router.py` (the sealed router
suite, run by `run_tests.py`) is a named gate here: if the row trips the 2/20 adversarial
false-fire budget or any recall/specificity floor, the fallback is shipping WITHOUT the
router row — description-only dispatch still triggers the skill — plus a named follow-up.
**Model-on:** `plugins/humblepowers/skills/choosing-tools/scripts/router_rules.json`
**Reuse:** `evals/trigger/choosing-tools.json`
**Acceptance criterion:** `uv run --no-project python scripts/lint_register.py` and
`uv run --no-project python scripts/word_budget.py` both pass on the new `SKILL.md` (a
baseline row added to `scripts/word_budget.json` per `scripts/word_budget.py:76` `no word-budget baseline`),
`uv run --no-project --with pyyaml -- python scripts/validate_plugins.py` passes with the
description within `scripts/validate_plugins.py:33` `DESC_CAP = 1536` and the body within
`scripts/validate_plugins.py:34` `SKILL_LINE_CAP = 500`, `gen_agents_md.py --check` passes
against the regenerated `AGENTS.md`, and `test_router.py` stays green (or the row is dropped
per the stated fallback); the correct-usage rubric checks that a produced record passes
`validate.py` and reconstructs without the conversation.

### §5 Dogfood fixture, decision tier, and the bridges
Create `examples/rg-2x2/record.yaml` and its generated `examples/rg-2x2/report.md`; extend
`validate.py` with the decision-tier comprehension gate; and add the mantis journal-envelope
emit to `render.py` with `test_mantis_fallback.py`. The RG-2×2 record is the first node of
the update chain and the acceptance fixture; a fathom-side emitter is out of this series
(the bridge reads the ledger directly). The corrected record marks the footprint outcome
`role: exploratory` with its Beta-Binomial posterior under the exploratory quarantine and the
wave-2 pre-fixed bar as an `analysis_plan.amendments[]` entry frozen before wave 2, so it
clears the `ER-PREREG` gate (a quarantined exploratory posterior is permitted at
measurement/decision tier, distinct from the probe posterior refusal); the activation outcome
is the `role: confirmatory` one that failed. The comprehension gate (Q3) requires a decision-tier
record to carry a `comprehension` block with each reader's four verbatim answers and a
resolving `transcript_path`, and passes only on unanimous four-question reconstruction. The
mantis emit (Q8) writes the update/provenance envelope, and `test_mantis_fallback.py` mocks
a parser rejection to assert the strict linking fallback (`record_ref` + `record_sha256`) is
well-formed.
**Acceptance criterion:** a defect-seeded RG-2×2 fixture carrying the case's six known
defects — the declared cells summing to 8 × 12 = 96 while disposition and denominators sum
to 48 (the two waves omitted); the un-operationalized outcome; the missing footprint
denominators; the undeclared paired comparison; the footprint carrying a `confirmatory_supported`
verdict while its frozen `role` is `exploratory` (`ER-PREREG`); and the absent CI — makes
`validate.py` exit 1 naming all six by error code, and the corrected `examples/rg-2x2/record.yaml` exits 0 with
`render.py --check` showing no drift against the committed `report.md`; a decision-tier
record missing the comprehension block, with an unresolvable `transcript_path`, or with any
reader reconstructing fewer than four questions, exits 1 (`ER-COMPREHEND`); and `test_mantis_fallback.py`
passes under `run_tests.py`.

## PR ↔ section manifest

| PR | Implements section | One concern? |
|---|---|---|
| PR01 | §1 | yes |
| PR02 | §2 | yes |
| PR03 | §3 | yes |
| PR04 | §4 | yes |
| PR05 | §5 | yes |

Dependency notes (a DAG, not extra coverage): PR02 recomputes what PR01 exposes, so it
lands after PR01; PR03 consumes `stats.py` and the record shape PR02 gates; PR04 ships the
skill once the machinery of PR01–PR03 exists and regenerates `AGENTS.md`; PR05 dogfoods the
whole chain and extends `validate.py` and `render.py`, so it lands last. PR01–PR04 are the
minimum viable discipline (probe and measurement usable end to end); PR05 closes the
decision tier and the founding-case regression fixture.

## Definition of Done (this spec)

- All five sections merged with their acceptance criteria demonstrated in the PR (test
  runs and gate output included).
- The RG-2×2 fixture acceptance test is green: `validate.py` exits 1 on the six-defect
  fixture naming all six by error code (defect #5 fires `ER-PREREG`), and 0 on the corrected
  `examples/rg-2x2/record.yaml` with the footprint marked `role: exploratory` under quarantine
  and the wave-2 amendment (§5).
- The trigger dev set and the sealed holdout are authored together, and the holdout is run
  once with its birth baseline recorded in `evals/trigger/holdout/BASELINES.md` before any
  description tuning (§4).
- The register linter and word budget are green, and `validate_plugins.py` and
  `run_tests.py` (under `--with pyyaml`) pass, each new record-parsing `test_*.py` printing
  an `ok:` sentinel and hard-failing when PyYAML is absent.
- The choosing-tools registration row has landed in `router_rules.json` and `test_router.py`
  stays green, or the row is dropped per the §4 fallback with a named follow-up.
- `AGENTS.md` is regenerated in PR04 and its `gen_agents_md.py --check` gate is green.
- Each public-surface section carries its humblepowers CHANGELOG entry in the same wave —
  §4 ships the skill, §5 the decision tier — per release-notes-in-wave.
- Generated / mirrored / snapshot artifacts downstream of touched surfaces, each with its
  freshness gate: the committed `examples/rg-2x2/report.md` (drift gate `render.py --check`,
  §3/§5); the `AGENTS.md` index (`gen_agents_md.py --check`, regenerated in §4); the
  `templates/SCHEMA.md` file generated from `templates/schema.json` (sync gate, §3); and the
  `scripts/word_budget.json` baseline for the new body (`word_budget.py`, §4). No other
  generated artifacts.

## Pre-mortem certification

- **Reviewer:** fresh non-author subagent (opus), round 3
- **Verdict:** CERTIFIED
- **Operator:** not applicable — set only for a CONDITIONAL-CERTIFY verdict
- **Certification artifact:** `docs/specs/2026-07-24-experiment-rigor-skill.premortem-r3.md`
- **Date:** 2026-07-24
- **Reviewed against:** the live working tree at 2026-07-24; keel kit 0.13.0; no external
  dependency SHAs (a code spec against in-repo gates)
- **Post-fold coherence:** the author applied the round-1 pre-mortem (FM-1..FM-10), the
  external 4-model panel (E1..E7), and the round-2 pre-mortem (R2-1..R2-4) as two sequential
  folds; the round-3 pass audited each round-2 finding to RESOLVED against current text and
  found the second fold clean. The round-2 BLOCKER (R2-1, the post-hoc-as-pre-registered gate
  defined nowhere) is resolved on its merits: `ER-PREREG` is now a real, buildable, non-vacuous
  gate with schema constructs (`outcomes[].role`, `added_after_freeze`,
  `analysis_plan.amendments[]`), §2 gate logic, an error code, and the §5 defect-#5 mapping — its
  `git show <plan_frozen_at.commit>:<path>` linchpin was executed against this repo and confirmed
  (content on hit, clean failure on miss, tier-graded downgrade when not in history). R2-2 (ADR
  schema.json-canonical), R2-3 (trial-row terminology, re-verified against the real fathom
  ledger), and R2-4 (`--schema-only` template acceptance) are all resolved. The load-bearing repo
  anchors and the ledger schema were re-verified against the metal, not inherited. No new BLOCKER
  or MAJOR surfaced; two MINOR advisories remain (R3-1: `ER-COMPREHEND` named in acceptance but not
  in §2's code list; R3-2: pin the corrected RG-2×2 fixture's tier as measurement) — one-line pins
  that do not corrupt the gated decision. Residual trust the spec names — comprehension genuineness
  ceded to review, the temporal anchor as chronology-not-proof, hand-run counts ceded — is design
  posture, not a finding
- **Failure modes considered & folded in:** FM-1 stale AGENTS.md premise (BLOCKER), FM-2
  PyYAML gate command, FM-3 real fathom ledger schema, FM-4 fathom emitter removed, FM-5
  sealed-router regression fallback, FM-6 pre-commit file selection, FM-7 declared-cells
  reconciliation, FM-8 verdict enum, FM-9 research-record SHAs, FM-10 exploratory-quarantine
  posterior; E1 comprehension honest-claim downgrade, E2 stats determinism, E3 canonical
  serialization drift, E4 per-tier hand policy, E5 temporal-anchor honest claim, E6
  machine-readable schema, E7 missing definitions; R2-1 pre-registration partition +
  `ER-PREREG` gate (BLOCKER), R2-2 ADR schema.json-canonical reconciliation, R2-3 trial-row
  ledger terminology, R2-4 `--schema-only` template acceptance — one fold-ledger row each below

### Fold ledger

| Finding | Target section | artifact:line | Confirmed |
|---|---|---|---|
| FM-1 stale AGENTS.md premise (BLOCKER) — regen required in PR04 | DoD + §4 | `docs/specs/2026-07-24-experiment-rigor-skill.md:411` `regenerated in PR04` | yes |
| FM-2 PyYAML gate command + hard-fail-not-skip | Gate commands + §2 | `docs/specs/2026-07-24-experiment-rigor-skill.md:42` `to carry` | yes |
| FM-3 real fathom ledger schema (cost_usd_est, verifier-derived disposition) | §3 + §2 | `docs/specs/2026-07-24-experiment-rigor-skill.md:295` `there is no` | yes |
| FM-4 fathom emitter removed from series | §5 + Output artifacts + Non-goals | `docs/specs/2026-07-24-experiment-rigor-skill.md:355` `out of this series` | yes |
| FM-5 sealed-router regression fallback | §4 | `docs/specs/2026-07-24-experiment-rigor-skill.md:335` `the sealed router` | yes |
| FM-6 pre-commit files-regex + pass_filenames | §2 + Q6 | `docs/specs/2026-07-24-experiment-rigor-skill.md:243` `deliberately diverging from the` | yes |
| FM-7 declared-cells reconciliation | §2 + §3 | `docs/specs/2026-07-24-experiment-rigor-skill.md:251` `8 cells × 12 = 96` | yes |
| FM-8 closed verdict enum | §3 + §2 | `docs/specs/2026-07-24-experiment-rigor-skill.md:303` `closed verdict enum` | yes |
| FM-9 research-record sha256 | Context | `docs/specs/2026-07-24-experiment-rigor-skill.md:24` `sha256 hashes at authoring` | yes |
| FM-10 exploratory-quarantine posterior | §5 | `docs/specs/2026-07-24-experiment-rigor-skill.md:357` `posterior under the exploratory` | yes |
| E1 comprehension honest-claim downgrade | ADR + §5/Q3 | `docs/adr/0007-experiment-rigor-delivery.md:103` `cannot prove the reads were genuine` | yes |
| E2 stats determinism (exact CIs, tolerances, signature) | §1 | `docs/specs/2026-07-24-experiment-rigor-skill.md:223` `beta_binomial(numerator, denominator` | yes |
| E3 canonical serialization + semantic-digest drift | §3 + §2 | `docs/specs/2026-07-24-experiment-rigor-skill.md:288` `semantic re-parse and digest` | yes |
| E4 per-tier source-hand policy | §2 + Q5 | `docs/specs/2026-07-24-experiment-rigor-skill.md:178` `at decision it is a` | yes |
| E5 temporal-anchor honest claim | ADR + §2 | `docs/adr/0007-experiment-rigor-delivery.md:88` `backdated commit (push-to-remote` | yes |
| E6 machine-readable schema.json + sync gate | §3 + Q9 | `docs/specs/2026-07-24-experiment-rigor-skill.md:200` `machine-readable field list` | yes |
| E7 missing definitions (GRADE shape, decision_rule, error codes, ledger_path, mantis fallback) | §3 + §5 | `docs/specs/2026-07-24-experiment-rigor-skill.md:305` `cross-experiment GRADE update shape` | yes |
| R2-1 pre-registration partition + ER-PREREG gate (BLOCKER) | §2 + §3 + §5 | `docs/specs/2026-07-24-experiment-rigor-skill.md:264` `reconstructs the frozen` | yes |
| R2-2 ADR schema.json-canonical reconciliation | ADR Consequences | `docs/adr/0007-experiment-rigor-delivery.md:139` `canonical machine-readable` | yes |
| R2-3 trial-row ledger terminology | §3 | `docs/specs/2026-07-24-experiment-rigor-skill.md:293` `each graded` | yes |
| R2-4 schema-only template acceptance | §3 | `docs/specs/2026-07-24-experiment-rigor-skill.md:315` `listing exactly the expected context-gate` | yes |
