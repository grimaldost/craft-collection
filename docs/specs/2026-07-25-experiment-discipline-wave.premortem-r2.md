# Pre-mortem (round 2) — the experiment-discipline wave

- **Spec:** `docs/specs/2026-07-25-experiment-discipline-wave.md`
- **Date:** 2026-07-25
- **Reviewer:** fresh non-author subagent (opus), round 2
- **Spec-hash:** `968b79cf1b195c58ff5dcee58675b0b72305086005b211410437f7643e3e8084`
- **Reviewed against:** worktree `C:/Users/grima/Documents/craft-collection-rigor`, branch
  `feat/experiment-rigor-skill` @ `113cc06` (working tree clean apart from the three
  untracked wave documents); `docs/adr/0008-experiment-discipline-plugin.md` read; the
  round-1 pre-mortem (FM-1..FM-25) read as the prior verdict record; keel kit 0.13.0
- **Prior round:** `docs/specs/2026-07-25-experiment-discipline-wave.premortem.md`
  (NEEDS-REVISION, 5 BLOCKER / 15 MAJOR / 5 MINOR)

The fold is good work. Every one of the 36 fold-ledger rows resolves to the exact line
it cites, and all 21 load-bearing code cites in the spec body resolve at the exact
line and string. The firing/effect decomposition genuinely dissolves round 1's
BLOCKERs rather than papering over them: with the paid run injecting text directly on
stdin, FM-3, FM-4, FM-15 and FM-16 stop being risks and become non-goals.

The failure I judge most likely now is not in the detector at all. It is in §1 — the
part round 1 called "the sound part of this wave". The `git mv` moves the RG-2×2
record away from the path its own freeze commit knows, and `git show <sha>:<path>`
does not follow renames. I ran the move in a scratch clone: the suite goes from 46/46
to 44/46, and `validate.py` on the chain-root record silently drops ER-PREREG from a
real reconstruction to a WARN. §1's acceptance criterion asserts the opposite.

---

## Resolution audit (round-1 findings against the current text)

| Finding | Status | Current-text evidence |
|---|---|---|
| FM-1 bank register | RESOLVED | spec:371 `direct-register phrasings the arms can actually match`; 12/12 split at :368; Part B's feasibility grounding revises the bank pre-freeze |
| FM-2 hook length floor | RESOLVED | spec:193-194 reproduces `inject_dispatch.py:52` `MIN_WORDS = 4` + companion char floor + slash skip (cite verified exact) |
| FM-3 inert arm unbuildable | RESOLVED by construction | spec:204-206 — arm files are offline generator inputs; the run injects text directly |
| FM-4 forbidden humblepowers edits | RESOLVED | Non-goals :78 `No edit to inject_dispatch.py or router.py at all` |
| FM-5 netted outcomes | **PARTIALLY-RESOLVED** | cells are now arm × prompt_class (:391) so the split is confirmatory-legal, but the pre-named **primary** contrast is still pooled `rigor_disposition` over all 24 clusters (:510, :519). Defensible as the stated "deployable-package question"; see R2-3 for the mechanical consequence |
| FM-6 forced Wilson | RESOLVED | :344 per-arm Wilson `demoted to` descriptive; contrasts carry inference. New gap at R2-5 |
| FM-7 wrong-unit MEWD | RESOLVED | :517 `inferential unit is 24 clusters`, ±0.15 pooled / ±0.20 within class |
| FM-8 oracle primeability | RESOLVED | :387-390 frozen wording constraint asserted by a test over the frozen texts |
| FM-9 per-contrast threat | RESOLVED | :402-405 residual, controlled for `wide − inert` only, `narrow − control` explicitly re-inherits |
| FM-10 contrast selection | RESOLVED | :510 one primary pre-named in the frozen decision rule; `check_prereg` freezes `analysis_plan` minus amendments (validate.py:928) |
| FM-11 freeze hook skip | RESOLVED | Gate commands :67 `One scoped, one-commit exception` |
| FM-12 FREEZE.md sweep | RESOLVED | all four sites named, generator first; `git grep -n FREEZE.md` returns exactly those four |
| FM-13 §3 word budget | RESOLVED | :309 `bump the word-budget baseline again`; DoD :496-498 names the three-PR order |
| FM-14 hook regex guards | RESOLVED | :237 `preserving the evals/.*/record.yaml alternative`; :266-268 guards both regexes |
| FM-15 harness composition | RESOLVED | Non-goals :82-86; `claude_runner.py:296 input=prompt` and `:202 plugin_dir: str \| None` verified exact |
| FM-16 hook-in-spawn | RESOLVED | Context :31 named precondition; ADR-0008:116-124 |
| FM-17 CI fetch depth | **PARTIALLY-RESOLVED** | `fetch-depth: 0` is right and needed (`validate.yml:13` has no fetch-depth). But the fold promoted FM-17's *disconfirming test* into an acceptance criterion with its sense inverted — see R2-2 |
| FM-18 cost anchor / phantom judge | RESOLVED | :212 `lower bound on a different profile`; no judging line item; `run.source: hand` + `hand_reason` |
| FM-19 PT-BR | RESOLVED | :406-409 `custom_language_delivery` residual, ASCII-safe oracle data, EN-restriction fallback taken from the outcome-free table |
| FM-20 render_report extension | RESOLVED (residual at R2-7) | :435-439 names the extension, its lines, and why the drift gate cannot see prose |
| FM-21 tier-0 task | RESOLVED | :295-299 dedicated task + its own rubric |
| FM-22 BASELINES | RESOLVED | :176 provenance re-anchor; `BASELINES.md:14` verified as a byte-identical-annotated row, `:18` verified as the experiment-rigor row reading `humblepowers 0.9.0` |
| FM-23 candidate displacement | RESOLVED | :405 `custom_candidate_displacement` + per-arm candidate lists in the table |
| FM-24 vacuous freeze recon | RESOLVED in wording (new side effect at R2-4) | :417 `is a no-op until results exist` |
| FM-25 stale reuse pointers | RESOLVED | :333, :412, :447 all marked `pre-move coordinate` with the post-§1 home |

No round-1 finding is UNRESOLVED. Two are PARTIALLY-RESOLVED and both partials are
carried below as their own rows rather than re-litigated.

---

## Findings

```yaml
- id: R2-1
  severity: BLOCKER
  title: "§1's `git mv` breaks the RG-2x2 freeze reconstruction: `git show <sha>:<path>` does not follow renames, so run_tests.py goes red and ER-PREREG silently degrades to a WARN"
  evidence: >-
    OBSERVED, not reasoned. Cloned the worktree to a scratch dir, ran
    `git mv plugins/humblepowers/skills/experiment-rigor
    plugins/experiment-discipline/skills/experiment-rigor` and nothing else:
    `scripts/run_tests.py` went 46/46 -> 44/46 with
    `plugins/experiment-discipline/.../test_acceptance_rg2x2.py` FAIL:
    "git show ed3c5a0e02f4b1fe5d60047e1bc43b88a91be4b2:plugins/experiment-discipline/skills/experiment-rigor/examples/rg-2x2/record.yaml
    failed -- freeze history unavailable (fail loud, no skip)" (module exit 1);
    and `validate.py ../examples/rg-2x2/record.yaml` went from 1 WARN to 2, the new one
    "WARN [ER-PREREG]: record not in history at ed3c5a0...:plugins/experiment-discipline/...;
    cannot reconstruct pre-registration". Sources:
    plugins/humblepowers/skills/experiment-rigor/scripts/validate.py:313 (`_show_at` runs
    `git show <commit>:<relpath>`), :911 (`relpath = _repo_relpath(cwd, record_path)` — the
    record's CURRENT path), :894-897 (`downgrade()` makes it a measurement-tier WARN);
    test_acceptance_rg2x2.py:152-157 (the same reconstruction, asserted "fail loud, no skip").
    Direct confirmation: `git show ed3c5a0:plugins/experiment-discipline/.../record.yaml`
    -> "fatal: path ... does not exist in 'ed3c5a0'".
  detail: >-
    The freeze commit ed3c5a0 stores the record at the humblepowers path. After the move,
    every consumer that reconstructs the frozen pre-registration asks git for the NEW path
    at the OLD commit, which git answers fatally. Two consequences, both contradicting the
    spec. (a) §1's acceptance criterion — "with no other change the full gate suite exits 0
    (... run_tests.py)" — is empirically false, and so is the DoD's "the full gate suite is
    green at the new paths". (b) The Enforcement status table claims the v1 record gates
    including ER-PREREG are "enforced | validate.py pre-commit hook, repointed in §1"; after
    the move ER-PREREG stops reconstructing anything on the one record that dogfoods it and
    degrades to the WARN branch the module's own docstring calls out as the failure it was
    hardened against ("a gate quietly ceasing to check, against the loud-failing thesis",
    validate.py:294). Neither remedy §1 already carries touches this: `fetch-depth: 0` and
    the keep-ref tag make the freeze OBJECT reachable, and the object is already reachable —
    the PATH is what moved. The obvious escape is closed too: re-anchoring the record to a
    fresh post-move freeze commit fails ER-ANCHOR, because a commit dated 2026-07-25 postdates
    the record's `run.first_run_at: 2026-07-24 12:00:00+00:00` (validate.py:765-772).
  smallest_fix: "§1 adds the rename-survival step: `plan_frozen_at` gains an optional `path` (the record's repo-relative path AT the freeze commit), `check_prereg` and `test_acceptance_rg2x2.py` reconstruct via `git show <commit>:<plan_frozen_at.path or current relpath>`, and §1 sets it to the pre-move path for the RG-2x2 record — with `validate.py`, `test_acceptance_rg2x2.py`, `templates/schema.json` and `templates/SCHEMA.md` added to §1's file list and the concept->module map."
  blast_radius: "The fix opens templates/schema.json + the regenerated SCHEMA.md in PR01, which §4 also edits for the v1.1 contrasts extension — two PRs now touch the same shared schema pair, in the order PR01 then PR04; SCHEMA.md's sync gate must be re-run in both."
  consumed_input: "test_acceptance_rg2x2.py:150-152 consumes `validate._repo_toplevel` / `validate._repo_relpath` over `DELIVERED_RECORD` (a path derived from `Path(__file__).resolve().parent`), and validate.py:916 consumes `_show_at(cwd, commit, relpath)`; both read the record's post-move location, verified by reading those call sites and by executing the move."
  disconfirming_test: "In a scratch clone, `git mv` the skill tree and run `python scripts/run_tests.py` plus `python validate.py ../examples/rg-2x2/record.yaml` — if the suite stays 46/46 and the validator still shows exactly one WARN, this mode is dead."
  target_section: "section 1"

- id: R2-2
  severity: MAJOR
  title: "§1's acceptance criterion and the DoD require a depth-1 clone to run run_tests.py green — unachievable by construction, and satisfiable only by making the freeze-durability gate vacuous"
  evidence: >-
    docs/specs/2026-07-25-experiment-discipline-wave.md:269-270 ("the keep-ref tag for
    `ed3c5a0` resolves and a depth-1 clone runs `run_tests.py` green") and :482-483 ("green on
    a depth-1 clone (the keep-ref tags and `fetch-depth: 0` make the freeze objects
    reachable)"); test_acceptance_rg2x2.py:154-157 asserts the reconstruction and states
    "fail loud, no skip" for exactly the shallow-clone case; validate.py:761-762 FAILs
    ER-ANCHOR when the commit is absent from history.
  detail: >-
    `git clone --depth 1` fetches the tip commit only; a lightweight tag on an ancestor is
    not fetched with it, so ed3c5a0 is absent and both the acceptance test and ER-ANCHOR go
    red. The parenthetical refutes the claim it is attached to: `fetch-depth: 0` exists in
    the same sentence *because* depth-1 does not work. This reads as a fold artifact —
    FM-17's `disconfirming_test` ("`git clone --depth 1` this branch ... and run
    `scripts/run_tests.py`") was promoted into an acceptance criterion with its sense
    inverted. An implementer has three moves: stall on an unsatisfiable criterion, or write a
    shallow-clone skip into test_acceptance_rg2x2.py — which voids the only enforcement of
    the freeze-durability invariant the spec introduces, and is precisely the standing
    deletion rule's target — or silently reinterpret. Two of the three are bad outcomes.
  smallest_fix: "Replace both clauses with: '`run_tests.py` is green on a full-depth checkout, which is what `fetch-depth: 0` guarantees; the keep-ref tag preserves the freeze commit across a squash-merge. A depth-1 clone is expected to fail the freeze reconstruction, and no skip may be added to make it pass.'"
  disconfirming_test: "`git clone --depth 1` this branch into a temp dir and run `scripts/run_tests.py`; if it is green, the criterion is achievable as written."
  target_section: "section 1 + Definition of Done"

- id: R2-3
  severity: MAJOR
  title: "§5's genuine-scoped secondary outcome fails ER-RECON if it carries per-arm rates, and §4/§6 both say it will"
  evidence: >-
    OBSERVED: ran `validate.check_recon` over a synthetic 8-cell/192 detector record.
    With `skeleton_wellformedness` carrying four arms at denominator 24 (the genuine cells):
    "FAIL ER-RECON: outcome 'skeleton_wellformedness': sum of arm denominators 96 !=
    N_expected 192". With the same outcome carrying `contrasts` and no `arms` block: CLEAN.
    Source: validate.py:472-484 (every outcome's arm denominators must sum to
    `sum(design.cells[].planned_n)`). Spec text: :393-397 (`a secondary scoped to the genuine
    cells`, `carried through §4's contrasts[] machinery`) vs :343 ("Per-arm Wilson stays") and
    :429-430 (finalize fills "the per-arm descriptive Wilson intervals").
  detail: >-
    This is round-1 FM-5's reconciliation constraint resurfacing on the fold's own new
    outcome. §6's acceptance criterion explicitly requires "the arm-denominator
    reconciliation now checked", so the collision is not hypothetical — it is the criterion.
    The spec never states that `skeleton_wellformedness` carries no `arms` block; two other
    passages imply it does. Two implementers diverge: one writes contrasts-only and passes,
    the other writes per-arm Wilson over the genuine cells and meets a red gate AFTER the
    $25-60 run is spent, whose only repairs are to delete the arms block or to widen the
    outcome back to all 192 — which re-imports exactly the dilution FM-5 named.
  smallest_fix: "§5 adds: 'the genuine-scoped secondary is reported through `clusters` + `contrasts[]` only and carries NO `arms` block, because ER-RECON requires every outcome''s arm denominators to sum to N (validate.py:472-484)' — and §4's 'per-arm Wilson stays' is qualified to outcomes scored over the full cell set."
  consumed_input: "validate.check_recon consumes `results.<outcome>.arms.*.denominator` and `design.cells[].planned_n`; verified by reading validate.py:437-485 and by executing check_recon on both record shapes."
  disconfirming_test: "Run `validate.check_recon` on a record with 8 cells of 24 and a second outcome whose four arms carry denominator 24 — if it returns clean, the mode is dead."
  target_section: "section 5 (and section 4)"

- id: R2-4
  severity: MINOR
  title: "The freeze record's disposition must be `{total: 192}` alone; §5's own Reuse template carries the shape that fails"
  evidence: >-
    OBSERVED: `check_recon` on a results-absent record with
    `disposition: {total: 192, completed: 0, excluded: 0}` returns
    "FAIL ER-RECON: disposition.total 192 != completed 0 + excluded 0"; with
    `disposition: {total: 192}` it is CLEAN (validate.py:452-463). §5's Reuse pointer is
    `templates/measurement.yaml`, whose disposition block is
    `{completed: 96, excluded: 0, total: 96}` (measurement.yaml:16-19). The passing shape is
    the in-repo precedent, asserted at test_acceptance_rg2x2.py:160
    (`assert frozen['disposition'] == {'total': 96}`), but §5 does not state it.
  detail: >-
    §5's acceptance criterion requires the freeze record to exit 0 with results absent AND to
    reconcile `disposition.total == 192`. The only shape satisfying both omits
    `completed`/`excluded` until finalize fills them. An implementer authoring from the named
    Reuse template hits a red gate at the stage-2 commit. Cheap to hit, cheap to fix, but it
    is a stated acceptance criterion that the stated Reuse artifact does not satisfy.
  smallest_fix: "§5 adds: 'the freeze record's `disposition` carries `total: 192` only — `completed`/`excluded` arrive at finalize (§6), matching the RG-2x2 freeze precedent'."
  disconfirming_test: "`validate.check_recon` on a results-absent record with total/completed/excluded = 192/0/0."
  target_section: "section 5"

- id: R2-5
  severity: MINOR
  title: "`contrasts[].interval` is stated but nothing recomputes it — stats.py returns no interval for a mean difference and refuses the normal approximation by name"
  evidence: >-
    stats.py:62-65 `class PairedDiff(NamedTuple): mean_diff; se; n_clusters` — no interval;
    stats.py:226 `_REFUSED_NORMAL = frozenset({'normal', 'wald', 'clt', 'gaussian', 'z'})`
    and :229 `confidence_interval` raises on those, offering only wilson / clopper_pearson /
    beta_binomial (binomial proportions); spec:339-340 lists `interval` as a contrast field
    and :340-343 says ER-STATS "recomputes every stated contrast from the cluster block via
    `stats.paired_difference` (and `stats.clustered_se` ...)".
  detail: >-
    Estimate and SE are recomputable and gated. The interval is not: no stats.py function
    produces a mean-difference interval, and §4's Reuse pointer names only
    `stats.py::paired_difference`. The Enforcement table's new invariant reads
    "paired-contrast integrity (a stated contrast is recomputed from per-cluster counts)",
    and Part B says "the headline precision is quoted on the clustered/paired scale" and "the
    record reports achieved precision on the clustered scale" — so the one number the
    decision reads is the one field the new gate does not recompute. That is a
    section-presence tick inside the mechanism this wave adds.
  smallest_fix: "§4 states how the interval is derived and checked — e.g. 'each contrast's `interval` is recomputed as estimate +/- t(0.975, n_clusters-1) * se from the recomputed values, with the quantile named in the record, and ER-STATS fails on mismatch at the existing ATOL/RTOL' — and adds the helper to §4's file list."
  disconfirming_test: "grep stats.py for any function returning an interval around a difference of means; if none exists, `contrasts[].interval` has no recomputation source."
  target_section: "section 4"

- id: R2-6
  severity: MINOR
  title: "The `clusters` block shape does not match `clustered_se`'s signature, and `paired_difference` raises on a fully-excluded prompt"
  evidence: >-
    stats.py:270 `clustered_se(outcomes: Sequence[int], cluster_ids: Sequence[Hashable])` —
    per-TRIAL 0/1 outcomes, not per-cluster numerator/denominator; stats.py:303-320
    `paired_difference` raises `'cluster sizes must be positive'` on any size <= 0 and
    `'paired difference needs at least 2 shared clusters'` below G=2. Spec:337-338 defines
    `clusters` as "per prompt id, per arm: numerator and denominator"; :410-411 pre-registers
    exclusions "through the disposition machinery".
  detail: >-
    `paired_difference` takes the clusters block verbatim (a genuine, verified fit — see the
    cleared list). `clustered_se` does not: it needs the counts expanded back into a 0/1
    trial list per cluster. The adapter is trivial and lossless, but unnamed, so two
    implementers can write two different call shapes. Separately, if both repeats of one
    prompt are excluded (refusal / truncation / tool error, all pre-registered), that
    cluster's size is 0 and every contrast touching it raises rather than degrading — the
    ceiling-halt fallback ("analyze complete prompt-pairs only") covers a truncated run but
    not a per-prompt total exclusion.
  smallest_fix: "§4 names the adapter ('the clusters block is expanded to per-trial 0/1 outcomes for `stats.clustered_se`') and §5's exclusion rules add 'a prompt whose runs are all excluded drops out of every contrast, with its cluster count recorded'."
  disconfirming_test: "Call `stats.clustered_se` with per-cluster numerator/denominator arrays; and call `stats.paired_difference` with one cluster size 0."
  target_section: "section 4 (and section 5's exclusion rules)"

- id: R2-7
  severity: MINOR
  title: "§6's `render_report` extension makes the committed RG-2x2 report.md stale in a way its own drift gate cannot see"
  evidence: >-
    render.py:99-167 `render_report` (one shared renderer for every record) and :193-210
    `check_drift`, which compares a sha256 over the PARSED embedded YAML only — prose is
    invisible to it (round-1 FM-20's own evidence, unchanged). Spec:433-439 extends
    `render_report` with the contrast table, clustered precision, the 2x2 breakdown, the
    turn/token tax and a leading activation line; DoD:499-500 lists
    `examples/rg-2x2/report.md` and `evals/experiments/act-hint/report.md` under
    "`render.py --check`, §1 and §6" without assigning the re-render.
  detail: >-
    Extending the shared renderer changes what `render_report` would emit for the RG-2x2
    record too. If PR06 does not re-render that report, the committed pair violates
    "derived, never hand-edited" while `render.py --check` stays green — the exact blind spot
    the fold cited as its reason for naming the extension. The fix is one clause, not a
    mechanism.
  smallest_fix: "§6's acceptance criterion adds: 'and `examples/rg-2x2/report.md` is re-rendered in the same PR, since `render_report` is shared and its drift gate is blind to prose'."
  consumed_input: "render.py:174 `_embedded_blocks` consumes only ```yaml fences, so prose added or lost outside a fence never reaches the digest `check_drift` compares."
  disconfirming_test: "After extending render_report, run `render.py --stdout` on the RG-2x2 record and diff against the committed report.md; then run `render.py --check` on the same pair and observe it pass regardless."
  target_section: "section 6"

- id: R2-8
  severity: MINOR
  title: "Gate commands omits the two ruff gates CI actually runs, over the six new Python files this wave adds"
  evidence: >-
    .github/workflows/validate.yml:19-22 runs `ruff check .` and `ruff format --check .`
    before the register linter and the tests; `.pre-commit-config.yaml:25-30` runs `ruff
    --fix` and `ruff-format` locally. The spec's Gate commands (:45-71) enumerate six gates
    and neither ruff invocation; §3/§5/§6 add `firing_table.py`, `verify.py`, `run_arms.py`,
    `finalize.py` and render.py/validate.py extensions.
  detail: >-
    Local pre-commit autofixes, so the divergence surfaces only as an unexpected reformat or
    as a CI red on a branch whose Gate commands list read green. Low blast radius, but the
    Gate commands section is the implementer's checklist and is otherwise exact.
  smallest_fix: "Add `ruff check .` and `ruff format --check .` to Gate commands, citing `.github/workflows/validate.yml:19-22`."
  disconfirming_test: "Read validate.yml's step list and diff it against the spec's Gate commands."
  target_section: "Gate commands"

- id: R2-9
  severity: MINOR
  title: "'Four arms differ by one thing — the text injected' is not what the design does, and the injected text's own shape is unspecified"
  evidence: >-
    spec:359-367 defines narrow and wide by their PATTERNS (which prompts fire), not by their
    text, while the sentence introducing them says the arms differ only in the injected text;
    :196-197 has the firing table record "the injected text id, and its estimated token
    count". The real hint the design is modelled on echoes the matched words per prompt
    (router.py:62-74 `hint_line`, `words = ', '.join(_ascii(w) for w in ...)`), so a faithful
    reproduction varies per row; a fixed per-arm string does not.
  detail: >-
    Both readings are buildable and both satisfy §5's acceptance criterion, but they differ
    in what "inert's estimated token count within +/-5% of wide's" means — a per-row match
    against a varying text, or a single global match. The construct statement ("the effect of
    an injected hint delivered at router-realistic firing patterns") licenses either, so this
    is latitude to close, not a design error.
  smallest_fix: "§5 states whether each arm's injected text is a fixed per-arm string or reproduces `hint_line`'s per-prompt matched-word echo, and that the +/-5% token match is asserted per firing row."
  disconfirming_test: "`python -c \"import router; print(router.hint_line(router.route('is the new skill actually effective', router.load_rules())))\"` — read whether the rendered text varies with the prompt."
  target_section: "section 5"
```

## Cleared

Claims I re-verified this round and found correct, recorded so they are not re-litigated.

```yaml
cleared:
  - claim: "All 36 fold-ledger rows anchor to the exact line and string they cite"
    cite: "mechanical re-check of every `<path>:<line>` `<quoted text>` pair in the ledger — 36/36 exact, zero drift, zero off-by-one"
  - claim: "All 21 load-bearing code cites in the spec body resolve at the exact line and string"
    cite: "run_tests.py:24; validate_plugins.py:78; lint_register.py:34; ascii_runtime_lint.py:43; .pre-commit-config.yaml:65; rg-2x2/record.yaml:6 and :3; inject_dispatch.py:52; claude_runner.py:296, :202, :221; test_router.py:59 and :45; word_budget.json:8; BASELINES.md:14 and :18; finalize.py:7 and :189; humblepowers/CHANGELOG.md:25; validate.py:547; ADR-0008:116"
  - claim: "The direct-delivery claim is real: the harness needs no change to prepend text to the measured prompt, and needs no second plugin dir"
    cite: "claude_runner.py:296 `input=prompt` inside `subprocess.run`; :261 `plugin_dir: str | None = None` on run_agent; :238-239 the single `--plugin-dir` append"
  - claim: "Every isolation primitive Part B's causal-path paragraph names exists on the real surface"
    cite: "claude_runner.py:63-77 `make_isolated_config` (credentials-only), :289-290 CLAUDE_CONFIG_DIR, :302 cwd, :226-227 --allowed-tools, :234 --max-budget-usd, :221 --no-session-persistence"
  - claim: "`stats.paired_difference`'s signature takes §4's clusters block verbatim"
    cite: "stats.py:303-308 `paired_difference(a_successes, a_sizes, b_successes, b_sizes)` — four per-cluster arrays of numerators and sizes, exactly the shape §4 freezes"
  - claim: "The 8-cell / N=192 design reconciles under ER-RECON for the confirmatory outcome"
    cite: "executed `check_recon` on 8 cells of 24 with `rigor_disposition` at four arms x denominator 48 — clean"
  - claim: "The hook's pre-filter the firing-table generator must reproduce is exactly as the spec states it"
    cite: "inject_dispatch.py:52-53 MIN_WORDS=4 / MIN_CHARS=15, :112 slash-command skip, :114 the floor return, :107 the SYNTHETIC_PREFIXES skip (the one filter the spec does not name — harmless, since no bank prompt is a subagent notice)"
  - claim: "The router semantics the generator must reproduce are patterns / negative_patterns / min_hits / max_candidates with a hits-descending stable sort"
    cite: "router.py:42-59; router_rules.json carries max_candidates 2 and nine rows, `humblepowers:experiment-rigor` among them"
  - claim: "The router id-prefix edit cannot move the sealed budgets"
    cite: "test_router.py:45 `skill_id.split(':', 1)[1] + '.json'` — the dataset lookup drops the prefix; :59 asserts only that an id HAS a plugin part"
  - claim: "CI runs a depth-1 checkout today, so `fetch-depth: 0` is genuinely needed"
    cite: ".github/workflows/validate.yml:13 `uses: actions/checkout@v7` with no fetch-depth; currency.yml runs no tests, so §1's scoping to validate.yml is correct"
  - claim: "The FREEZE.md population is exactly the four sites §1 sweeps, one of them a writer"
    cite: "`git grep -n FREEZE.md` -> CHANGELOG.md:25, finalize.py:7, finalize.py:189 (the writer), record.yaml:3"
  - claim: "The ASCII ratchet holds the new and moved files at zero, so §3's format-(a)-only reasoning is mechanically correct"
    cite: "ascii_lint_baseline.json has 16 keys, none under experiment-rigor or evals/experiments; ascii_runtime_lint.py:43 BASELINE_NAME, SCAN_DIRS = ('plugins','scripts','evals')"
  - claim: "The word-budget key is required-not-optional and orphan keys are tolerated"
    cite: "word_budget.py:67-82 `check_budgets` iterates counts (a body with no baseline fails); word_budget.json:8 keys the old path at 827"
  - claim: "The suite is green today, so any post-move red is attributable to this wave"
    cite: "`scripts/run_tests.py` on a fresh clone of the branch: 46/46 passed"
  - claim: "`design.cells` and `analysis_plan` are frozen against drift, so the pre-registration claim has real teeth"
    cite: "validate.py:926-933 (cells compared as a whole subtree; analysis_plan compared minus amendments), :956-968 (post-freeze outcome quarantine), :970-985 (a confirmatory verdict is legal only on a frozen-confirmatory outcome)"
  - claim: "ADR-0008 is in sync with the folded spec"
    cite: "ADR:91-96 (generated half gated / tier-0 review-only) matches the Enforcement table; ADR:112-115 (inert arm controls the mechanism contrast, not wholesale) matches §5's per-contrast threat text; ADR:116-124 (firing/effect split, live-hook delivery as a named precondition) matches Context:28-32 and §6"
  - claim: "No stale pre-fold arithmetic survives"
    cite: "no occurrence of 168, $60, '14 prompts', '42 per arm', 'skeleton_completeness' or the +/-10% match anywhere in the spec; 192 / 24 prompts / 8 cells / 48 per arm / $75 are consistent at :210, :368, :391, :416, :424, :490, :516"
```

## Prose

**What the fold got right.** The structural move — computing firing offline against a
frozen bank and delivering the injection directly in the paid run — is the right
answer to round 1's cluster of experiment BLOCKERs, and it is right for a reason worth
naming: it converts four unverified assumptions about a live hook into a table an
auditor can read before a cent is spent. The oracle's 2×2 truth table with
both-required-on-genuine and neither-required-on-decoy is a genuine improvement over a
single accuracy rate; the labeled validation set with its recall/specificity in the
record is the discipline applied to its own instrument. The threat rows written per
contrast rather than blanket, with `narrow − control` explicitly re-inheriting the
founding case's confound, is the kind of honesty the whole wave exists to institutionalize.
And the citation hygiene is the best I have seen in this repo: 36 ledger anchors and 21
code cites, all exact.

**Where it fails is the part nobody was looking at.** Round 1 called §1 "the sound
part" and spent its attention on §4/§5. The fold restructured §4/§5 accordingly. Both
rounds then carried §1's central operation — `git mv` a tree containing a record whose
pre-registration is anchored to a commit by PATH — without simulating it. Executing it
takes ninety seconds and turns the suite red. The specific damage is worse than a red
test: `validate.py` keeps exiting 0, because ER-PREREG's not-in-history branch is a
measurement-tier WARN. So the wave's flagship claim — that the record gates are
enforced at the new paths — would be committed, gated, and false, on the one record
that dogfoods the gate. That is the failure mode this discipline was built to catch,
appearing in the move that creates its plugin.

**A note on the remedy.** The obvious repair — re-freeze the record at a post-move
commit — is unavailable, and it is worth stating why, because an implementer will try
it: ER-ANCHOR fails when the freeze commit postdates `run.first_run_at`, and the RG-2×2
record's first run is dated 2026-07-24T12:00Z. The remaining options all touch
`validate.py` and the schema, which is why R2-1 is a BLOCKER rather than a two-line
condition: it needs a scoped addition to §1's file list and a decision about where the
frozen path is recorded, and that decision interacts with §4's schema work and with the
PR ordering. It is not a large change. It is not a wording change either.

**On the two remaining ER-RECON collisions (R2-3, R2-4).** These are one defect class,
not two instances: the fold designed a new record shape and never ran it past
`check_recon`. Both are now observed rather than predicted. Fixing them is two clauses.
I would fold them with R2-1 rather than separately, and I would run the same synthetic
`check_recon`/`check_stats` pass over the *whole* §5/§6 record shape before the next
certification attempt — including the contrasts block, whose `interval` field (R2-5)
currently has no recomputation source at all.

**What I did not attack, and why.** The residual trust the spec names — the floor
asymmetry on the genuine half, `narrow − control`'s inherited confound, the
oracle-as-proxy limit, and the live-hook delivery precondition — is stated design
posture, not defect, and I have treated it as such. The primary contrast being the
pooled net-benefit quantity (round-1 FM-5's residue) is likewise a defensible choice
once the genuine/decoy decomposition is pre-registered as first-class cells; I record it
as PARTIALLY-RESOLVED rather than reopening it. And I have not re-litigated the
$25–60 estimate band against the $75 ceiling: the anchor is honestly labelled a lower
bound on a different profile, and `--dry-run` before spend is the right mechanism for a
number nobody can compute offline.

Unverified-offline: 5

PREMORTEM-VERDICT: NEEDS-REVISION — fresh non-author subagent (opus), round 2, keel kit 0.13.0
</content>
</invoke>
