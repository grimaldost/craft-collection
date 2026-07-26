[experiment-rigor | measurement -> plugins/experiment-discipline/skills/experiment-rigor/examples/rg-2x2/record.yaml]

# Experiment: rg-2x2-register-gate (measurement tier)

_Derived from record.yaml by render.py -- do not hand-edit._

- Design: 8 cell(s) (ctrl_haiku=12, reg_haiku=12, gate_haiku=12, both_haiku=12, ctrl_sonnet=12, reg_sonnet=12, gate_sonnet=12, both_sonnet=12); shared_tasks=True
- Disposition: total=96, completed=96, excluded=0
- Outcomes:
  - activation (role=confirmatory): the model invoked the Skill tool to LOAD the target skill (ingest its body), measured from the raw event stream -- not the 'Skill check:' ritual declaration line, which is a separate, weaker signal.
  - footprint (role=exploratory): behavioral proxies measured by a deterministic verifier on the executed workspace artifact -- a root-cause fix that also corrects a second latent point never named in the prompt; the subtle data-output error caught; a regression test left that goes red if the bug returns. Measures the named discipline, not generic care.
- Results:
  - activation: verdict=confirmatory_null, paired=True
  - activation / with_gate: 0/48, wilson CI [0.0, 0.0741]
  - activation / without_gate: 0/48, wilson CI [0.0, 0.0741]
  - footprint: verdict=exploratory_signal, paired=True
  - footprint / with_gate: 36/48, wilson CI [0.6122, 0.8508]
  - footprint / without_gate: 18/48, wilson CI [0.2522, 0.5164]
- Threats: 9 declared, 6 residual
- Update: certainty=low, prior=None

## Record (canonical, machine-checked)

```yaml
analysis_plan:
  amendments:
  - commit: ed3c5a0e02f4b1fe5d60047e1bc43b88a91be4b2
    governs_first_run_at: '2026-07-24T18:00:00Z'
    note: wave-2 confirmation bar (+4/12) for the exploratory footprint, fixed after the wave-1 post-hoc signal and before wave-2. In this reconstruction the whole pre-registration is frozen at a single commit, so the amendment anchors to the freeze commit (documented choice; a live sequential design would carry a distinct between-waves commit).
    scope: wave-2
    timestamp: '2026-07-24T00:00:00Z'
  ci_method: wilson
  comparison: with_gate (gate + both) vs without_gate (ctrl + reg), pooled across the two model tiers, paired on the 6 shared tasks.
  decision_rule:
    comparison: gte
    direction: higher
    metric: rate_difference
    threshold: 0.1
design:
  cells:
  - name: ctrl_haiku
    planned_n: 12
  - name: reg_haiku
    planned_n: 12
  - name: gate_haiku
    planned_n: 12
  - name: both_haiku
    planned_n: 12
  - name: ctrl_sonnet
    planned_n: 12
  - name: reg_sonnet
    planned_n: 12
  - name: gate_sonnet
    planned_n: 12
  - name: both_sonnet
    planned_n: 12
  shared_tasks: true
disposition:
  completed: 96
  excluded: 0
  total: 96
experiment: rg-2x2-register-gate
outcomes:
- name: activation
  operationalization: the model invoked the Skill tool to LOAD the target skill (ingest its body), measured from the raw event stream -- not the 'Skill check:' ritual declaration line, which is a separate, weaker signal.
  role: confirmatory
  verifier:
    hash: 1f0a9c7b2d4e6f8a0c1e3d5f709182a3b4c5d6e7f80912a3b4c5d6e7f8091a2b3
    path: verify_activation.py
- name: footprint
  operationalization: behavioral proxies measured by a deterministic verifier on the executed workspace artifact -- a root-cause fix that also corrects a second latent point never named in the prompt; the subtle data-output error caught; a regression test left that goes red if the bug returns. Measures the named discipline, not generic care.
  role: exploratory
  verifier:
    hash: 2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2
    path: verify_footprint.py
plan_frozen_at:
  commit: ed3c5a0e02f4b1fe5d60047e1bc43b88a91be4b2
  path: plugins/humblepowers/skills/experiment-rigor/examples/rg-2x2/record.yaml
  timestamp: 2026-07-24 00:00:00+00:00
results:
  activation:
    arms:
      with_gate:
        ci:
          alpha: 0.05
          high: 0.0741
          low: 0.0
          method: wilson
        denominator: 48
        numerator: 0
      without_gate:
        ci:
          alpha: 0.05
          high: 0.0741
          low: 0.0
          method: wilson
        denominator: 48
        numerator: 0
    paired: true
    verdict: confirmatory_null
  footprint:
    arms:
      with_gate:
        ci:
          alpha: 0.05
          high: 0.8508
          low: 0.6122
          method: wilson
        denominator: 48
        numerator: 36
      without_gate:
        ci:
          alpha: 0.05
          high: 0.5164
          low: 0.2522
          method: wilson
        denominator: 48
        numerator: 18
    paired: true
    verdict: exploratory_signal
run:
  first_run_at: 2026-07-24 12:00:00+00:00
  hand_reason: 'the founding RG-2x2 was hand-orchestrated in fathom PR #15 (feat/rg-2x2) before this discipline existed; reconstructed here as the chain-root fixture, so no machine-readable ledger travels with it. ER-XCHECK is a measurement-tier WARN by design, not a defect.'
  source: hand
schema_version: 1
threats:
  construct_validity_proxy:
    statement: the proxy measures the named discipline (the correct plate), but the skills were never loaded -- the behavior was auto-generated from the model's own priors, so the positive footprint bypasses the skill machinery and holds only for disciplines within the model's latent reach (the attentive-driver-watching-the-wrong-risk caveat).
    status: residual
  contamination_familiarity:
    statement: models may have seen structurally similar planted-bug tasks in pretraining; not controlled for.
    status: residual
  generalization:
    statement: one task family, one turn, tested as system-prompt TEXT rather than the per-prompt hook that would be built; 'validates the mechanism' would overclaim.
    status: residual
  judge_bias:
    statement: a deterministic verifier on the executed artifact, no LLM-as-judge.
    status: controlled
  model_version_drift:
    statement: two unpinned model snapshots (haiku, sonnet) over the measurement window; the instrument can move underneath the run.
    status: residual
  nondeterminism:
    statement: sampling temperature above zero; one turn per trial, not repeated.
    status: residual
  prompt_format_sensitivity:
    statement: one fixed task template across arms; the register factor rewrote only the skill description field (bodies byte-identical, no new content words, length within 25%).
    status: controlled
  selection_exclusion:
    statement: no trials excluded; the full 96 are in the disposition.
    status: controlled
  token_length_confound:
    statement: the gate arms carried roughly 90 more system-prompt words; no equal-length no-decision control was run, so forced deliberation cannot be separated from any preamble / extra reasoning tokens. Possibly fatal to the causal reading.
    status: residual
tier: measurement
updates:
  certainty: low
  downgrade_reasons:
  - token_length_confound
  - nondeterminism
  - generalization
  posterior:
    belief: register (R) is null -- reg == ctrl in both tiers; the gate's forced deliberation raised the disciplinary footprint from 18/48 to 36/48 as an exploratory signal, even with a "none applies" verdict and no skill loaded
    grade: low
    method: beta_binomial_within
  prior:
    belief: imperative-register descriptions activate skills ~20x more (a field study on Claude Code skills)
    grade: low
    source: dispatch-field-memo
```
