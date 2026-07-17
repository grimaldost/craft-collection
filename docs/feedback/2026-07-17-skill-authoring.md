# skill-authoring feedback — the reseal A/B caught an ineffective tuning

- **Date:** 2026-07-17
- **Tool/version:** humblepowers 0.6.0 (skill-authoring exercised from the
  working tree)
- **Context:** applied the description contract + register rules + sealed-holdout
  shipping requirement to tune three under-firing trigger descriptions
  (toolkit-awareness, choosing-tools, python-engineering), each A/B'd against a
  fresh blind holdout authored by an independent agent. Full write-up:
  `docs/specs/agent-portability-trigger-tuning.md`.
- **Outcome:** the doctrine worked exactly as designed — the sealed-holdout
  discipline caught that the tuning regressed one skill and no-op'd another
  before any of it shipped. Two small doc gaps surfaced.

## What worked

- **The sealed-holdout + pre-registered-bar discipline is the whole reason
  nothing bad shipped.** Untuned-vs-tuned A/B on a fresh blind holdout showed
  toolkit-awareness *regressing* (0.67→0.33) and choosing-tools unmoved
  (0.11→0.11); a naive "the wording looks better, ship it" pass would have
  shipped both. "Tuning pressure, not register, is what moves recall" held
  literally — and sometimes moves it the wrong way.
- **Rule 3 (negative space names every adjacent owner) is a good smell test.**
  Two of the three descriptions had *no* negative space; noticing that was what
  made the boundary problems (people-ownership vs installed-tool ownership;
  choosing-tools dispatch vs toolkit-awareness inventory) concrete.
- **The register linter caught a real banner** (a three-conjunction all-caps
  run) in the write-up doc — mechanical enforcement of the detectable subset did
  its job.

## Friction

- **[LOW] "Single sanctioned read" vs a reseal A/B's two reads is
  under-specified.** The BASELINES/`skill-authoring` rule says a holdout is read
  once at seal time. A reseal A/B legitimately reads the *fresh* holdout twice —
  untuned baseline (B0) and tuned (B1) — both *after* the tuning is fixed, so
  neither read informs the tuning. I reasoned this is compliant (the point is
  "never consulted *while tuning*", not "never read twice"), but the doctrine
  doesn't spell out the reseal-A/B case, so the compliance call is left to the
  reader.

## Misses

- **[LOW] No guidance on when a gap is NOT a wording problem (phase: doctrine
  scope).** choosing-tools was unmoved by any wording change (0.11 tuned or
  untuned, dev 0.50 both). skill-authoring frames under-triggering as a
  description-surface fix, but some gaps are dataset/harness/selection-behavior
  problems that no description edit reaches. A one-line "if an A/B shows zero
  movement, the lever is not the description — stop tuning and look at the
  dataset or the selection context" would have saved a tuning iteration.

## Vacuous gates

- None observed. The holdout gate was the opposite of vacuous — it is the gate
  that made the whole exercise honest.

## Proposed promotions / changes

1. **[LOW]** reseal A/Bs read the fresh holdout twice (B0 untuned + B1 tuned),
   both after tuning is fixed → add one clause to the shipping-requirement /
   holdout section clarifying that a reseal A/B is compliant: the bar is "never
   consulted while tuning", and reads on an already-fixed description do not
   spend the seal for overfit purposes. Home:
   `plugins/humblepowers/skills/skill-authoring/SKILL.md`.
2. **[LOW]** under-triggering is not always a wording problem → add a
   stop-condition: "if an untuned-vs-tuned A/B shows no movement, the lever is
   the dataset or the selection context, not the description." Home: same file,
   Evidence or Shipping-requirement section.
