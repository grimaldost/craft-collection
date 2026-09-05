# Pre-mortem (round 2) — experiment-rigor skill

- **Spec:** `docs/specs/2026-07-24-experiment-rigor-skill.md`
- **Date:** 2026-07-24
- **Reviewer:** fresh non-author subagent (opus), round 2
- **Spec-hash:** `ea03a988d9fb322af4bdc5fe8e856ef126cc21ec650e891f28127f4f6b522bfd`
- **Reviewed against:** the live working tree at 2026-07-24; keel kit 0.13.0; craft in-repo
  gates (`scripts/*.py`, `.pre-commit-config.yaml`); the round-1 verdict record
  (`…-experiment-rigor-skill.premortem.md`, FM-1..FM-10 + folded panel E1..E7); the fathom
  repo at `C:/Users/grima/Documents/fathom` (real `ledger/*.jsonl`); ADR-0007.

This is the re-gate pass. Per the round-≥2 posture: FIRST a resolution audit of every prior
finding against current text, THEN a hunt for fold-introduced and fold-missed defects under
the rising bar (a finding blocks only if it plausibly corrupts the decision the spec gates).

## Fold verification (do the 17 claimed edits exist at their anchors?)

Every Fold-ledger row lands. Anchor text is present at (or within ±1 line of) each cited
`artifact:line` — the off-by-one drift on FM-6 (`deliberately diverging` is line 234, not 233),
FM-7 (`8 cells × 12 = 96` is line 242, not 241) and E2 (`beta_binomial(...)` signature is line
214, not 213) is immaterial; the claimed edits are real. The nine repo-reality anchors round 1
cited were independently re-verified this pass and all hold:

- `gen_agents_md.py` globs `*/SKILL.md` (`:91`) and `--check` returns 1 on drift (`:119-127`).
- `.pre-commit-config.yaml` `run-tests` hook (`:60`) currently lacks `--with pyyaml` — the FM-2
  change is real and correctly targeted; `agents-md-fresh` (`:40-45`) is `always_run`.
- `run_tests.py` `SEARCH_DIRS=('plugins','evals')` (`:24`), `has_sentinel` accepts `ok:`/`skip:` (`:45`).
- `validate_plugins.py` `DESC_CAP=1536` (`:33`), `SKILL_LINE_CAP=500` (`:34`), `check_budgets` (`:181`).
- `lint_register.py` `DEFAULT_SCOPE = ROOT / 'plugins'` (`:34`); `word_budget.py:76` baseline message.
- `router_rules.json:5` is `"skills"`; `test_router.py` carries the 2/20 adversarial budget (`:159-173`)
  and per-skill recall/specificity floors (`:110-125`).
- Real fathom ledger keys (`ablation-v2.jsonl`): `cost_usd_est` (not `cost_usd`), `pin_level`,
  no `disposition`/`n`/`model_versions`; `verifier_results` present; `_is_pass` at `report.py:37`.

## Resolution audit (prior findings → current status)

```yaml
resolution_audit:
  - id: FM-1  # BLOCKER stale AGENTS.md premise
    status: RESOLVED
    evidence: spec:6,381 (regenerated AGENTS.md in PR04, gate green); §4:297-299 lists AGENTS.md in PR04
  - id: FM-2  # PyYAML gate command + hard-fail-not-skip
    status: RESOLVED
    evidence: spec:39-46 canonical `--with pyyaml` command + run-tests hook change; §2:254-259 hard-fail-not-skip
    note: the run-tests-hook edit is not explicitly bound to a PR, but §2/PR02 owns .pre-commit-config.yaml per the concept map — advisory only
  - id: FM-3  # real fathom ledger schema
    status: PARTIALLY-RESOLVED
    evidence: spec:272-277 pins cost_usd_est / verifier-derived disposition / n=count / pin_level, and §3 acceptance requires a "verbatim excerpt of a real fathom ledger"
    residual: "grade row's verifier_results" is inaccurate — verifier_results is on `trial` rows (R2-3)
  - id: FM-4  # fathom emitter removed
    status: RESOLVED
    evidence: no emit_record_fragment path remains (grep clean); Non-goals:65-67; Output-artifacts:6; §5:328
  - id: FM-5  # sealed-router regression fallback
    status: RESOLVED
    evidence: §4:308-311 names test_router.py as a gate + the ship-without-the-row fallback
  - id: FM-6  # pre-commit files-regex + pass_filenames
    status: RESOLVED
    evidence: §2:233-234 + Q6:182-187 files-regex + pass_filenames, commented as diverging; §2 acceptance:258-259 tests exclusion
  - id: FM-7  # declared-cells reconciliation (factors ambiguity)
    status: RESOLVED
    evidence: §2:240-242 recast to N_expected = Σ design.cells[].planned_n, "8 cells × 12 = 96; model tier is one factor level"; Context:13-14 and §5:339-340 consistent
  - id: FM-8  # closed verdict enum
    status: RESOLVED
    evidence: §3:279-280 enumerates the four verdicts and tags the confirmatory_* class
  - id: FM-9  # research-record sha256
    status: RESOLVED
    evidence: Context:24-27 records both hashes and marks the records local-only
  - id: FM-10  # exploratory-quarantine posterior
    status: PARTIALLY-RESOLVED
    evidence: §5:329-332 files the corrected posterior under the exploratory quarantine, "so it does not trip the post-hoc-as-pre-registered gate"
    residual: the referenced gate is never defined — no code, no §2 logic, no schema construct (R2-1). The fold rests on an unbuilt mechanism.
  - id: E1  # comprehension honest-claim downgrade
    status: RESOLVED
    evidence: adr:101-108 (":103 cannot prove the reads were genuine or fresh"); spec Q3:163-165 ceded-to-review, keel B2 posture
  - id: E2  # stats determinism
    status: RESOLVED
    evidence: §1:208-214 exact CIs, signature, ATOL 1e-9 / RTOL 1e-6, Beta(1,1) prior
  - id: E3  # canonical serialization + semantic-digest drift
    status: RESOLVED
    evidence: §3:264-269 semantic re-parse/digest, not byte diff; ER-PARITY:249-251 split; enforcement-table:94
  - id: E4  # per-tier source-hand policy
    status: RESOLVED
    evidence: Q5:173-178 probe/measurement-WARN/decision-FAIL; §2 ER-XCHECK:246-247
  - id: E5  # temporal-anchor honest claim
    status: RESOLVED
    evidence: adr:87-88 backdated-commit residual; §2 ER-ANCHOR:243-245
  - id: E6  # machine-readable schema.json + sync gate
    status: PARTIALLY-RESOLVED
    evidence: Q9:198-203, §3:277-283, enforcement-table:105 — spec is now schema.json-canonical
    residual: ADR Consequences:139 still calls SCHEMA.md canonical — the E6 pivot was not propagated to the ADR (R2-2)
  - id: E7  # missing definitions
    status: PARTIALLY-RESOLVED
    evidence: GRADE shape §3:281-283; decision_rule Q4:169-171; ledger_path §3:272; envelope fallback Q8/§5; 9 ER codes in §2
    residual: the "error codes" sub-item is incomplete — the comprehension gate (§5) and the post-hoc gate (§5 acceptance) have NO ER-codes, and the post-hoc gate has no logic at all (R2-1, R2-5)
```

## New / missed findings (rising bar)

```yaml
findings:
  - id: R2-1
    severity: BLOCKER
    evidence: spec:236-253 (the exhaustive §2 gate list — 9 codes, none for pre-registration consistency); spec:277-283 (schema.json field list — no partition field, no result→analysis_plan linkage); spec:330-332 ("the post-hoc-as-pre-registered gate", referenced, never defined); spec:338-347 + 371-372 (centerpiece acceptance + DoD headline require it); adr:20-22,98
    claim: >
      The "post-hoc-as-pre-registered gate" — the discipline's keystone, catching founding
      defect #5 and the ADR's own disqualifying case ("a post-hoc finding was presented as
      pre-registered") — is referenced as if it exists but is defined nowhere: no error code,
      no §2 gate logic, and no schema construct that would make it mechanically buildable. The
      centerpiece six-defect acceptance ("validate.py exits 1 ... naming all six by error
      code") and the DoD headline are therefore not satisfiable as written.
    detail: >
      §2 is the exhaustive home of validate.py's gates and codes (ER-SCHEMA, ER-RECON,
      ER-ANCHOR, ER-XCHECK, ER-STATS, ER-PARITY, ER-LINK, ER-THREAT, ER-PROBE). None catches a
      `confirmatory_*` result that was not pre-registered. ER-PROBE is explicitly probe-only
      ("a posterior on a probe"; "Q7's confirmatory_* verdict or a posterior on a probe",
      spec:253) — at measurement/decision tier confirmatory verdicts are ALLOWED, so ER-PROBE
      does not fire on the RG-2×2 decision-tier fixture. Decisively, the record schema
      (spec:277-283) carries the frozen `analysis_plan` (Q4) and a separate per-result
      `results.*.verdict`, but NO field links a result to the frozen prereg and NO
      confirmatory/exploratory "partition" is a schema construct — the word "partition" occurs
      only in prose (SKILL.md bright line spec:300; adr:98). So there is no data path by which
      validate.py could decide "this confirmatory result was post-hoc". FM-10 folded a fix that
      PRESUMES this gate exists (the corrected record is placed "so it does not trip" it); the
      fold rests on a mechanism the spec never builds. A zero-context implementer at PR05 must
      invent (a) the schema representation of the partition, (b) the result→prereg linkage that
      detects post-hoc-as-confirmatory, and (c) the error code — three material design choices
      the spec leaves open. Two implementers diverge on the discipline's central gate; the
      headline acceptance cannot be demonstrated.
    smallest_fix: >
      Add to §3/schema.json a confirmatory/exploratory partition construct and the linkage a
      result carries to the frozen analysis_plan (e.g. each declared confirmatory outcome ties
      to an `analysis_plan` entry; results outside it must carry an exploratory verdict), and
      add to §2 a named gate + error code (e.g. ER-PREREG: a `confirmatory_*` result whose
      outcome is absent from the frozen `analysis_plan`, or a post-hoc finding not under the
      exploratory partition, exits 1). Then re-word §5's defect #5 and FM-10's "quarantine"
      note to reference that code.
    disconfirming_test: >
      Point to any spec/ADR line that (a) names an error code for the post-hoc gate AND (b)
      defines the record field(s) linking a result's verdict to the frozen analysis_plan. If
      none exists, the six-defect fixture cannot produce a sixth itemised failure and the
      acceptance fails.
    target_section: §3 (schema.json) + §2 (new gate/code) + §5 (defect #5 wording)

  - id: R2-2
    severity: MINOR
    evidence: adr:139 ("SCHEMA.md is the canonical per-tier field list"); spec:198-199,282-283 (schema.json canonical, SCHEMA.md generated); spec:105 (sync gate)
    claim: >
      The E6 fold made schema.json canonical and SCHEMA.md generated in the spec, but ADR-0007
      Consequences:139 still says "SCHEMA.md is the canonical per-tier field list" — a direct
      contradiction the fold did not propagate to the ADR.
    detail: >
      Execution follows the spec, which is internally consistent (schema.json canonical,
      SCHEMA.md generated from it, a sync gate asserts agreement). So this does not corrupt
      the build. It is a stale cross-artifact reference that should be reconciled so the
      decision record does not assert the opposite of the spec it governs.
    smallest_fix: >
      Edit ADR-0007:139 to "schema.json is the canonical machine-readable per-tier field list;
      SCHEMA.md is generated from it (sync gate)". (ADR edit — out of scope for the cert block.)
    disconfirming_test: read adr:139 — it names SCHEMA.md, not schema.json, as canonical.
    target_section: ADR-0007 Consequences (not the spec)

  - id: R2-3
    severity: MINOR
    evidence: fathom ledger/ablation-v2.jsonl (kinds run/trial; verifier_results on `trial` rows; cost_usd_est on `run` rows); report.py:37,258,448; spec:273-274
    claim: >
      §3 says disposition is "derived from each grade row's verifier_results". In the real
      ledger, `verifier_results` lives on `trial` rows (there is no `grade` kind in the sampled
      bank; report.py has a `grading` branch but reads `t.get("verifier_results")` off trials),
      and `cost_usd_est` is on `run` rows — so from_fathom.py joins across run and trial rows.
    detail: >
      Not blocking: §3's acceptance pins the fixture to "a verbatim excerpt of a real fathom
      ledger ... verifier-derived disposition matching its rows", which anchors the implementer
      to the real shape and self-corrects the "grade row" wording. Flagged as an accuracy nit.
    smallest_fix: >
      §3: change "each grade row's verifier_results" to "each graded trial row's
      verifier_results (the rows fathom grades)".
    disconfirming_test: >
      `python -c "import json; print({json.loads(l)['kind'] for l in open('.../ledger/ablation-v2.jsonl')})"` — {run, trial}, no grade.
    consumed_input: fathom ledger/<bank>.jsonl trial + run rows, read this session.
    target_section: §3

  - id: R2-4
    severity: MAJOR
    evidence: spec:290 ("each of the three templates passes validate.py at its declared tier"); spec:122 ("Tier skeleton"); ER-ANCHOR spec:243-245; Q3 comprehension spec:156-165; Output-artifacts spec:6 (no template transcript files)
    claim: >
      The §3 acceptance requires the measurement and decision tier templates to pass the FULL
      validate.py, but a "skeleton" cannot: the anchor gate (ER-ANCHOR) needs a
      `plan_frozen_at.commit` that is in git history and predates the earliest run, and the
      decision-tier comprehension gate needs `transcript_path`s that resolve to files — and
      those transcript files are not in the deliverable list.
    detail: >
      A template that passes every gate is a complete valid record, not a skeleton; and a
      decision-tier template cannot pass without committed example transcript files that
      Output-artifacts (spec:6) does not list. So the acceptance is either unsatisfiable as
      written or the deliverable set is incomplete. Secondary to R2-1, but a concrete
      acceptance-vs-artifact contradiction, not a stylistic one.
    smallest_fix: >
      Narrow §3's clause to "each template passes validate.py's schema+tier well-formedness
      (ER-SCHEMA) at its declared tier" (not the anchor/comprehension/parity gates), OR make
      the templates complete minimal exemplars and add the decision template's example
      transcript files to Output-artifacts and the DoD.
    disconfirming_test: >
      Fill decision.yaml as a skeleton and run validate.py — it exits 1 on ER-ANCHOR (placeholder
      commit not in history) and on the comprehension gate (transcript_path does not resolve).
    target_section: §3 (acceptance) + Output artifacts / DoD
```

```yaml
cleared:
  - claim: all 17 Fold-ledger edits landed at their anchors (±1 line drift on FM-6/FM-7/E2, immaterial)
    cite: spec:415-431 fold ledger vs the cited spec/ADR lines, each re-read this pass
  - claim: FM-1 (the round-1 BLOCKER) is fully resolved and its repo premise re-verified
    cite: gen_agents_md.py:91,119-127; spec:6,381; §4:297-299
  - claim: the fathom emitter (FM-4) is fully excised — no cross-repo deliverable remains
    cite: grep emit_record_fragment → none; Non-goals:65-67; Output-artifacts:6; §5:328
  - claim: the real fathom ledger schema (FM-3) is correctly pinned in substance (cost_usd_est, verifier-derived disposition, n=count, pin_level)
    cite: ablation-v2.jsonl keys; report.py:37,414-417; spec:272-277
  - claim: the reconciliation term (FM-7) is now cell-sum based, dissolving the factors ambiguity, and the 8×12=96 / 48-per-arm arithmetic is internally consistent across Context, §2, §5
    cite: spec:13-14,240-242,339-340
  - claim: the sealed-router regression risk (FM-5) is named as a gate with a documented fallback
    cite: §4:308-311; test_router.py:110-125,159-173
  - claim: the PyYAML gate-command fix (FM-2) targets the correct hook line, which currently lacks --with pyyaml
    cite: .pre-commit-config.yaml:60; spec:39-46
```

## Prose

The fold is real and largely clean. All 17 ledger edits landed at their anchors, the round-1
BLOCKER (FM-1, stale AGENTS.md) is fully resolved and its repo premise re-verified, the fathom
emitter is cleanly excised, the fathom ledger schema is pinned in substance to the real rows,
and the reconciliation gate was recast onto an explicit cell-sum (dissolving the FM-7 factors
ambiguity) with arithmetic that reconciles end to end. The nine self-cited repo anchors all
hold against the current tree. On a purely resolution-audit basis this fold would pass.

What blocks certification is a defect the fold's own FM-10 row exposes rather than fixes.
FM-10 places the corrected RG-2×2 posterior "so it does not trip the post-hoc-as-pre-registered
gate" — but that gate is defined nowhere. §2's gate list is exhaustive and contains no
pre-registration-consistency check; ER-PROBE is explicitly probe-only; and the record schema
(§3) has no confirmatory/exploratory partition construct and no field linking a `results.*.verdict`
to the frozen `analysis_plan`. "Partition" is prose (a SKILL.md bright line, an ADR bullet),
never a schema field. So the discipline's keystone — catching a post-hoc finding dressed as
pre-registered, which the ADR itself names as the disqualifying case — has no mechanical home,
and the centerpiece six-defect acceptance ("validate.py ... naming all six by error code", a DoD
headline) cannot produce its sixth failure as written. A zero-context implementer at PR05 must
invent the partition schema, the result→prereg linkage, and the error code — three material
design choices on which two implementers diverge. That is fold-adjacent damage under the rising
bar: it corrupts the exact decision the spec gates (does validate.py catch the founding case's
six defects?), not merely the spec's polish. This is R2-1 (BLOCKER).

R2-4 (MAJOR) is a second, independent acceptance gap: the §3 requirement that all three tier
"skeleton" templates pass the full validate.py is unsatisfiable for the measurement/decision
templates (the anchor gate needs an in-history commit predating runs; the decision comprehension
gate needs resolving transcript files that are not deliverables). The remaining findings are
advisories: the E6 schema-canonicity pivot was not propagated to ADR-0007:139, which still calls
SCHEMA.md canonical (R2-2); and §3's "grade row's verifier_results" mislabels the `trial` rows
that carry them, though the real-ledger-excerpt acceptance self-corrects it (R2-3).

None of this impugns the ADR's decision or the skill's shape. R2-1 and R2-4 are bounded
spec/schema additions — but R2-1 requires a genuine design decision (how a result links to the
frozen pre-registration), not a mechanical one-liner, so it is a full revision item, not a
CONDITIONAL-CERTIFY condition. The certification block is left unfilled.

Unverified-offline: 0
PREMORTEM-VERDICT: NEEDS-REVISION — fresh non-author subagent (opus), round 2
