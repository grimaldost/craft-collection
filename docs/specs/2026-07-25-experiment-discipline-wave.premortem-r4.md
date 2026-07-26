# Pre-mortem (round 4) — the experiment-discipline wave

- **Spec:** `docs/specs/2026-07-25-experiment-discipline-wave.md`
- **Date:** 2026-07-25
- **Reviewer:** fresh non-author subagent (opus), round 4
- **Spec-hash:** `7326cc64c7479587d10401a4fc4068a3aa3e63bfe83b5cc0450dc319151ac103`
- **Reviewed against:** worktree `C:/Users/grima/Documents/craft-collection-rigor`, branch
  `feat/experiment-rigor-skill` @ `113cc06` (clean apart from the untracked wave documents);
  `docs/adr/0008-experiment-discipline-plugin.md` read; all three prior pre-mortems read as
  the verdict record; keel kit 0.13.0
- **Prior rounds:** `…premortem.md` (r1, NEEDS-REVISION, 5 BLOCKER / 15 MAJOR / 5 MINOR);
  `…premortem-r2.md` (r2, NEEDS-REVISION, 1 BLOCKER / 2 MAJOR / 6 MINOR);
  `…premortem-r3.md` (r3, NEEDS-REVISION, 0 BLOCKER / 3 MAJOR / 3 MINOR)

The third fold landed and it landed well. All six round-3 findings resolve to current text,
all 58 fold-ledger anchors and all 23 load-bearing body cites resolve at the exact line and
string (mechanically re-checked this round, zero drift), and the two folds that carried real
design weight — the pin's PR ownership under fallback-on-lookup-failure semantics, and the
control arm's corrected prior with a two-sided genuine-side rule — are both right and both
land in the places that matter.

No new BLOCKER and no new MAJOR. What round 4 finds is the same defect class round 3 found,
one artifact over and one order of magnitude smaller: the fold that moved the schema edit
into PR01 did not re-derive the DoD's mirror sweep, so PR01 now perturbs a golden with a
per-change freshness gate that no section assigns it to regenerate. I executed it: 45/46,
`test_schema.py` red, and 46/46 again once the regeneration lands. Three other minor
residues sit in text the third fold newly wrote — a parity criterion that over-reaches to an
arm whose text is authored rather than router-derived, an arm-rules composition the spec
still leaves to the implementer with a threat row that reads "controlled" either way, and a
cited baseline number transported from a register the bank deliberately does not use.

All four are named ≤2-line edits with determined answers. None of them is a redesign, none
touches the arms, outcomes, analysis plan, or spend, and three of them must land before §5's
freeze commit because they are what the frozen record says about itself.

---

## Resolution audit (round-3 findings against the current text)

| Finding | Status | Current-text evidence |
|---|---|---|
| R3-1 pin implemented as worded turns `test_acceptance_rg2x2.py` red; PR ownership self-contradictory (MAJOR) | **RESOLVED** | Both halves land. (a) §1 :291-297 states the rule as "**fall back when the pinned lookup fails**, not merely when the field is absent", with the trade explicitly stated ("a *wrong* pin resolves silently through the current path instead of failing loudly, so the pin is a durability aid, not a second integrity check"). (b) §1 :280-286 "**PR01 therefore lands the whole mechanism — the field, its reader, and the fixture that exercises it — not just the value**", naming `templates/schema.json`, `check_prereg` in `scripts/validate.py`, and `test_acceptance_rg2x2.py`; the enforcement row :133 now reads "§1 lands `plan_frozen_at.path`, its reader in `check_prereg`, and the acceptance-fixture adjustment"; the concept→module map gains the row at :148. The legality argument re-verified independently: `check_prereg` (validate.py:888-931) reads `plan_frozen_at` only for `commit` (:892) and diffs `design.cells`, `analysis_plan` minus amendments, and the frozen outcomes — `path` is never compared. The two-stage move test at :313-322 matches r3's executed result exactly (46/46 pre-move; 46/46 post-move once `AGENTS.md` is regenerated; the without-pin counterfactual recorded as 44/46). One residue, new and mine: R4-4 |
| R3-2 control is not a no-treatment baseline; the near-zero prior is argued from a premise the design refutes (MAJOR) | **RESOLVED**, one residue | Part B :708-730 is rewritten from the top: "**not a no-treatment baseline**", "Every arm loads `plugins/experiment-discipline` with the `Skill` tool available", "Control therefore measures **the skill's own trigger surface with no hint**", "`wide − control` is the hint's **marginal** effect over a loaded, unhinted skill, not 'convention versus nothing'". The genuine-side rule is two-sided at :722-726; the compressed-contrast spend risk is stated at :727-729; §5's frozen run config now names "**the tool allowlist stated explicitly, including whether `Skill` is in it**" (:511-514) with the consequence spelled out. Residue: the number the corrected prior cites is transported from the wrong register — R4-3 |
| R3-3 nothing ties the firing table to the real router (MAJOR) | **RESOLVED** | Settled decisions :197-215 now has the generator "**drive the real router read-only** — it imports `router`, calls `load_rules(<arm rules file>)` (the path parameter the function already accepts), `route`, and `hint_line`". Re-verified at source: `load_rules(path: str \| Path = RULES_PATH)` (router.py:34), `route` (:42-59), `hint_line` (:62-76). Every semantic r3 said the enumeration omitted is now covered by construction and named as such — the `Cf` strip, the 4000-char truncation, `.lower()` (router.py:46), the order-preserving dedup and three-word cap (`list(dict.fromkeys(m['matched']))[:3]`, :68), `_ascii`, and the `'; '` join (:72). The pre-filter constants and both skips are named against `inject_dispatch.py:52` `MIN_WORDS = 4` (verified, with `MIN_CHARS = 15` at :53, the `SYNTHETIC_PREFIXES` skip at :107, and the slash skip). The parity test at :543-545 makes fidelity a checked property. Residue: the parity criterion's scope — R4-2 |
| R3-4 `known_versions` mirrored in `validate._EMBEDDED_SCHEMA` | **RESOLVED** | §4 :428-431 "**and bump `validate._EMBEDDED_SCHEMA['known_versions']` in the same diff**", with the sync test named as the reason; DoD :639-642 adds the mirror row and re-derives the "No other generated artifacts" close. Re-verified independently: `_EMBEDDED_SCHEMA = {'known_versions': [1], …}` (validate.py:84-85); `test_schema_json_agrees_with_embedded_schema` asserts `data[key] == value` for every embedded key. Executed the orthogonality: a `known_versions` bump alone does **not** change `SCHEMA.md` (so R3-4 and R4-4 really are two different mirrors, not one) |
| R3-5 sign test names no tie rule and no recomputation | **RESOLVED as to the tie rule; the recomputation half is a declared, defensible divergence** | §4 :412-420 fixes the rule before the freeze: "**a zero per-cluster delta is dropped, and the surviving effective cluster count is recorded beside the p-value**", with the reason stated (ties are the modal cluster at 2 repeats, so the effective n is load-bearing). The recomputation half is declined on the record: "The p-value itself needs no gate: it is derivable by hand from the recorded deltas (the effective n and the count of positives are both in the record)". I checked that claim rather than accepting it: the per-outcome `clusters` block carries per-prompt per-arm numerator and denominator, so every per-cluster delta — and therefore its sign, the tie count, and the surviving n — is fully determined by recorded fields. The claim is true, the enforcement row at :132 is honestly scoped to "estimate, SE, and interval", and the sign test is the *robustness bound*, not the primary interval. I accept the divergence as stated design posture |
| R3-6 primeability binds the bank as well as the rules | **RESOLVED** | §5 :492-498 "**the constraint binds the bank as well as the rules** — a wide pattern whose span reaches a noun can echo an element name such as 'method' straight into the treatment. So the same test runs over the bank, and a violating row is repaired **before the freeze** by editing the bank prompt or narrowing the pattern, the same pre-registered shape as the PT-BR firing-rate fallback below." The acceptance criterion carries it at :548-549 ("neither any injected text **nor any bank prompt**"). The mechanism re-verified: `matched.append(hit.group(0).strip())` (router.py:55) rendered at :68, so echoed words are literal prompt spans |

No round-3 finding is UNRESOLVED or PARTIALLY-RESOLVED. Two carry residues in text the fold
itself wrote; both are below, as R4-2 and R4-3.

---

## Findings

```yaml
- id: R4-1
  severity: MINOR
  title: "The arm rule files' composition is unstated, and under the only reading consistent with 'control (nothing injected)' the `custom_candidate_displacement` threat's stated control is a column that cannot vary"
  evidence: >-
    Spec:451-459 defines the arms by their evaluation-act ROW ("**narrow** (a conservative row
    for the direct evaluation-act register…)", "**wide** (adds the bare 'test / evaluate'
    class…)") and states "**control** (nothing injected)". Settled decisions :199 has the
    generator call `router.load_rules(<arm rules file>)`, and `load_rules` (router.py:34-40)
    consumes a COMPLETE rules document — `rules['skills']` plus the top-level
    `max_candidates`. Nothing in §5, the concept->module map row (:165 "Detector arm rule
    variants"), or the acceptance criterion says which of the shipped nine rows each arm file
    carries. Enumerated the shipped rules to ground the fork: `router_rules.json` holds nine
    rows at `max_candidates: 2`, among them `humblepowers:test-driven-development` (5
    patterns) and `humblepowers:systematic-debugging` (8 patterns) — exactly the rows a decoy
    such as "run the test suite and paste the output" is drawn to match. So the two readings
    are not both satisfiable: a full-copy arm file makes CONTROL fire (contradicting ":451
    nothing injected"), and a single-row arm file makes displacement structurally impossible
    (one row can never lose a `max_candidates: 2` race).
  detail: >-
    The single-row reading is the one the spec's own words force, and it is the right design.
    What it does not support is the threat row: ":524 `custom_candidate_displacement` is
    controlled by the firing table recording each arm's candidate list per prompt" — under
    single-row files that column reads `[experiment-discipline:experiment-rigor]` or `[]` on
    every row of every arm, so it records nothing and controls nothing. The real displacement
    risk (adding the row to the LIVE nine-row rules pushes another candidate out) is a
    production question this design does not measure at all — the same bucket as the live-hook
    delivery precondition the wave already names honestly. Round 1's FM-9 established the
    standard here: a threat row must not assert more than the design delivers, and the fold
    got that exactly right for `token_length_confound`. This is the one remaining row that
    still says "controlled" for a mechanism the design cannot exercise. Two further sentences
    inherit it: Part B :722-726 justifies the two-sided genuine-side rule with "the router
    keeps at most two candidates on a hits-descending sort, which is the
    `custom_candidate_displacement` threat this section already names" — but the measured
    spawn never runs the router (the injection is delivered directly on stdin, :216-219), so
    the behavioral displacement claim it wants ("the injected hint displaces the model's own
    dispatch") is sound on its own and does not need the router clause at all; and Settled
    decisions :208 lists "the join across candidates" among the fidelity the real router buys
    for free, which under single-row files never executes. MINOR rather than MAJOR because the
    pre-spend audit catches the bad branch for free: the frozen firing table is reviewed
    before a cent is spent (:205-206, :731-737), and a control arm that fires is visible in it
    on the first read.
  smallest_fix: "§5 pins the composition — 'each arm's rules file carries the evaluation-act row alone (control carries none), so the shipped nine-row competition is out of frame' — and `custom_candidate_displacement` becomes **residual**, its statement naming that the offline table exhibits no displacement because no competing rows are present, and that displacement under the live nine-row rules stands with live-hook delivery as an unmeasured production precondition."
  consumed_input: "`router.load_rules(path)` at router.py:34-40 consumes a whole rules document (`rules['skills']`, compiled `patterns` / `negative_patterns`); `route` at :57-59 consumes the top-level `max_candidates` for the hits-descending slice. Both read at source, and the shipped nine rows enumerated by parsing `router_rules.json` (max_candidates 2; TDD and systematic-debugging present)."
  disconfirming_test: "Build a candidate control rules file as a full copy of `router_rules.json` minus the experiment-rigor row, run `router.route` over three draft decoys ('run the test suite and paste the output' and two siblings); if none returns a candidate, control can carry the full row set without firing and both readings coexist."
  target_section: "section 5 (and Part B's two-sided-rule justification)"

- id: R4-2
  severity: MINOR
  title: "The new parity criterion asserts every frozen row's injected text equals the real router's output, but inert's text is authored by design — the criterion is unsatisfiable for one arm, and the literal repair silently changes what `wide − inert` measures"
  evidence: >-
    Spec:543-545 (folded from R3-3): "**a parity test asserts every frozen row's candidate list
    and injected text equal the real router's output for that prompt under that arm's rules**".
    Against §5's own construction two paragraphs earlier (:460-470): the router-derived text is
    scoped to two arms — "so `narrow` and `wide` inject text that varies with the prompt that
    triggered it… because it *is* the live composition path" — and then "`inert` **then gets a
    per-prompt neutral text** matched to **that prompt's** wide text within ±5% on estimated
    tokens", i.e. authored, not composed by `hint_line`. `hint_line` (router.py:62-76)
    unconditionally emits "Prompt wording matches triggers for: <id> (matched: …)", so no
    rules file can make it emit an authored neutral sentence.
  detail: >-
    Control is fine (empty candidates, empty text, parity holds trivially). Inert is not: its
    injected-text column can never equal `hint_line`'s output for its own rules. Two
    implementers diverge and the second branch is the costly one. (a) The sensible reading
    scopes parity to the router-derived arms and asserts, for inert, that the firing row set
    equals wide's — which is what §5 already requires at :547 ("wide and inert firing on an
    identical row set"). (b) The literal reading is satisfiable in exactly one way: give inert
    a rules row carrying wide's patterns under a neutral id, so `hint_line` emits "Prompt
    wording matches triggers for: <neutral-id> (matched: …). Check fit before starting;
    'nothing fits' remains a valid outcome." That text names no experiment, evaluation, rigor,
    or tier, so it passes §5's stated inert constraint (:458-459) and passes parity and passes
    the ±5% token match almost automatically — and it is no longer an inert control, because it
    still instructs the model to consult a skill. `wide − inert` would then measure "naming
    experiment-rigor versus naming anything", not content versus neutral preamble, which is the
    one contrast §5 says "isolates content" (:452-453) and Part B names as the
    confound-separation secondary (:657-658). This is the fold-verbatim hazard the method
    warns about: R3-3's `smallest_fix` was written about the generator and applied unchanged
    to a criterion that has to quantify over four arms.
  smallest_fix: "§5's parity criterion is scoped: 'for the router-derived arms (`narrow`, `wide`) a parity test asserts every frozen row's candidate list and injected text equal the real router's output under that arm's rules; `inert` is asserted against wide's row set and its authored neutral text, and `control` against an empty candidate list'."
  consumed_input: "`router.hint_line` at router.py:62-76 — the fixed prefix and suffix are literals in the function, not per-row fields, so no rules file can vary them; read at source. `router_rules.json` rows confirmed to carry only {id, patterns, negative_patterns, min_hits}."
  disconfirming_test: "Call `router.hint_line(router.route(<a wide-matching prompt>, router.load_rules(<a draft inert rules file>)))` and compare the output to any sentence that would qualify as 'a neutral house-style text'; if the two can be made equal, the criterion is satisfiable for inert as written."
  target_section: "section 5"

- id: R4-3
  severity: MINOR
  title: "The corrected control prior transports a 0.33 measured on a paraphrase-dominated holdout onto a bank deliberately authored in the direct register; the only same-register observation is one query at 3/3, so the un-named risk on the genuine half is a ceiling, not only compression"
  evidence: >-
    Spec:715-721: "the sealed holdout put its description at 0.33 recall [0.15, 0.58], with the
    lexically adjacent positive at 3/3 (`evals/trigger/holdout/BASELINES.md:18`
    `experiment-rigor`) — **measured on the direct evaluation-act register the genuine half is
    deliberately authored in**, because that is the register the arms' patterns must match. So
    control is expected **materially above zero** on the genuine half, low but not structurally
    floored". Read BASELINES.md:18 end to end: "the holdout positives are **pure intent
    paraphrases (authored to avoid the dev set's lexical markers)**, and the one
    lexical-adjacent positive ('lock the hypothesis and the pass rule…') hit 3/3 while the four
    paraphrase positives missed (0/3, 2/3, 0/3, 0/3)". So 5/15 = 0.33 is dominated by exactly
    the register §5's bank does NOT use (:474-475 "the genuine half carrying the direct-register
    phrasings the arms can actually match (a pure-paraphrase bank would be null on this
    instrument)"). Two further transport gaps, both checkable: that run is a TRIGGER arm —
    `evals/config.json` `trigger_max_turns: 3`, `allowed_tools_trigger: Skill,Read,Glob,Grep`,
    against the detector's task-shaped spawns at a turn cap of 6 (:228) — and its metric is
    ACTIVATION, where the oracle scores line-and-skeleton (:483-487).
  detail: >-
    The prior's DIRECTION is right and R3-2's correction was the important move. What the fold
    added on top is the attribution clause, and that clause is false of the number it is
    attached to: the aggregate was measured on the register the bank avoids, and the only
    same-register observation is a single query at 3/3 (n=1 × 3 repeats). Read honestly, the
    genuine-side prior is not "low" — it is WIDE, and its upper tail is a ceiling. That matters
    because a ceiling is a different failure from the compression the spec does name (:727-729):
    a compressed contrast is a power problem the two-sided rule and the achieved-precision
    report handle; a control arm at ceiling leaves `wide − control` no headroom at all, and none
    of §6's four pre-committed interpretations (:575-581) distinguishes "nothing moved because
    there is no effect" from "nothing moved because there was no room". The one piece of
    in-repo evidence cutting the other way is the founding case itself — RG-2×2 measured the
    ritual declaration at 47/48 while the behavior it declared occurred 0/48 (Context :19-26) —
    which is precisely why the oracle requires BOTH and why the line-only rate is already a
    first-class number (:679). So a ceiling on the composite is far from established, and this
    stays MINOR. But the record is about to be frozen with a baseline expectation whose cited
    evidence does not say what the sentence says it says, in the one field this discipline holds
    cannot be revised afterwards.
  smallest_fix: "Part B's baseline expectation states the transport honestly — 'the 0.33 aggregate was measured on a holdout whose four of five positives are pure intent paraphrases (BASELINES.md:18); the single same-register positive hit 3/3, so the genuine-side prior is wide rather than low' — and §6's null leg adds 'a null with control at or near ceiling on the genuine half is recorded as no headroom, not as no effect, and the pre-registered read is the decoy side and `wide − inert`'."
  consumed_input: "`evals/trigger/holdout/BASELINES.md:18` read whole (register composition, per-positive breakdown 3/3 + 0/3 + 2/3 + 0/3 + 0/3, specificity 1.00, $2.67, 27 runs); `evals/config.json` read for `trigger_max_turns: 3` and `allowed_tools_trigger` — the arm profile that produced the number."
  disconfirming_test: "Two control-arm spawns (no injection, `--plugin-dir plugins/experiment-discipline`, §5's frozen allowlist) on two direct-register genuine prompts, scored for the format-(a) line AND the five elements. Both correct => the ceiling is live and the primary contrast needs re-pointing before spend; both empty => the 'low' reading holds and only the attribution needs repair. ~$0.30, and it is the same probe R3-2 already priced."
  target_section: "Experiment design (Part B) (and section 6's null leg)"

- id: R4-4
  severity: MINOR
  title: "PR01 now edits `templates/schema.json`, whose `SCHEMA.md` mirror has a per-change freshness gate — no section assigns the regeneration to PR01, the DoD attributes it to §4 alone, and §1's stated 46/46 executed check is false as a result"
  evidence: >-
    OBSERVED. Fresh clone of 113cc06: `scripts/run_tests.py` -> 46/46, and
    `render.schema_markdown(schema.json) == templates/SCHEMA.md` -> True. Then I applied §1's
    instruction alone (:284-286 "this section adds `plan_frozen_at.path` … to
    `templates/schema.json`") in the only form `schema.json` provides for a sub-field shape —
    `field_shapes['plan_frozen_at'] = ['commit', 'path']` — and changed nothing else. Result:
    **45/46**, `test_schema.py` FAIL
    `test_schema_md_is_in_sync_with_schema_json: 'templates/SCHEMA.md is stale; regenerate with
    `python scripts/render.py --schema-md > templates/SCHEMA.md`'`. Regenerating `SCHEMA.md` in
    the same edit restores **46/46**. Source: `schema_markdown` iterates
    `sorted(schema['field_shapes'])` at render.py:516-517 and emits one bullet per shape, so any
    new shape key changes the generated text; `test_schema_md_is_in_sync_with_schema_json`
    compares the generated text to the committed file. Executed the orthogonality too: a
    `known_versions` bump alone does NOT change `SCHEMA.md`, so this is a different mirror from
    R3-4's `_EMBEDDED_SCHEMA`, not a restatement of it.
  detail: >-
    Fold damage of exactly R3-4's class, introduced by the R3-1 fold that moved the schema edit
    from PR04 into PR01. §1 does gesture at it — ":286-287 §4 later layers `contrasts[]` onto
    the same schema pair, so the order is PR01 then PR04 and `SCHEMA.md`'s sync gate re-runs in
    both" — but a gate re-running is not a regeneration, `SCHEMA.md` appears in neither §1's
    acceptance criterion nor its prose file list, and the DoD's generated-artifact enumeration
    assigns it away: ":642-643 `templates/SCHEMA.md` regenerated from `schema.json` (its sync
    gate, **§4**)". That enumeration is the spec's own claim to have swept the mirror class, and
    it is now wrong for the same reason R3-4 found it wrong one artifact earlier. The concrete
    consequence is that §1's headline executed check is numerically false for PR01's actual
    scope: ":314-316 with the field, the reader and the fixture adjustment in place but nothing
    relocated, `scripts/run_tests.py` is **46/46**" — with the field in `schema.json` and no
    regeneration it is 45/46. Loud, self-describing, and one command to fix, which is why this
    is MINOR; but §1 states that number precisely because round 3 established that a stated
    executed check has to be true. A second, smaller wrinkle rides along: 46 is a count of
    discovered test MODULES, not test items (`run_tests.py` prints
    `f'{len(tests) - len(failed)}/{len(tests)}'` over `rglob('test_*.py')`, and 46 modules is
    the current population, enumerated), so PR01's own new tests — the pre-move-blob
    byte-identity test and the two hook-regex guard tests §1 requires — move the denominator if
    any of them lands in a new module.
  smallest_fix: "§1 adds `templates/SCHEMA.md` to what PR01 regenerates ('the schema pair moves together: adding the field to `schema.json` reddens the sync gate until `render.py --schema-md > templates/SCHEMA.md` is re-run in the same diff'), the DoD's mirror row is re-attributed to '§1 and §4', and §1's two suite counts are stated as 'zero failures' rather than a literal 46 so PR01's own new test modules cannot invalidate the criterion."
  blast_radius: "`templates/SCHEMA.md` is the human field guide shipped inside the skill and read by `validate_plugins.py`'s reference resolution; it is regenerated again in PR04 for the `contrast` / `cluster` shapes (executed: adding a `contrast` field shape also changes the generated text), so the pair moves twice and the sync gate is the freshness check both times."
  consumed_input: "`render.schema_markdown` at render.py:452-520 consumes `schema['field_shapes']` (:516-517, sorted, one bullet per key) and `schema['tiers'] / required_fields / optional_fields / prereg_fields / comprehension_questions / prior`; `test_schema.py::test_schema_md_is_in_sync_with_schema_json` consumes both the generated text and `templates/SCHEMA.md`. Both read at source and the collision executed in a scratch clone, then repaired to green."
  disconfirming_test: "In a scratch clone add `field_shapes['plan_frozen_at'] = ['commit','path']` to `templates/schema.json` and run `scripts/run_tests.py`. If it stays 46/46, the schema pair does not move together and this mode is dead."
  target_section: "section 1 (and the Definition of Done's mirror list)"
```

## Conditions

```yaml
conditions:
  - id: C1
    fix: "§5 pins the arm rules composition (each arm's file carries the evaluation-act row alone; control carries none) and demotes `custom_candidate_displacement` to residual, naming that the offline table has no competing rows and that live nine-row displacement stands with live-hook delivery as an unmeasured production precondition."
    must_land_before: "PR05's freeze commit (it is a threat-block statement in the frozen record)"
  - id: C2
    fix: "§5's parity criterion is scoped to the router-derived arms (`narrow`, `wide`), with `inert` asserted against wide's row set plus its authored neutral text and `control` against an empty candidate list."
    must_land_before: "PR05"
  - id: C3
    fix: "Part B's baseline expectation states that the 0.33 aggregate was measured on a paraphrase-dominated holdout and that the single same-register positive hit 3/3, so the genuine-side prior is wide rather than low; §6's null leg adds that a null with control at ceiling is recorded as no headroom rather than no effect."
    must_land_before: "PR05's freeze commit (it is the record's own baseline expectation)"
  - id: C4
    fix: "§1 regenerates `templates/SCHEMA.md` in the same diff as the `schema.json` field addition, the DoD's mirror row is re-attributed to '§1 and §4', and §1's two suite counts read 'zero failures' rather than a literal 46."
    must_land_before: "PR01"
```

## Cleared

Claims I re-verified this round, at source or by execution, and found correct.

```yaml
cleared:
  - claim: "All 58 fold-ledger anchors resolve to the exact line and string they cite"
    cite: "mechanical re-check of every `<path>:<line>` `<quoted text>` pair in the ledger — 58/58 exact, zero drift, zero off-by-one (10 rows added since round 3, all clean)"
  - claim: "All 23 load-bearing code cites in the spec body resolve at the exact line and string"
    cite: "mechanical re-check over the body (everything above the fold ledger) — 23/23 exact, zero problems"
  - claim: "The suite is green on a fresh clone of 113cc06 today, so any post-fold red is attributable to this wave"
    cite: "`git clone --no-hardlinks` of the worktree, `uv run --no-project --with pyyaml -- python scripts/run_tests.py` -> 46/46 passed; 46 is the module population, enumerated independently by re-running the runner's own `rglob('test_*.py')` over ('plugins','evals')"
  - claim: "`check_prereg` genuinely never compares `plan_frozen_at`, so §1's legality argument for writing `path` under the freeze holds"
    cite: "validate.py:888-931 — `plan_frozen_at` read only at :892 for `commit`; the drift subset is `design.cells` as a subtree, `analysis_plan` minus amendments, and the frozen outcomes. Independently re-read this round rather than carried from r3"
  - claim: "`field_shapes` is documentation, not enforcement — validate.py never reads it, so adding `plan_frozen_at` there cannot make a v1.0 record fail"
    cite: "`grep -n field_shapes validate.py` returns zero hits; the only consumer is `render.schema_markdown` at render.py:516-517. Confirmed by execution: the field-shape addition produced exactly one failure (the SCHEMA.md sync gate), no ER-SCHEMA regression on any delivered record"
  - claim: "The router surface the generator drives read-only is exactly as Settled decisions now describes it"
    cite: "router.py:34 `load_rules(path: str | Path = RULES_PATH)`; :42-59 `route` (Cf strip + `MAX_PROMPT_CHARS` 4000 truncation + `.lower()` at :46, negative_patterns, min_hits, hits-descending stable sort, `max_candidates` slice); :62-76 `hint_line` (`list(dict.fromkeys(m['matched']))[:3]` at :68, `_ascii`, the `'; '` join at :72, fixed prefix and suffix). Every clause in the spec's fidelity list is present"
  - claim: "The hook's pre-filter constants and both skips are exactly as cited"
    cite: "inject_dispatch.py:52 `MIN_WORDS = 4`, :53 `MIN_CHARS = 15`, the `SYNTHETIC_PREFIXES` skip at :107, the slash-command skip and the floor return in `_prompt_submit`. The spec's 'every bank prompt above the hook's floor' criterion makes the floor a no-op for the actual bank, so the reimplemented three lines carry no residual risk"
  - claim: "The 0.33 / 3-of-3 numbers themselves are exact (the transport is the issue, not the arithmetic)"
    cite: "BASELINES.md:18 — recall 0.33 [0.15, 0.58], specificity 1.00 [0.76, 1.00], 5+/4- x 3 repeats, 1/27 error, $2.67; per-positive 3/3 + 0/3 + 2/3 + 0/3 + 0/3 = 5/15 = 0.33, arithmetic checked"
  - claim: "ER-XCHECK at measurement tier with `source: hand` is a WARN even with `hand_reason` declared, so §5's 'declared posture' framing is mechanically right"
    cite: "validate.py:810-820 — the measurement branch returns `_warn('ER-XCHECK', …)` unconditionally; `hand_reason` only removes the '(declare run.hand_reason)' suffix"
  - claim: "`ER-STATS` recomputes each stated per-arm CI through `stats.confidence_interval` at `stats.ATOL`/`stats.RTOL` and skips an outcome with fewer than two arms, so §4's 'at the existing tolerances' and §5's contrasts-only secondary are both mechanically supported"
    cite: "validate.py:546-566 (recompute + `math.isclose` at ATOL/RTOL); :573-575 `if not (isinstance(arms, dict) and len(arms) >= 2): continue`"
  - claim: "`stats.py` still has no interval for a difference of means and still refuses the normal family, so `paired_interval` remains a needed addition — and a stdlib t quantile is buildable inside the module"
    cite: "stats.py:62 `PairedDiff`; :226 `_REFUSED_NORMAL`; :229-260 `confidence_interval` offering only wilson / clopper_pearson / beta_binomial; and `_beta_cdf` (:111) plus `_bisect` (:123) already in the module, which is what a Student-t quantile needs"
  - claim: "The ASCII ratchet's baseline contains no experiment-rigor or evals/experiments path, so the moved files and every new file are held at zero and the DoD's 'ascii_lint_baseline.json (unchanged)' is correct"
    cite: "`scripts/ascii_lint_baseline.json` enumerated — 16 keys, none under `plugins/humblepowers/skills/experiment-rigor` or `evals/experiments`"
  - claim: "Both pre-commit record hooks still name the old location in `entry:` AND `files:`, and the `evals/.*` alternative §1 must preserve is really there in both"
    cite: ".pre-commit-config.yaml:58 and :65 (validator, two-alternative regex verbatim), :71 and :77 (render-check, four-alternative regex covering record.yaml AND report.md)"
  - claim: "The CI cites are exact and `fetch-depth: 0` is still genuinely needed"
    cite: ".github/workflows/validate.yml:13 `uses: actions/checkout@v7` with no fetch-depth; :20 `ruff check .`; :22 `ruff format --check .`; :30 `python scripts/run_tests.py`. CI does not run word_budget.py or ascii_runtime_lint.py directly, which matches the enforcement table's 'in pre-commit' scoping"
  - claim: "The word-budget key and value are as cited and the FREEZE.md population is still exactly the four sites §1 sweeps, one of them a writer"
    cite: "`scripts/word_budget.json` keys `plugins/humblepowers/skills/experiment-rigor/SKILL.md` at 827; `git grep -n FREEZE.md` -> CHANGELOG.md:25, finalize.py:7, finalize.py:189 (the writer), record.yaml:3, and the file is absent from `examples/rg-2x2/`"
  - claim: "The sign test really is hand-derivable from recorded fields, so the author's flagged divergence from R3-5 is defensible rather than a section-presence tick"
    cite: "§4's `clusters` block is per prompt id, per arm numerator and denominator (:397-399), which determines every per-cluster delta, hence each delta's sign, the tie count, and the surviving effective n — and the effective n is separately recorded beside the p-value (:414-416). The enforcement row at :132 is honestly scoped to 'estimate, SE, and interval'"
  - claim: "ADR-0008 stays in sync with the third fold"
    cite: "ADR:91-96 (generated half gated / tier-0 review-only) matches the enforcement table; ADR:116-124 (firing/effect split computed 'offline from the real router semantics', live-hook delivery as a named precondition) matches Settled decisions :197-215 and Context :28-32. The third fold changed nothing the ADR asserts"
  - claim: "No stale arithmetic survives the third fold"
    cite: "192 = 4 arms x 24 prompts x 2 repeats = 8 cells x 24; 48 per arm; 24 clusters, 12 within a class; $75 ceiling with a $25-60 band; +/-0.15 pooled and +/-0.20 within a class — internally consistent at :216-225, :460-470, :499-507, :660-667"
```

## Prose

**What the third fold got right.** R3-1's repair is the one I would have asked for and it is
implemented from the executed evidence rather than the wording: PR01 owns the field, the
reader, and the fixture; the fallback fires on lookup FAILURE, not on an absent field; and
the trade that costs — a wrong pin resolving silently through the current path — is stated in
the spec rather than left for an implementer to discover. R3-3's repair is better than a
repair: putting the generator on the real router converts seven enumerated semantics plus the
three the enumeration had missed into behavior nothing can under-copy, and the parity test
turns "router-realistic" from a claim into a check. And R3-2 is the finding that mattered
most, folded in the field where it has to live — Part B's baseline expectation now says what
the control arm actually is, the genuine-side rule is two-sided, and §5's frozen run config
names the one allowlist entry that decides which experiment this is. The citation hygiene held
through a third fold: 58 ledger anchors and 23 body cites, all exact, which after three rounds
of restructuring is not luck.

**Where the third fold leaves damage, and why it is small.** All four residues are in text the
fold itself wrote, and three of them share a shape: a repair authored about one artifact was
applied to a sentence that quantifies over four. R3-3's `smallest_fix` said "every frozen row"
because it was reasoning about the generator; folded verbatim into a criterion, it now asserts
something about an arm whose text is authored by design (R4-2). R3-2's `smallest_fix` supplied
the 0.33 as shorthand; the fold added an attribution clause on top, and the clause is false of
the number it is attached to (R4-3). R3-1's fold moved the schema edit into PR01 and nobody
re-derived the DoD's mirror sweep, which is R3-4's own finding recurring one artifact later
(R4-4) — I executed that one rather than reasoning it, 45/46 and then 46/46 with the
regeneration. The fourth (R4-1) is not a fold artifact at all: the arm rule files' composition
has been unstated since round 1, FM-23 answered the displacement question with a table column,
and nobody checked whether that column can vary. It cannot, under the only reading consistent
with "control (nothing injected)".

**Why none of this is MAJOR.** The bar rose three times and this round I held it. R4-4 is a
loud red gate with the fix printed in its own assertion message. R4-2's bad branch is
reachable but the good one is obvious, and the pre-spend audit of the frozen firing table is a
real safety net for R4-1's bad branch too — a control arm that fires is visible in the table
on the first read, before a cent moves. R4-3 is the one I thought hardest about promoting: a
control arm at ceiling would make `wide − control` null-by-construction, which is the
floor/ceiling failure the method tells me to hunt. I did not promote it because the founding
case is the counter-evidence sitting in this same repo — RG-2×2 measured a declaration at
47/48 against a behavior at 0/48 — and the oracle requires both, which is exactly why the
composite is not plausibly ceilinged even if activation is. What is wrong is the sentence, not
the design, and the cheapest disconfirming observation is the ~$0.30 probe round 3 already
priced.

**What I did not attack, and why.** The residual trust this spec names is stated design
posture and I have treated it as such: the floor asymmetry on the decoy half, `narrow −
control`'s re-inherited length confound, the oracle-as-proxy limit, the t reference on few
clusters declared an approximation, the compressed-contrast spend risk, the ungated sign test
(which I checked is genuinely hand-derivable rather than accepting the claim), and the
live-hook delivery precondition. I did not reopen the pooled primary contrast, the
humblepowers 0.8.0 rollback, the cost band, or the ±5% token match. One thing I noticed and
deliberately left as an advisory rather than a finding: the pre-registered PT-BR fallback
("restrict the primary analysis to EN") halves the cluster count to 12 and to 6 within a
class, and Part B's precision paragraph quotes only the 24-cluster figures — the record's
"achieved precision on the clustered scale" covers it, so it is a nicety, not a defect.

**For the fold.** C4 is observed and its repair is determined — apply it from the executed
evidence. C1 and C3 are pre-registration statements and must be settled before §5's freeze
commit, not during §6; C2 before PR05 authors the parity test. None of the four changes an
arm, an outcome, a contrast, the analysis plan, the spend, or a PR boundary, which is why this
is a certification with conditions rather than a fourth revision cycle. The wave is sound.

Unverified-offline: 4

PREMORTEM-VERDICT: CONDITIONAL-CERTIFY — fresh non-author subagent (opus), round 4, keel kit 0.13.0
