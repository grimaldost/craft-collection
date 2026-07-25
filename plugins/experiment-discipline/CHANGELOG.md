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
- **Two references:** `references/threats-catalog.md` (the nine-key closed threat
  enum, one paragraph per key, kept in sync with `templates/schema.json` by
  `test_threats_catalog.py`) and `references/small-n-stats.md` (Miller's five rules
  adapted, the exact-methods rule, the Beta(1, 1) prior and its sensitivity, and the
  within-experiment-only pooling boundary — cross-experiment belief moves through a
  qualitative GRADE link, never pooled counts).
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
