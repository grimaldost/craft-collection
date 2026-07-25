# Experiment: act-hint-detector (measurement tier)

_Derived from record.yaml by render.py -- do not hand-edit._

- Design: 8 cell(s) (control_genuine=24, control_decoy=24, narrow_genuine=24, narrow_decoy=24, wide_genuine=24, wide_decoy=24, inert_genuine=24, inert_decoy=24); shared_tasks=True
- Disposition: total=192, completed=None, excluded=None
- Outcomes:
  - rigor_disposition (role=confirmatory): the response's 2x2 state under verify.py, which reads the response TEXT and no arm label. `line` is the format-(a) activation line present verbatim in shape on a line of its own; `skeleton` is all five tier-0 elements present (method, metric, results, conclusion, and the one-line "what this updates"), detected by the label patterns in oracle_patterns.json. On a GENUINE evaluation act correct means BOTH -- a line emitted without the substance scores zero, which is the founding RG-2x2 declaration-without-behavior pattern made measurable rather than rewarded. On a DECOY correct means NEITHER, which prices the cheapest way to game the genuine half. The full 2x2 state is recorded per run, so the line-only rate is a first-class number.
  - skeleton_wellformedness (role=exploratory): on the GENUINE cells only: at least one numerator-over-denominator figure is present in the response AND every such figure is numerically consistent with itself (numerator <= denominator, denominator >= 1). This is the weaker, SECONDARY question -- whether the element most often dropped actually carries a denominator -- and it is scoped to a subset of the declared cells, so it is reported through `clusters` and `contrasts[]` ONLY and carries no `arms` block: ER-RECON holds every arm block's denominators to N_expected, which a subset-scoped outcome cannot satisfy. The enum has no "secondary", so the role field reads `exploratory` and this sentence is what says which kind of exploratory it is: pre-registered and scoped, not post-hoc.
- Threats: 12 declared, 9 residual

## Record (canonical, machine-checked)

```yaml
analysis_plan:
  aa_calibration: 'narrow_minus_wide RESTRICTED TO THE GENUINE HALF is pre-registered here as an A/A calibration, exploratory like the rest. The frozen table shows narrow and wide delivering BYTE-IDENTICAL text on all 12 genuine prompts -- wide''s extra test/evaluate class adds no genuine match, so on that half the two arms are the same treatment run twice. Its expected value is exactly 0, and whatever it does show is the instrument''s own noise floor: the smallest difference this design can report without a treatment behind it. Reading the primary contrast beside it is free, and a primary effect no larger than the A/A spread is not an effect.'
  ceiling_halt_fallback: if the 75 USD ceiling halts the run, the pre-registered fallback analyzes COMPLETE PROMPT-PAIRS only -- a prompt is kept only where every arm of the contrast carries both of its repeats -- and the reduced precision is reported on the clustered scale.
  ci_method: wilson
  comparison: wide vs control on rigor_disposition (primary); wide vs inert (secondary)
  contrast_estimator: paired_difference
  decision_rule:
    comparison: gte
    direction: two_sided
    metric: rate_difference
    threshold: 0.15
  decision_rule_note: 'TWO-SIDED on the genuine half. The corrected control prior no longer licenses a directional bet, and a treated arm can land BELOW control if the injected hint displaces the model''s own dispatch -- a behavioral claim that stands on its own. The decoy half is two-sided as before: control near perfect and treated arms able to lose ground, which is the habituation cost the wide arm exists to price. The threshold is the honest MEWD on the clustered scale: a plausible two-sided half-width is about 0.15 pooled over 24 clusters and about 0.20 within a class of 12, and a difference of differences is wider still.'
  exclusions:
    arms_block_rule: 'OBSERVED PRE-SPEND against the real validator and pre-registered here rather than discovered at finalize: ER-RECON holds every outcome''s arm denominators to sum to N_expected (192), so a record stating per-arm counts alongside a non-zero disposition.excluded cannot reconcile. The rule is therefore fixed now -- the confirmatory outcome states its `arms` block only when disposition.excluded is 0. With any exclusion BOTH outcomes are reported contrasts-only over the surviving clusters and the descriptive per-arm Wilson rates, which an exclusion is the first thing to invalidate, are not stated at all.'
    fully_excluded_prompt: a prompt whose runs are ALL excluded in either arm of a contrast drops out of that contrast entirely, with the surviving cluster count recorded. stats.paired_difference raises on a zero-size cluster rather than degrading, so the drop-out rule is what keeps one dead prompt from taking the analysis down.
    operationalization: 'a run is excluded IFF the harness reports is_error or the response text is empty; a response that DECLINES for lack of an allowed tool is NOT an exclusion -- it is scored as written. This is load-bearing rather than housekeeping: 10 of the 12 decoys ask for actions the arms cannot perform (Bash, Write and Edit are all denied), so without this line the refusal-versus-response judgement would decide after the fact whether the decoy half exists at all. A spawn that says it cannot run the suite, and stops, has still answered without the shape, which is exactly what a decoy is scored on.'
    rule: a refusal, a truncation, or a tool error is excluded with its reason through the disposition machinery, and the response text of an excluded run is not scored.
  exploratory_contrasts: 'every other contrast is exploratory and is reported as such: narrow_minus_control, narrow_minus_inert, inert_minus_control, the per-class decompositions, and anything at all on skeleton_wellformedness. Nothing confirmatory may be added after the freeze -- a post-freeze finding is quarantined (added_after_freeze: true, role: exploratory), which ER-PREREG enforces against the freeze commit.'
  interpretations:
  - condition: wide moves beyond its interval and inert does not
    id: content_carries
    read: 'the hint''s CONTENT carries the effect. "Content" here means the REALISTIC hint, not disembodied semantics: the wide text is the router''s own composition, so its content includes the literal plugin-qualified skill id `experiment-discipline:experiment-rigor`, the echoed matched words from the prompt, and the imperative to check fit before starting. A model that reacts to the named id rather than to the sentence''s meaning selects this leg too, and that is the correct reading of it -- a shipped row ships the id.'
  - condition: wide and inert both move alike
    id: preamble_only
    read: the effect is preamble cost and the content is irrelevant; ship no row on this evidence
  - condition: inert moves and wide does not
    id: inert_moves_alone
    read: likewise a preamble effect with content contributing nothing; ship no row
  - condition: nothing moves beyond its interval
    id: recorded_null
    read: a recorded null. A null with control AT OR NEAR CEILING on the genuine half is recorded as NO HEADROOM, not as no effect -- the instrument had nowhere to move, which is a different finding and a different follow-up. The read then rests on the DECOY side, where the habituation cost is visible whatever the genuine ceiling does, and on wide - inert.
  interval:
    alpha: 0.05
    assumptions: roughly symmetric per-cluster deltas and a t reference distribution on few clusters. This is the one approximation in the stats module, and naming it beside the exact bound below -- before the run -- is what stops the friendlier of the two from being chosen afterwards.
    formula: estimate +/- t(1 - alpha/2, n_clusters - 1) * se, with the t quantile recorded
    method: paired_t
    source: stats.paired_interval over the per-cluster deltas
    status: approximation
  language_fallback: 'decided from the FROZEN FIRING TABLE, which holds no outcome data, so reading it before the run is a design decision and not a peek at a result: if the table shows the PT-BR firing rate below half the EN rate, the primary analysis restricts to the EN half. Observed in the frozen table -- narrow fires 6/12 EN and 6/12 PT-BR, wide 9/12 and 9/12. The rates are equal, so the fallback does NOT fire and the primary analysis runs over all 24 prompts.'
  per_arm_intervals:
    method: wilson
    note: an UPPER BOUND on precision -- it prices independent trials on a design whose unit is the prompt cluster. Stated only for the full-cell-set confirmatory outcome, and only when disposition.excluded is 0 (see exclusions.arms_block_rule). The headline precision is always quoted on the clustered scale.
    role: descriptive
  primary_contrast:
    arms:
    - wide
    - control
    name: wide_minus_control
    outcome: rigor_disposition
    question: the deployable-package question. A shipped row ships its tokens too, so the package contrast is what a rollout decision would actually rest on.
    role: confirmatory
  robustness_bound:
    method: sign_test
    reported: beside every contrast's interval, never instead of it
    sided: two_sided
    status: exact, distribution-free, TWO-SIDED
    tie_rule: 'a ZERO per-cluster delta is DROPPED and the surviving effective cluster count is reported beside the p-value. Fixed here, before the freeze: with 2 repeats a per-cluster delta lives in {-1, -0.5, 0, 0.5, 1} and ties are expected to be the modal cluster, so the effective n is load-bearing information rather than a footnote, and picking the rule after seeing the deltas is precisely the latitude naming both statistics is meant to remove.'
  secondary_contrast:
    arms:
    - wide
    - inert
    name: wide_minus_inert
    outcome: rigor_disposition
    question: confound separation -- the mechanism question. wide and inert fire on an identical row set at an identical insertion point with token-matched text, so this pair is the only one in the design that isolates CONTENT from preamble.
    role: exploratory
    role_note: PRE-REGISTERED AND SCOPED, not post-hoc. The experiment design calls this the confound-separation SECONDARY; the role field reads `exploratory` only because the schema's role enum has no "secondary" value. It is named here, before the freeze, with its arms and its question fixed, which is the distinction the enum cannot carry.
  unit_of_analysis: the prompt CLUSTER -- 24 of them, 12 within a class -- not the run. Each prompt contributes a per-arm rate over its 2 repeats and every contrast is the mean of the per-prompt differences with the task-level paired SE from stats.paired_difference. An independent-trials figure over 48 runs per arm would price a precision this design does not have.
baseline_expectation:
  ceiling_risk: 'the prior''s upper tail is a CEILING RISK, a different failure from the compression named below: with control at or near ceiling on the genuine half there is no headroom for any arm to move into, and a null then says nothing about the hint. That leg is pre-registered at analysis_plan.interpretations.recorded_null.'
  compression_risk: a non-zero control also COMPRESSES the contrast against a MEWD already declared large. That is a spend risk stated up front rather than discovered after the money is gone.
  control_is_not_no_treatment: every arm loads plugins/experiment-discipline with the Skill tool available, and by run time the tier-0 rung and the activation-line emission rule are in that skill's body -- so the control spawn already carries, in its own loaded plugin, a skill that instructs the behavior the oracle scores. Control measures THE SKILL'S OWN TRIGGER SURFACE WITH NO HINT, and wide - control is the hint's MARGINAL effect over a loaded, unhinted skill, not "convention versus nothing".
  decoy_side: control near perfect and the treated arms able to lose ground -- the habituation cost the wide arm exists to price, and the half the read falls back to if the genuine side is at ceiling.
  measured_number: 'the repo holds one number for that surface: the sealed holdout put this skill''s description at 0.33 recall [0.15, 0.58] (evals/trigger/holdout/BASELINES.md). It transports POORLY to this bank. Four of that holdout''s five positives are pure intent paraphrases, which is the register the lexical ceiling predicts near-zero recall on; the single SAME-REGISTER positive -- the direct evaluation-act register this bank''s genuine half is deliberately written in, because that is the register the arms'' patterns must match -- hit 3/3.'
  prior: the genuine-side prior is therefore WIDE RATHER THAN LOW. Control is expected materially above zero and the hint's effect is incremental over that; 0.33 is not carried across as a point estimate.
construct_boundary: this experiment measures the effect of an INJECTED HINT DELIVERED AT ROUTER-REALISTIC FIRING PATTERNS. Firing is computed offline by a generator that drives the real router read-only and is frozen in firing_table.json; the paid run delivers the frozen text directly, prepended to the prompt on stdin. Whether the live UserPromptSubmit hook delivers that same text inside a production spawn is NOT measured here. That, and candidate displacement under the live nine-row rules, are named PRECONDITIONS for any production rollout of a row -- not results of this run.
design:
  cells:
  - name: control_genuine
    planned_n: 24
  - name: control_decoy
    planned_n: 24
  - name: narrow_genuine
    planned_n: 24
  - name: narrow_decoy
    planned_n: 24
  - name: wide_genuine
    planned_n: 24
  - name: wide_decoy
    planned_n: 24
  - name: inert_genuine
    planned_n: 24
  - name: inert_decoy
    planned_n: 24
  shared_tasks: true
disposition:
  total: 192
experiment: act-hint-detector
firing:
  below_floor_rows: 0
  control:
    decoy: 0/12
    en: 0/12
    fired: 0
    genuine: 0/12
    pt: 0/12
  inert:
    decoy: 6/12
    en: 9/12
    fired: 18
    genuine: 12/12
    pt: 9/12
  narrow:
    decoy: 0/12
    en: 6/12
    fired: 12
    genuine: 12/12
    pt: 6/12
  note: every bank prompt clears the dispatch hook's floor (>= 4 words and >= 15 characters), so no row is a no-injection-everywhere row here; the generator still emits such a row visibly rather than as a silent hole, and a test covers that path.
  rows: 96
  table: firing_table.json
  wide:
    decoy: 6/12
    en: 9/12
    fired: 18
    genuine: 12/12
    pt: 9/12
  wide_inert_row_identity: 'identical by construction: inert''s rules file carries wide''s patterns byte for byte, so the firing decision is the same computation, not the same intention.'
  wide_inert_token_match: every one of the 18 firing rows matches exactly on the declared estimate (characters / 4); worst-row deviation 0.00 percent against a 5 percent tolerance.
materials:
  bank:
    path: bank.json
    sha256: 212b9d12578a164fcef5ff309f088cdb88d69a5b5cd23d92460f54656c83719d
  firing_table:
    path: firing_table.json
    sha256: ef5679822b9e92a5063603d2b4d5a954d205c3bc8908d61fd06f3d95fa616d62
  oracle:
    path: verify.py
    sha256: 68ce9df4a8f578efd18e1f88050c8a6cfd57106bcb8033ce583b0732481c0762
  oracle_labels:
    path: oracle_labels.json
    sha256: b746067a6c0b02772d9b48cb681babc15b8776f8eb5da665a9852599b20de61c
  oracle_patterns:
    path: oracle_patterns.json
    sha256: dfb6da7bd49bc25dec44f04159e99e1d9ebd3dee2b55084bb2fd54be40f5151f
  rules_control:
    path: rules/control.json
    sha256: 44288dee0bbdbf87284beed4dff785583f01b993033e7a44bde096d5cf14ea19
  rules_inert:
    path: rules/inert.json
    sha256: 15b72b4780f944952fa05ef79de790bbf3d1072359ba9ece95d1052796fff44d
  rules_narrow:
    path: rules/narrow.json
    sha256: e961ead09b95165d507955aa05ccbbe6fa36bc99531802cbdd46ea8f6590a8a2
  rules_wide:
    path: rules/wide.json
    sha256: 8d2cea4682c393abff804f3609d2ff5c11877021570085388b03708645389d1d
oracle_validation:
  adversarial_items: 'four of the sixteen exist to pin a defect found at review rather than to pad a count: the PLUGIN-QUALIFIED activation line the injection itself supplies (en-both-03), a SENTENCE-FINAL inconsistent figure the earlier fraction pattern dropped (en-skeleton-03), a DATE that must not parse as a rate (pt-neither-03), and a line QUOTED inside a fenced block, which is showing the convention rather than emitting it (en-neither-02).'
  labeled_set: oracle_labels.json
  languages:
  - en
  - pt
  n: 16
  note: the positive class is the 2x2 state `both` -- the only state that counts a genuine prompt correct, and therefore the call the confirmatory outcome rests on. Sixteen labeled items is a small validation set and 4/4 recall on it is a weak upper bound, not a claim of perfect sensitivity; its job is to catch a pattern edit that changes what the oracle means, which is why every label pins four independent calls (line, skeleton, state, wellformedness) rather than one. It measures the oracle against labels, not against doctrine -- the systematic false negative on an unlabelled prose check is named under threats.construct_validity_proxy, not here.
  per_state_n_min: 3
  positive_class: both
  recall:
    denominator: 4
    numerator: 4
    rate: 1.0
  sha256: b746067a6c0b02772d9b48cb681babc15b8776f8eb5da665a9852599b20de61c
  specificity:
    denominator: 12
    numerator: 12
    rate: 1.0
  states_covered:
  - both
  - line_only
  - skeleton_only
  - neither
outcomes:
- name: rigor_disposition
  operationalization: the response's 2x2 state under verify.py, which reads the response TEXT and no arm label. `line` is the format-(a) activation line present verbatim in shape on a line of its own; `skeleton` is all five tier-0 elements present (method, metric, results, conclusion, and the one-line "what this updates"), detected by the label patterns in oracle_patterns.json. On a GENUINE evaluation act correct means BOTH -- a line emitted without the substance scores zero, which is the founding RG-2x2 declaration-without-behavior pattern made measurable rather than rewarded. On a DECOY correct means NEITHER, which prices the cheapest way to game the genuine half. The full 2x2 state is recorded per run, so the line-only rate is a first-class number.
  role: confirmatory
  verifier:
    hash: 68ce9df4a8f578efd18e1f88050c8a6cfd57106bcb8033ce583b0732481c0762
    path: verify.py
- name: skeleton_wellformedness
  operationalization: 'on the GENUINE cells only: at least one numerator-over-denominator figure is present in the response AND every such figure is numerically consistent with itself (numerator <= denominator, denominator >= 1). This is the weaker, SECONDARY question -- whether the element most often dropped actually carries a denominator -- and it is scoped to a subset of the declared cells, so it is reported through `clusters` and `contrasts[]` ONLY and carries no `arms` block: ER-RECON holds every arm block''s denominators to N_expected, which a subset-scoped outcome cannot satisfy. The enum has no "secondary", so the role field reads `exploratory` and this sentence is what says which kind of exploratory it is: pre-registered and scoped, not post-hoc.'
  role: exploratory
  verifier:
    hash: 68ce9df4a8f578efd18e1f88050c8a6cfd57106bcb8033ce583b0732481c0762
    path: verify.py
plan_frozen_at:
  commit: b8307b70dfca69b0accf1a4010d4ed36d19fae89
  path: evals/experiments/act-hint/record.yaml
  timestamp: '2026-07-25T20:38:57-03:00'
run:
  first_run_at: 2026-08-05 00:00:00+00:00
  hand_reason: no fathom ledger produces these rows. The detector runs on the in-repo craft harness (evals/harness/claude_runner.py) because the outcomes are properties of the response text and the isolation primitives -- one isolated credentials-only CLAUDE_CONFIG_DIR for the run set, a fresh spawn per run, a tool allowlist, a --plugin-dir -- already exist there; a fathom bank would rebuild them cross-repo. ER-XCHECK's measurement-tier WARN is therefore a declared posture, not an accident. run_arms.py appends every run to runs.jsonl, which travels with the record as the reconstructible trace.
  n_planned: 192
  source: hand
run_config:
  allowed_tools: Skill,Read,Glob,Grep
  allowlist_identical_across_arms: true
  ceiling_rule: 'the runner refuses to START a spawn when the amount already spent plus that spawn''s own cap would cross the ceiling, so the ceiling is never crossed and then noticed. The one-cap margin also absorbs a known under-count: the harness retries a transient failure internally and reports only the last attempt''s cost, so the accumulator can read low on a retried job.'
  ceiling_usd: 75.0
  cost_projection_usd:
    per_run_high: 0.31
    per_run_low: 0.13
    total_high: 59.52
    total_low: 24.96
  cwd_fixture: evals/experiments/act-hint/cwd_fixture
  disallowed_tools: Write,Edit,NotebookEdit,Bash,WebFetch,WebSearch,Task
  insertion_note: the frozen injected text, one blank line, then the bank prompt, delivered on the spawn's stdin. One insertion point, never moved, identical across arms.
  insertion_point: prefix_blank_line
  isolation: 'ONE isolated credentials-only CLAUDE_CONFIG_DIR is built for the run set (no CLAUDE.md, no settings.json, no history) and every spawn uses it; it carries no per-run state, so sharing it across the set is not a channel between runs. PER RUN: a fresh spawn under --no-session-persistence, the restricted allowlist above, and the neutral cwd fixture holding no expected answer. No state carries between repeats, and the config dir is identical for every arm.'
  max_turns: 6
  model: claude-sonnet-4-6
  model_rationale: the repo's standard agent model (evals/config.json `agent_model`). The only in-repo cost anchor is a trigger-arm run at about 0.099 USD per read-only 3-turn spawn on this same model -- a LOWER BOUND on a different profile, not a like-for-like rate, because the detector's spawns are task-shaped. Budgeting 0.13-0.31 USD per run at a turn cap of 6 puts the estimate at 24.96-59.52 USD, inside the declared 25-60 band and under the 75 USD ceiling.
  order: randomized and interleaved across arms under random.Random(seed).shuffle
  order_seed: 20260725
  per_run_budget_usd: 0.4
  plugin_dir: plugins/experiment-discipline
  repeats: 2
  runner: evals/experiments/act-hint/run_arms.py over evals/harness/claude_runner.py
  sampling: CLI default -- no temperature or top-p flag is passed, so sampling is above zero
  sampling_mode: cli_default
  skill_tool_in_allowlist: true
  timeout_seconds: 300
schema_version: 1.1
threats:
  construct_validity_proxy:
    statement: 'the oracle scores the SHAPE of the response, which is a proxy for the discipline the shape is meant to carry, and it errs in both directions. FALSE POSITIVE: a five-element wrapper around an unconsidered answer scores correct; skeleton_wellformedness is the partial answer (a denominator present and self-consistent) and it is a secondary, not the headline. FALSE NEGATIVE, and the more likely of the two: the oracle detects the five elements by their LABELS, so it scores the reference''s worked-example format rather than the rung''s actual rule -- and the reference says explicitly that "a check that carries all five in two sentences is a good check" and that the point is that every element is answerable, not that the response has five headings. A fully doctrine-compliant unlabelled prose check therefore scores 0 of 5. The consequence is stated rather than repaired: absolute rates read LOW and must not be quoted as the rate at which the discipline was followed, while the CONTRASTS stay interpretable because the mode is arm-uniform -- nothing in any arm''s injected text touches labelling. The one arm-differential interaction this had, an inert text that discouraged the labelled shape, was removed from the clause pool before the freeze.'
    status: residual
  contamination_familiarity:
    statement: the tier-0 shape is a plain five-element report structure and models may have seen structurally similar shapes in pretraining. That is not removable here, and it is partly what the control arm measures rather than a confound to subtract.
    status: residual
  custom_candidate_displacement:
    statement: 'the offline firing table exhibits NO displacement, and the reason is structural rather than reassuring: each arm''s rules file carries the evaluation-act row ALONE, so route() can return at most one candidate and there is nothing to crowd out. Displacement under the live nine-row router_rules.json is therefore UNMEASURED, and it stands -- together with live-hook delivery -- as a production precondition rather than as a result of this run. It is also why the genuine-side decision rule is two-sided: a hint can displace the model''s own dispatch, which is a behavioral claim that does not depend on the router''s row competition at all.'
    status: residual
  custom_language_delivery:
    statement: the PT-BR patterns are UNCALIBRATED -- authored for this bank, not fitted against a labeled PT-BR set -- and the router's ASCII collapse rewrites an accented echoed span, so 2 of the 6 PT-BR genuine rows deliver "isso ? eficaz" / "qual ? melhor" where the EN rows deliver clean text. The PT-BR half therefore receives a slightly degraded hint. The pre-registered fallback (analysis_plan.language_fallback) restricts the primary analysis to EN if the frozen table shows PT-BR firing below half the EN rate; the frozen table shows the rates EQUAL, so the fallback does not fire and all 24 prompts stay in.
    status: residual
  custom_oracle_primeability:
    statement: 'CONTROLLED MECHANICALLY: a test runs the oracle''s own activation-line and five-element patterns over every bank prompt AND every frozen injected text, so the treatment cannot hand the model the answer the oracle scores. The constraint binds the bank as well as the rules because the router echoes literal spans of the prompt into the hint. The RESIDUAL is that a ban list can only cover the prime paths it names: the two primeability-class defects found at review -- the oracle rejecting the plugin-qualified id the injection itself supplies (an arm-differential FALSE negative, since only the treated arms carry the id) and a quoted-in-a-fence line scoring as an emitted one -- were both missed by this test, because neither was a banned string appearing where it should not be. Both are fixed in the frozen oracle; the class is not closed by fixing two of its members, so this row stays visible rather than being retired.'
    status: controlled
  generalization:
    statement: 'one bank of 24 prompts in two languages, one model, one turn cap, one insertion point, one plugin loaded. And the construct boundary carried throughout: this measures THE EFFECT OF AN INJECTED HINT DELIVERED AT ROUTER-REALISTIC FIRING PATTERNS. Whether the live UserPromptSubmit hook delivers that same text inside a production spawn is NOT measured here -- it is a named precondition for any production rollout of a row.'
    status: residual
  judge_bias:
    statement: verify.py alone scores the runs -- a deterministic regex oracle, frozen by SHA, carrying no arm label, validated against a 12-item hand-labeled set spanning both languages and all four 2x2 states before use (recall 3/3, specificity 9/9 on the `both` state). No LLM judge exists in this design, so no judging line item appears in the cost.
    status: controlled
  model_version_drift:
    statement: one unpinned model snapshot (claude-sonnet-4-6) over the measurement window; the instrument can move underneath the run. Arm order is randomized and interleaved under seed 20260725, so a drifting snapshot cannot line up with an arm -- that bounds the damage, it does not remove it.
    status: residual
  nondeterminism:
    statement: CLI default sampling (no temperature flag is passed, so it is above zero) with 2 repeats per cell. Two repeats is also what puts a per-cluster delta in {-1, -0.5, 0, 0.5, 1} and makes ties the expected modal cluster, which the sign test's tie rule is fixed in advance for.
    status: residual
  prompt_format_sensitivity:
    statement: one bank, one prompt text per id across every arm, one insertion point (the injected text, a blank line, then the prompt, fed on stdin). The only thing that varies between arms is which prompts receive an injection and what text they receive.
    status: controlled
  selection_exclusion:
    statement: no run has happened, so no exclusion is observed. The exclusion rules are pre-registered in analysis_plan.exclusions (reason-tagged exclusion, the fully-excluded-prompt drop-out, and the arms-block rule); the finalize step restates this row against the observed disposition.
    status: residual
  token_length_confound:
    statement: 'written per contrast, not blanket. The token-matched inert arm controls it for `wide - inert` ONLY: every firing row''s inert text matches wide''s estimated token count exactly in the frozen table (0.00 percent deviation on all 18 firing rows, against a 5 percent tolerance). NO arm is length-matched to narrow, so `narrow - control` re-inherits the founding RG-2x2 case''s confound intact. And the package contrasts -- `wide - control` and `narrow - control` -- make NO mechanism claim: they price a deployable row, tokens included.'
    status: residual
tier: measurement
```
