# Pre-mortem prompt

A generative complement to the deterministic DoR checks. Deterministic checks find
structural gaps; the pre-mortem finds "this approach is wrong." Run it after DoR
Part A passes and before execution.

## When / who

- **When:** the end of Specify — the closing step of the DoR gate (2→3 boundary).
  The spec and its PR↔section manifest already exist; this runs before the spec
  becomes a runnable series and before any code.
- **Who:** a fresh agent that has not authored the spec (a stateless pass, so the
  judgment is externalized, not the author's own). keel's bundled
  `pre-mortem-review` agent can execute it, or run it as an orchestrator
  pre-series hook (e.g. pr-pilot's), or a manual pass.

## Prompt

```
You are reviewing a spec and its PR manifest before any code is written.

Assume this series shipped and then FAILED — the refactor broke something, the
scope sprawled, or the result was incoherent across PRs.

List the failure modes — all BLOCKER and MAJOR modes, plus any notable MINOR —
most likely first. For each:
- the failure (one line),
- the most likely cause (which section, which assumption, which missing invariant),
- the smallest change to the SPEC or a PR PROMPT that would prevent it.

Do not propose implementation. Only changes to the spec/manifest/prompts.

Ground every claim: read the referenced code and cite file:line; default skeptical.
Apply these grounding checks (the failure class the method most often misses):
- For each "reuse / port / model-on the proven X" instruction, READ X and confirm it
  handles THIS wave's shapes — "proven" means proven on the original caller's inputs.
- Scrutinize each "what already exists" claim by grepping that the seam is built.
- Source-ground capability claims: any reuse / capability / existence claim ("X does (not) exist", "X has no engine for this") is verified against the cited symbol source or its tests — not a consumer API doc or a generated reference alone — and tagged observed or inferred; an API-doc-only capability claim is a hypothesis until the source is read.
- Generated-artifact behavior on the target: a claim about how a GENERATED artifact behaves (generated SQL/DDL, a rendered template, codegen output, a serialized schema) is unverified until that output is executed or parsed on the real target/runtime — reading the generator's source is a hypothesis; flag such a claim as unverified-offline and name whether the offline tests share the target's dialect (identifier quoting, type coercion, reserved words are classic divergences a mock accepts).
- When a design supersedes a prior version, verify decisions against the committed
  register, not the superseded doc.

Grounding-completeness (DC1) — a claim the author "verified" is still wrong if the VIEW was
partial, stale, moved, or wrong-shaped. Attack each:
- Population, not exemplars: a "green on arrival / verified clean" claim must enumerate the FULL
  matched population (run the predicate over the real input), not the instances already seen; the
  scope read (src AND tests AND docs, and sibling repos) must be named.
- Whole-file, not projected: a file recorded "verified clean" from one section/table read is
  unproven for the rest — re-read each cleared file end to end.
- Stale / moved referent: a finding cited from a PRIOR pre-mortem carries its date and is
  re-verified against the current tree; a spec reasoning against an editable/external dependency
  must record its SHA, and you re-verify that SHA at run time and state it.
- Evidence-timeline on overturn: when you OVERTURN a prior claim, state the evidence timeline
  (current state, and when/why it differs) — never "X is wrong" alone; a moved referent can
  otherwise launder a false narrative into the spec.
- The verifier's own script: a purity grep, a count regex, or a fold checker is itself an
  artifact — give it the same grounding scrutiny (a column-0 regex blind to indented code, or a
  fence that reads CLEAN on command failure, is the same blind spot one level up).
- Stress-test recorded predictions: a predicted signal, an expected outcome, or a "this
  discriminates" claim recorded in the spec is a claim to ATTACK, not a fact — could the quantity
  predicted to vary actually floor/ceiling (every arm passes, or every arm fails) so the run
  measures nothing? For an eval/experiment spec, each measured criterion carries a one-line baseline
  expectation. And before hardening internal validity, ground the headline's key variable against the empirical record it needs (prior-run data/ledger, the reused instrument): if that record cannot supply the variation the study measures, the study is null on these instruments — run this feasibility check FIRST, a null here short-circuits the round.
- Instrument defeatability: for an eval/experiment spec, ask the cheapest way an agent sidesteps the planted difficulty (a tool, a shortcut, a grep) so the run measures nothing — distinct from the ceiling/floor question; an instrument an agent trivially bypasses yields a null for a reason the design never controlled.
- Experimental-design validity (measurement/experiment specs): attack the design AS an experiment, not just the subject — name the estimand and the unit of analysis (the per-item delta vs the aggregate); are there enough reps to detect the minimum effect worth detecting, or is a 1-rep delta just noise (a power question — distinct from the feasibility check above: power is whether N can detect the effect, feasibility is whether the record supplies the variable at all)? is the comparison blinded and are confounds held constant? is there a correctness oracle distinct from "it ran green"? was the analysis plan pre-registered, or chosen after seeing results?
- Measured-unit causal path & capability (specs that measure an agent/process): trace the causal arrow the study assumes from BOTH ends against code, not the spec's summary. (a) inert-treatment — does the measured path READ what the treatment changes? a store the measured call recomputes live (or never reads) makes the treatment inert: the study is mis-built, not null (distinct from feasibility, which asks whether the record HOLDS the variable; here it holds it but the measured path ignores it). (b) side channel — enumerate every capability the measured unit has BEYOND the intended input (tools, network, filesystem + cwd, prior/session state) and confirm none is a side channel to the ground truth that swamps the independent variable, making the result CONFOUNDED, not null; this sharpens instrument defeatability rather than replacing it (a grep of the ground truth is both a defeat and a side channel — the new teeth are the full-capability enumeration and the confounded-not-null framing). (c) enforcement mechanism — every isolation / safety / leakage invariant the spec asserts names a buildable enforcement mechanism claimed by a numbered section/PR, not a bare assertion and not a smoke that TESTS a jail no PR CREATES.

Mechanical consumers (DC2) — the spec models the logical design, but mechanical processes consume
the artifact too:
- Staged-files x in-place-gates: for every file the orchestrator's file-staging step STAGES into the worktree, enumerate
  which in-place gates will SEE it (`mypy .`, `ruff .`, repo-wide greps, pytest collection) and
  simulate each interaction (excluded / walked-clean / must-relocate).
- Diff-shape x lint: for any constraint on a diff's SHAPE (in-place / single-hunk / no-reorder),
  apply it to one representative file and run the repo's full lint+format gate; if the autofixer
  edits or rejects the literal form, the constraint contradicts the gate — rewrite it as
  line-content purity, not position.
- Cross-PR generated artifacts: if a PR regenerates a derived artifact (a generated API-doc mirror,
  an exported-symbol snapshot) from a source surface, check whether a LATER PR mutates that surface —
  if so the regenerator must re-run in/after the last mutating PR, and its freshness test runs on the
  FULL tree, not a per-domain subset. And if a freshness gate asserts that artifact in sync on EVERY change to its source (a committed mirror/lockfile/golden with a per-change test), the regenerate-after-the-last-mutating-PR option does not apply — it is not deferrable: each PR that perturbs the source regenerates its slice in that same PR. And the trigger runs BOTH directions: whenever the series TOUCHES a source surface, enumerate that surface's downstream generated/mirrored/golden artifacts and their freshness gates — a wave that plans no regeneration can still leave a mirror stale, and its freshness gate then fails at execution on a spec every pass certified.

Cross-artifact consistency (DC4-B) — artifacts that must agree (design, REVIEW command, CHANGELOG):
- Intent vs. executable: every test or gate the DESIGN names for the reviewer subset must appear in
  the executable mandated command — diff the named subset against the actual command; a public config
  or dataclass field appears in the generated mirror, so predict churn, not none.

Verify the transformation (DC3) — the fold/fix is an unverified, instance-scoped delta:
- Per-finding fold ledger: require a finding -> target -> artifact:line -> confirmed row per folded
  finding; nothing else reviews the post-fold delta.
- Fold-scope recursion & class-not-instance: scope each fix to the whole defect CLASS (sweep the
  artifact for siblings), not the cited instance; the SECOND pass attacks the FIRST pass's folds.

Counting — does each test-count count pytest ITEMS (post-parametrize), not function defs? Is each
code construct enumerated by AST, with grep only as a superset pre-filter?

Emit findings as a YAML list, one entry per failure mode, then the prose. Each mode also names its cheapest disconfirming test — the one observation that would confirm or refute it (distinct from smallest_fix, which prevents the mode; and from the stress-tested predictions above, which attack the spec's own claims) — so a predicted-but-dead risk is closed by evidence, not left as a worry:
  - id: FM-1
    severity: BLOCKER      # BLOCKER | MAJOR | MINOR
    evidence: path/to/file.py:line
    smallest_fix: "<one-line spec/prompt edit>"
    blast_radius: "<required when the smallest_fix touches shared/global config (an addopts line, a repo-wide marker, a schema default): one line naming what else the fix reaches>"
    disconfirming_test: "<the cheapest observation that would confirm or refute this mode>"
    consumed_input: "<required when the mode predicts a cross-artifact coupling (changing X breaks / drifts / regenerates Y): the concrete input the dependent actually consumes (installed symbols / packaging metadata / a generated file / a gate's scan surface), verified by READING that consumer — a coupling that cannot name its consumed input is a hypothesis to close via its disconfirming_test, not a MUST>"
    target_section: "section N"

Also return, when applicable: an optional `cleared:` list — claims you verified and found CORRECT, each with its cite — so a cleared risk is recorded as a confirmation rather than prose that reads as an unapplied fix; on CONDITIONAL-CERTIFY, a structured `conditions:` list (each condition a named fix of at most two lines), so multi-spec synthesis is collation, not interpretation; and an `Unverified-offline: <N>` count on the line immediately preceding the terminal verdict line — every directive that requires EXECUTION (the autofixer simulation, post-parametrize collection counting, AST enumeration) that your runner cannot execute leaves its claim tagged unverified-offline, and N is that count.

Convergence (so hardened verification stays bounded): a pass STOPS when it surfaces zero new
BLOCKER/MAJOR findings; emit CONDITIONAL-CERTIFY when only named MINOR fixes remain (ready modulo a
listed <=N-line fix), rather than forcing another full round.

Rising bar (round >=2): on a re-review the bar for BLOCKER/MAJOR rises — a finding is blocking only if it plausibly corrupts the decision the spec gates, not merely improves the spec. A round that surfaces only nice-to-haves is CERTIFY-with-advisories (fold them as advisories), not another full round; do not manufacture a blocker to justify a pass.

Re-gate posture (round >=2, the resolution audit): inputs are the revised spec plus the prior round's verdict record; FIRST audit each prior finding to RESOLVED / PARTIALLY-RESOLVED / UNRESOLVED with current-text evidence, THEN hunt fold-introduced defects (the second-pass rule above) under the rising bar; a fold that silently narrowed a promoted item is UNRESOLVED, not resolved.

SERIES-pass checklist (when this is the SERIES pass over a decomposed PR set, attacking execution reality a DESIGN pass cannot see): base-branch content reality — confirm the base branch actually CONTAINS the infra/symbols the series consumes, not merely that a base exists (a series on the wrong base reads green and builds nothing); per-PR gate x contract-test interactions — a gate or contract test one PR adds may trip every later PR, so simulate it across the series, not just its own PR; cross-prompt contract drift — when PR prompts are multi-authored, diff the contract one prompt emits against what the next consumes; decomposition completeness — every headline property and referenced asset the plan asserts is BUILT by a named PR (a "resumable" or "fallback" with no implementing PR ships as prose), and each acceptance test is ABLE to prove its invariant (a stub cannot prove a real-process property).

<paste: the spec + the PR↔section manifest>
```

## Output handling

You are read-only: RETURN your findings, ending with a machine-greppable last line
`PREMORTEM-VERDICT: <CERTIFIED | CONDITIONAL-CERTIFY | NEEDS-REVISION>` so a caller can gate without
parsing prose — do not write the spec yourself. State your reviewer identity after the verdict
token on that same line (the bundled agent states `pre-mortem-review@<keel version>` from its
identity line), so a cached or stale copy self-announces on every verdict it returns. Your final
message is the artifact the caller saves verbatim (`<spec-stem>.premortem.md`, B2); recording the
`## Pre-mortem certification` block is the caller's step — do not report your own read-only-ness
as a deviation. The caller folds and records: fold the proposed
changes back in **from the structured findings list** — apply each `smallest_fix` to its
`target_section` mechanically. Re-ground each proposed fix first: a `smallest_fix` is a hypothesis, not an instruction — verify it against the code before folding, since folding a wrong fix verbatim ships the bug it named. Then run a **post-fold coherence
re-read**: read each edited artifact end to end and confirm every finding was applied
consistently across ALL of its sections (Task / pre-read / Process / file-list); for any
finding that NARROWED scope (removed a deletion / relocation / file), re-derive every
dependent count (blast radius, file-list, DoD counts) and reconcile contradictions. This
post-fold hop is where a fix lands in one section while a contradicting instruction
survives in another — nothing else reviews the delta. The re-read also hunts the fold's OWN errors: re-ground each NEW or REWORDED claim the fold added (not only the findings it resolved), since a multi-finding fold can introduce a newly-introduced claim that is itself wrong; and when the fold PIVOTS the spec onto a new premise (not just a narrowed scope), re-verify the new premise's linchpin against code, since the pivot rests on a mechanism the original never used.

The caller records the verdict in the spec's `## Pre-mortem certification` block: `CERTIFIED` once no
blocking failure mode remains (else leave it uncertified and list the outstanding modes),
with a `Reviewer:` and a `Post-fold coherence:` line. The pre-mortem is **required** — DoR
does not pass without a recorded certification by a non-author reviewer (`keel check-ready`
checks for it, B1). Its findings frequently become new DoR checks — the loop closing again.
