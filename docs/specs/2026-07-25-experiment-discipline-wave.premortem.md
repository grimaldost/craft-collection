# Pre-mortem — the experiment-discipline wave

- **Spec:** `docs/specs/2026-07-25-experiment-discipline-wave.md`
- **Date:** 2026-07-25
- **Reviewer:** fresh non-author subagent (opus), round 1
- **Spec-hash:** `75b50c4bf9849ee9afe5ec9f35777e6df22d5c99c7ddbfac61119b1e01bd3f50`
- **Reviewed against:** worktree `C:/Users/grima/Documents/craft-collection-rigor`, branch `feat/experiment-rigor-skill` @ `113cc06`; ADR-0008 read; keel kit 0.13.0

Assume this series shipped and then failed. The failure I judge most likely is not
the re-home — that part is well grounded. It is that §4/§5 spend $27–54 and 168
spawns on an instrument whose treatment never reaches the measured unit, and whose
two confirmatory outcomes net the two effects the wave exists to separate.

---

## Findings

```yaml
- id: FM-1
  severity: BLOCKER
  title: "§4's bank register contradicts Part B's own feasibility check; the run is a likely structural null"
  evidence: "docs/specs/2026-07-25-experiment-discipline-wave.md:300 ('8 genuine evaluation acts in paraphrase') vs :473-478 ('the bank's genuine half must carry the direct-register phrasings the narrow row can actually match; a bank of pure intent paraphrase would be null on this instrument'); evals/trigger/holdout/BASELINES.md:19 (direct 0.94 / embedded 0.44 / paraphrase 0.12); plugins/humblepowers/skills/choosing-tools/scripts/router.py:42"
  detail: >-
    The spec states the bank two incompatible ways in the same document, and Part B
    asserts §4 already resolved it ("§4's bank therefore fixes the register mix before
    the freeze") — §4's text does not. On the paraphrase reading, the router fires on
    roughly 1 of 8 genuine prompts, all four arms converge, and $27-54 buys a null the
    design never controlled. Nothing in §4's acceptance criterion checks that any arm's
    rules actually match any bank prompt: the mechanical test asserts pattern EQUALITY
    between inert and wide and byte-stability of the shipped rules, never match COVERAGE
    over the bank.
  smallest_fix: "§4 fixes the register mix numerically (e.g. 6 direct-register + 2 embedded genuine) and freezes a per-prompt match-coverage table in the record, with a test asserting each arm's rules fire on exactly that set."
  disconfirming_test: "Run `router.py --prompt` (with each candidate rules file) over the 14 draft bank prompts and count matches per arm; if narrow matches <6 of 8 genuine, the bank is null on this instrument."
  target_section: "section 4"

- id: FM-2
  severity: BLOCKER
  title: "The hook's own length floor silently excludes bank prompts — including a decoy §4 quotes verbatim"
  evidence: "plugins/humblepowers/skills/choosing-tools/scripts/inject_dispatch.py:52-53 (MIN_WORDS = 4, MIN_CHARS = 15) and :114 (`if len(prompt) < MIN_CHARS or len(prompt.split()) < MIN_WORDS: return 0`); docs/specs/2026-07-25-experiment-discipline-wave.md:303 (decoy 'run the tests')"
  detail: >-
    The treatment is delivered by `_prompt_submit`, which returns 0 — no injection, no
    telemetry — before the router runs, for any prompt under 4 words or 15 characters.
    "run the tests" is 3 words / 13 characters. So the decoy half that is supposed to
    price wide's habituation cost receives no injection in ANY arm, and it fails
    silently: every gate in §4 still exits 0. The same floor quietly removes any short
    genuine prompt from the treated set while leaving it in the denominator.
  smallest_fix: "§4 records the hook's MIN_WORDS/MIN_CHARS floor as a bank authoring constraint (every prompt >= 4 words and >= 15 chars) and freezes the per-prompt injection-eligibility column beside the match-coverage table of FM-1."
  disconfirming_test: "Feed each draft bank prompt to `inject_dispatch.py --prompt-submit` with the gate env set and check stdout is non-empty; any silent prompt is outside the instrument."
  target_section: "section 4"

- id: FM-3
  severity: BLOCKER
  title: "The arm rule files cannot carry hint text — the inert arm as specified is unbuildable, and its length match has no home"
  evidence: "plugins/humblepowers/skills/choosing-tools/scripts/router.py:62-77 (`hint_line` composes one fixed sentence from the matched skill id and the echoed matched words); router_rules.json rows carry only {id, patterns, negative_patterns, min_hits} (verified by enumerating all nine rows)"
  detail: >-
    Three claims collapse against the same fact. (a) §4's test is to assert the four
    files "differ from each other only in the evaluation-act row's patterns and hint
    text" — there is no hint field in the rule schema. (b) inert is specified as "a
    generic neutral house-style reminder naming no experiment, evaluation, rigor, or
    tier"; `hint_line` unconditionally emits "Prompt wording matches triggers for:
    <plugin:skill> (matched: ...)", so an inert arm built from a rules file NECESSARILY
    names a skill — and if that skill is experiment-rigor, inert is not inert. (c) "inert's
    hint word count within +/-10% of wide's" is not a property of a rule file at all: the
    rendered text varies per prompt because the matched words are echoed into it. The
    length-confound control — the mechanism the enforcement table lists as "planned" and
    the DoD calls the reason `token_length_confound` is "controlled" — has no buildable
    home in any numbered section.
  smallest_fix: "§4 names the router change that adds a per-row `hint` template (fixed text, no echoed words) and lists router.py in the concept->module map; or the inert arm is dropped and `token_length_confound` reverts to residual."
  blast_radius: "A per-row hint field changes the shipped router's rendering path for all nine rows and the live UserPromptSubmit hook; test_router.py::test_payload_is_ascii and ::test_matched_words_reported both read hint_line output."
  consumed_input: "inject_dispatch.py:123 consumes `router.hint_line(router.route(...))` — the injected string is built entirely inside router.py; nothing in router_rules.json reaches the injected text except the id."
  disconfirming_test: "`python -c \"import router; print(router.hint_line(router.route('is the new skill actually effective', router.load_rules())))\"` — read whether any per-row text can vary the sentence."
  target_section: "section 4"

- id: FM-4
  severity: BLOCKER
  title: "§4 requires shipped-humblepowers code changes the spec's version and CHANGELOG mechanics deny"
  evidence: "plugins/humblepowers/skills/choosing-tools/scripts/inject_dispatch.py:102-104 (the only env gate) and :121-123 (`import router; router.route(prompt, router.load_rules())` — load_rules called with NO path); router.py:34 (`load_rules(path=RULES_PATH)` accepts a path, nothing passes one)"
  detail: >-
    "Selected by a config flag beside the existing gate" describes code that does not
    exist: there is no env var, no argument, and no call site that can point the hook at
    an alternate rules file. Building it edits inject_dispatch.py and threads a path
    through. But the Settled decision binds humblepowers' CHANGELOG to "one new entry for
    the only thing that actually changed there — the choosing-tools router row now naming
    a cross-plugin id", and rolls the manifest back to 0.8.0. So PR04 either cannot select
    arms, or 0.8.0 ships an undocumented behavior change in a live prompt-path hook. The
    concept->module map lists neither file.
  smallest_fix: "Add `inject_dispatch.py` and `router.py` to §4's file list and the concept->module map, and either bump humblepowers to 0.8.1 with a CHANGELOG entry for the arm-selection flag, or move the flag out of humblepowers into a run_arms.py-owned shim that sets the rules path itself."
  blast_radius: "Touching inject_dispatch.py reaches the installed UserPromptSubmit hook for every user with HUMBLEPOWERS_DISPATCH_PROMPT_INJECT=1; the hook contract is fail-open-silent, so a regression is invisible."
  consumed_input: "plugins/humblepowers/hooks/hooks.json invokes `${CLAUDE_PLUGIN_ROOT}/skills/choosing-tools/scripts/inject_dispatch.py --prompt-submit`; the version consumed by the marketplace is plugins/humblepowers/.claude-plugin/plugin.json's `version`."
  disconfirming_test: "grep inject_dispatch.py for any environment read other than HUMBLEPOWERS_DISPATCH_PROMPT_INJECT / _ROUTER / _STATE_DIR; if none selects a rules path, the flag must be built."
  target_section: "section 4"

- id: FM-5
  severity: BLOCKER
  title: "Both confirmatory outcomes NET the two effects the experiment exists to separate"
  evidence: "docs/specs/2026-07-25-experiment-discipline-wave.md:311-316 (both outcomes 'scored over all 168 so each one's arm denominators reconcile to N') vs :469-471 ('the wide arm's predicted decoy loss is exactly the habituation cost the experiment exists to price'); plugins/humblepowers/skills/experiment-rigor/scripts/validate.py:472-484 (recon requires each outcome's arm denominators to sum to N_expected)"
  detail: >-
    `rigor_disposition` is one accuracy rate per arm over 24 genuine + 18 decoy runs. A
    hint that raises genuine detection by k and lowers decoy restraint by k moves that
    rate by exactly zero — and that is the pattern Part B PREDICTS for wide. The primary
    outcome is structurally incapable of pricing the cost the arm was added to price.
    `skeleton_completeness` is worse: the decoy half ("absent when not due") is expected
    at ~1.0 in every arm, so 18/42 of the denominator is a constant and any real effect is
    diluted by ~43% before the interval is drawn. Decomposing after the run is post-freeze
    exploratory (validate.py:956-968), so the honest split is unavailable at analysis time.
    The reconciliation constraint the spec cites as a virtue (denominators sum to N) is
    precisely what forces the netting.
  smallest_fix: "Freeze four confirmatory outcomes with disjoint denominators — genuine-half disposition (n=24/arm), decoy-half restraint (n=18/arm), and the same split for skeleton_completeness — and reconcile N as the sum across outcomes' cells rather than forcing each outcome over all 168."
  disconfirming_test: "Construct the 2x2 by hand: set genuine 8/24 -> 20/24 and decoy 18/18 -> 6/18 for one arm and recompute the composite rate; if it moves less than the frozen threshold, the outcome cannot detect the effect it was designed for."
  target_section: "section 4"

- id: FM-6
  severity: MAJOR
  title: "ER-STATS mechanically forces the anti-conservative interval; 'task-clustered intervals' cannot be recorded"
  evidence: "plugins/humblepowers/skills/experiment-rigor/scripts/validate.py:546-566 (every stated `ci` is recomputed via `stats.confidence_interval(num, den, method, alpha)` and FAILS on mismatch); stats.py:270-300 (`clustered_se`) and :303-326 (`paired_difference`) return standard errors, not intervals"
  detail: >-
    §5 and Part B both promise "paired, task-clustered intervals". The record cannot carry
    one: the validator recomputes each arm's interval from the raw 42/arm counts, so a
    clustered (wider) interval fails ER-STATS and the unclustered Wilson is the only value
    that passes. 42 runs are 14 prompts x 3 repeats, not 42 independent trials; the
    committed number will therefore state a precision the design does not have, and the
    gate is what compels it. §5's acceptance criterion ("every stated interval matching a
    stats.py recomputation") and Part B's clustering promise are mutually exclusive as written.
  smallest_fix: "Pre-register that per-arm `ci` is the unclustered Wilson (an upper bound on precision) and that the clustered/paired SE is reported in the existing `clustered_se` field (validate.py:584-596), with the report's headline precision quoted on the clustered scale."
  disconfirming_test: "Take any plausible per-arm split (e.g. 26/42), compute wilson(26,42) and clustered_se over 14 prompt clusters, and check whether the clustered half-width fits inside the Wilson bounds the validator will demand."
  target_section: "section 5"

- id: FM-7
  severity: MAJOR
  title: "MEWD is computed on the wrong unit of analysis — the one Part B itself names"
  evidence: "docs/specs/2026-07-25-experiment-discipline-wave.md:419-425 ('at 42 per arm a Wilson interval near a rate of 0.5 is roughly +/-0.15') vs :417-418 ('the unit is one prompt-run; the 14 prompts are shared across arms, so comparisons are paired and standard errors are clustered on prompt id')"
  detail: >-
    +/-0.145 is correct for 42 independent Bernoulli trials and wrong for the stated
    design: with G=14 clusters the effective unit count is nearer 14, and a
    difference-of-differences (wide - inert against control) on 14 paired clusters is
    wider still. §5 will be asked to name "whether wide - inert separates attention
    direction from preamble length" on a contrast whose interval plausibly spans the whole
    plausible effect range. The spec's own honesty clause ("this is a directional read")
    does not repair a stated number that is off by roughly a factor of two.
  smallest_fix: "Restate 'Reps / power & MEWD' with G=14 clusters as the unit, quote the paired per-prompt difference SE from stats.paired_difference, and set the MEWD on that scale."
  disconfirming_test: "Simulate 14 per-prompt differences at the predicted effect size and compute stats.paired_difference's SE; compare its 2*SE to the claimed 0.20-0.25 MEWD."
  target_section: "Experiment design (Part B)"

- id: FM-8
  severity: MAJOR
  title: "The oracle is defeatable by the treatment: the inert arm controls length, not lexical priming of the regex"
  evidence: "docs/specs/2026-07-25-experiment-discipline-wave.md:305-306 ('verify.py, the deterministic regex oracle over the response') and :436-439; the treatment is text injected into the user prompt (inject_dispatch.py:114-135)"
  detail: >-
    Outcome 1 scores "a well-formed activation line with a declared tier"; outcome 2 scores
    "the five skeleton elements". Both are lexical surfaces. Any hint whose text names the
    line format or the five element words hands the model the exact tokens the regex greps
    for, so an arm can move both outcomes by vocabulary echo with no change in evaluative
    behavior. `wide - inert` controls token COUNT and injection POSITION; it does not
    control lexical overlap with the oracle, because inert is required to name nothing
    evaluative and therefore shares none of wide's target vocabulary. The claimed guard
    ("the decoys guard the cheapest way to game outcome 1") addresses over-declaration,
    a different attack.
  smallest_fix: "Add a frozen wording constraint — no arm's hint may contain the activation-line format or any of the five element names — asserted by §4's arm-file test, and declare `construct_validity_proxy` residual with this statement."
  disconfirming_test: "Write the draft wide hint and run verify.py's regexes against the hint text alone; any element the hint itself satisfies is a channel from treatment to score."
  target_section: "section 4"

- id: FM-9
  severity: MAJOR
  title: "`token_length_confound: controlled` overstates — narrow - control stays length-confounded, and it is the arm most likely to ship"
  evidence: "docs/specs/2026-07-25-experiment-discipline-wave.md:322-324 (the threat 'declared controlled and naming the inert arm as its mechanism') vs :410-413 (the estimand names narrow - control, wide - control, inert - control); plugins/humblepowers/skills/experiment-rigor/examples/rg-2x2/record.yaml:91-95 (the founding case's residual token_length_confound: '~90 more system-prompt words ... Possibly fatal to the causal reading')"
  detail: >-
    The inert arm is length-matched to WIDE only, and fires on WIDE's match set. So
    narrow - control is exactly the founding case's declared near-fatal flaw, re-inherited
    for the conservative row the wave would actually ship; and inert - control prices tokens
    at wide's coverage, which cannot be transported to narrow's smaller match set. The
    enforcement table is honest ("wide vs inert: same match set, same position, word count
    within +/-10%") while §4's acceptance criterion and the DoD declare the threat controlled
    without qualification. The record's threat row will therefore assert more than the
    design delivers — the exact defect this discipline exists to catch.
  smallest_fix: "Write the `token_length_confound` statement as controlled-for-wide/residual-for-narrow, and name wide - inert as the only contrast the threat status licenses."
  disconfirming_test: "Ask whether any arm is length-matched to narrow; if none is, narrow - control carries the confound by construction."
  target_section: "section 4"

- id: FM-10
  severity: MAJOR
  title: "The frozen decision_rule cannot name a primary contrast, and no gate constrains contrast selection"
  evidence: "plugins/humblepowers/skills/experiment-rigor/templates/schema.json field_shapes.decision_rule = ['metric','comparison','threshold','direction'] (one contrast); validate.py contains no read of `decision_rule`; validate.py:388-397 (one `verdict` per OUTCOME, never per contrast); validate.py:956-968 (the post-freeze quarantine fires on new OUTCOMES only)"
  detail: >-
    With four arms and two outcomes there are twelve pairwise comparisons and exactly two
    verdict slots, neither of which records which contrast produced it. ER-PREREG detects
    EDITS to `analysis_plan`, never VIOLATIONS of it, and choosing a different contrast on
    an already-frozen outcome adds no outcome, so the quarantine never fires. "The frozen
    decision_rule names which contrast is primary, so the added arm buys separation without
    licensing a hunt across contrasts" is unenforced prose about a schema slot that holds one
    unnamed comparison. The claim in Part B that "§5 may add nothing confirmatory afterwards
    ... which the pre-registration gate enforces mechanically" is true only for outcomes.
  smallest_fix: "Freeze explicit `analysis_plan.primary_contrast` and `analysis_plan.secondary_contrasts` keys, state that every other contrast is exploratory, and require §5's report to print the contrast beside each verdict."
  disconfirming_test: "grep validate.py for 'decision_rule' — if it is never read, the rule is documentation, not a gate."
  target_section: "Experiment design (Part B)"

- id: FM-11
  severity: MAJOR
  title: "The stage-1 freeze commit cannot pass the repointed record hooks; the choreography that says so is documented only where this wave deletes the pointer"
  evidence: "git commit ed3c5a0 message: 'The record-level validate hook is skipped once here by design: plan_frozen_at.commit is PENDING until this commit's own SHA exists (the freeze bootstrap documented in FREEZE.md)'; validate.py:753-757 (absent/PENDING commit -> ER-ANCHOR FAIL at measurement tier); templates/measurement.yaml:1-5 (same warning); docs/specs/2026-07-25-experiment-discipline-wave.md:59-61 ('Every other hook runs')"
  detail: >-
    §4 mandates "exactly the two-stage choreography the dogfood example uses". That
    choreography required a one-commit SKIP of the experiment-rigor-validate hook, because
    the record cannot name its own SHA. The spec's Gate commands enumerate the skipped hooks
    (check-merge-conflict, check-added-large-files, check-json) and close "Every other hook
    runs" — so an implementer meets a red hook the spec says cannot happen. Two implementers
    diverge: one runs `SKIP=experiment-rigor-validate git commit`, the other opens a debugging
    session against a gate that is behaving correctly. Meanwhile §1's only instruction about
    FREEZE.md is to remove a dangling pointer to it, leaving the choreography undocumented.
  smallest_fix: "§4 states the one-commit skip explicitly (which hook, which commit, why, and that stage 2 restores the gate), and §1 relocates FREEZE.md's choreography text into the new plugin rather than only deleting the reference."
  blast_radius: "The named skip touches the repo's standing pre-commit contract; it must be scoped to one commit, not added to the standing skip list in Gate commands."
  disconfirming_test: "Author a measurement-tier record with `plan_frozen_at.commit: PENDING` and run `validate.py` on it — ER-ANCHOR fails, so the hook blocks the commit."
  target_section: "section 4"

- id: FM-12
  severity: MAJOR
  title: "The FREEZE.md fix is instance-scoped; the generator that re-emits the reference is untouched, and §1 relocates a fourth instance into the new plugin"
  evidence: "the live population is four, not one: examples/rg-2x2/finalize.py:7, finalize.py:189 (`fh.write('# re-run finalize.py to regenerate. See FREEZE.md for the choreography.\\n')` — it WRITES the reference into the regenerated record), examples/rg-2x2/record.yaml:3, and plugins/humblepowers/CHANGELOG.md:25; validate_plugins.py:162-170 resolves only `references/*.md` cited in SKILL.md and `${CLAUDE_PLUGIN_ROOT}` paths, so nothing gates any of them"
  detail: >-
    §1 names only finalize.py:7. Fixing that line leaves the generator at :189 re-emitting
    the dangling reference into record.yaml on every finalize, so the defect regenerates
    itself. Worse, CHANGELOG.md:25 is inside the 0.9.0/0.10.0 text the Settled decision
    RELOCATES verbatim into `plugins/experiment-discipline/CHANGELOG.md` as the 0.1.0 birth
    entry — the wave carries the dangling reference into the new plugin as its founding
    document. FREEZE.md is genuinely absent (added in ed3c5a0, deleted in 107a9a2), so the
    spec's claim is correct; its fix scope is not.
  smallest_fix: "§1's instruction reads 'sweep every FREEZE.md reference (finalize.py:7 and :189, record.yaml:3, and the relocated CHANGELOG text), generator first, and name what replaces the choreography doc'."
  consumed_input: "finalize.py:189 writes the header line consumed by examples/rg-2x2/record.yaml:3; render.py's drift gate compares parsed YAML only, so a stale comment passes --check silently."
  disconfirming_test: "`git grep -n 'FREEZE.md'` — four live hits, one of which is a writer."
  target_section: "section 1"

- id: FM-13
  severity: MAJOR
  title: "§3 grows the SKILL.md body with no word-budget bump; PR03 goes red on a gate the spec lists as green"
  evidence: "docs/specs/2026-07-25-experiment-discipline-wave.md:254 ('Add the emission rule to the `SKILL.md` body'); scripts/word_budget.py:68-82 (`check_budgets` fails a body over its baseline); the DoD at :396-398 attributes the bumps to '§1 for the path key and §2 for the body growth' only; §3's acceptance criterion names no budget step"
  detail: >-
    §2 bumps the baseline for its own growth. §3 then adds the emission rule to the same
    body and to three templates, and its acceptance criterion checks render.py, the ASCII
    ratchet, and SKILL.md content — never `word_budget.py`. `validate_plugins.py` calls
    `check_budgets` on every commit, so PR03 fails a gate the spec certified as accounted for.
  smallest_fix: "Add 'the word-budget baseline is bumped again in the same diff, naming what the emission rule displaces' to §3's acceptance criterion and to the DoD's generated-artifact list."
  blast_radius: "scripts/word_budget.json is shared global config read by validate_plugins.py in pre-commit AND CI; three separate PRs now edit the same key."
  consumed_input: "validate_plugins.py:179-181 reads `scripts/word_budget.json` and feeds it to `check_budgets(current_counts(ROOT), ...)`; the key is the full path `plugins/<plugin>/skills/<skill>/SKILL.md`."
  disconfirming_test: "Append the emission-rule paragraph to a scratch copy of SKILL.md and run `word_budget.body_word_count` against the §2-bumped baseline."
  target_section: "section 3"

- id: FM-14
  severity: MAJOR
  title: "The repointed validate hook can silently drop the detector's own gate, and no test catches it"
  evidence: ".pre-commit-config.yaml:65 (`files: ^(plugins/humblepowers/skills/experiment-rigor/examples/.*/record\\.yaml|evals/.*/record\\.yaml)$` — two alternatives); test_validate.py:769-771 asserts only the examples path plus a docs/design negative; test_validate.py:793 asserts `evals/some-exp/report.md` matches — but only for the RENDER-check hook"
  detail: >-
    §1 says to repoint "both hooks' `entry:` and `files:` regexes" without saying the
    `evals/.*/record\\.yaml` alternative must survive. A mechanical repoint that rewrites the
    regex to the new plugin path leaves `evals/experiments/act-hint/record.yaml` — the wave's
    own frozen pre-registration — outside the validator hook entirely. §1's acceptance
    criterion tests only that "staging the moved examples/rg-2x2/record.yaml triggers both
    repointed pre-commit hooks", which stays green. The render-check hook has a guard test;
    the validator hook does not.
  smallest_fix: "§1's acceptance criterion adds: 'and `evals/experiments/act-hint/record.yaml` matches BOTH repointed `files:` regexes', with the missing positive assertion added to test_validate.py's validate-hook test."
  blast_radius: ".pre-commit-config.yaml is repo-global; the two `files:` regexes are the only mechanism keeping gitignored docs/design records out of the gate (the FM-6/Q6 divergence documented at :62-64)."
  consumed_input: "pre-commit consumes the `files:` regex to select staged paths; test_validate.py::_record_hook parses the same YAML and re.search-es the regex, so the test is the only reader that can prove coverage."
  disconfirming_test: "`re.search(regex, 'evals/experiments/act-hint/record.yaml')` against the post-§1 regex."
  target_section: "section 1"

- id: FM-15
  severity: MAJOR
  title: "'The harness already composes exactly that' is false after the re-home: build_command emits ONE --plugin-dir and run_agent has no env parameter"
  evidence: "evals/harness/claude_runner.py:200-201 (`plugin_dir: str | None`) and :238-239 (single `cmd += ['--plugin-dir', str(plugin_dir)]`); every consumer resolves one plugin (grade_tasks.py:105, run_triggers.py:413, holdout_check.py:115); test_build_command.py:10 pins the single-flag shape; run_agent (claude_runner.py:258-272) exposes config_dir and cwd but no env, and builds env from `os.environ.copy()` at :288; README.md:35 shows the CLI DOES accept repeated --plugin-dir"
  detail: >-
    Before §1, hook and skill both lived in humblepowers and one --plugin-dir sufficed. §1
    puts the treatment (choosing-tools' UserPromptSubmit hook) in humblepowers and the
    measured skill in experiment-discipline — the detector now needs two plugin dirs and a
    per-spawn env var for the arm gate. The CLI supports the first; the harness supports
    neither. The Settled decision cites claude_runner.py:239 as proof the composition
    already exists, which is the "proven on the original caller's inputs" failure: it is
    proven for one plugin and no hook. No PR is assigned the harness change, and
    test_build_command.py pins the surface that must change.
  smallest_fix: "Add `evals/harness/claude_runner.py` (multi `--plugin-dir` + a per-spawn `env` parameter) and `evals/harness/test_build_command.py` to §4's file list and the concept->module map."
  blast_radius: "build_command is shared by run_triggers, grade_tasks, holdout_check, offer_probe, judge and smoke; widening plugin_dir to a sequence touches every caller and its tests."
  consumed_input: "test_build_command.py:10 consumes `build_command(plugin_dir='plugins/session-workflow', ...)` and asserts the emitted argv; grade_tasks.py:105 consumes `cfg['plugin_of_skill'][skill]` to build the single path."
  disconfirming_test: "Read build_command's signature: if plugin_dir is `str | None`, two plugins cannot be passed without a change."
  target_section: "section 4"

- id: FM-16
  severity: MAJOR
  title: "No in-repo run has ever demonstrated a plugin hook firing inside a spawn, and the isolated config is explicitly settings-free"
  evidence: "evals/harness/claude_runner.py:63-64 (`make_isolated_config`: 'a temp CLAUDE_CONFIG_DIR that is authenticated and nothing else'); the only harness mention of hooks anywhere is validate_plugins' STATIC hooks.json shape tests (test_validate_plugins.py:57-149) — no runtime path; plugins/humblepowers/hooks/hooks.json invokes `${CLAUDE_PLUGIN_ROOT}/.../inject_dispatch.py --prompt-submit`"
  detail: >-
    Whether `claude -p --plugin-dir X` under a credentials-only CLAUDE_CONFIG_DIR registers
    and runs X's UserPromptSubmit hook is the single load-bearing assumption of the whole
    experiment, and the repo contains no evidence for it. If the hook does not fire, all
    four arms are byte-identical spawns, every gate in §4 and §5 still passes, and the
    record reports a null the design never controlled. This is the feasibility check that
    should short-circuit the round, and it is unrun. The dry-run gate as specified ("prints
    the plan and the projected cost without spending") cannot detect it.
  smallest_fix: "§4's acceptance criterion adds a single real probe spawn — one prompt, treatment arm, assert the `<toolkit-dispatch>` block appears in the transcript — as a hard precondition before any of the 168 runs is authorized."
  disconfirming_test: "One spawn: `run_agent` with both plugin dirs, the env gate set, a matching prompt, and a grep of the transcript for `<toolkit-dispatch>`. Costs ~$0.10 and settles the entire design."
  target_section: "section 4"

- id: FM-17
  severity: MAJOR
  title: "The byte-identity test depends on git history CI does not fetch — and the existing acceptance suite already does"
  evidence: "docs/specs/2026-07-25-experiment-discipline-wave.md:216-217 (`git show 113cc06:plugins/humblepowers/skills/experiment-rigor/SKILL.md`); .github/workflows/validate.yml:13 `uses: actions/checkout@v7` with no `fetch-depth` (default 1) and :30 `run: python scripts/run_tests.py`; test_acceptance_rg2x2.py:154-156 already asserts `git show <freeze-sha>` succeeds with 'freeze history unavailable (fail loud, no skip)'; validate.py:760-762 FAILs ER-ANCHOR when the commit is absent from history"
  detail: >-
    The wave's headline invariant — description-stability under re-home — gets exactly one
    enforcement mechanism, and it is a `git show` against a SHA on a branch that has never
    been opened as a PR. In a depth-1 CI checkout the object is absent and the test goes red
    (or, worse, is written to skip and becomes vacuous). The same shallow clone already
    breaks test_acceptance_rg2x2.py and degrades ER-ANCHOR/ER-PREREG for the committed
    rg-2x2 record. Because this branch has never run CI, the whole "gate suite is green"
    claim in Gate commands and the DoD is local-only.
  smallest_fix: "§1 adds `fetch-depth: 0` to `.github/workflows/validate.yml` (and lists the file), or the byte-identity test compares against a committed frozen blob (`tests/fixtures/premove-description.txt`) instead of a SHA."
  blast_radius: "fetch-depth: 0 changes checkout cost for every CI job in validate.yml and currency.yml; the SHA 113cc06 also disappears if this branch is squash-merged, which the CHANGELOG rollback implies."
  consumed_input: "`scripts/run_tests.py` (SEARCH_DIRS = ('plugins','evals'), :24) collects every `test_*.py`, so the new test runs in the CI job at validate.yml:30; the git object it consumes is supplied by the checkout step's fetch depth."
  disconfirming_test: "`git clone --depth 1` this branch into a temp dir and run `git show 113cc06:...` plus `scripts/run_tests.py`."
  target_section: "section 1"

- id: FM-18
  severity: MAJOR
  title: "The cost anchor mixes an incompatible run profile and budgets a judge the design says does not exist"
  evidence: "evals/trigger/holdout/BASELINES.md:18 ($2.67, 27 runs — a TRIGGER-arm run); evals/config.json (`trigger_max_turns: 3`, `allowed_tools_trigger: 'Skill,Read,Glob,Grep'`, `disallowed_tools_trigger` blocks all writes) vs `max_turns: 8`; docs/specs/2026-07-25-experiment-discipline-wave.md:182-184 ('roughly $2-3 of judging') vs :436-439 ('the oracle is a deterministic regex frozen by hash') and templates/measurement.yaml judge_bias 'deterministic regex verifier, no LLM judge'"
  detail: >-
    The $0.099/run anchor comes from read-only 3-turn trigger spawns; the detector needs
    task-shaped spawns. Scaling by turn cap alone is the wrong dimension. Separately, the
    estimate carries a judging line item that the design's own construct denies — either an
    LLM judge is in the loop (and `judge_bias` cannot be recorded as controlled) or the
    ceiling is padded with a phantom. And with no `run.ledger_path` producer in this repo,
    ER-XCHECK degrades to a measurement-tier WARN (validate.py:807-818), so the $60 ceiling
    and the n=168 claim get no mechanical cross-check at all.
  smallest_fix: "State whether verify.py alone scores the runs (drop the judging line and record `judge_bias: controlled`) or a judge is used (record it residual), and declare `run.source: hand` with a `hand_reason` in the frozen record so ER-XCHECK's WARN is a stated posture rather than an accident."
  disconfirming_test: "Run `run_arms.py --dry-run` cost math against `evals/config.json`'s task-arm settings rather than the trigger settings and compare to the $27-54 band."
  target_section: "Settled decisions (bound)"

- id: FM-19
  severity: MAJOR
  title: "PT-BR is not a held-constant block — it is an uncalibrated arm of the instrument with a differently-rendered treatment"
  evidence: "plugins/humblepowers/skills/choosing-tools/scripts/test_router.py:201-216 (a sealed test asserting 'the router is monolingual-English and degrades to silence' on PT prompts); evals/trigger/holdout/BASELINES.md:19 ('PT-BR arm still needs its own labeled dev set before any PT tuning'); router.py:29-31 and :70 (`hint_line` pushes matched words through `_ascii`, so a PT-BR match is injected with '?' substitutions an EN match never carries); scripts/ascii_runtime_lint.py SCAN_DIRS includes 'evals' and holds files absent from the baseline at zero"
  detail: >-
    The shipped router is monolingual English by design AND by sealed test. The detector's
    PT-BR patterns are brand new with zero dev evidence, so injection rate almost certainly
    differs by block — language modifies TREATMENT DELIVERY, which is the definition of a
    confound, not a held-constant block. Worse, when a PT-BR row does match, the injected
    text is degraded to '?'-substituted ASCII, so the two blocks receive materially
    different treatments. And `evals/experiments/act-hint/verify.py` will need accented
    PT-BR regexes: the ASCII ratchet flags non-ASCII runtime string literals and holds new
    files at zero, forcing either `\\u` escapes or a `# ascii-ok` suppression the spec never
    anticipates (§3 reasons about this ratchet for render.py and §4 is silent).
  smallest_fix: "Either drop PT-BR from v1 of the bank, or declare language a factor level in `design.cells` (8 cells, not 4) with its own denominators and a `custom_language_delivery` threat row naming the _ascii rendering difference."
  disconfirming_test: "Route the draft PT-BR bank prompts through each candidate rules file and compare match counts to the EN half; and run `ascii_runtime_lint.py` over a scratch verify.py carrying one accented regex."
  target_section: "section 4"

- id: FM-20
  severity: MAJOR
  title: "§5's report cannot be render.py-derived, and the drift gate would not notice if it were hand-written"
  evidence: "plugins/humblepowers/skills/experiment-rigor/scripts/render.py:99-167 (`render_report` emits a fixed skeleton: design, disposition, outcome lines, per-arm rate lines via `_rate_line`, a threat count, a one-line update, and the canonical YAML block); :193-210 (`check_drift` compares a sha256 over the PARSED embedded YAML only)"
  detail: >-
    §5's acceptance criterion requires the report to state achieved precision, name which
    arms moved rigor_disposition, report the wide - inert contrast, and carry the
    descriptive turn/token tax and GRADE downgrade reasons. `render_report` prints none of
    these and has no free-prose slot; no section is assigned to extend it (the concept->module
    map gives render.py only §3's activation-line generator). And because the drift gate is
    semantic over the YAML block, hand-added prose passes `--check` while violating the
    "derived, never hand-edited" invariant the DoD asserts — so the wave's flagship record
    would be enforced by a gate that cannot see the violation. §5 also requires the activation
    line to OPEN the report, which is another render_report change §3 does not cover.
  smallest_fix: "§5 names the `render_report` extension (contrast lines, achieved precision, descriptive secondaries, the leading activation line) with its test, or moves those statements into typed record fields the existing renderer already prints."
  consumed_input: "render.py:174 `_embedded_blocks` consumes only ```yaml fences; prose outside a fence never reaches the digest `check_drift` compares."
  disconfirming_test: "Run `render.py --stdout` on the rg-2x2 record and look for any contrast, precision, or free-prose line; then append a paragraph to report.md and re-run `--check`."
  target_section: "section 5"

- id: FM-21
  severity: MINOR
  title: "§2's tier-0 rubric item is vacuous on the only task in the bank"
  evidence: "evals/tasks/experiment-rigor/tasks.json holds ONE task (`er-measurement-record`) whose prompt mandates producing a record.yaml; evals/harness/grade_tasks.py:117-131 (`resolve_task_rubric` supports inline and per-task rubrics); evals/config.json gates.correct_usage = 0.7"
  detail: >-
    The enforcement table lists the tier-0 rung as review-only, enforced by "correct-usage
    rubric". Adding an item to the SHARED rubric.json asserting "the five elements are
    present in a response that opens no record" can only score false against the single
    record-producing task — a rubric row that measures nothing about the rung and slightly
    depresses the weighted score. The mechanism for a differently-shaped task already exists
    and §2 does not use it.
  smallest_fix: "§2 adds a tier-0 TASK to `evals/tasks/experiment-rigor/tasks.json` plus `rubric.er-tier0-check.json`, rather than one item on the shared rubric."
  disconfirming_test: "Score the existing er-measurement-record transcript against the proposed tier-0 item — it fails by construction."
  target_section: "section 2"

- id: FM-22
  severity: MINOR
  title: "The BASELINES precedent cite points at the wrong row, and the re-home orphans that row's provenance anchor"
  evidence: "evals/trigger/holdout/BASELINES.md:18 is the experiment-rigor row and carries NO byte-identical note; the precedent lives at :14-:17 (compaction-survival / toolkit-awareness / choosing-tools / python-engineering), each a fresh RUN recorded with the note; :18's 'description measured' cell reads 'humblepowers 0.9.0', the version §1 deletes"
  detail: >-
    Two problems. The cited precedent is not at the cited line, and the real precedent rows
    are new measured runs annotated 'description byte-identical', not annotations added to a
    prior row without a run — so it licenses less than the spec claims. And after §1 rolls
    humblepowers back to 0.8.0 and relocates 0.9.0/0.10.0, the seal's own provenance pointer
    ('humblepowers 0.9.0') names a version that exists in no CHANGELOG, breaking the audit
    trail the no-reseal argument rests on.
  smallest_fix: "Cite BASELINES.md:14 as the note precedent, and have §1's edit re-anchor :18's 'description measured' cell to a surviving coordinate (the commit SHA plus experiment-discipline 0.1.0)."
  disconfirming_test: "Read BASELINES.md:18 and look for a byte-identical note; then grep the post-§1 CHANGELOGs for 'humblepowers 0.9.0'."
  target_section: "Settled decisions (bound)"

- id: FM-23
  severity: MINOR
  title: "Adding a rule row can DISPLACE an existing candidate, so treated arms differ from control by a removed hint too"
  evidence: "plugins/humblepowers/skills/choosing-tools/scripts/router.py:58-59 (`matches.sort(key=lambda m: -m['hits']); return matches[: rules.get('max_candidates', 2)]`); router_rules.json `max_candidates: 2` with rows for test-driven-development and systematic-debugging that the decoys ('run the tests', 'check whether it passes') are drawn to match"
  detail: >-
    On a prompt that already matches two rows, adding the evaluation-act row can push one
    out. So narrow/wide/inert differ from control not only by an added hint but by a removed
    one — an uncontrolled second manipulation on exactly the decoys the habituation story
    depends on. wide - inert is clean (identical patterns); narrow - control and
    inert - control are not.
  smallest_fix: "Record, per bank prompt, the candidate list each arm's rules produce, and name displacement in `prompt_format_sensitivity` (or a `custom_candidate_displacement` row)."
  disconfirming_test: "Route each decoy through control and wide rules and diff the returned id lists."
  target_section: "section 4"

- id: FM-24
  severity: MINOR
  title: "§4's acceptance criterion asserts a reconciliation the validator cannot perform at freeze"
  evidence: "plugins/humblepowers/skills/experiment-rigor/scripts/validate.py:437-485 (`check_recon` compares N_expected to `disposition.total` only when disposition is present, and to arm denominators only when `results` exists); docs/specs/2026-07-25-experiment-discipline-wave.md:318-321 ('exits 0 ... with the plan frozen and results absent, reconciling 4 cells x 42 = 168 against the disposition total and each outcome's arm denominators')"
  detail: >-
    On a results-absent record the arm-denominator half of the reconciliation is a no-op:
    `planned_n` could sum to 160 and the gate still exits 0. The criterion as written reads
    as a check the run has passed when it has only passed half of it — a vacuous gate at
    exactly the moment the freeze is supposed to be airtight.
  smallest_fix: "Reword §4's criterion to 'sum(design.cells.planned_n) == disposition.total == 168' and move the arm-denominator reconciliation into §5's criterion."
  disconfirming_test: "Author a freeze record with planned_n summing to 160 and disposition.total 160 and run validate.py — it exits 0 and the 168 claim is never checked."
  target_section: "section 4"

- id: FM-25
  severity: MINOR
  title: "Post-§1 Reuse pointers and cites name paths §1 deletes"
  evidence: "docs/specs/2026-07-25-experiment-discipline-wave.md:317 (§4 Reuse: `plugins/humblepowers/skills/experiment-rigor/templates/measurement.yaml`), :346 (§5 Reuse: `plugins/humblepowers/.../examples/rg-2x2/finalize.py::finalize_record`), :274 (§3's acceptance cites the RG-2x2 record), :21-22 (Context cite); §1's own acceptance criterion requires no path under plugins/humblepowers/ to match experiment-rigor"
  detail: >-
    PR04 and PR05 run after PR01, so every one of these Reuse pointers resolves to nothing at
    the moment the implementing agent reads it. The dependency notes make the ordering
    explicit, which makes the stale pointers a certainty rather than a risk.
  smallest_fix: "Rewrite all post-§1 pointers to `plugins/experiment-discipline/skills/experiment-rigor/...` and mark the Context cite as pre-move."
  consumed_input: "The implementing agent consumes the Reuse path literally; §1's `git mv` is what invalidates it."
  disconfirming_test: "After PR01, `test -f plugins/humblepowers/skills/experiment-rigor/templates/measurement.yaml`."
  target_section: "sections 4 and 5"
```

## Cleared

Claims I checked and found correct — recorded so they are not re-litigated.

```yaml
cleared:
  - claim: "Router cross-plugin naming is supported; the sealed router budgets cannot regress from an id-prefix edit"
    cite: "test_router.py:59 ('id must be plugin:skill'), :45 (`skill_id.split(':', 1)[1] + '.json'`); evals/trigger/experiment-rigor.json exists; a census of dispatch-router-recall.json's `expected` ids returns 8 skills and ZERO experiment-rigor cases, so the sealed recall floors at test_router.py:176-198 are untouched by the prefix change"
  - claim: "The re-homed tests are discovered at the new path without change"
    cite: "scripts/run_tests.py:24 SEARCH_DIRS = ('plugins', 'evals') with :28 rglob('test_*.py')"
  - claim: "validate_plugins enforces marketplace/plugin.json description equality"
    cite: "scripts/validate_plugins.py:76-79"
  - claim: "render.py is absent from the ASCII baseline and is therefore held at zero; format (a) is pure ASCII"
    cite: "scripts/ascii_lint_baseline.json (16 keys, no experiment-rigor path); scripts/ascii_runtime_lint.py:43 BASELINE_NAME"
  - claim: "word_budget.json:8 keys `.../experiment-rigor/SKILL.md` at 827, and a new key is REQUIRED not optional"
    cite: "scripts/word_budget.json:8; scripts/word_budget.py:74-76 ('no word-budget baseline — add one')"
  - claim: "The $2.67 / 27-run cost anchor and the 0.33 paraphrase recall are exact"
    cite: "evals/trigger/holdout/BASELINES.md:18 (5+/4- x 3 repeats = 27, 1 error run, $2.67, recall 0.33 [0.15, 0.58], specificity 1.00)"
  - claim: "The router's register gradient (direct 0.94 / paraphrase 0.12) is exact"
    cite: "evals/trigger/holdout/BASELINES.md:19"
  - claim: "The FREEZE.md reference is genuinely dangling"
    cite: "FREEZE.md added in ed3c5a0, deleted in 107a9a2; absent from the working tree"
  - claim: "The founding RG-2x2 reports its confirmatory `activation` outcome at 0/48 in both arms, and declares token_length_confound residual and possibly fatal"
    cite: "examples/rg-2x2/record.yaml:112-132 and :91-95"
  - claim: "Both pre-commit record hooks currently name the old location in entry: AND files:"
    cite: ".pre-commit-config.yaml:60, :65, :69, :77 (4 hits)"
  - claim: "AGENTS.md discovers the new plugin automatically — no allowlist to edit"
    cite: "scripts/gen_agents_md.py:91 `(plugin_dir / 'skills').glob('*/SKILL.md')` over `plugins/*`"
  - claim: "The closed threat enum is exactly nine keys, matching 'the nine core threats each carry a row'"
    cite: "validate.py:108-118"
```

## Prose

**The re-home (§1) is the sound part of this wave, and it is nearly right.** The
consumer list is close to complete — I swept the tracked population
(`git grep -l 'humblepowers/skills/experiment-rigor'`) and found one unlisted
consumer, `test_validate.py:769,790`, which hardcodes the old path but is caught by
`run_tests.py`. The router-id argument is verified rather than assumed, the sealed
holdouts genuinely contain no experiment-rigor cases, and the gate cites are exact.
What §1 gets wrong is scope, not direction: the FREEZE.md fix is instance-scoped
past its own generator (FM-12), the hook regex can be narrowed in a way no test
catches (FM-14), and the one enforcement mechanism for the wave's headline
invariant depends on git history CI does not fetch (FM-17).

**§4 and §5 are where this fails.** I ran the feasibility check first, as the
method requires, and it does not clear. The study's independent variable is a hint
injected by a `UserPromptSubmit` hook, and four separate things stand between that
hook and the measured response, none of them established:

1. Nothing in this repo has ever demonstrated a plugin hook firing inside a
   `claude -p --plugin-dir` spawn under a credentials-only config (FM-16). If it
   does not fire, all four arms are identical and every gate still passes.
2. The harness cannot compose the two plugins the re-home creates, and has no
   per-spawn env plumbing for the arm gate (FM-15).
3. There is no code path that points the hook at an alternate rules file, and
   building one edits humblepowers, which the spec's version and CHANGELOG
   mechanics forbid (FM-4).
4. The rule schema has no hint-text field, so the inert arm — the one thing
   separating this study from the founding case's declared near-fatal confound —
   cannot be built as specified, and its ±10% length match is not a property of any
   file the test could read (FM-3).

Even granting all four, the measurement does not measure its construct. The two
confirmatory outcomes are single accuracy rates over genuine and decoy items
pooled, so the sensitivity gain and the habituation loss — the two quantities the
wave exists to weigh against each other — cancel inside one number, and the decoy
half of `skeleton_completeness` is a near-constant that dilutes any effect by
roughly 43% (FM-5). The outcomes are lexical surfaces scored by a regex, and the
treatment is text; an arm that supplies the oracle's vocabulary moves the score
without moving behavior, and the inert arm controls length but not that (FM-8).
`token_length_confound` is declared controlled while narrow — the row that would
actually ship — is exactly as confounded as the RG-2×2 was (FM-9). And the
"frozen decision_rule licenses only the named primary contrast" claim rests on a
schema slot holding one unnamed comparison, with twelve available contrasts, two
verdict slots, and no gate that reads the rule at all (FM-10).

Finally, the arithmetic. The `±0.15` precision figure is the independent-trials
number for a design whose own stated unit of analysis is the prompt cluster
(FM-7), and the validator will mechanically *force* that anti-conservative
interval into the record because ER-STATS recomputes each arm's CI from the raw
42 (FM-6). So the record's stated precision will be both wrong and gate-enforced —
which is the specific failure mode this discipline was built to prevent, appearing
in the first study it governs.

Two structural notes for the fold. First, several fixes are cheap and mechanical
(FM-13, FM-14, FM-21, FM-22, FM-24, FM-25) and can be folded without re-grounding.
The experiment findings cannot: FM-3, FM-4, FM-15 and FM-16 together decide
whether §4/§5 are buildable at all, and the right next step is the ~$0.10 probe in
FM-16's `disconfirming_test` before another word is written about arms. Second,
if that probe fails, the honest move is to split the wave: §1–§3 are a coherent,
well-grounded, low-risk series that stands on its own, and the detector becomes
its own spec with the hook-firing question answered first.

Unverified-offline: 5

PREMORTEM-VERDICT: NEEDS-REVISION — fresh non-author subagent (opus), round 1, keel kit 0.13.0
