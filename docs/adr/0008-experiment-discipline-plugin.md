# ADR-0008 — Extract experiment-rigor into an experiment-discipline plugin

- **Status:** Accepted
- **Date:** 2026-07-25

## Context

`docs/adr/0007-experiment-rigor-delivery.md` put the `experiment-rigor` skill
inside **humblepowers** and explicitly rejected a dedicated plugin on three
grounds: it would fragment the humblepowers dispatch surface, double the
eval/holdout overhead for one discipline, and forfeit free same-plugin
references. That call was right for what shipped. The wave that followed changed
each of the three premises, and the change lands before the branch has ever been
opened as a PR — so the residence can still be corrected by adding commits
rather than by migrating a released plugin.

The three grounds, each now inverted:

1. **"One discipline" no longer describes the scope.** The v1 skill covered
   agent-LLM small-n experiments. This wave adds a rung below `probe` — a
   prose-only *check* that applies to any evaluation act, including the ones
   nobody would open a record for ("is this faster", "which of these is better").
   The discipline's subject is now evaluation acts generally, not one experiment
   genre riding a process-discipline plugin's surface.
2. **The mechanism mass outgrew a skill slot.** humblepowers is a prose-discipline
   plugin: its other skills are bodies with trigger surfaces. `experiment-rigor`
   ships four stdlib-plus-PyYAML scripts, a machine-readable schema, three tier
   templates, two references, a dogfood example with its own freeze choreography,
   and two dedicated pre-commit hooks whose `files:` regexes name its paths
   directly. That is a plugin's worth of machinery living in a skill directory.
3. **The same-plugin reference bought nothing that a cross-plugin one does not.**
   The dispatch router already addresses skills by `plugin:skill` and already
   carries three different plugin prefixes; its test suite asserts only that an id
   *has* a plugin part. The skill directory is self-contained — it resolves its
   scripts, templates, and references relatively, never through the plugin root —
   so residence was never load-bearing.

## Decision

Extract the skill into a new plugin, **`experiment-discipline`**, sibling in shape
to `engineering-discipline` (manifest, README, CHANGELOG, `skills/`). The skill
keeps its name, `experiment-rigor`, and its frontmatter `description` stays
**byte-identical**: the sealed trigger holdout was sealed against that exact
surface with a birth baseline, and any description edit would force a reseal that
this wave does not buy. The holdout row records the re-home with the
byte-identical note, following that file's own precedent for a wave that moved a
skill without touching its trigger surface.

Three further decisions ride the extraction:

- **Scope widened to evaluation acts.** The plugin's subject is the act of
  evaluating and reporting on anything, tiered by decision weight. Small-n agent
  experiments remain the heavy end, not the definition.
- **A tier-0 rung, `check`, below `probe`.** Prose-only: no file, no gate, no
  validator. It names the minimal shape any evaluation act should carry in the
  response itself — method, metric, result(s) with denominators, conclusion, and a
  one-line "what this updates". It is guidance, deliberately flexible, and it does
  not change the entry criterion for the tiers above it: a record is still owed
  only when a decision rides on the result. The rung exists because the
  alternative to a cheap shape is not a rigorous one, it is an unstructured
  assertion.
- **A visibility convention, as an invariant.** Automation should make work
  fluid, never invisible. Whenever the frame engages at any tier, one austere,
  greppable, plain-text line is emitted at the top of the work product. The line
  is a **claim tied to an artifact**, not a badge: at `probe` and above it names
  the record path and is *generated from the record*, so it cannot drift from what
  it claims; at tier-0 it names `inline`, and its truthfulness is carried by the
  response containing the skeleton. The founding case supplies the reason this
  must be an artifact claim rather than a marker: the RG-2×2 measured the ritual
  declaration at 47/48 while the behavior it declared occurred 0 times, so a
  declaration with nothing behind it must be a detectable lie, not a decoration.

## Alternatives considered

- **Stay in humblepowers (the ADR-0007 status quo)** — rejected: all three
  premises that justified it have inverted, and the correction is free only while
  the branch is unopened; after release it becomes a user-visible migration.
- **Move into fathom** — rejected on the same ground ADR-0007 used and this wave
  reinforces: fathom owns scenario-blind execution and the ledger, while the
  discipline must run on a hand-executed check with no harness at all.
- **A standalone repository** — rejected: it would lose the shared gate suite
  (register linter, word budget, structural validator, AGENTS.md freshness, the
  test runner) that mechanizes this collection's quality claims, in exchange for
  an independence nothing needs.
- **Rename the skill while re-homing** — rejected: the trigger holdout, its birth
  baseline, the dev set, the correct-usage bank, and the router row are all keyed
  to `experiment-rigor`; renaming would spend the seal for cosmetics.

## Consequences

- New invariants: the **visibility convention** (an activation line, tied to an
  artifact, at every tier) and **description-stability under re-home** (a move may
  not edit a sealed trigger surface). The generated half of the visibility line —
  `probe` and above — is mechanizable and gets a generator plus a checker; the
  tier-0 half names no file and stays review-only and measured, not gated. The
  spec's enforcement table records which is which rather than claiming both.
- The marketplace gains a fourth plugin; installs stay individual, so the
  cross-plugin references between `choosing-tools` and `experiment-rigor` become
  ordinary role-generic references with the router id carrying the new prefix.
- humblepowers returns to the version it held before this wave. Its 0.9.0 and
  0.10.0 entries described a skill it will not contain and were never released, so
  they move to the new plugin's CHANGELOG as its birth entry rather than standing
  as a historical claim about humblepowers; the humblepowers CHANGELOG records
  only what actually changed there — the router row's cross-plugin id — and points
  at the new plugin.
- The tier-0 rung is guidance without a gate, which is a deliberate exception to
  the collection's mechanism-over-prose default. It is bounded: tier-0 makes no
  claim a gate could check (there is no artifact), and the standing deletion rule
  still applies to every gate above it. Whether the rung and the visibility line
  actually change behavior is not asserted — it is the question the wave's own
  measured experiment asks, governed by this discipline. That experiment carries a
  token-matched inert arm beside its hint arms, so the founding case's own declared
  near-fatal confound — extra preamble tokens masquerading as an effect — is
  controlled for the mechanism contrast rather than re-inherited wholesale by the
  first study this discipline governs.
- The measured experiment separates **firing** from **effect**, and the separation
  bounds what it can claim. Which prompts a candidate row would fire on is computed
  offline from the real router semantics and frozen as a table, so exposure is
  auditable before any spend; the paid run then delivers the injected text directly.
  The experiment therefore measures the effect of the hint *text* at
  router-realistic firing patterns. Whether the live `UserPromptSubmit` hook
  delivers that text inside a production spawn is a separate, unmeasured question,
  and it stands as a named precondition for shipping any row into production — not
  as an assumption this wave's result quietly rests on.
