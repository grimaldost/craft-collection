# Pre-mortem (round 3) — experiment-rigor skill

- **Spec:** `docs/specs/2026-07-24-experiment-rigor-skill.md`
- **Date:** 2026-07-24
- **Reviewer:** fresh non-author subagent (opus), round 3
- **Spec-hash:** `80efe7733a19414d015782ab25c60c353a3ac5c81e6dbc4dd01e2086ee7499d4`
- **Reviewed against:** the live working tree at 2026-07-24; keel kit 0.13.0; craft in-repo
  gates (`scripts/*.py`, `.pre-commit-config.yaml`); the round-1 verdict record
  (`…-experiment-rigor-skill.premortem.md`, FM-1..FM-10 + folded panel E1..E7) and the
  round-2 verdict record (`…-experiment-rigor-skill.premortem-r2.md`, R2-1..R2-4); the fathom
  repo at `C:/Users/grima/Documents/fathom` (real `ledger/*.jsonl`); ADR-0007.

Second re-gate pass over the second fold (the fold that added the `ER-PREREG` gate,
`outcomes[].role` + `added_after_freeze` + `analysis_plan.amendments[]`, and
`validate.py --schema-only`). Per the round-≥2 posture: FIRST a resolution audit of every
round-2 finding against current text, THEN a hunt for second-fold-introduced defects under
the rising bar (a finding blocks only if it plausibly corrupts the decision the spec gates —
does `validate.py` catch the founding case's six defects and pass the corrected record?).
Load-bearing repo claims were re-verified against the metal this pass, not inherited.

## Fold verification (did the second fold's 4 rows land at their anchors?)

All four round-2 ledger rows land, and the two prior folds still hold:

- **R2-1 → `ER-PREREG`.** §2:264-270 defines the gate (git-show reconstruction of the frozen
  prereg subset + the in-record `confirmatory_*`-verdict-on-non-`confirmatory`-role check +
  role-change detection); §3:300-302 adds the schema constructs `outcomes[].role`,
  `added_after_freeze`, `analysis_plan.amendments[]`; the Settled-decisions partition block
  (spec:205-213) binds it; enforcement table row (spec:103) and concept map (spec:120) carry
  it; §5:359,371 map defect #5 to `ER-PREREG`.
- **R2-2 → ADR reconciliation.** ADR:139 now reads "`schema.json` is the canonical
  machine-readable per-tier field list and `SCHEMA.md` is generated from it (a sync gate
  asserts agreement)" — the E6 pivot is propagated; ADR no longer contradicts the spec.
- **R2-3 → trial-row terminology.** §3:297-298 now "each graded trial row's `verifier_results`
  (the rows fathom grades)" and "`from_fathom` joins across run and trial rows".
- **R2-4 → `--schema-only`.** §2:271-273 defines the schema-only mode (context gates skipped
  and listed as skipped); §3:315-317 acceptance recast to "each template passes
  `validate.py --schema-only`" + full validate on the decision template fails listing exactly
  the context-gate codes.

Repo-reality anchors re-verified fresh this pass (all hold): `gen_agents_md.py` globs
`plugins/*/skills/*/SKILL.md` (`:91`) and `--check` returns 1 on `current != fresh`
(`:121-127`); `run_tests.py` `SEARCH_DIRS=('plugins','evals')` (`:24`), `has_sentinel`
accepts `ok:`/`skip:` (`:45`); `validate_plugins.py` `DESC_CAP=1536` (`:33`),
`SKILL_LINE_CAP=500` (`:34`); `lint_register.py` `DEFAULT_SCOPE = ROOT/'plugins'` (`:34`);
`word_budget.py:76` baseline message; `router_rules.json` `"skills"` at line 5;
`test_router.py` `RECALL_BAR=0.60`/`SPECIFICITY_BAR=0.90` and the 2/20 adversarial budget
(`:165`); `.pre-commit-config.yaml` `run-tests` (`:60`) still lacks `--with pyyaml` and
`agents-md-fresh` (`:40-45`) is `always_run` (FM-2 change real and correctly targeted). The
real fathom ledger (`ablation-v1.jsonl`): kinds `{run, trial}`, `verifier_results` ONLY on
`trial` rows, `cost_usd_est` ONLY on `run` rows, no `cost_usd`/`disposition`/`n`/`model_versions`.

## Resolution audit (round-2 findings → current status)

```yaml
resolution_audit:
  - id: R2-1  # BLOCKER — post-hoc gate defined nowhere
    status: RESOLVED
    evidence: >
      ER-PREREG is now a fully-built gate: schema constructs (spec:300-302 outcomes[].role,
      added_after_freeze, analysis_plan.amendments[]), gate logic + error code (spec:264-270),
      §5 defect-#5 mapping (spec:371). The three post-hoc-dressing vectors are each
      mechanically caught: (a) a confirmatory_* verdict on an in-record role:exploratory /
      added_after_freeze outcome fires in-record (no git); (b) re-labelling an exploratory
      outcome confirmatory after freeze is caught by the git-diff "any role change exits 1";
      (c) adding a new confirmatory outcome absent from the frozen plan is caught as prereg-
      subset drift. The centerpiece six-defect acceptance can now produce its sixth failure.
    linchpin_check: >
      The pivot's new mechanism is `git show <plan_frozen_at.commit>:<path>`. Executed against
      this repo: returns content for an in-history path, and fails cleanly
      ("fatal: path ... does not exist in <sha>") for a missing one — so validate.py can both
      reconstruct the frozen record AND detect the not-in-history case to downgrade it. The
      not-in-history downgrade is tier-graded (measurement WARN + reason / decision FAIL, the
      Q5 hand ladder), so the gate degrades honestly rather than vacuously. Mechanism sound.
  - id: R2-2  # MINOR — ADR still called SCHEMA.md canonical
    status: RESOLVED
    evidence: adr:139 now names schema.json canonical, SCHEMA.md generated (sync gate)
  - id: R2-3  # MINOR — "grade row" mislabel
    status: RESOLVED
    evidence: spec:297-298 "graded trial row" + "joins across run and trial rows"; matches ledger
  - id: R2-4  # MAJOR — templates cannot pass full validate.py
    status: RESOLVED
    evidence: >
      §2:271-273 --schema-only; §3:315-317 acceptance = templates pass --schema-only, full
      validate on the decision template fails listing exactly ER-ANCHOR/ER-XCHECK/ER-PREREG/
      ER-COMPREHEND. Satisfiable: a decision template authored as a complete exemplar with
      deliberately-unresolvable context anchors (placeholder plan_frozen_at.commit, no ledger,
      unresolvable transcript_path) passes every non-context gate and fails exactly those four.
      The "exactly" clause is self-correcting, not vacuous — a stray ER-THREAT/ER-STATS failure
      would surface as a red acceptance.
```

## New / missed findings (rising bar — advisories only)

```yaml
findings:
  - id: R3-1
    severity: MINOR
    evidence: spec:246-264 (§2 enumerates ER-SCHEMA/RECON/ANCHOR/XCHECK/STATS/PARITY/LINK/THREAT/PROBE/PREREG — 10 codes, no ER-COMPREHEND); spec:316,375 (ER-COMPREHEND named only in §3/§5 acceptance); spec:105 (enforcement row), spec:120 (concept map), spec:353,361-363 (§5 "extend validate.py with the decision-tier comprehension gate")
    claim: >
      ER-COMPREHEND — the decision-tier comprehension gate's error code — is referenced in the
      §3 and §5 acceptance criteria but is not listed among §2's ten enumerated ER-codes.
    detail: >
      Not a divergence and not a vacuous gate: §5 explicitly owns the comprehension gate as a
      validate.py extension, the enforcement table and concept map both list it, and the code
      string is spelled consistently as ER-COMPREHEND in both places it appears. A zero-context
      implementer building the full spec adds the gate and uses that code. The gap is only that
      §2, which otherwise reads as the exhaustive code catalog, omits the tenth-plus code. Fold
      one line into §2 on a future touch; it does not block execution.
    smallest_fix: >
      Add ER-COMPREHEND to §2's gate list ("the decision-tier comprehension gate (ER-COMPREHEND:
      a missing/incomplete comprehension block or an unresolvable transcript_path at decision
      tier), built in §5").
    disconfirming_test: >
      Grep §2 for ER-COMPREHEND — absent; grep §3/§5 acceptance — present and consistent.
    target_section: §2 (advisory)

  - id: R3-2
    severity: MINOR
    evidence: spec:6 (Output-artifacts lists examples/rg-2x2/{record.yaml,report.md} — no transcript files); spec:352-361,371-375 (§5 fixture text); spec:157-165 (Q3 comprehension = decision tier); spec:98-99 ADR ladder (partition/GRADE/comprehension = decision tier)
    claim: >
      The corrected RG-2×2 acceptance fixture's tier is never stated. It carries a
      confirmatory/exploratory partition and a within-experiment posterior (decision-tier-ish
      features in the ADR ladder), yet its "exits 0" acceptance and its deliverables
      (record.yaml + report.md only) are consistent only with a NON-comprehension tier.
    detail: >
      Satisfiable and coherent under the measurement-tier reading, which the spec's own
      structure implies: §5 tests the comprehension gate with a SEPARATE decision-tier defect
      fixture (spec:373-375), not the RG-2×2 record; the six-defect fixture (spec:367-372) omits
      comprehension entirely. At measurement tier the corrected record needs no comprehension
      block (no transcript files owed — deliverables complete), ER-ANCHOR is satisfied by a real
      freeze commit predating the recorded runs (residual ceded), and ER-PREREG passes (footprint
      now exploratory_signal; git path either clean-diffs an in-branch freeze commit or downgrades
      to a WARN at measurement — either exits 0). The only residual ambiguity is cosmetic (a
      measurement-tier ER-PREREG WARN vs a clean pass via a two-commit freeze construction); both
      readings exit 0, so the gated decision is not corrupted. Pin the tier for zero-context clarity.
    smallest_fix: >
      In §5, state the corrected RG-2×2 record's tier (measurement) so the implementer does not
      author it as decision tier and then owe comprehension transcript files not in Output-artifacts.
    disconfirming_test: >
      Point to any spec line stating the RG-2×2 record's tier — none exists; the acceptance and
      deliverables are consistent only with a non-decision tier.
    target_section: §5 (advisory)
```

```yaml
cleared:
  - claim: R2-1 fully resolved — ER-PREREG is a real, buildable, non-vacuous gate; git-show mechanism executed and confirmed against this repo
    cite: spec:264-270,300-302,371; `git show <sha>:<path>` run this session (content on hit, clean fatal on miss)
  - claim: R2-2/R2-3/R2-4 all resolved with current-text evidence
    cite: adr:139; spec:297-298; spec:271-273,315-317
  - claim: the second fold introduced no arithmetic drift — 8 cells × 12 = 96 vs 48-per-arm reconciles across Context/§2/§5, ER-code set is internally consistent
    cite: spec:13-14,240-242,251,339-340,367-372
  - claim: all prior-round repo anchors re-verified fresh (gen_agents_md, run_tests, validate_plugins, lint_register, word_budget, router_rules/test_router, pre-commit hooks) and the real fathom ledger schema
    cite: scripts/gen_agents_md.py:91,121-127; run_tests.py:24,45; validate_plugins.py:33,34; lint_register.py:34; word_budget.py:76; router_rules.json:5; test_router.py:27,28,165; .pre-commit-config.yaml:40-45,60; fathom ledger/ablation-v1.jsonl kinds/keys
  - claim: repo merges (not squashes), so a fixture's in-branch freeze commit referenced by plan_frozen_at.commit survives on main and git-show keeps resolving post-merge
    cite: git log — "Merge pull request #104..#106" merge commits
  - claim: the six-defect fixture can name all six by code (ER-RECON, ER-SCHEMA×(un-op'd, missing denom), ER-STATS/ER-SCHEMA (undeclared paired, absent CI), ER-PREREG (defect #5 in-record))
    cite: spec:367-372; §2 gate branches spec:246-264
```

## Prose

The second fold is clean and closes the round-2 blocker on its merits, not on momentum. R2-1
was the keystone gap: the post-hoc-as-pre-registered check — the discipline's reason to exist
and the ADR's named disqualifying case — had no schema construct, no gate, and no code, while an
earlier fold (FM-10) already presumed it. The fold supplies all three: `outcomes[].role` +
`added_after_freeze` + `analysis_plan.amendments[]` as schema fields, the `ER-PREREG` gate logic
in §2, the error code, and the §5 defect-#5 mapping. Crucially, the gate is buildable and
non-vacuous. I executed its new premise — `git show <plan_frozen_at.commit>:<path>` — against
this repo: it returns the frozen file on a hit and fails cleanly on a miss, so `validate.py` can
both reconstruct-and-diff the frozen prereg subset and detect the not-in-history case to downgrade
it on the tier-graded ladder. The three ways a post-hoc finding gets dressed as pre-registered
(a confirmatory verdict on an exploratory/post-freeze outcome; a role re-label after freeze; a new
confirmatory outcome absent from the frozen plan) are each caught — the first in-record with no
git dependency, the latter two by the git-diff. The centerpiece six-defect acceptance can now
produce its sixth itemised failure.

R2-2, R2-3, R2-4 are all resolved with current-text evidence: the ADR now names schema.json
canonical (no longer contradicting the spec), the "trial row" terminology matches the real ledger
(re-verified: `verifier_results` on trial rows, `cost_usd_est` on run rows), and the
`--schema-only` mode makes the template acceptance satisfiable — a decision template authored as a
complete exemplar with deliberately-unresolvable context anchors passes every non-context gate and
fails exactly the four the acceptance names, a self-correcting clause rather than a vacuous one.

The two new findings are advisories under the rising bar, neither corrupting the gated decision.
R3-1: `ER-COMPREHEND` is named in the §3/§5 acceptance but not in §2's enumerated code list — a
cosmetic catalog omission, since §5 explicitly owns the comprehension-gate extension and the code
string is consistent, so no implementer misses the gate or its code. R3-2: the corrected RG-2×2
fixture's tier is unstated, but its "exits 0" acceptance and its record.yaml+report.md-only
deliverables are consistent with the measurement-tier reading that the spec's own structure implies
(the comprehension gate is tested by a separate decision-tier fixture; the six-defect fixture omits
comprehension), so no transcript files are owed and the fixture is satisfiable. Both are one-line
pins for a future touch, not blockers.

Nothing in this pass impugns the ADR's decision, the skill's shape, or the two prior folds. The
load-bearing repo anchors and the fathom ledger schema were re-verified against the metal, not
inherited; the git-show pivot linchpin was executed, not assumed. No new BLOCKER or MAJOR finding
surfaced; the round-2 BLOCKER and MAJOR are both resolved. Per the convergence and rising-bar
rules, a pass that surfaces only nice-to-haves certifies with advisories rather than forcing
another round.

Unverified-offline: 0
PREMORTEM-VERDICT: CERTIFIED — fresh non-author subagent (opus), round 3
