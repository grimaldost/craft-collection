# Changelog — experiment-discipline

Notable changes to this plugin. Bump the `version` in `.claude-plugin/plugin.json`
with each release.

## 0.1.0 — 2026-07-25

Birth of the plugin. The `experiment-rigor` skill was built inside humblepowers
(as 0.9.0 and 0.10.0, neither released) and is extracted here per
`docs/adr/0008-experiment-discipline-plugin.md`: the discipline is about
evaluation acts, not about the process disciplines humblepowers collects, and it
carries a mechanism spine — a validator, a renderer, a statistics module, a schema
and its gates — that a process-discipline plugin has no business hosting. The
frontmatter `description` is byte-identical across the move, so the sealed trigger
holdout and its birth baseline stay valid and no reseal is owed
(`evals/trigger/holdout/BASELINES.md`).

A rigid, thin skill over four stdlib-plus-PyYAML scripts that turn a typed
`record.yaml` into a validated, derived report across a probe / measurement /
decision tier ladder — every load-bearing rule a gate that exits non-zero, not a
line of prose to remember. The founding case is a small register-by-gate A/B whose
prose write-up three fresh readers could not reconstruct: the arithmetic never
closed, the outcome was never operationalized, rates carried no denominators, a
post-hoc finding was presented as pre-registered, and no uncertainty was reported.
The discipline gates the disqualifying half (methods uncertainty) and structures
the declarable half (effect uncertainty).

### Added

- **experiment-rigor** (rigid): the thin skill body routes to the scripts and states
  the bright lines — the plan freeze and its `git show` drift gate, declared-cells
  reconciliation (declared cells == disposition == denominators), the confirmatory /
  exploratory partition with a post-freeze quarantine, the small-n CI refusal (no CLT
  below a denominator of 30 — Wilson, Clopper-Pearson, or a within-experiment
  Beta-Binomial), a rate that needs both a numerator and a denominator, record-is-source
  with the report derived, and probe self-labeling. Binds keel's Definition of Ready
  and fresh-context reader tooling role-generically.
- **References:** `references/threats-catalog.md` (the nine-key closed threat
  enum, one paragraph per key, kept in sync with `templates/schema.json` by
  `test_threats_catalog.py`) and `references/small-n-stats.md` (Miller's five rules
  adapted, the exact-methods rule, the Beta(1, 1) prior and its sensitivity, and the
  within-experiment-only pooling boundary — cross-experiment belief moves through a
  qualitative GRADE link, never pooled counts).
- **The tier-0 `check` rung** (the skill body's ladder plus a third reference,
  `references/report-skeleton.md`): an evaluation act answered inline — no file, no
  record, no gate, and never a `tier:` value. The reference carries the five-element
  shape (method, metric, result(s) with denominators, conclusion, and a one-line
  "what this updates"), three worked micro-examples (the third for an evaluation
  act with nothing measured, whose result element is the explicit absence), and
  the boundary the widened scope makes load-bearing: an evaluation act asks a
  question whose correct answer is a valuative claim, an execution or lookup
  request asks for an action or a fact and owes nothing here, and a correctness
  question is a fact even when phrased valuatively. The rung is guidance by design
  (`docs/adr/0008-experiment-discipline-plugin.md`), so it is reviewed and measured
  rather than gated: `evals/tasks/experiment-rigor/` gains a
  dedicated tier-0 task (`er-tier0-check`) with its own
  `rubric.er-tier0-check.json`, since the bank's only other task mandates a record
  and a shared-rubric item for the rung could score nothing but false. The body's
  word budget moves 827 -> 950 (`scripts/word_budget.json`); nothing is removed —
  the diff is pure addition, and the growth buys only the rung's name, its entry
  rule, and one sentence of boundary, while the five elements, the worked
  examples, and the boundary's edge cases stay lazy in the reference rather than
  in the eager body.
- **The activation line and its generator** (`render.py --activation-line` and
  `--check-activation-line`, the skill body, `references/report-skeleton.md`, and all
  three tier templates): whenever the frame engages, one plain line opens the work
  product naming the tier and the artifact behind it. At `probe` and above it is
  generated from the record rather than typed —
  `[experiment-rigor | measurement -> <record path>]` — and the checker exits 1 when a
  pasted line's tier **or** path disagrees with the record, so the claim cannot drift
  from the artifact it names. Inside a repository the path is relative to the repository
  root with POSIX separators, so the same record yields the same line on every machine
  and checkout; outside one there is no anchor, so the line names the resolved absolute
  path and `artifact_ref` says so on stderr — round-trippable but not portable. The
  comparison is exact after `strip()`: a backslash spelling of the right file is a
  disagreement and is reported as one. Both flags build through one `activation_line()`
  builder: the format string exists in exactly one place. At tier-0 the artifact
  reference is the literal `inline` — nothing resolves it, so that rung's line is
  reviewed and measured rather than gated, and the generator refuses a record declaring
  `tier: check` rather than inventing a path for it. The generated form is ASCII (`|`
  and `->`) because the generator's literals are runtime-reachable strings under the
  ASCII ratchet and `render.py` is held at zero findings; a glyph-prefixed variant is
  therefore available only as a hand-written annotation, a mechanical consequence rather
  than a taste ruling — and the CLI reconfigures stdout to UTF-8 so that pasting such a
  line under a cp1252 console yields the `MISMATCH` verdict instead of an encoding
  crash. `scripts/test_render.py` covers both directions of the checker, the exact
  repo-relative path, the Windows-spelled path, the tier-0 refusal, an unreadable record
  (reported as `ERROR`, exit 1, no traceback), the cp1252 console, the absolute-path
  fallback with its stderr note, and the CLI round trip. The leading line is not yet
  emitted into a derived `report.md`: `render_report` is unchanged here and §5 of the
  wave spec, which re-renders the RG-2x2 example, owns that. The body's word budget
  moves 950 -> 1062 (`scripts/word_budget.json`); nothing is removed — the growth is
  pure addition, and it buys the emission rule, the two command names, the two example
  lines (the tier-0 form and a record-backed one), and one correct-usage checkbox (the
  only checkable item at tier-0, where the other four are vacuous), while the
  tier-specific spelling and the ASCII rationale stay in the templates' comments and the
  tier-0 form's reasoning in `references/report-skeleton.md`, out of the eager body.
- **Schema v1.1 — the paired-contrast machinery** (`templates/schema.json`,
  `validate._EMBEDDED_SCHEMA`, `scripts/stats.py`, `scripts/validate.py`,
  `scripts/render.py`, `templates/SCHEMA.md`, `templates/measurement.yaml`,
  `references/small-n-stats.md`). The
  shipped `ER-STATS` branch recomputed each arm's interval from raw per-arm counts,
  which mechanically forces an independent-trials Wilson interval onto a design whose
  unit is the prompt cluster. Two additive blocks fix it: `results.<outcome>.clusters`
  (per prompt id, per arm: a numerator and a denominator) and
  `results.<outcome>.contrasts[]` (a `name`, the ordered `arms` pair, an `estimator`,
  the `estimate`, its `se`, `n_clusters`, an `interval`, and a `sign_test`). `ER-STATS`
  recomputes every stated contrast from the cluster block at the existing ATOL/RTOL
  tolerances and names the offending contrast; a contrast with no cluster block behind
  it fails rather than passing unchecked. The per-arm Wilson interval stays and is still recomputed,
  demoted to **descriptive** — an upper bound on precision — with the headline quoted
  on the clustered scale, and the derived report marks the demotion in the line itself.
  An outcome scored over a subset of the cells carries **no `arms` block at all**;
  that absence is how the validator tells the two scopes apart, so no new field was
  added to declare it. `stats.py` gains `paired_interval` (the t-interval
  `estimate +/- t(1 - alpha/2, clusters - 1) * se`, with the quantile recorded in the
  record and recomputed by the gate), `student_t_quantile` (the stdlib has no
  Student-t inverse, so the CDF is summed from the finite elementary series that
  exists for integer df and inverted by the module's fixed bisection — exact at every
  df; a p so close to 1 that the quantile cannot be bracketed raises rather than
  returning the bracket end), `sign_test` (exact,
  distribution-free, with the tie rule fixed here before the freeze: a zero
  per-cluster delta is dropped and the surviving effective cluster count is reported),
  `expand_cluster_counts` (the lossless counts-to-trial-list adapter `clustered_se`
  needs, tested by round trip and against a known SE), and `cluster_deltas` (the one
  definition `paired_difference` averages and `sign_test` counts signs of). The sign
  test is **stated in the record and recomputed by the gate**: every contrast carries
  `sign_test` (`p_value`, `effective_n`, `positive`) and `ER-STATS` checks all three
  against the cluster block. It is a record field rather than only an emission because
  the drift and parity gates re-parse the embedded typed block — a p-value living only
  in the report's prose could be edited to anything and still pass both. `validate.py`
  additionally echoes the recomputed triple as an `INFO` line, which confirms the
  arithmetic and hands a record still being authored the values to write down; the
  check is the recomputation, not the echo, and `render.py` quotes the record rather
  than deriving a second answer. `ER-RECON` gains one rule: where an outcome carries both blocks, the clusters
  must sum per arm to that arm's counts, so the record cannot hold two answers to the
  same question. `known_versions` moves to `[1, 1.1]` in **both** `schema.json` and
  `validate._EMBEDDED_SCHEMA` (the sync test reddens on either one alone, verified in
  both directions), and the extension is purely additive: the RG-2x2 example record
  and both other tier templates are unchanged and still validate. `SCHEMA.md` was
  regenerated through its generator, not hand-edited.
- **Trigger dev set and sealed holdout** authored at one sitting
  (`evals/trigger/experiment-rigor.json`, `evals/trigger/holdout/experiment-rigor.json`),
  plus a correct-usage rubric (`evals/tasks/experiment-rigor/`) checking that a produced
  record passes `validate.py` and the Methods reconstruct without the conversation. The
  holdout was sealed with its birth baseline in `holdout/BASELINES.md`:
  recall 0.33 [0.15, 0.58] on pure intent paraphrases (the intent-category floor the
  trigger-lexical-ceiling predicts, not a verdict), specificity 1.00 [0.76, 1.00] with
  all four sibling near-misses silent; the description was never tuned against either set.
- **The RG-2x2 dogfood fixture** (`skills/experiment-rigor/examples/rg-2x2/`): the
  founding case as a faithful measurement-tier `record.yaml` — 8 declared cells x 12 =
  96, the confirmatory `activation` outcome that failed (`confirmatory_null`), the
  quarantined exploratory `footprint` outcome carrying its within-experiment
  Beta-Binomial posterior and the wave-2 pre-fixed bar as an `analysis_plan.amendments`
  entry, the token-length confound named as a residual threat, and the field-belief
  prior -> register-null / deliberation-signal posterior update. Its two-stage freeze
  choreography is documented in `examples/rg-2x2/FREEZE.md` and executed by
  `finalize.py`, so the stage-1 commit anchors `plan_frozen_at.commit`.
- **The acceptance test** (`scripts/test_acceptance_rg2x2.py`): a seeded
  six-defect variant makes `validate.py` exit 1 naming all six by code (`ER-RECON`,
  `ER-SCHEMA` twice, `ER-STATS` twice, `ER-PREREG`), while the corrected record — the
  real fixture through the real finalize step, against a real freeze commit — exits 0
  with `render.py --check` showing no drift. Decision-tier fixtures cover the
  comprehension gate: a missing block and a below-4/4 reader each exit 1
  (`ER-COMPREHEND`), a complete record with resolving transcript files and a
  second-party attestation exits 0.
- **The mantis journal-envelope emit** (`render.py --emit-journal`): a record's belief
  update rendered as a journaling-sessions envelope. The primary shape carries the
  provenance as extra header fields (a superset both mantis parsers tolerate — verified
  against `mantis.ingestion.journal` and `journal_v2`); a `--strict` fallback drops the
  superset and links the record hash-pinned (`record_ref` + `record_sha256`) for a parser
  that rejects unknown keys. `scripts/test_mantis_envelope.py` tests the tolerance (the
  real parser when importable, else the documented envelope-schema contract, marking
  which); `scripts/test_mantis_fallback.py` mocks a rejecting parser and asserts the
  strict fallback is accepted, well-formed, and resolvable.
- **`plan_frozen_at.path` — the frozen coordinate** (`templates/schema.json`,
  `validate.check_prereg`, `templates/SCHEMA.md`). `git show <commit>:<path>` does not
  follow renames, so a record relocated after its freeze pins the path it had **at** the
  freeze commit. Resolution falls back to the record's current path when the pinned
  lookup **fails** — not merely when the field is absent — so every v1.0 record still
  reconstructs and a fixture that relocates a pinned record stays green. The trade is
  deliberate: a wrong pin resolves silently through the current path rather than failing
  loudly, so the pin is a durability aid, not a second integrity check.
- **Freeze durability:** each freeze commit carries a lightweight keep-ref tag
  (`freeze/rg-2x2-stage1` -> `ed3c5a0`) so a squash-merge cannot orphan it, and CI checks
  out at `fetch-depth: 0` so the freeze objects `ER-PREREG` and the acceptance suite read
  are present. A depth-1 clone is expected to fail the reconstruction loudly; no skip
  exists to make it pass.
- **The act-hint detector, frozen before its run.** The plugin itself gains no code
  here: the experiment lives under `evals/experiments/act-hint/` — a 24-prompt bank
  (12 genuine evaluation acts, 12 execution/lookup decoys, half EN and half PT-BR
  within each class, authored against `references/report-skeleton.md`'s boundary), four
  arm rules files, an offline firing-table generator and its frozen table, the oracle
  and its language patterns, a hand-labeled oracle-validation set, the arm runner, the
  freeze-stage `record.yaml` with its derived `report.md`, and `FREEZE.md` +
  `freeze_fill.py` for the two-stage choreography. What the plugin contributes is the
  discipline the experiment is held to. The frozen record carries no results, so it
  exercises schema v1.1 as a **plan**: it is the first record whose `analysis_plan`
  names `contrasts[]` as the reporting shape, and the pre-spend gate drives synthetic
  `clusters` + `contrasts[]` + `sign_test` blocks past `validate.py` in both the
  zero-exclusion and the with-exclusion shape. The end-to-end exercise on real counts
  belongs to the run and its finalize step. Firing is decomposed from
  effect: `firing_table.py` drives the real humblepowers router **read-only** (it
  imports `router.load_rules` / `route` / `hint_line` and the dispatch hook's own floor
  constants) over the frozen bank and freezes, per arm and per prompt, whether an
  injection fires, the candidate ids, and the injected text **verbatim** — so exposure
  is auditable for free before a cent is spent, and the paid run delivers frozen bytes
  rather than a recomputation. The shipped `router_rules.json` is untouched and pinned
  byte-for-byte by a test. Every load-bearing property is a check rather than a claim:
  parity of both router-derived arms against the real router, wide-vs-inert row-set
  identity with a per-row token match (0.00% worst-row deviation against a 5%
  tolerance), primeability over **both** the injected texts and the bank (the router
  echoes literal prompt spans, so the constraint binds the bank too), the hook floor
  over every prompt, the oracle reproducing all twelve hand labels, and a **pre-spend
  shape gate** that drives the complete record — the freeze stage and two fully
  populated final stages — past `validate.py` before any spend. That gate earned its
  keep immediately: it observed that `ER-RECON` holds every outcome's arm denominators
  to `N_expected`, so a record stating per-arm counts alongside a non-zero
  `disposition.excluded` cannot reconcile. The rule is therefore pre-registered rather
  than discovered — the confirmatory outcome states its `arms` block only when nothing
  was excluded, and any exclusion moves both outcomes to the contrasts-only shape.
- **The derived report grew the sections the drift gate cannot see** (`scripts/render.py`,
  `scripts/test_render.py`, and the re-rendered `examples/rg-2x2/report.md`).
  `render_report` now emits, for every block a record actually carries: the contrast table
  on the clustered scale with each row's stated interval, its half-width and the sign test
  beside it; the achieved precision of the contrast the plan named primary, quoted against
  the declared MEWD; the 2×2 state breakdown with the line-only rate as its own column; the
  descriptive turn and cost tax; and the pre-committed interpretation the data selected
  with the precondition a rollout still owes. Every number is READ from the record — the
  renderer quotes, `ER-STATS` recomputes — and a row labels itself (the A/A calibration
  names itself the noise floor) rather than the renderer knowing which contrast is which. A
  record with none of those blocks renders none of those sections: absence produces
  absence, not a header over an empty table. `render_report` also takes the record's path
  now, and with it the report opens with the **generated** activation line from §3's
  `record_activation_line` rather than a typed one; tier-0 `check` records name no artifact
  and get no line. Because one renderer serves every record and the drift gate digests only
  the embedded YAML, extending it would have staled the committed RG-2×2 prose while
  `--check` stayed green — so that report is re-rendered in the same change (its diff is
  exactly the leading line) and its `finalize.py` passes the path, so a re-run cannot drop
  the line silently.
- **`finalize.py` for the act-hint detector** (`evals/experiments/act-hint/finalize.py`,
  `test_finalize.py`): the other end of the freeze choreography, deterministic and
  idempotent. It re-verifies every frozen material SHA before writing anything (an edit to
  bank, rules, table or oracle after the freeze fails loudly rather than quietly changing
  what was measured), scores every run through the frozen oracle, and applies the
  pre-registered rules as READ from the record: the exclusion rule verbatim (excluded iff
  the harness errored or the response text is empty — a decline for lack of a tool is
  scored as written), the fully-excluded-prompt drop-out with the surviving cluster count
  recorded, the stricter complete-prompt-pairs fallback whenever a planned run never
  started (a ceiling halt declines a prompt left with one repeat, which the ordinary
  drop-out would have kept), and the arms-block rule (per-arm counts and their descriptive
  Wilson intervals only when nothing was excluded). It fills the observed disposition with
  per-reason counts, the per-cluster blocks, every contrast through
  `stats.paired_difference` / `paired_interval` with the recomputed sign-test triple beside
  it, the 2×2 state breakdown, the descriptive tax, the observed first-run timestamp in
  place of the pre-run placeholder, and the prior → posterior update linking the founding
  RG-2×2 as its chain prior.
  Both frozen filtering rules are CONTRAST-scoped, as the plan writes them — "a prompt whose
  runs are all excluded in either arm of a contrast drops out of THAT contrast" — so each
  contrast lives in its own pair-scoped results key holding only that pair's two arms and
  only the prompts that survive for it. A prompt dead in `narrow` therefore costs the
  narrow contrasts a cluster and costs the wide−control primary nothing. The two declared
  outcomes keep their own keys, carry the verdicts and a descriptive full-arm cluster block
  (which the arms block reconciles against), and state no contrasts of their own.
  The interpretation is selected MECHANICALLY: the four pre-committed legs partition the
  2×2 of (the primary contrast moved, `inert − control` moved), and a contrast moves when
  its two-sided interval excludes 0 **and** its estimate reaches the declared MEWD — so no
  fifth leg is reachable. Two frozen qualifiers ride on that lookup without adding a leg:
  the second leg's own word **alike** is decided by the frozen secondary (`wide − inert`,
  the only pair in the design that isolates content from preamble), and where the secondary
  does move, the leg is recorded with `alike: false` and its "the content is irrelevant"
  reading is suppressed rather than quoted, replaced by the size of the content component
  the secondary separated; and **no headroom** is scoped to the recorded null exactly as the
  frozen text scopes it, since under any other leg something moved, which is itself proof
  there was room. The A/A calibration is held out of every signal test — an A/A that moves
  is a diagnostic failure, and it is recorded as a named `instrument_noise` flag.
  The tests drive it end to end on synthetic runs in a staged throwaway repo, so
  `ER-ANCHOR`, `ER-PREREG` and `ER-LINK` do their real work: both disposition branches reach
  a clean `validate.py` and `render.py --check`, twice through is byte-identical in both
  members of the pair, a tampered material is refused before anything is written, data
  built for each of the four legs selects that leg, and the measured F2 scenarios are
  pinned (a prompt dead in narrow leaves the primary at 24 clusters; a ceiling halt drops
  prompts only from the contrasts whose arms it touched). The producer → consumer interface
  is held by a test that drives `run_arms.execute` through its real spawn with the harness
  stubbed and scores the row it wrote, and the exclusion rule's load-bearing half — a
  decline for lack of a tool is scored, not excluded — has its own case, since that is the
  modal decoy response rather than an edge case. `finalize.py` loads `stats`, `validate` and
  `render` by explicit path: a bare `import stats` can resolve to the harness module of the
  same name that sits at the front of `sys.path`.
