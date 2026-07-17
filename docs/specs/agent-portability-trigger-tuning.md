# Trigger-tuning experiment — the three 0.00-holdout skills (2026-07-17)

- **Date:** 2026-07-17 (overnight autonomous run)
- **Skills:** toolkit-awareness, choosing-tools, python-engineering
- **Outcome:** all three tunings **reverted**. Simple description tuning did not
  fix these trigger gaps: one regressed on unseen data, one had no effect, one
  improved but stayed below the gate. A pre-registered A/B against fresh blind
  holdouts is what caught this.
- **Net shipped from this experiment:** nothing to the skill surfaces (correct
  outcome), plus this record and one user-approvable candidate (§ python-engineering).

## Why this was attempted

The 2026-07-16 eval run (`agent-portability-eval-run.md`) birthed 0.00 holdout
recall for these three skills on intent-paraphrase positives, and named
description tuning under the reseal protocol as the follow-up. Their trigger
descriptions were byte-identical to pre-wave, so the gaps predate the
portability work; this experiment tests whether wording alone closes them.

## Method (pre-registered before seeing any tuned result)

1. An **independent subagent, blind to any tuning**, authored a fresh sealed
   holdout per skill (6 positives spanning the full territory + 4 hard
   near-miss negatives from the adjacent owners). The blindness is structural:
   the author was given only a neutral territory brief — never the miss data,
   the current description, or the word "gap".
2. **A/B on the same fresh holdout:** run it on the **untuned** description
   (B0), then on the **tuned** description (B1). B0 isolates whether the
   current description already generalizes; B1−B0 isolates the tuning's effect
   on unseen data. Plus a tuned **dev** run for a larger-sample cross-check.
3. **Pre-registered ship criterion (fixed before results):** ship a tuning only
   when `B1 recall > B0 recall`, `B1 recall ≥ 0.8`, `B1 specificity ≥ 0.9`, and
   dev recall has not regressed — all four. Otherwise revert and record, with
   **no moving the bar after seeing results** (the exact discipline
   skill-authoring's sealed-holdout rule exists to protect).

The tunings themselves were principled, not string-chasing: each surfaced the
missing intent as concrete paraphrases, and two (toolkit-awareness,
python-engineering) added the negative space their descriptions were missing
(a skill-authoring rule-3 violation). Register lint, DESC_CAP, and word budget
all passed on the tuned versions.

## Results (fresh blind holdout, recall; proxy-TLS errors inflate variance — excl-err shown)

| skill | B0 untuned | B1 tuned | Δ | B1 specificity | tuned dev | verdict |
|---|---|---|---|---|---|---|
| toolkit-awareness | 0.67 (excl 0.80) | **0.33 (excl 0.50)** | **−0.34** | 0.75 (down from 0.83) | 0.79 (excl 0.83) | REGRESSED → revert |
| choosing-tools | 0.11 | **0.11** | **0.00** | 1.00 | 0.50 (unchanged) | NO EFFECT → revert |
| python-engineering | 0.56 (excl 0.62) | **0.67 (excl 0.71)** | **+0.11** | 1.00 (held) | 0.79 (excl 0.86) | IMPROVED but < 0.8 gate → revert (pre-registration) |

Fresh holdouts and the raw A/B logs are preserved in the session scratchpad;
the fresh holdouts were an experiment and were **not** sealed as canonical
sets (nothing shipped), so `evals/trigger/holdout/BASELINES.md`'s 2026-07-16
rows stand unchanged.

## Reading each result

- **toolkit-awareness — the tuning made it worse.** Adding the ownership
  paraphrases and (especially) the people-ownership / dispatch / skill-authoring
  negative space pushed the model to *withhold* on inventory questions it had
  been firing on: B1 recall fell to 0.33 and specificity to 0.75. The current
  (untuned) description generalizes better on the fresh holdout (0.67/0.80-excl)
  than the old spent holdout's 0.00 suggested — the 0.00 was specific to that
  set's phrasings, not a general weakness. **Keep the current description.**
- **choosing-tools — wording is not the lever.** Identical 0.11 on the fresh
  holdout tuned or untuned, and identical 0.50 on dev. The skill under-selects
  regardless of description; in the isolated single-plugin eval the model tends
  to answer dispatch prompts directly rather than load the skill. This needs
  design/dataset/harness attention (or is partly a measurement artifact of the
  headless single-plugin arm), not a trigger rewrite.
- **python-engineering — a real but marginal, sub-gate improvement.** Surfacing
  the audit/modernize-existing intent lifted unseen recall 0.56→0.67 (excl
  0.62→0.71), lifted dev 0.71→0.79, and held specificity at 1.00 (the
  TypeScript-modernization near-miss stayed correctly rejected). The direction
  is consistent across three measurements, so the lift is real — but 0.67 is
  below the 0.8 gate the untuned version also fails, and the point gain sits
  inside the (wide, error-inflated) CI. Per the pre-registered bar it does not
  ship autonomously.

## The python-engineering candidate (for your approval)

This is the one change worth a human decision. It is a strict improvement on
this evidence and also fixes a doctrine violation (the current description has
no negative space). To apply it, replace the `python-engineering` frontmatter
`description` with:

```yaml
description: >
  Modern Python engineering standards and best practices. Use this skill
  whenever a user wants to: scaffold a Python project, configure tooling
  (uv, ruff, ty, mypy, structlog, pytest, hypothesis, pydantic-settings,
  opentelemetry, pip-audit), set up pyproject.toml, src-layout, pre-commit,
  CI/CD, Docker; or audit and modernize an existing, inherited, or legacy
  project's tooling, configuration, and dev setup against current standards —
  whether the build, lint, or CI config has drifted, what is outdated or
  sub-par, or bringing an older project up to modern practice; or asks about
  Python architecture, packaging, testing, type checking, observability,
  security, async patterns, typing.Protocol, dependency injection, CLAUDE.md,
  or Cursor rules. Covers hexagonal architecture, functional core/imperative
  shell, property-based testing, snapshot testing, testcontainers, Trusted
  Publishers, and Sigstore. Not for explaining what a piece of Python does
  (comprehension), not for debugging a specific runtime bug, not for a
  throwaway one-off script with no project, and not for non-Python stacks.
```

If you accept it, it should carry a fresh sealed holdout + birth baseline (the
one used here, or a new one) recorded below the 0.8 gate with the honest note
that it is an improvement over the 0.56 untuned floor, not a gate-pass — the
same shape as the choosing-models 0.75 birth-baseline precedent.

## What this says about the gaps

The honest finding: **these three trigger gaps are not description-wording
problems** (or not only that). One skill's description is already better than
its old holdout implied; one is unmoved by wording; one improves only
marginally. Closing them properly is deeper work — richer dev datasets that
train the intent category, a look at why choosing-tools under-selects in
isolation, and possibly harness/measurement changes — not a one-night rewrite.
That is the follow-up to schedule, and it belongs to a human-steered round
(trigger surfaces are product-voice decisions), not an autonomous one.
