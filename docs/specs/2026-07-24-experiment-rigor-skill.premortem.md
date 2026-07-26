# Pre-mortem — experiment-rigor skill

- **Spec:** `docs/specs/2026-07-24-experiment-rigor-skill.md`
- **Date:** 2026-07-24
- **Reviewer:** fresh non-author subagent (opus), round 1
- **Spec-hash:** `2a030789eda58b4f4f125950621b40fe450ac159c73012b65aac142f6bd93d84`
- **Reviewed against:** the live working tree at 2026-07-24; keel kit 0.13.0; craft in-repo
  gates (`scripts/*.py`, `.pre-commit-config.yaml`, `.github/workflows/validate.yml`); the
  fathom repo at `C:/Users/grima/Documents/fathom`; the two founding research records
  (present in the working tree, gitignored/untracked).

Assume this series shipped and then failed. Failure modes below, most likely first, as a
YAML list, then prose, then a `cleared:` list of verified-correct claims.

```yaml
findings:
  - id: FM-1
    severity: BLOCKER
    evidence: scripts/gen_agents_md.py:91,120-133; .pre-commit-config.yaml:40-45; .github/workflows/validate.yml:27-28; spec:310-312
    claim: >
      The AGENTS.md freshness generator IS landed and enforced, but the DoD says it is not
      and marks regeneration "not-applicable" — so PR04 ships a new SKILL.md without
      regenerating AGENTS.md and the gate exits 1 in pre-commit AND CI.
    detail: >
      `gen_agents_md.py` globs `plugins/*/skills/*/SKILL.md` (line 91) and `--check` returns 1
      when the committed AGENTS.md differs from a fresh render (line 120-133). It is wired into
      pre-commit as `agents-md-fresh` (always_run) and into CI as "AGENTS.md freshness". Adding
      `plugins/humblepowers/skills/experiment-rigor/SKILL.md` (PR04, §4) makes `current != fresh`,
      so the gate fails on the very PR that adds the skill. The spec's DoD (line 310-312) asserts
      "that generator is not yet landed" — false; `scripts/gen_agents_md.py` exists (dated
      2026-07-23) and ADR-0002 that specifies it is Accepted. AGENTS.md currently contains zero
      `experiment-rigor` entries, so the drift is guaranteed the moment the skill lands.
    smallest_fix: >
      In the DoD, strike "(that generator is not yet landed)"; make AGENTS.md regeneration
      REQUIRED in PR04 (§4) and add AGENTS.md to PR04's touched-file list.
    blast_radius: >
      AGENTS.md is a repo-root generated index enforced in both pre-commit and CI; the only
      PR that perturbs its source is PR04 (adds a skill). PR05 adds no skill, so it does not
      re-drift the index.
    disconfirming_test: >
      Create a stub plugins/humblepowers/skills/experiment-rigor/SKILL.md and run
      `uv run --no-project python scripts/gen_agents_md.py --check`; it exits 1.
    consumed_input: >
      gen_agents_md.py reads each SKILL.md frontmatter (name + description) and renders AGENTS.md;
      a new SKILL.md is a new indexed row. Verified by reading the generator.
    target_section: Definition of Done (+ §4)

  - id: FM-2
    severity: MAJOR
    evidence: .pre-commit-config.yaml:58-63; scripts/run_tests.py:45,49-53; spec:35-36,181-186,205-209,223-228
    claim: >
      The record-handling scripts must parse record.yaml (nested YAML → PyYAML), but the spec's
      stated gate/acceptance command and the local pre-push runner do not provide pyyaml, so the
      central validate.py gate either hard-fails locally or passes green-via-`skip:` (vacuous).
    detail: >
      Only stats.py is declared stdlib-only (§1). validate.py/render.py/from_fathom.py consume
      record.yaml, whose shape (readers[], updates.prior.source_id, results.*.verdict, per-reader
      booleans) is deeply nested — not a stdlib-parseable flat subset. The spec's gate command and
      §1-§3 acceptance use `uv run --no-project python scripts/run_tests.py`, and the pre-commit
      run-tests hook is `uv run --no-project -- python scripts/run_tests.py` — neither carries
      `--with pyyaml`. Confirmed this session: `uv run --no-project python -c "import yaml"` →
      ModuleNotFoundError. run_tests.py accepts a `skip:` sentinel as PASS (line 45), so a test
      that guards `import yaml` with `skip:` makes the mechanism spine gate go GREEN while running
      zero real record checks locally. CI is unaffected (validate.yml:18 pip-installs pyyaml), so
      the local gate and CI diverge on the load-bearing gate. No existing plugin test imports yaml
      (no precedent to crib the pattern from).
    smallest_fix: >
      State that validate.py/render.py/from_fathom.py depend on pyyaml and give their gate/
      acceptance command as `uv run --no-project --with pyyaml -- python scripts/run_tests.py`;
      update the run-tests pre-commit hook to add `--with pyyaml`.
    blast_radius: >
      Editing the `run-tests` pre-commit hook (or the shared acceptance command) changes how the
      ENTIRE plugin/evals test suite runs, not just this skill's tests.
    disconfirming_test: >
      `uv run --no-project python -c "import yaml"` → ModuleNotFoundError (run: confirmed), so a
      record-parsing test under the stated command cannot import yaml.
    target_section: Gate commands / §2 / §3

  - id: FM-3
    severity: MAJOR
    evidence: fathom src/fathom/report.py:37,258,414-417; fathom ledger row keys (bank/cli_version/config_hash/cost_usd_est/dataset_version/duration/exit_code/kind/pin_level/repeat/task_id/tool_git_sha/turns/usage); spec:199-200,219-220
    claim: >
      from_fathom.py and the §2 run cross-check are modelled on a fathom ledger schema that does
      not exist; the §3 acceptance is satisfiable against a hand-invented fixture and passes
      without real-fathom compatibility.
    detail: >
      The spec says from_fathom.py reads "disposition, n, cost_usd, model_versions" from ledger
      rows, and §2 cross-checks hand fields against "the ledger rows". Real rows carry
      `cost_usd_est`, not `cost_usd` — fathom's own report.py:414-417 warns "cost_usd_est ... NOT
      usage['cost_usd'] — the CLI never emits that key". There is no `disposition` field: pass/fail
      is derived from GRADE rows' `verifier_results` via `_is_pass` (report.py:37,258), joined to
      run rows. `n` is a row count, not a field. There is no `model_versions` field; the nearest
      is `pin_level` (a tier label like "strong") and `cli_version`/`tool_git_sha` (empty "" in the
      sampled row). So three of the four cross-checked quantities are derivations/aggregations, not
      readable fields — the reuse-on-unverified-shape class.
    smallest_fix: >
      §3 pins from_fathom.py to the real ledger schema (cost_usd_est; disposition from grade-row
      verifier_results via the same pass predicate; n = count; model version from pin_level/config,
      not a model_versions field), and requires the §3 test fixture be a real fathom ledger sample
      rather than an invented shape; §2's cross-check field list is corrected to those quantities.
    disconfirming_test: >
      `python -c "import json; print(sorted(json.loads(open('.../fathom/ledger/ablation-v2.jsonl').readline()).keys()))"`
      shows no `disposition`/`cost_usd`/`n`/`model_versions`.
    consumed_input: >
      fathom `ledger/<bank>.jsonl` rows, read directly this session — the schema above is the
      consumed surface.
    target_section: §3 (and §2)

  - id: FM-4
    severity: MAJOR
    evidence: fathom src/fathom listing (report.py is a module; no report/ package); spec:6,259-261; spec PR-manifest:284
    claim: >
      The fathom-side emitter is an un-decomposable, untested, mis-pathed deliverable inside a
      craft-repo PR.
    detail: >
      The output-artifacts line and §5 list `fathom/src/fathom/report/emit_record_fragment.py` in
      the fathom repo, and the PR manifest maps this to PR05 ("one concern? yes"). A craft-collection
      PR cannot modify another repo, so the emitter is a separate change with no PR slot in this
      series; no §5 acceptance criterion tests it; and the path conflicts with fathom's layout —
      `src/fathom/report.py` is a MODULE, there is no `report/` package, so `report/emit_record_fragment.py`
      cannot coexist with `report.py`. In-repo from_fathom.py does not need the emitter (it reads the
      ledger directly), so the emitter is cleanly detachable from this series.
    smallest_fix: >
      Remove the fathom emitter from this spec's output-artifacts, §5, and DoD (track it as a
      separate fathom-repo change with its own acceptance), or mark it explicitly out-of-series with
      no gate here and correct the path to fathom's module layout.
    disconfirming_test: >
      `ls C:/Users/grima/Documents/fathom/src/fathom/report/` — not a directory; `report.py` is a file.
    target_section: §5 / Output artifacts / PR manifest

  - id: FM-5
    severity: MAJOR
    evidence: plugins/humblepowers/skills/choosing-tools/scripts/test_router.py:159-174,110-125; router.py:42-59; spec:234-254
    claim: >
      Adding the choosing-tools router row is a change to SEALED shared config with zero remaining
      false-fire budget, and the spec neither flags it nor plans for a regression.
    detail: >
      router_rules.json feeds test_router.py, run by run_tests.py. The adversarial holdout
      false-fire budget is 2/20 and already fully consumed ("any third false-fire is a regression",
      test_router.py:159-174). There are also per-skill floors (recall >= 0.60, specificity >= 0.90,
      lines 110-125) and the sealed recall-holdout floors. experiment-rigor's new experiment/eval/
      measurement regexes can fire on one of the 20 adversarial near-miss negatives, or displace a
      candidate in the top-2 (max_candidates=2, router.py:59), tripping run_tests.py at PR04. §4's
      NAMED acceptance gates are lint_register, word_budget, and validate_plugins — test_router.py is
      not named, and the spec offers no fallback if the row regresses a sealed set.
    smallest_fix: >
      §4 must require running run_tests.py/test_router.py after adding the row, and state the
      fallback: ship the skill WITHOUT a router row if the row cannot clear the 2/20 budget and the
      recall/specificity floors (the skill's own frontmatter description still triggers it).
    blast_radius: >
      router_rules.json is shared dispatch config gated by three sealed test_router.py assertions;
      a new row can regress any routed skill's floor or the global 2/20 adversarial budget.
    disconfirming_test: >
      Add the row and run `uv run --no-project python scripts/run_tests.py`; test_router.py's
      floors and the 2/20 budget stay green.
    consumed_input: >
      router_rules.json['skills'], consumed by test_router.py over the sealed
      holdout/dispatch-router-{recall,adversarial}.json sets — verified by reading the test.
    target_section: §4

  - id: FM-6
    severity: MAJOR
    evidence: .pre-commit-config.yaml:32-63; spec:207-209; spec Q6:152-156
    claim: >
      The travelling-record pre-commit gate's "skips gitignored docs/design records" property is
      asserted in the acceptance but is untested and diverges by implementation choice.
    detail: >
      §2 acceptance asserts "the pre-commit hook matches `**/record.yaml` while skipping the
      gitignored `docs/design/**` records." pre-commit `files:` is a regex, not a glob; and the
      repo's local-hook convention is `always_run: true, pass_filenames: false` (every existing
      local hook). A validate.py that internally rglobs `**/record.yaml` under that convention does
      NOT honor .gitignore, so it would scan the gitignored docs/design records — contradicting Q6
      ("local records validated on demand only") and the acceptance. No test proves the skip:
      test_validate.py exercises validate.py's logic, not pre-commit's file selection, so the clause
      is vacuously "satisfied".
    smallest_fix: >
      §2 specifies the hook uses `files: (^|/)record\.yaml$` with `pass_filenames: true` (pre-commit
      only feeds staged/tracked files, so gitignored records are naturally excluded) and drops the
      "glob" wording; if always_run is kept, validate.py must take explicit paths and a test must
      assert docs/design exclusion.
    disconfirming_test: >
      Force-add a docs/design/x/record.yaml plus a travelling record, stage both, run the hook —
      only the travelling record is validated.
    target_section: §2

  - id: FM-7
    severity: MINOR
    evidence: spec:197; spec enforcement-table:82; research record:38 ("2x2 x 2 tiers x 6 tasks x 2 waves = 96")
    claim: >
      "factors x tiers x tasks x waves" is ambiguous — reconciliation needs the factorial CELL
      count (4 for a 2x2), not the number of factors (2) — and could mis-build the gate that
      catches the founding "96 != 48" defect.
    detail: >
      The founding case reconciles as 4 x 2 x 6 x 2 = 96, where 4 is the 2x2 cell count. If
      SCHEMA.md/validate.py encode `factors` as the count of factors (2), N = 2 x 2 x 6 x 2 = 48 and
      the gate rejects the correct 96 record (or accepts a wrong one). The centerpiece reconciliation
      gate must not itself be built on the arithmetic ambiguity it exists to catch.
    smallest_fix: >
      SCHEMA.md/§2 define the term as the product of factor levels (cell count), with the
      2x2 -> 4 worked example, so the record encodes 4.
    disconfirming_test: >
      Encode the RG-2x2 record with the 2x2 as 4 cells; validate.py reconciles to 96.
    target_section: §2 / §3 (SCHEMA.md)

  - id: FM-8
    severity: MINOR
    evidence: spec Q7:158-159; spec:203
    claim: >
      The "confirmatory class" of `results.*.verdict` values (probe refusal, Q7) and the verdict
      enum are never enumerated, so two implementers diverge on what a probe may carry.
    smallest_fix: >
      SCHEMA.md enumerates the verdict enum and tags each member confirmatory/exploratory; §2
      refers to that tag rather than an unnamed "class".
    disconfirming_test: >
      A probe fixture carrying each enumerated verdict; only confirmatory-tagged ones exit 1.
    target_section: §3 (SCHEMA.md) / §2

  - id: FM-9
    severity: MINOR
    evidence: git ls-files docs/research/ (empty); git check-ignore docs/research/foo.md (ignored); spec:20-22; adr:34-36
    claim: >
      The two founding research records the spec and ADR reason against are gitignored and
      untracked, and no SHA is recorded, so a reader on a clean clone cannot verify the linchpin
      empirical claims (36/48, 18/48, the six defects).
    detail: >
      The records are present in THIS working tree and do ground the numbers (see cleared list), so
      this is not blocking; but the travelling spec+ADR cite empirical linchpins the repo does not
      carry and against which the pre-mortem's "record the SHA of an editable dependency" rule
      cannot be satisfied.
    smallest_fix: >
      Note in Context that the founding records are local-only, and inline the reconciled N and the
      two footprint counts (36/48, 18/48) into the spec so the acceptance fixture is self-grounding.
    disconfirming_test: n/a — a documentation-portability observation, closed by inlining.
    target_section: Context

  - id: FM-10
    severity: MINOR
    evidence: spec §1:181-186; spec §5:267-274; research record:54,66-72 (footprint is "secundario/exploratorio")
    claim: >
      The founding footprint move is exploratory/post-hoc (defect #5 requires it be quarantined),
      yet §1 computes a Beta-Binomial posterior on it; the spec never says the CORRECTED record files
      that posterior inside the exploratory partition, so the "corrected" acceptance fixture could
      itself trip the post-hoc-as-pre-registered gate.
    smallest_fix: >
      State in §5 that the corrected RG-2x2 record places the footprint Beta-Binomial under the
      exploratory quarantine, and that stats-on-a-quarantined-exploratory-finding is permitted at
      measurement/decision tier (distinct from the probe posterior refusal).
    disconfirming_test: >
      Run validate.py on the corrected record; it exits 0 with the footprint posterior present under
      the exploratory partition.
    target_section: §5 (+ §1 note)

cleared:
  - claim: run_tests.py discovers plugins/ + evals/ and enforces an ok:/skip: sentinel
    cite: scripts/run_tests.py:24,45 — SEARCH_DIRS=('plugins','evals'); has_sentinel accepts ok:/skip:
  - claim: validate_plugins caps (DESC_CAP=1536, SKILL_LINE_CAP=500) and word-budget ratchet
    cite: scripts/validate_plugins.py:33,34,181 — DESC_CAP, SKILL_LINE_CAP, check_budgets
  - claim: lint_register default scope is plugins/ (spec's docs/specs prose is out of scope)
    cite: scripts/lint_register.py:34 — DEFAULT_SCOPE = ROOT / 'plugins'
  - claim: word_budget fails a body with no baseline ("no word-budget baseline")
    cite: scripts/word_budget.py:76
  - claim: skill-authoring §Shipping requirement item 2 is "Sealed holdout, with a birth baseline"
    cite: plugins/humblepowers/skills/skill-authoring/SKILL.md:91
  - claim: BASELINES.md is the seal-with-baseline record; router_rules.json['skills'] array anchor
    cite: evals/trigger/holdout/BASELINES.md:1; router_rules.json:5
  - claim: the founding-case numbers reconcile and are grounded
    cite: research record:38 (2x2 x 2 x 6 x 2 = 96, $17.21), :66-67 (36/48=75% vs 18/48=37.5%), :119 (4x2x6=48, text said 96), :123-124 (denominators absent; truth is 36/48 and 18/48) — §1's 36/48, 18/48 and §5's six defects match
  - claim: choosing-tools dev eval and evals/config.json thresholds exist for reuse
    cite: evals/trigger/choosing-tools.json; evals/config.json (trigger_recall 0.8 / specificity 0.9 / correct_usage 0.7)
```

## Prose

The design is coherent and the guardrail thesis (mechanism over prose; a loud-failing gate per
load-bearing rule) is sound. The spec's own bookkeeping is largely accurate: line-cited gate
references check out, and the founding RG-2x2 numbers the acceptance fixture depends on are
grounded in the present working-tree research record (36/48 vs 18/48, N reconciling to 96 via
4x2x6x2, the six named defects). Those are recorded in `cleared:` so they are not re-litigated.

What blocks execution is a stale premise about the tree, not a flaw in the discipline. FM-1 is
the decisive one: the AGENTS.md generator the DoD calls "not yet landed" is landed and enforced
in both pre-commit and CI, so PR04 — the PR that adds the skill — fails the freshness gate on
arrival unless it also regenerates AGENTS.md. This is the exact cross-PR generated-artifact
freshness class: a wave that plans no regeneration leaves a mirror stale and its gate fails at
execution on a spec every pass certified. The fix is a two-line DoD correction plus adding
AGENTS.md to PR04's file list.

The MAJORs cluster around seams the spec models but did not read to the metal. The record
scripts introduce PyYAML into a plugin test suite whose stated runner and pre-push hook do not
carry it (FM-2, confirmed: `import yaml` raises under `uv run --no-project`), and the `skip:`
sentinel lets the central gate pass vacuously locally while only CI exercises it. The fathom
bridge is modelled on a ledger schema that does not exist — `cost_usd_est` not `cost_usd`
(fathom's own code warns about this exact key), disposition derived from grade rows, `n` a
count, no `model_versions` field (FM-3) — so its acceptance passes against an invented fixture.
The fathom-side emitter cannot be a PR in this repo, has no acceptance test, and targets a path
that collides with fathom's existing `report.py` module (FM-4). And the router row edits sealed
shared config whose adversarial false-fire budget (2/20) is already fully spent, with no plan
for a regression (FM-5). FM-6 is a vacuously-satisfiable acceptance clause: the "skips
gitignored docs/design records" property is asserted but nothing tests it and the repo's hook
convention pulls toward the opposite behavior.

The MINORs (FM-7..FM-10) are definitional or documentation gaps: the reconciliation term
"factors" needs to mean cell-count; the confirmatory verdict class needs enumerating; the
founding records are local-only with no SHA; and the corrected fixture must file the exploratory
footprint posterior under quarantine so it does not trip its own gate.

None of the findings impugn the ADR's decision or the skill's shape. They are execution-reality
gaps a design pass could not see — resolvable by spec/manifest edits, no re-architecture.

Unverified-offline: 0
PREMORTEM-VERDICT: NEEDS-REVISION — fresh non-author subagent (opus), round 1
