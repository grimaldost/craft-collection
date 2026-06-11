---
name: skill-authoring
description: Author and revise Claude Code skills with calibrated trigger descriptions and eval-gated quality — the description is a trigger surface that competes on fit, not an advertisement that competes on volume. Use when creating a new skill, when an existing skill over- or under-triggers and the description needs rework, when adding negative space ("not for X — that is Y") or example trigger phrasings, when deciding whether a skill body is rigid (bright-line constraints) or flexible (judgment-delegating guidance), or when porting a skill from an imperative register to a neutral one. Covers the calibration doctrine — dense concrete triggers, explicit non-triggers naming the owning sibling, plain-declarative bright lines, descriptive failure-mode catalogs without identity pressure, and the shipping requirement of a trigger dataset with sealed holdout plus a correct-usage rubric for rigid skills. The register linter mechanically enforces the register rules. Not for measuring an existing skill's behavior (that is evaluate-skill) and not for deciding which installed skill to use on a task (that is choosing-tools).
---

# Skill Authoring

A skill competes for selection in a context window shared with every other
installed tool. There are two ways to win: describe your territory precisely,
or shout. Shouting works once — then every neighbor escalates, emphasis stops
carrying information, and selection quality degrades for the whole toolkit.
This doctrine is the first way, made enforceable.

This is a **rigid** skill: the description contract, register rules, and
shipping requirement are bright lines, each with a mechanical check.

## The description contract

The frontmatter `description` is a trigger surface. It has one job: let a
model holding only descriptions rank this skill correctly against its
neighbors — high when the task is the skill's, low when it is not.

1. **Open with a verb-led capability sentence.** What the skill does and
   produces, before any trigger list.
2. **Quote the triggers users actually type.** Concrete phrasings ("wrap up",
   "which tool should handle this"), task shapes, and situations — not
   abstract categories. Paraphrase variety beats repetition.
3. **Draw the boundary, then name the owner.** Every description ends with
   negative space: "Not for X — that is Y." Naming the sibling does two jobs:
   it stops the skill from poaching, and it routes the reader to the right
   place.
4. **No obedience language.** Descriptions never instruct the model to use
   them, never inflate stakes, never claim priority over neighbors. A
   description that needs to demand attention is compensating for triggers
   that fail to earn it.

## Selection and execution are different layers

The description decides *when* the skill loads. The body instructs *how* the
work proceeds once loaded. Keep the registers separate:

- A bright line in a body is content, stated plainly: "production code is
  written only against a test you have watched fail." Firm, testable, neutral.
- Identity pressure is not content: "you are rationalizing", "you do not have
  a choice", all-caps banners. These bully the reader's judgment instead of
  informing it, and they read as noise to anyone auditing the skill.
- Catalogs of known failure modes and rationalizations are valuable — keep
  them as *descriptive* tables ("common shortcuts and what they miss"), so a
  reader recognizes the pattern without being accused of it.

## Rigid or flexible — declare it

Every skill states which it is, near the top of the body:

- **Rigid**: bright-line constraints plus the verification step that proves
  compliance. For disciplines whose dominant failure mode is self-granted
  exceptions (TDD, verification before completion).
- **Flexible**: principles with judgment explicitly delegated — the skill says
  what to optimize for and trusts the reader to adapt.

The choice is part of the design, not the prose: a rigid skill with soft
constraints fails differently from a flexible skill with hard constraints,
and both fail.

## Register rules

The deny-list: imperative-obedience phrases, importance banners, and runs of
three or more consecutive all-caps words outside code — the patterns that buy
salience instead of fit. Emphasis budget inside a body: bold the one
load-bearing sentence of a section, sparingly. If a constraint feels like it
needs caps to hold, it needs a verification step or a gate instead — move the
enforcement to mechanism. Enforce the deny-list mechanically where you can:
craft-collection wires a register linter (`scripts/lint_register.py`) into
pre-commit; a standalone install applies the same rules by review until it
wires its own gate.

## Shipping requirement

A skill ships when all of these exist, not before:

1. **Trigger dataset** — balanced positives and negatives; the negatives
   include near-misses that sit in named siblings' territory.
2. **Sealed holdout** — authored at the same sitting as the dev set and never
   consulted while tuning the description. A holdout that informed tuning is
   dev data, not a holdout.
3. **Correct-usage rubric** (rigid skills) — tasks plus checks that the output
   actually followed the discipline, deterministic where possible.
4. **Gates pass** — recall, specificity, and correct-usage thresholds, run by
   a behavioral eval harness when one is available (craft-collection ships
   one: datasets under `evals/trigger/`, thresholds in `evals/config.json`,
   run mechanics owned by session-workflow's evaluate-skill). Standalone
   installs keep requirements 1–3 as authored artifacts and run them with
   whatever harness they have — the discipline is the contract, the harness
   is one implementation.

## References between tools

Skills reference other tools without depending on them. Four rules and a test:

1. **Same-plugin references are free** — the plugin installs as a unit.
2. **Cross-tool references are role-generic with a named example and a
   working fallback**: "when a registered model-tier policy is installed
   (e.g. pr-pilot's model-tiers), its thresholds win — otherwise these
   heuristics." Name the role, give the example, work alone.
3. **Artifacts never carry tool dependencies.** A plan or spec that embeds
   "REQUIRED SUB-SKILL: <tool>" locks the artifact to a toolchain; state the
   execution contract in the artifact itself instead.
4. **Bindings over assumptions** — when integration genuinely needs wiring,
   the user supplies it (a bindings table, a config entry); tools never hunt
   the environment for each other.

The degradation test: uninstall every other tool — the skill still produces a
correct, if less optimized, result.

## Evidence

The register question is measured, not aesthetic. The craft-collection record:
calibrated descriptions reach 0.95–1.00 trigger recall on current models, and
the one overfit description in the collection's history was caught by a sealed
holdout collapsing (1.00 on the dev set, 0.25–0.50 unseen) — tuning pressure,
not register, is what moves recall. The persuasion-style alternative rests on
a compliance study (objectionable-request compliance under social-influence
framings) whose outcome variable is not process adherence in agentic work;
treat its transfer here as unsupported until the register ablation says
otherwise.

## Authoring checklist

- [ ] Verb-led capability sentence opens the description
- [ ] Concrete trigger phrasings, with paraphrase variety
- [ ] Negative space names every adjacent owner
- [ ] No obedience language anywhere in the description
- [ ] Rigid or flexible declared; bright lines plain; catalogs descriptive
- [ ] Register deny-list clean (lint-enforced where a gate is wired)
- [ ] Cross-tool references are role-generic with fallback (degradation test)
- [ ] Dev dataset and sealed holdout authored together, before any tuning
- [ ] Correct-usage rubric for rigid skills
