---
name: experiment-rigor
description: "Structure an experiment and its write-up so the Methods reconstruct without the conversation and the uncertainty is declared, not hidden — a typed record.yaml across a probe / measurement / decision tier ladder, every load-bearing rule a script that exits non-zero rather than a line of prose. Use when you pre-register an A/B, freeze a plan before running it, write up an experiment or a comparison, add error bars or a confidence interval to a rate, reconcile declared cells against the runs that happened, separate confirmatory from exploratory outcomes, name the threats to validity, design the 2x2, or ask whether a skill, tier, model, or strategy actually helps and how you would show it rigorously. Covers the small-n refusal (no CLT below 30 — Wilson, Clopper-Pearson, or a within-experiment Beta-Binomial), the design-arithmetic reconciliation (declared cells == disposition == denominators), the plan freeze and its drift gate, the rate that needs both a numerator and a denominator, probe self-labeling, and record-is-source with the report derived. Not for running the scenario matrix or scoring a bank — that is fathom's fathom-eval; not for measuring one skill's trigger activation — that is evaluate-skill; not for judging whether a spec is ready to build — that is keel's Definition of Ready; and not for a throwaway spot-check you will decide nothing on."
---

# Experiment Rigor

Turn an experiment into a typed `record.yaml` whose `report.md` is derived, not
written. This is a **rigid** skill: the scripts under `scripts/` are the
mechanism, and each bright line below is a gate that exits non-zero with a stable
error code (`validate.py`), not advice to remember. The dividing line the
discipline draws: **methods uncertainty is disqualifying, effect uncertainty is
declarable** — a reader who cannot reconstruct what was manipulated, where, and
how it was measured has found a defect; a wide confidence interval is an honest
result.

Paths below are relative to `${CLAUDE_PLUGIN_ROOT}/skills/experiment-rigor/`, and
PyYAML is the scripts' only non-stdlib dependency — run them as the gates do:

```bash
uv run --no-project --with pyyaml -- python \
  "${CLAUDE_PLUGIN_ROOT}/skills/experiment-rigor/scripts/validate.py" <record.yaml>
```

The same two gates ship as pre-commit hooks (`experiment-rigor-validate`,
`experiment-rigor-render-check`); the README names the install surface.

## The tier ladder

`tier` is a field, not a second skill. It selects the required fields and which
gates apply. Tier-0 is the exception: it names no artifact, so it never appears
as a `tier:` value.

- **check** (tier-0) — the structured check. An evaluation act answered inline in
  the response: no file, no record, no gate. An *evaluation act* asks a question
  whose correct answer is a valuative claim ("is this effective", "which is
  better"); an *execution or lookup request* asks for an action or a fact and
  owes nothing here. The five-element shape — method, metric, result(s) with
  denominators, conclusion, and a one-line "what this updates" — the boundary,
  and two worked examples live in `references/report-skeleton.md`. This rung is
  guidance, not a bright line, and entry above it is unchanged: a record is owed
  when a decision rides on the result.
- **probe** — cheap and exploratory. Refuses a confirmatory verdict or any
  posterior; a probe that wants either graduates to measurement.
- **measurement** — a frozen pre-registration and a reported interval on every
  rate.
- **decision** — adds the comprehension gate: fresh-context readers reconstruct
  the Methods before the result is allowed to move a decision.

## The loop

1. Copy the tier skeleton from `templates/<tier>.yaml`; the field guide is
   `templates/SCHEMA.md` (generated from `templates/schema.json`, the canonical
   schema).
2. Author the record. While drafting, `validate.py <record> --schema-only` checks
   shape without the context gates (they are skipped and listed).
3. Freeze the plan: commit the pre-registration and record
   `plan_frozen_at.commit` before the first run.
4. Run the experiment; fill results. `from_fathom.py` maps a fathom ledger into
   the run-derived fields.
5. `validate.py <record>` runs the full gate. `render.py <record>` derives
   `report.md`; `render.py --check` is the drift gate over a committed pair. Never
   hand-edit `report.md`.

## The activation line

Whenever the frame engages, one plain line opens the work product, naming the
tier and the artifact behind it. At `probe` and above it is generated, not typed:
`render.py --activation-line <record>` prints it, and `--check-activation-line
"<line>" <record>` exits non-zero when the tier or the path disagrees — the line
is a claim tied to the artifact, not a badge. At tier-0 the artifact reference is
the literal `inline`, which nothing resolves.

```text
[experiment-rigor | check -> inline]
[experiment-rigor | measurement -> experiments/retry-backoff/record.yaml]
```

## Bright lines

Each is a gate in `validate.py`; the error code is named so a failure points at
the rule.

- **The freeze (`ER-PREREG`).** The pre-registration subset — `design.cells`, each
  outcome's `role`, operationalization, and verifier hash, and `analysis_plan` —
  is reconstructed with `git show` on `plan_frozen_at.commit` and compared to the
  analyzed record. Any drift fails. A confirmatory verdict is legal only on an
  outcome whose frozen `role` is `confirmatory`. The two guards the freeze buys —
  a null bank, and a pre-committed rule for what a finding must survive — are
  worked, with the day they both fired, in `references/two-guards.md`.
- **Declared-cells reconciliation (`ER-RECON`).** `N_expected` is the sum of
  `design.cells[].planned_n`, and it must equal the disposition total and every
  outcome's sum of arm denominators. The model tier is one named factor level, not
  a separate multiplier.
- **The confirmatory / exploratory partition.** `outcomes[].role` belongs to the
  frozen plan. An outcome added after the freeze carries `added_after_freeze: true`
  and `role: exploratory` — the quarantine — and may report only an
  `exploratory_signal` or `inconclusive` verdict, never a confirmatory one.
- **The small-n CI refusal (`ER-STATS`).** No CLT / normal method below a cell
  denominator of 30. Allowed: `wilson`, `clopper_pearson`, `beta_binomial`. Every
  stated interval is recomputed from `stats.py` and must match to four decimals.
  `references/small-n-stats.md` covers the rest.
- **A rate needs both a numerator and a denominator (`ER-SCHEMA`).** A rate lives
  under `results.<outcome>.arms.<arm>` with both; a loose rate at the outcome
  level fails.
- **Record is source, report is derived (`ER-PARITY`, `render.py --check`).** The
  record is the single source of truth; `report.md` is regenerated and must not
  contradict it.
- **Probe self-labeling (`ER-PROBE`).** A probe carrying a confirmatory verdict or
  a posterior fails; the message names the graduation path to measurement.
- **Threat coverage (`ER-THREAT`).** Every core threat in the closed enum carries
  a row with a status and a statement; silence on one fails. The enum is in `references/threats-catalog.md`.

## What binds, role-generically

- **Readiness before build.** When a spec-readiness gate is installed (for
  example keel's Definition of Ready), a decision-tier experiment that will inform
  a build defers spec readiness to it rather than re-deciding it here. Absent one,
  the experiment stands alone.
- **Fresh-context readers.** The decision-tier comprehension block records
  independent readers who reconstruct the Methods with no access to this
  conversation. Any fresh-context reader tooling that is installed can produce
  those reads; the block records the transcript path and the four verbatim
  answers, and their genuineness is ceded to review. The gate checks presence,
  resolution, and unanimity, not sincerity.

## Boundaries

Running the scenario matrix, scoring a bank, or driving the paid run is fathom's
`fathom-eval`; this skill structures and gates the record that results. Measuring
one skill's trigger activation is `evaluate-skill`. Judging whether a spec is
ready to decompose is a readiness gate (keel's Definition of Ready). A throwaway
spot-check you will decide nothing on needs none of this.

## Correct-usage check

- [ ] The record passes `validate.py` at its declared tier (exit 0).
- [ ] The Methods reconstruct from the record alone — what was manipulated, where
      it was placed, how each outcome was operationalized, whether execution was
      real — without the conversation.
- [ ] Every reported rate carries a recomputable interval; no CLT below 30.
- [ ] `report.md` is derived (`render.py`), not hand-edited (`render.py --check`
      clean).
- [ ] The work product opens with the activation line — `inline` at tier-0, and at
      `probe` and above the generated line, `--check-activation-line` clean.
