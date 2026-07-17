# Spec — <feature/refactor name>

- **Date:** YYYY-MM-DD
- **Status:** draft | ready (DoR passed) | in progress | done
- **Audience:** <who/what reads this>
- **Output artifact(s):** <paths>

*Optional header field for a declared non-series round: `- **Phases:** Decide+Specify
(Decompose: skipped)` — when Decompose is explicitly named as skipped, `check-ready` (A4) relaxes
the PR↔section manifest requirement to absent-ok. A manifest that IS present is still fully
checked, everything else in Part A applies regardless, and the declaration is content the
pre-mortem can challenge — not an escape hatch (ADR-0014).*

## Context

Why this work, and what it builds on (link the relevant ADRs).

## Goal

One or two sentences: what this delivers.

## Gate commands

The exact commands that gate this work, named precisely (scope and excludes included) so
prompts and reviewers don't guess: e.g. `ruff check .`, `uv run pytest`, and the project's
type-check invocation. State *which* command, not "the linter".

## Non-goals

What this explicitly does NOT cover. Bounds scope so workers can't sprawl.

## Invariants touched

List every architectural invariant this work could affect (boundaries, locks,
immutability, schema contracts...). Each must already have an ADR; if not, write
the ADR first. *Naming these is a DoR requirement.*

## Enforcement status

| Invariant | Status | Gate/mechanism |
|---|---|---|
| <invariant key> | enforced \| review-only \| planned \| absent | <the gate, when enforced> |

*check-ready (A10): no prose may claim an invariant is "enforced" / "guaranteed" unless its
row here is `enforced`. Checked only when this table is present; a claim inside backticks, or
one negated ("not enforced", "to be enforced later"), does not fire.*

## Concept → module map

| Concept introduced/changed | Module / file it lives in |
|---|---|
| <concept> | `path/to/module` |

*Every concept must map to a home. A concept with no module is a DoR failure. Mark a new path
"(to be created)" and name it — full path, or bare basename when unique — in the body of the
§ that creates it (`check-ready` A5); in a greenfield spec that is every row.*

## Numbered sections

Each numbered section is a unit of work a single PR can cite. Keep them small and
single-concern.

### §1 <title>
What changes. **Acceptance criterion:** <the observable condition that means §1 is
done>.

### §2 <title>
What changes. **Acceptance criterion:** <...>.

*(Add sections as needed. Every section needs an acceptance criterion — this is
both a DoR check and each PR's exit gate.)*

*Ground factual claims with `path:line` anchors, repo-root-relative (`src/pkg/mod.py:NN`). A
backticked token on the same line right after an anchor IS its snippet: `check-ready` (A6)
requires it be an exact substring of that line — don't backtick prose emphasis or `...` elision
there. A bare anchor verifies only that the file and line exist; a claim-supporting anchor SHOULD
carry its snippet, so the gate verifies the evidence, not just the address. Cite a new ADR as
`docs/adr/NNNN-slug.md` using the next free number on your base, never a hardcoded guess.*

*Reuse notation: pin a reuse target as `**Model-on:** <backticked path>` or
`**Reuse:** <backticked path::symbol>`; `check-ready` (A9) resolves the path, and the symbol
when given — so a spec cannot say "model-on / reuse X" without X actually existing.*

*Anchor ranges: a multi-line citation is `` `path:lo-hi` ``; `check-ready` (A11) flags a range that
opens a bracket/brace/paren it does not close, so a citation cannot silently truncate a collection
literal mid-structure. Quote a literal complete or not at all.*

*Gate-adversarial examples: when the spec must QUOTE something the gate itself scans for — a
literal `Verdict:` line, a bare to-do placeholder token, an example `### heading` — put it inside a
code fence; fenced content is masked before every check, while the same example unfenced can
false-fail (A3) or shadow the real certification (B1).*

*Out-of-wave consumers: when a section MOVES, RENAMES, or RETYPES a symbol, or strips content from a
file, list every consumer beyond the import graph — scripts that regex/parse the file's TEXT
(docs-sync checks, doc anchors, tests reading it as data) and every READER of a retyped symbol — and
add each to that PR's file-list. (Not gated; the pre-mortem attacks it.)*

*Measurement / experiment specs: fill the optional `## Experiment design (Part B)` section below — the
eval/experiment DoR items (`definition-of-ready.md`, Part B) gate the axes it names.*

*Counting: a test-count tripwire counts pytest ITEMS (post-parametrize collection), not function
defs, and shows the parametrize expansion; enumerate code constructs by AST, never a bare text grep
(grep is a superset pre-filter only); pin both the UNIT and the AUTHORITY of any recount.*

## PR ↔ section manifest

| PR | Implements section | One concern? |
|---|---|---|
| PR01 | §1 | yes |
| PR02 | §2 | yes |

*Every section must be covered by exactly one PR, and every PR must cite exactly
one section. A many-to-one or uncovered section is a DoR failure.*

## Definition of Done (this spec)

Concrete, checkable conditions for the whole spec (beyond per-section criteria).

- Generated / mirrored / snapshot artifacts downstream of touched surfaces
  (consumer-reference mirrors, golden fixtures, lockfiles), each with its freshness gate —
  or the word "none": <enumerate them here; the pre-mortem challenges this declaration>

*Release-notes-in-wave: any section that adds public surface or changes behaviour carries its
CHANGELOG entry (and a migration-guide section, if consumer-facing) in the SAME wave — release-notes
completeness is a per-wave exit condition, not a terminal-audit cleanup; a consistency gate (e.g. a
docs-sync check) verifies cross-references, not completeness.*

## Experiment design (Part B)

*(Measurement / experiment specs only — delete this whole section for a code spec. The eval/experiment DoR
items (`definition-of-ready.md`, Part B) gate these axes; the reviewer certifies the design, `keel
check-ready` the certification. Fill the `<...>` placeholders; this is a `##` section, so it needs no
acceptance criterion and carries no anchors.)*

- **Estimand + unit of analysis:** <the effect measured, at what grain — per-item delta vs aggregate>
- **Reps / power & MEWD:** <N per arm; the minimum effect worth detecting; why N can detect it — a 1-rep delta is noise>
- **Blinding + held-constant factors:** <what is blinded; what is held equal across arms>
- **Correctness oracle (not "ran green"):** <what decides "correct", distinct from the run completing>
- **Measured-unit causal path:** <treatment end — the measured path READS what the treatment changes (not inert); measured-unit end — capabilities beyond the intended input enumerated, no side channel to the ground truth>
- **Enforcement of isolation invariants:** <each leakage/isolation invariant, and the buildable mechanism that enforces it, claimed by a numbered section/PR>
- **Pre-registered analysis plan:** <the analysis fixed before results are seen>

## Pre-mortem certification

*The externalized correctness pass (`pre-mortem-prompt.md`), certified by a fresh
reviewer who did NOT author this spec. `keel check-ready` does not pass until the
verdict is `CERTIFIED` (ADR-0002). A freshly-scaffolded spec is, correctly, not Ready.
Save the pass's returned output to the sibling `<spec-stem>.premortem.md` (header: spec path,
date, reviewer, `Spec-hash:` from `keel spec-hash`) and name it below — `check-ready` B2 verifies
a named artifact's existence, verdict agreement, and spec-hash currency. B2 raises the cost of
forging a certification; it does not prove the pass was blind — that residual trust stays named.*

- **Reviewer:**
- **Verdict:** not yet certified
- **Operator:** <required only when the Verdict is CONDITIONAL-CERTIFY — the named owner who accepts "ready modulo a named fix"; check-ready then passes with a WARN (B1). If the Operator applies the conditions, the verdict stays CONDITIONAL-CERTIFY with a discharge note — the operator close, definition-of-ready.md Part B>
- **Certification artifact:**
- **Date:**
- **Reviewed against:** <external dependency SHAs/versions reasoned against, if any>
- **Post-fold coherence:**
- **Failure modes considered & folded in:**

### Fold ledger

*Required when the certification claims a non-trivial fold (R1); a clean certify dozes: one row per folded finding so the post-fold delta is
reviewable. `check-ready` (A12) holds each `artifact:line` to a resolving anchor — it verifies the
fold was recorded against a real line, not that it is correct (that is the reviewer's job). A row's
anchor MAY carry a backticked snippet (`` `path:line` `snippet` ``): A12 then verifies the snippet
matches that line, so an in-range edit that moves the anchored content no longer decays silently. Leave the
header only (no data rows) and A12 dozes. The ledger must be the FIRST table under this `### Fold ledger`
heading — A12 reads only the first contiguous table, so a round-history / disposition table belongs in
its own section, not after the ledger here.*

| Finding | Target section | artifact:line | Confirmed |
|---|---|---|---|

---
*This template is structured so that most of the deterministic Definition-of-Ready
checks (`definition-of-ready.md`) pass by construction: numbered sections,
per-section acceptance criteria, the concept→module map, and the PR↔section
manifest are all required fields. The one field NOT satisfied by construction is the
pre-mortem certification — a non-author reviewer must sign it, which is the point
(ADR-0002).*

<!-- keel kit 0.13.1 -->
