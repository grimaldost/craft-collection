# Pre-mortem (round 3) — the experiment-discipline wave

- **Spec:** `docs/specs/2026-07-25-experiment-discipline-wave.md`
- **Date:** 2026-07-25
- **Reviewer:** fresh non-author subagent (opus), round 3
- **Spec-hash:** `dbae4e61262fa1f75531de35bba2fc725086fbdb32a4f225fa701c9d1de76dc2`
- **Reviewed against:** worktree `C:/Users/grima/Documents/craft-collection-rigor`, branch
  `feat/experiment-rigor-skill` @ `113cc06` (clean apart from the untracked wave documents);
  `docs/adr/0008-experiment-discipline-plugin.md` read; both prior pre-mortems read as the
  verdict record; keel kit 0.13.0
- **Prior rounds:** `…premortem.md` (round 1, NEEDS-REVISION, 5 BLOCKER / 15 MAJOR / 5 MINOR);
  `…premortem-r2.md` (round 2, NEEDS-REVISION, 1 BLOCKER / 2 MAJOR / 6 MINOR)

The second fold landed. All 48 fold-ledger rows resolve to the exact line and string
they cite (mechanically re-checked, 48/48, zero drift), and every round-2 finding has
current text behind it. But the two folds this round exists to attack both leave damage,
and one of them is refuted by execution: I implemented §4's `plan_frozen_at.path`
semantics exactly as the spec words them, in a scratch clone, and §1's headline
executed-check acceptance criterion — "the suite is 46/46 green" — is false. It is
45/46, with three named failures inside `test_acceptance_rg2x2.py`, a file no section
lists.

The failure I judge most likely now is not mechanical at all. It is that the control
arm is not a no-treatment baseline. Every arm loads `plugins/experiment-discipline`
(Settled decisions :211, "so the skill is loadable"; Part B :615 holds the tool
allowlist and the plugin dir equal across arms), and by run time §2 and §3 have put the
tier-0 rung and the activation-line emission rule *into that skill's body*. So the
control spawn carries, in its own loaded plugin, a skill whose body instructs exactly
the behavior the oracle scores. Part B's pre-registered baseline expectation — "the
activation line is **new behavior introduced by this wave**, so control is expected at
or near **zero** on the genuine half" (:653-655) — states a reason the design's own arm
configuration refutes, and the pre-registered one-sided decision rule on the genuine
half rides on that reason.

---

## Resolution audit (round-2 findings against the current text)

| Finding | Status | Current-text evidence |
|---|---|---|
| R2-1 `git mv` breaks the RG-2×2 freeze reconstruction (BLOCKER) | **PARTIALLY-RESOLVED** | The pin exists and is right in principle: §1 :266-278 sets `plan_frozen_at.path` to the pre-move path and argues its legality; §4 :390-393 adds the field with a v1.0 fallback; enforcement :133. `check_prereg` genuinely does not compare `plan_frozen_at` (validate.py:920-931 diffs `design.cells`, `analysis_plan` minus amendments, and the frozen outcomes only) — re-verified, the legality argument holds. What is unresolved is the *implementation surface*: see R3-1, observed |
| R2-2 inverted depth-1 criterion | RESOLVED | §1 :296-302 "`run_tests.py` is green on a **full-depth** checkout… A depth-1 clone is *expected to fail*… **no skip may be added to make it pass**"; DoD :568-572 carries the same sense; enforcement :127 "a depth-1 clone fails loud, never skips". No surviving inverted clause anywhere in the file |
| R2-3 subset-scoped secondary collides with ER-RECON | RESOLVED | §5 :459-463 "carrying no `arms` block"; §4 :374-376 qualifies per-arm Wilson to "outcomes scored over the **full** cell set"; §6 :510-512 "for the full-cell confirmatory outcome only". Re-executed `check_recon` on the folded shape (8 cells × 24, `rigor_disposition` at 4 arms × 48, `skeleton_wellformedness` contrasts-only): clean. The pre-spend gate at :500-506 is named as its own gate and is the right mechanism |
| R2-4 freeze-stage disposition shape | RESOLVED | §5 :467-471 "`total: 192` alone", with the Reuse-template mismatch named. Re-executed: `{total: 192}` clean; `{total: 192, completed: 0, excluded: 0}` fails ER-RECON |
| R2-5 `contrasts[].interval` had no recomputation source | RESOLVED, one MINOR residue | §4 :379-385 adds `stats.paired_interval` (t on per-cluster deltas, df = clusters − 1) and wires `ER-STATS` through it; Part B :645-648 pre-registers it as the primary interval. Re-verified stats.py's surface: `PairedDiff` (:62-65) carries no interval and `confidence_interval` (:226-260) refuses the normal family, so the addition is genuinely needed. Residue: the sign test rides along unrecomputed and untied — R3-4 |
| R2-6 clusters adapter + fully-excluded prompt | RESOLVED | §4 :386-389 names the lossless expansion for `clustered_se` (signature re-verified at stats.py:270); §5 :481-486 adds the drop-out rule with `paired_difference`'s raise-on-zero-size as its stated reason (re-verified at stats.py:322) |
| R2-7 shared-renderer staleness | RESOLVED | §6 :536-541 assigns the RG-2×2 re-render to the same PR; DoD :587-589 lists both report pairs. `check_drift` re-verified as a digest over the parsed embedded YAML (render.py:193-210), and `render_report` handles an outcome with no `arms` block without raising (render.py:143) |
| R2-8 missing ruff gates | RESOLVED | Gate commands :50-55, cite `.github/workflows/validate.yml:20` verified exact (`:19-22` runs `ruff check .` then `ruff format --check .`) |
| R2-9 injected text shape unspecified | RESOLVED, and it opens two new seams | §5 :422-431 makes the text per-prompt, frozen verbatim, with the ±5% match a per-row property. `hint_line`'s per-prompt echo re-verified at router.py:62-76 (the echo composed at :68). The two seams the new per-prompt reproduction opens are R3-2 (nothing ties the reproduction to the real router) and R3-5 (the primeability constraint now binds prompt-derived text) |

No round-2 finding is UNRESOLVED. R2-1 is PARTIALLY-RESOLVED and is carried below as
R3-1 rather than re-litigated.

---

## Findings

```yaml
- id: R3-1
  severity: MAJOR
  title: "§1's `plan_frozen_at.path` pin, implemented as §4 words it, turns test_acceptance_rg2x2.py red — the '46/46 green' executed-check acceptance is false, and the mechanism's PR ownership contradicts itself"
  evidence: >-
    OBSERVED, not reasoned. Fresh clone of 113cc06: `scripts/run_tests.py` -> 46/46.
    Then, with NO move, I implemented §4's stated semantics literally (spec:390-393:
    "the reconstruction resolves `git show <commit>:<plan_frozen_at.path>`, falling back
    to the record's current repo-relative path when the field is ABSENT") — one line in
    `check_prereg` (validate.py:911), `plan_frozen_at.path` set on the delivered RG-2x2
    record to its pre-move humblepowers path, and `report.md` regenerated. Result:
    45/46, `test_acceptance_rg2x2.py` reporting three failures —
    `test_corrected_record_validates_and_has_no_drift` (warn codes became
    {'ER-XCHECK','ER-PREREG'}, breaking the :188 assertion),
    `test_decision_complete_record_exits_zero` (FAIL ER-PREREG "record not in history at
    <sha>:plugins/humblepowers/skills/experiment-rigor/examples/rg-2x2/record.yaml"),
    and `test_six_defect_fixture_exits_one_naming_all_six` (codes collapsed to
    {'ER-RECON','ER-STATS','ER-SCHEMA'} — the expected ER-PREREG FAIL disappears because
    check_prereg returns early on the broken reconstruction). Cause: the module's temp-repo
    helper writes the record at the repo ROOT (test_acceptance_rg2x2.py:83 `path = d /
    'record.yaml'`) while the validated record is `finalize.finalize_record(_load_frozen(),
    sha)` — built from the DELIVERED record, so it carries the pin. I also tested the
    obvious fixture repair (popping `path` inside `_freeze_commit`): still 3 failures,
    because the pin travels on the finalized record, not the frozen copy.
  detail: >-
    Two halves, one defect class. (a) The semantics are under-specified in the one
    direction that matters: falling back only when the field is ABSENT breaks every
    fixture that relocates a pinned record. I verified the repair by execution — resolve
    the pin, and fall back to the current relpath when the PINNED LOOKUP FAILS (not only
    when the field is absent), plus a one-line change to the reconstruction at
    test_acceptance_rg2x2.py:152 so it reads the pin too. That gives 46/46 pre-move; after
    `git mv plugins/humblepowers/skills/experiment-rigor
    plugins/experiment-discipline/skills/experiment-rigor` it gives 45/46 with the SOLE
    failure being `evals/harness/test_gen_agents_md.py` ("committed AGENTS.md is stale"),
    the regeneration §1 already assigns — and `validate.py` on the moved chain-root record
    reports exactly one WARN (ER-XCHECK). So §1's claim becomes true, but only under a
    semantics the spec does not state and a file edit no section lists.
    (b) Ownership is self-contradictory. The enforcement table (:133) assigns the mechanism
    to "§4 `plan_frozen_at.path` + the reconstruction reading it"; §1 (:270-273) says "§4
    adds… and teaches the reconstruction to use it; this section sets it"; the manifest
    (:557-561) lands PR01 first; and §1's acceptance demands 46/46 WITH the pin set. A
    PR01 that writes the value without the reader reproduces round 2's failure exactly —
    the pin is inert, ER-PREREG degrades to the measurement-tier WARN, which round 2
    measured at 44/46. The one sentence pulling the other way ("Because PR01 therefore
    edits the same schema pair §4 extends") names schema.json and SCHEMA.md, not
    validate.py or the acceptance test.
  smallest_fix: "§4 states the fallback fires when the pinned lookup FAILS, not only when the field is absent; §1 states that PR01 lands the reader itself — `templates/schema.json`, `check_prereg` in `scripts/validate.py`, and the reconstruction in `scripts/test_acceptance_rg2x2.py` — with §4 layering `contrasts[]` on the same pair, and adds `test_acceptance_rg2x2.py` to §1's file list and the concept->module map."
  blast_radius: "The fallback-on-failure semantics also govern every future renamed record, and it is a small dilution of the pin's loudness (a wrong pin silently resolves via the current path) — state that trade explicitly rather than leaving it to the implementer."
  consumed_input: "validate.py:911 `relpath = _repo_relpath(cwd, record_path)` feeding :916 `_show_at(cwd, commit, relpath)`; test_acceptance_rg2x2.py:150-157 consuming `validate._repo_toplevel` / `_repo_relpath` / `_show_at` over DELIVERED_RECORD; test_acceptance_rg2x2.py:80-84 writing the temp-repo record at the repo root. All three read by hand and all three exercised by execution."
  disconfirming_test: "In a scratch clone, set `plan_frozen_at.path` on the delivered RG-2x2 record, teach `check_prereg` to prefer it with an absent-field-only fallback, regenerate report.md, and run `scripts/run_tests.py` with no move at all. If the suite stays 46/46, this mode is dead."
  target_section: "section 1 (and section 4)"

- id: R3-2
  severity: MAJOR
  title: "The control arm is not a no-treatment baseline: every arm loads the plugin whose skill body (post-§2/§3) mandates the behavior the oracle scores, so Part B's near-zero prior states a reason the design refutes — and the genuine-side rule is pre-registered one-sided on it"
  evidence: >-
    Spec:653-661 ("the activation line is **new behavior introduced by this wave**, so
    control is expected at or near **zero** on the genuine half — that side is an
    increase-only question and the decision rule is one-sided there") against
    Settled decisions :210-212 ("one `--plugin-dir` (`plugins/experiment-discipline`, so
    the skill is loadable)") and Part B :614-617 ("Held equal across arms: … tool
    allowlist, cwd fixture …"). §2 (:304-321) puts the tier-0 `check` rung and its
    five-element shape in `SKILL.md`; §3 (:332-341) puts the activation-line emission rule
    in `SKILL.md` and all three templates. PR02/PR03 land before PR05/PR06 (:557-561), so
    by run time the skill body every arm loads instructs the exact line-plus-skeleton the
    oracle scores. The repo has a measured number for that surface:
    `evals/trigger/holdout/BASELINES.md:18` — experiment-rigor sealed-holdout recall
    0.33 [0.15, 0.58], with the lexically-adjacent positive at 3/3 and one paraphrase
    positive at 2/3; and the description's own closing trigger clause is
    `plugins/humblepowers/skills/experiment-rigor/SKILL.md:3` "or ask whether a skill,
    tier, model, or strategy actually helps and how you would show it rigorously" — the
    same direct evaluation-act register §5 authors the genuine bank half in (:415-419).
    Both existing eval arms carry `Skill` in the allowlist
    (`evals/config.json` `allowed_tools_trigger` / `allowed_tools_task`), so the skill is
    invocable in every arm unless §5's unstated allowlist removes it.
  detail: >-
    This is not the floor question round 2 declined to reopen; it is the opposite
    direction. `wide - control` measures the hint's MARGINAL effect over a loaded,
    unhinted skill, not "convention vs. nothing". Three consequences the spec does not
    carry. (1) The pre-registered prior is wrong for a stated reason the arm
    configuration refutes; a record whose baseline expectation is argued from a false
    premise is the exact defect this discipline exists to catch, in the first study it
    governs. (2) The one-sidedness follows from the false premise: if the hint DISPLACES
    the model's own dispatch — `max_candidates: 2` with a hits-descending sort
    (router.py:58-59), the `custom_candidate_displacement` threat the spec already names
    (:476) — a treated arm can land BELOW control on the genuine half, and a one-sided
    rule cannot report that as confirmatory. (3) Power: a non-zero control compresses the
    contrast against an honestly-declared MEWD that is already "a large effect"
    (+/-0.15 pooled, :607-610), which is a spend decision, not a wording one. Note this is
    NOT an argument for dropping the plugin dir from control — holding it equal is right.
    It is an argument that the recorded prior must say what control actually is.
  smallest_fix: "Part B's baseline expectation restates the real reason and the real prior — 'every arm loads `plugins/experiment-discipline`, so control measures the skill's own trigger surface with no hint; the sealed holdout puts that at 0.33 [0.15, 0.58] (BASELINES.md:18), so control is expected low but not structurally zero, and `wide - control` is the hint's marginal effect over a loaded skill' — the genuine-side decision rule becomes two-sided (displacement can move a treated arm below control), and §5's frozen run config names whether `Skill` is in the tool allowlist."
  consumed_input: "The measured spawn consumes the skill body via `--plugin-dir` (claude_runner.py:238-239, single flag, verified) plus the `Skill` tool from `--allowed-tools` (claude_runner.py:226-227); `evals/config.json` supplies the in-repo allowlist precedent. Read by hand at each call site."
  disconfirming_test: "Two control-arm spawns (no injection, `--plugin-dir plugins/experiment-discipline`, the allowlist §5 will freeze) on two genuine bank prompts, grepping the response for the format-(a) line and the five elements. If both come back empty, control is near zero as stated and only the stated REASON needs repair; ~$0.30."
  target_section: "Experiment design (Part B) (and section 5's frozen run config)"

- id: R3-3
  severity: MAJOR
  title: "Nothing ties the firing table to the real router: the spec licenses a hand reimplementation and the semantics list it hands the implementer is incomplete, so 'router-realistic firing patterns' is asserted, not gated"
  evidence: >-
    Spec:196-201 asks for "an offline generator that reproduces the real router semantics
    — `patterns`, `negative_patterns`, `min_hits`, `max_candidates` ordering, and the
    hook's own pre-filter (`inject_dispatch.py:52` `MIN_WORDS = 4`, its companion
    character floor, and the slash-command skip)" and :422-424 adds "reproduces the real
    router's composition — including its echo of the matched words into the hint
    sentence". Read against the source, that enumeration omits: router.py:46 (the `Cf`
    format-category strip, the `MAX_PROMPT_CHARS` 4000-char truncation, and `.lower()`),
    router.py:68 (`list(dict.fromkeys(m['matched']))[:3]` — order-preserving dedup AND a
    three-word cap), router.py:68 `_ascii(w)` (the '?'-substitution that makes a PT-BR
    echo differ from an EN one — named as a THREAT at :477-480 but not as a generator
    requirement), router.py:72 (the '; ' join across up to `max_candidates` rows), and
    inject_dispatch.py:107 (the `SYNTHETIC_PREFIXES` skip). §5's acceptance criterion
    (:493-499) checks the table's SHAPE and the wide/inert row-set identity; no criterion
    compares a single row to the real router's output. Meanwhile `router.load_rules(path)`
    accepts a path (router.py:34) and `route` / `hint_line` are plain functions, so the
    generator can drive the real router read-only — which the "no edit to router.py"
    non-goal (:83) permits, since importing is not editing.
  detail: >-
    Two implementers diverge and both pass every stated gate: one calls
    `router.load_rules(<arm rules>)` / `router.route` / `router.hint_line` and is faithful
    by construction; the other reimplements from the checklist, silently drops the
    three-word cap or the lowercase normalization, and freezes a table whose injected
    texts are not what the live router would emit. The frozen SHAs then make that table
    tamper-evident but not correct — integrity, not fidelity. The construct statement the
    whole wave is bounded by (":28-30", "the effect of an injected hint delivered at
    router-realistic firing patterns") rests entirely on that fidelity, and the stated
    control for it is human audit ("auditable before a cent is spent", :205-206;
    ADR-0008:119-121) — prose where a free mechanism is available, in the collection whose
    thesis is the reverse.
  smallest_fix: "§5 states that `firing_table.py` imports and calls `router.load_rules(<arm rules file>)`, `router.route` and `router.hint_line` read-only (plus `inject_dispatch`'s floor constants and its slash / synthetic-prefix skips) rather than reimplementing them, and its acceptance criterion adds 'a test asserts every frozen row's candidate list and injected text equal the real router's output for that prompt and that arm's rules'."
  consumed_input: "`router.load_rules(path=RULES_PATH)` at router.py:34 (a path parameter nothing currently passes), `route` at :42-59, `hint_line` at :62-77, `inject_dispatch._prompt_submit`'s filters at :107-114 — all read at source, and the shipped `router_rules.json` row for experiment-rigor enumerated (7 patterns, 2 negative_patterns, min_hits 1, max_candidates 2)."
  disconfirming_test: "Read `router.load_rules`'s signature — if it accepts a path, the arm rule files can be fed through the real router directly and the reimplementation is optional, so the divergence risk is free to close."
  target_section: "section 5 (and Settled decisions)"

- id: R3-4
  severity: MINOR
  title: "`known_versions` is mirrored in `validate._EMBEDDED_SCHEMA`; §4's bump reddens the schema sync gate, and the DoD says 'No other generated artifacts'"
  evidence: >-
    OBSERVED. In the scratch clone I changed `templates/schema.json` `"known_versions":
    [1]` to `[1, 1.1]` and nothing else, exactly as §4 instructs (:394-396 "Update
    `schema.json` (the new field shapes plus `known_versions`)" and :407-409
    "`known_versions` carrying both"). `test_schema.py` -> 2 failures:
    `test_schema_json_agrees_with_embedded_schema` ("schema.json['known_versions']
    [1, 1.1] != embedded [1]") and `test_schema_json_loads_without_weakening_the_gate`.
    Source: validate.py:84-85 `_EMBEDDED_SCHEMA = {'known_versions': [1], …}`;
    test_schema.py:44-49 asserts `data[key] == value` for EVERY embedded key.
    `known_versions` is the one key §4 touches that is mirrored — `field_shapes`,
    `optional_fields` and `prereg_fields` are absent from the embedded copy, so the new
    contrast / cluster / `plan_frozen_at.path` shapes are safe.
  detail: >-
    The DoD's mirror enumeration (:582-589) lists AGENTS.md, word_budget.json,
    ascii_lint_baseline.json, SCHEMA.md and the two report pairs, then closes "No other
    generated artifacts." `validate._EMBEDDED_SCHEMA` is a mirror of schema.json with a
    per-change freshness gate, and it is not on the list. Loud and one line to fix, but
    the DoD sentence is the spec's own claim to have swept the class.
  smallest_fix: "§4 adds 'and `validate._EMBEDDED_SCHEMA['known_versions']` in the same diff (test_schema.py:44-49 is the sync gate)'; the DoD's mirror list gains that row and the 'No other generated artifacts' close is re-derived."
  blast_radius: "`_EMBEDDED_SCHEMA` is validate.py's fallback when templates/schema.json is absent, and `_assert_schema_complete` reads `known_versions` as a load-bearing list key (validate.py:139-152) — the two copies must move together or the fallback path validates against a different version set."
  consumed_input: "test_schema.py:43-49 consumes `validate._EMBEDDED_SCHEMA.items()` and `json.loads(templates/schema.json)`; `validate.load_schema` merges schema.json over the embedded defaults at :186-192. Both read, and the collision executed."
  disconfirming_test: "Edit `known_versions` in schema.json alone and run `python plugins/.../scripts/test_schema.py`."
  target_section: "section 4 (and Definition of Done)"

- id: R3-5
  severity: MINOR
  title: "The pre-registered exact sign test names no tie rule and no recomputation, and under the spec's own baseline expectation ties are the modal per-cluster outcome"
  evidence: >-
    Spec:384-386 ("every contrast additionally carries an **exact sign-test p-value** as
    the distribution-free robustness bound beside the interval"), :404-405 ("a sign-test
    p-value is emitted beside every contrast" — emitted, where the estimate, SE and
    interval are each "recomputed… fails on mismatch"), and Part B :645-648. With 2
    repeats per prompt per arm, a per-cluster rate is in {0, 0.5, 1} and a per-cluster
    delta is in {-1, -0.5, 0, 0.5, 1}; Part B :653-658 expects control near zero on the
    genuine half and near perfect on the decoy half, so a zero delta is the modal cluster.
    stats.py carries no sign test; the exact binomial tails it would use are already there
    (`_upper_tail` :101, `_lower_tail` :106).
  detail: >-
    Two gaps in one clause. The tie rule (drop ties and report the surviving n, versus
    split them) changes the p-value, and choosing it after seeing the deltas is exactly
    the latitude Part B says naming both statistics before the run exists to remove. And
    the sign test is the only number in the new contrast block that no gate recomputes,
    inside the mechanism this wave adds — R2-5's complaint one level down. Both are one
    clause each, and both must be settled BEFORE the freeze, not after.
  smallest_fix: "§4 adds 'ties (a zero per-cluster delta) are dropped and the surviving n is recorded beside the p-value, and `ER-STATS` recomputes the sign-test p-value from the cluster block like the estimate, SE and interval'."
  disconfirming_test: "Compute the sign-test p-value on a plausible delta vector (say 18 zeros, 5 positive, 1 negative) under drop-ties and under split-ties; if the two agree to the record's rounding, the rule is not load-bearing."
  target_section: "section 4 (and Part B's analysis plan)"

- id: R3-6
  severity: MINOR
  title: "The primeability constraint is asserted over text that is partly prompt-derived, so it binds the BANK as well as the arm rules — and the spec assigns it only to the rules"
  evidence: >-
    §5:451-454 "no arm's injected text may contain the activation-line format or any of
    the five element names, asserted by a test over the frozen texts". After R2-9 the
    injected text is composed per prompt by reproducing `hint_line`, whose echoed words
    are literal spans of the PROMPT: router.py:55 `matched.append(hit.group(0).strip())`,
    rendered at :68. The five element names are method / metric / result(s) with
    denominators / conclusion / "what this updates" (:308-309). A wide-arm pattern in the
    "bare test / evaluate" class whose span reaches a noun — `which (method|approach) is
    better` over a genuine bank prompt — echoes "method" straight into the treatment.
  detail: >-
    Free to discover (the table is frozen before spend) and free to repair (edit the bank
    or narrow the pattern), which is why this is MINOR rather than MAJOR. But the spec
    assigns the constraint to the arm rule files, and after the per-prompt fold the
    constraint is a joint property of the rules AND the bank — so the pre-registered
    response, like the PT-BR firing-rate fallback at :478-481, should name which artifact
    gets revised and that it happens before the freeze.
  smallest_fix: "§5 adds 'the constraint binds the bank as well as the rules — since the echoed words are prompt spans, a violating row is repaired by editing the bank prompt or narrowing the pattern, before the freeze'."
  disconfirming_test: "Draft the wide arm's patterns and run `router.route` over the draft bank; if no matched span contains a skeleton element name, the mode is dead for this bank."
  target_section: "section 5"
```

## Cleared

Claims I re-verified this round, at source, and found correct.

```yaml
cleared:
  - claim: "All 48 fold-ledger rows anchor to the exact line and string they cite"
    cite: "mechanical re-check of every `<path>:<line>` `<quoted text>` pair — 48/48 exact, zero drift, zero off-by-one (12 rows added since round 2, all clean)"
  - claim: "`check_prereg`'s diff subset genuinely excludes `plan_frozen_at`, so writing `path` cannot trip the drift check"
    cite: "validate.py:926-933 compares `design.cells` as a subtree and `analysis_plan` minus amendments; :943-951 the per-outcome scalars and `verifier.hash`; :961-969 the post-freeze quarantine; :974-986 the confirmatory-verdict legality. `plan_frozen_at` is read only at :892 for the commit and never compared. §1's legality argument (:273-277) is exactly right"
  - claim: "stats.py really has no interval for a difference of means and really refuses the normal family, so `paired_interval` is a needed addition, not a section-presence tick"
    cite: "stats.py:62-65 `PairedDiff(mean_diff, se, n_clusters)`; :226 `_REFUSED_NORMAL`; :229-260 `confidence_interval` offering only wilson / clopper_pearson / beta_binomial. df = n_clusters - 1 is available on the returned tuple, and `statistics.NormalDist` is already imported at :37, so a deterministic stdlib t quantile is buildable within the module's stated stdlib-only contract"
  - claim: "The clusters -> `clustered_se` adapter is genuinely needed and `paired_difference` genuinely takes the block verbatim"
    cite: "stats.py:270 `clustered_se(outcomes, cluster_ids)` — per-TRIAL 0/1; :303-308 `paired_difference(a_successes, a_sizes, b_successes, b_sizes)` — four per-cluster arrays; :322 the raise on a non-positive cluster size that §5's drop-out rule exists to avoid"
  - claim: "ER-RECON passes the folded 8-cell record in both stages"
    cite: "executed `check_recon`: 8 cells x 24 with `disposition: {total: 192}` and no results -> clean; the same with `{total: 192, completed: 0, excluded: 0}` -> FAIL (R2-4's fold is load-bearing); the final stage with `rigor_disposition` at 4 arms x 48 and a contrasts-only `skeleton_wellformedness` -> clean (validate.py:466-482 skips an outcome with no `arms`)"
  - claim: "`check_stats` and `render_report` both tolerate a contrasts-only outcome, so R2-3's shape does not break a second gate downstream"
    cite: "validate.py:573-575 (`if not (isinstance(arms, dict) and len(arms) >= 2): continue` — the `paired` declaration requirement is skipped, not failed); render.py:143 `(ores.get('arms') or {}).items()`"
  - claim: "The router composition the generator must reproduce is exactly as I describe it in R3-3, including the matched-word echo"
    cite: "router.py:42-59 `route` (the Cf strip / 4000-char truncation / lower at :46, negative_patterns, min_hits, hits-descending stable sort, max_candidates slice); :62-76 `hint_line` (per-match `dict.fromkeys` dedup at :68, [:3] cap, `_ascii`, the '; ' join at :72, fixed suffix); inject_dispatch.py:52-53, :107, :112, :114"
  - claim: "The harness cites are exact and the direct-delivery claim still holds"
    cite: "claude_runner.py:202 `plugin_dir: str | None`, :221 `--no-session-persistence`, :296 `input=prompt` — each read at the line"
  - claim: "The ASCII ratchet cannot reach the bank or the oracle's pattern data, so §5's 'patterns live in JSON' reasoning is mechanically correct"
    cite: "ascii_runtime_lint.py:47-61 `iter_target_files` — git-tracked `*.py` under ('plugins','scripts','evals') with `test_*.py` excluded; JSON is never scanned. New .py files are held at zero by the ratchet semantics documented at :13-18"
  - claim: "The SCHEMA.md regeneration path and its sync gate exist as §4 assumes"
    cite: "render.py:441-460 `schema_markdown` + `--schema-md` at :602/:619; test_schema.py:70-76 compares the generated text to templates/SCHEMA.md"
  - claim: "The CI cites are exact and `fetch-depth: 0` is still genuinely needed"
    cite: ".github/workflows/validate.yml:13 `uses: actions/checkout@v7` with no fetch-depth; :20 `run: ruff check .`; :22 `ruff format --check .`; :30 `run: python scripts/run_tests.py`"
  - claim: "Both pre-commit record hooks still name the old location in `entry:` AND `files:`, and the `evals/.*/record\\.yaml` alternative §1 must preserve is really there"
    cite: ".pre-commit-config.yaml:60 and :65 (validator), :69 and :77 (render-check); :65 carries the two-alternative regex verbatim"
  - claim: "§1's 'no path under plugins/humblepowers/ still matches experiment-rigor except the router row and the CHANGELOG pointer' is achievable — that IS the population"
    cite: "`git grep -n experiment-rigor -- plugins/humblepowers ':!plugins/humblepowers/skills/experiment-rigor'` returns exactly CHANGELOG.md (6 hits) and router_rules.json:145"
  - claim: "The word-budget baseline is clean today, so §1/§2/§3's three bumps start from a green state"
    cite: "`python scripts/word_budget.py` -> 'word budget: 25 skill bodies within budget'; word_budget.json:8 keys the old path at 827"
  - claim: "The suite is green on a fresh clone of 113cc06, so any post-fold red is attributable to this wave"
    cite: "`git clone --no-hardlinks` of the worktree, `python scripts/run_tests.py` -> 46/46 passed"
  - claim: "The depth-1 fold landed with the correct sense in all three places it appears"
    cite: "enforcement table :127; §1 :296-302; DoD :568-572. No surviving 'depth-1 clone runs green' clause anywhere in the file"
  - claim: "ADR-0008 stays in sync with the second fold"
    cite: "ADR:91-96 (generated half gated / tier-0 review-only) matches the enforcement table; ADR:116-124 (firing/effect split, live-hook delivery as a named precondition) matches Context :28-32 and §6 :542-544. The ADR does not assert anything the fold changed"
  - claim: "No stale arithmetic survives the second fold"
    cite: "192 / 24 prompts / 8 cells of 24 / 48 per arm / 12 clusters within a class / $75 ceiling / $25-60 band are internally consistent at :216-225, :435, :455, :467, :489-492, :605-612; 8 x 24 = 192 checks"
```

## Prose

**What the second fold got right.** R2-1's remedy is the right remedy: the freeze's
coordinate belongs in the record, not in the filesystem, and the legality argument
(`plan_frozen_at` is the pointer, never the pinned content) is verified correct at
validate.py:920-931 rather than asserted. R2-3's contrasts-only secondary and the
pre-spend synthetic shape gate together convert a whole defect class — record-shape
collisions discovered after the money is spent — into a free pre-flight, and I
re-executed both halves to confirm they behave as claimed. The depth-1 sense is
restored in all three places it appears, including the enforcement table, with no
surviving inverted clause. And the citation hygiene held through a second fold: 48
ledger anchors and every load-bearing code cite I re-pulled, exact.

**Where the second fold leaves damage.** Round 2 closed with an instruction: run the
whole shape past the validator before the next certification attempt. The record shapes
were run. The *code* change R2-1 asked for was not — and it is the same class of miss,
one level up. Implementing §4's stated semantics literally takes ten minutes and turns
three tests red in the module that dogfoods the freeze gate, and the file it breaks
appears in no section, no file list, and no concept→module map row. §1 states its move
test "as an executed check, because this section's central operation is a rename and
renames are cheap to simulate and expensive to get wrong". The rename was simulated.
The pin that repairs it was not. I have executed both, and I have named the exact
implementation that makes §1's 46/46 claim true — so the fix is small and its answer is
known, which is why this is MAJOR and not BLOCKER: the failure is loud, not silent.

**The finding I care most about is R3-2, and it is not a fold artifact.** It is the
question no round has asked: what is the control arm actually a control for? The answer
the design gives — a spawn with `experiment-discipline` loaded, `Skill` available, and a
skill body that (after §2 and §3) instructs the very line and skeleton the oracle scores
— is a good control. It is just not the control Part B's recorded prior describes. The
sentence "the activation line is new behavior introduced by this wave" is true of the
world and false of the arm, and the one-sided decision rule on the genuine half is
derived from it. The repo even holds the number: this skill's own sealed holdout put its
description at 0.33 recall, with 3/3 on the lexically adjacent positive — measured on a
register close to the one §5 deliberately authors the genuine half in, because that is
the register the arms' patterns must match. A prior argued from a premise the design
refutes, feeding a one-sided rule, in the first study this discipline governs, is worth
two lines of Part B before the freeze rather than a footnote in §6 afterwards.

**On R3-3, and why I did not raise it higher.** The generator is the wave's cheapest and
best structural idea, and freezing its output makes the exposure auditable. But
"auditable" is the only control the design names for fidelity, and the real router is
importable with a path argument it already accepts. Reproducing seven enumerated
semantics by hand when eight lines of import gives all of them — including the three the
enumeration omits — is the one place this spec argues for prose where mechanism is free.
I stopped short of calling it a BLOCKER because a divergence is discoverable at freeze
review and the paid run is gated behind a dry run; I did not drop it to MINOR because the
injected text *is* the treatment, and the omitted semantics (a three-word cap, an
order-preserving dedup, an ASCII collapse that only bites the PT-BR half) change it.

**What I did not attack, and why.** The residual trust the spec names — the pooled
primary contrast as the deployable-package question, `narrow − control`'s inherited
length confound, the oracle-as-proxy limit, the t reference on few clusters declared an
approximation, and the live-hook delivery precondition — is stated design posture and I
have treated it as such. I did not reopen round-1 FM-5's residue, which round 2 recorded
as PARTIALLY-RESOLVED and defensible once the genuine/decoy split is pre-registered as
first-class cells. I did not re-litigate the cost band, the humblepowers 0.8.0 rollback
(no gate reads a CHANGELOG-to-manifest version correspondence — `validate_plugins.py:89`
checks field presence only, so the choice stands on its own reasoning), or the ±5%
token match, which is trivially authorable at characters ÷ 4 once the texts are frozen
per row.

**For the fold.** R3-1 and R3-4 are observed and their repairs are determined — apply
them from the executed evidence, not from the wording. R3-2 and R3-5 are
pre-registration decisions and must be settled before §5's freeze commit, not during §6.
R3-3 and R3-6 are one clause each. None of the six is a redesign; all six are edits to
spec text plus, for R3-1, three file names added to a list. But R3-2 changes what the
frozen record says about its own prior and its own decision rule, which is the one thing
this discipline holds cannot be changed after the freeze — so it is folded now or not
at all.

Unverified-offline: 5

PREMORTEM-VERDICT: NEEDS-REVISION — fresh non-author subagent (opus), round 3, keel kit 0.13.0
