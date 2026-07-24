# ADR-0007 — Experiment-rigor discipline: one rigid skill, gates carry the load

- **Status:** Accepted
- **Date:** 2026-07-24

## Context

A working session on craft-collection's dispatch produced a small A/B (RG-2×2:
a 2×2 register/gate factorial, 2 tiers, 6 tasks, 2 waves — 96 trials, $17). The
agent explained it in prose; three fresh, isolated frontier readers were given
the explanation plus a comprehension question. All three, independently,
reconstructed the narrative but flagged the same holes: the arithmetic did not
close (the text said 96 while 4×2×6 reads as 48 — the two waves were never
stated), the outcome ("disciplined behaviour") was illustrated but never
operationalized, the 75% / 37.5% figures carried no denominators, the
comparison behind them was inferred rather than asserted, a post-hoc finding was
presented as pre-registered, and no uncertainty was reported. The readers
behaved well; the text simply did not contain the methods.

The meta-lesson, made structural here: **uncertainty about effect size and
generalization is declarable and must be declared; uncertainty about what was
manipulated, where, and how it was measured is disqualifying and must be gated.**
A follow-up survey of four mature traditions (pre-registration and reporting
standards; FAIR/PROV/RO-Crate provenance; ML artifact documentation; eval
tooling and the validity critique) concluded: adopt the mature epistemology and
provenance vocabulary wholesale, build only a thin, tiered adaptation layer for
the agent-LLM case, and gate it mechanically — façade rigor is real and measured
(the Foundation Model Transparency Index fell 58→40; ~32k model cards ship with
empty critical sections), and tools die while flat files survive (Model Card
Toolkit archived, Neptune sunset). A synthesis brief chose the mechanism-first
skeleton on craft's conventions. This ADR records the delivery-form decision and
the invariants; the implementation spec
(`docs/specs/2026-07-24-experiment-rigor-skill.md`) implements it, and the two
research records live at
`docs/research/2026-07-24-experimental-rigor-and-comprehension-case.md` and
`docs/research/2026-07-24-four-traditions-survey.md`.

## Decision

### Delivery form

One rigid skill, `experiment-rigor`, inside the **humblepowers** plugin, beside
`test-driven-development` and `verification-before-completion`. The skill body is
thin; four stdlib scripts carry the load — `stats.py` (exact CIs, within-experiment
Beta-Binomial, paired/clustered SE), `validate.py` (the central gate), `render.py`
(derives the report, checks drift, walks the update chain), and `from_fathom.py`
(reads a fathom ledger into run-derived fields). Every load-bearing rule is a gate
that exits non-zero, never a section-presence tick. Records live where the work
lives (`docs/design/…` locally, or beside a fathom bank); the skill ships
machinery, never data.

### Bind, don't duplicate

- **fathom stays execution** — it owns the append-only ledger and `verify.py`.
  The record format is the contract: `from_fathom.py` reads the ledger and the
  run cross-check gate compares hand-written run-derived fields to the ledger
  rows. `from_fathom.py` reads the ledger directly; a fathom-side run-derived
  emitter is possible future work in the fathom repo, not part of this delivery.
  The discipline must survive fathom's absence — the comprehension case itself was
  a hand-run probe with no harness — so it cannot live inside fathom.
- **keel owns spec readiness** — the decision-tier frozen-design self-review
  binds keel role-generically: where a Definition-of-Ready gate is installed the
  frozen design passes it before spend, otherwise the temporal-anchor gate on the
  frozen record is the fallback. No DoR logic is duplicated.
- **choosing-tools** gains one registration row so dispatch shortlists the
  discipline at experiment-shaped task starts; negative space keeps it apart from
  `fathom-eval` (which owns "run the matrix").
- **mantis journal ingestion** — `render.py` emits the update/provenance block in
  the mantis journal-envelope shape; the record YAML is a tolerated superset. The
  spec verifies the ingestion parser tolerates the extra keys, and falls back to a
  strict envelope that links to the record if it does not — the standing
  journal-contract constraint (silent field / enum / required failure modes).

### Core invariants

- **record.yaml is the single source of truth; report.md is derived, never
  hand-edited.** `render.py` generates the report and embeds the canonical typed
  blocks; a drift gate (`render.py --check`) fails on any divergence.
- **Every load-bearing rule is a loud-failing gate.** `validate.py` exits 1,
  itemised, across schema+tier, design-reconciliation, temporal-anchor, run
  cross-check, stats-integrity plus the small-n CI refusal, drift/parity,
  link-resolution, threat-coverage, probe refusal, and the decision-tier
  comprehension gate. Presence, arithmetic, freeze, links, and well-formedness
  are gated; the correctness of a threat, a construct-validity judgement, or a
  GRADE rationale is held by review, not adjudicated by a script. Two of these
  gates are chronology/evidence checks whose residual trust is named, not hidden:
  the temporal anchor raises the cost of moving a goalpost but cannot detect a
  backdated commit (push-to-remote is the external anchor recommended at decision
  tier), and the comprehension gate enforces the evidence trail but cannot prove
  the reads were fresh — the same posture as keel's B2.
- **Standing deletion rule.** Any gate that degrades into a section-presence
  check is deleted, not tolerated. A new failure mode becomes a gate or a catalog
  row — never a new skill clause. Mechanism over prose: the body must not grow one
  clause per finding.
- **Tier ladder with a near-zero-cost probe.** probe (labels itself, refuses any
  confirmatory result or posterior) → measurement (pre-registration, disposition
  ledger, exact CI per cell, top threats, update block) → decision (confirmatory /
  exploratory partition with post-hoc quarantine, frozen-design review, GRADE, and
  a fresh-reader comprehension result). The probe's only formalism is
  self-labelling, so the discipline survives haste.
- **The comprehension gate's design intent is an out-of-class input** (fresh
  readers) — the strongest available answer to the same-class façade ceiling, but
  the validator cannot prove the reads were genuine or fresh. It enforces the
  contract and the evidence trail: a decision-tier record is unusable without a
  comprehension block recording each reader's four verbatim answers and a
  resolving per-reader transcript path. The genuineness and freshness of the reads
  are ceded to review, residual named — the same posture as keel's B2 (it raises
  the cost of forging a certification; it does not prove the pass was blind). The
  spawning automation stays out-of-plugin (a published plugin cannot import the
  local, gitignored cross-model harness), referenced role-generically.

## Alternatives considered

- **New dedicated plugin** — rejected: fragments the humblepowers dispatch
  surface, doubles eval/holdout overhead for one discipline, and forfeits free
  same-plugin references.
- **Two skills (design + report)** — rejected: the arc is one discipline; tier is
  a field, not a second trigger surface that poaches at report time.
- **Build inside fathom** — rejected: couples the discipline to one harness; it
  must survive fathom's absence and run on hand-executed probes.
- **Full JSON-LD / RO-Crate / PROV ontology** — rejected: semantic overhead at
  $17/run; adopt ~6 PROV terms as field names only.
- **Checklist skill, no validator** — rejected: empirically fails (FMTI 58→40;
  ~32k hollow model cards) — a template with no mechanical gate degrades to façade.
- **Renderer server / MkDocs / tracking DB** — rejected: tools die (Model Card
  Toolkit archived, Neptune sunset); a flat file plus one script survives.
- **Ship the comprehension spawner inside the plugin** — rejected: it would import
  local gitignored, key-from-mantis tooling and break on any other install; the
  contract ships in the validator, the automation binds role-generically.

## Consequences

- New invariants enter the guardrail set: record-is-source-of-truth (report
  derived), a loud-failing gate per load-bearing rule, the standing deletion rule,
  the small-n CI refusal, the temporal anchor, run cross-check equality, and the
  comprehension-gate-before-decision. Most are enforced by `validate.py` once
  built; until then they are `planned`, and the spec's enforcement-status table
  says so honestly rather than claiming a gate that does not yet run.
- `schema_version` starts at 1; `schema.json` is the canonical machine-readable
  per-tier field list and `SCHEMA.md` is generated from it (a sync gate asserts
  agreement); `validate.py` rejects unknown versions.
- The bridge reads the fathom ledger directly; no cross-repo edit is part of this
  delivery.
- The discipline is dogfooded: the founding RG-2×2 case is both the first node of
  the update chain and the acceptance fixture — the validator must catch its six
  known defects and pass the corrected record.
