# Changelog — humblepowers

Notable changes to this plugin. Bump the `version` in `.claude-plugin/plugin.json`
with each release. History before 0.3.2 lives in git (`git log -- plugins/humblepowers`):
0.1.0–0.3.1 covered the initial five-skill port, the `planned-execution` skill (0.3.0),
and the honest-cross-tool-references + MIT-license pass (0.3.1).

## 0.4.2 — 2026-06-17

The debugging facet of the 2026-06-17 triage's reinforced "observe, don't infer"
cluster (4 reports / 2 arcs), plus the choosing-tools re-dispatch refinement. Body
only — no `description` changed, so no holdout re-seal. Factored, not triplicated: the
principle's canonical statement stays in `data-engineering-discipline` Axiom 2; these
skills state their own facet and cross-link by name.

### Changed

- `systematic-debugging`: Phase 1's "reproduce" step now makes **dynamic observation
  precede static theory** — for a behavior/regression question, run the failing path and
  read real output before hypothesizing from source — with an explicit exception for
  destructive / irreversible / not-yet-buildable paths (read and instrument first), so
  the rigid skill doesn't mandate "run it" where running is the wrong move. Same step
  adds **confirm the code that ran is the code you read** (resolve `module.__file__` +
  version; editable vs installed diverge silently), cross-linking
  `data-engineering-discipline` Axiom 2. Two new "Common shortcuts" rows — "I read the
  code, so I know what it does" and "I'm pretty sure it's X" (no run yet) — keep the
  inference tripwire descriptive rather than adding a second bright line. (From the
  `2026-06-17-di-incremental-debug-systematic-debugging` and
  `2026-06-17-v1-publish-wheel-fix-systematic-debugging` arcs.)
- `verification-before-completion`: a claims-table row — **an artifact ships right only
  when the built artifact is inspected directly**; a green editable/CI run may never
  build the wheel/image/bundle it stands in for (per
  `2026-06-17-v1-publish-wheel-fix-verification-before-completion#1`).
- `choosing-tools`: "When this runs" now states that **inside a long autonomous task the
  internal phase shifts (design→build→run→report) are direction changes too** — a cheap
  re-dispatch and a one-line naming of the active discipline, rather than riding the
  opening choice for hours (per `2026-06-16-model-tier-calibration#1`,
  `2026-06-16-context-size-calibration#1`).

## 0.4.1 — 2026-06-15

A `skill-authoring` correctness note (the prior triage's `#T8a` watch item); body
only, no description changed.

### Added

- `skill-authoring`: the description contract now warns that a plain-scalar
  `description` must not contain `: ` (colon-space) — YAML reads it as a nested
  mapping and the frontmatter silently breaks, collapsing the skill's recall to zero,
  caught only by `validate_plugins`. Quote it, use a `>` folded block, or an em-dash.
  Shifts the catch left from `evaluate-skill`'s measurement-side pitfall to authoring
  time (per `2026-06-10-humblepowers-build#5`). (`#T8b`, an Edit-tool anchor-hygiene
  note, was declined as a niche, single-report workflow item.)

## 0.4.0 — 2026-06-15

Close the regression-test gap the humblepowers-vs-superpowers eval found (N4): on a
small bug fix the worth-loading bar declines the full `test-driven-development` skill,
and the regression test gets skipped ~half the time (50–60% vs superpowers' ~90–100%).
This is a calibration **refinement, not a reversal** — the bar still gates skill
*ceremony*, but a bug fix's cheap, durable core (leave a red-green regression test) now
applies even when the full skill isn't loaded. Body/doctrine + the inert dispatch
injection only; no `description` changed, so no holdout re-seal. **Validated by the
dyno `humble-vs-super-v1` outcome eval (2026-06-15, n=10/arm on the two bug-fix
tasks):** `regression_test_present` rose from **50% (humble-only) / 60%
(stack-humble)** to **100% / 100%** — matching superpowers (90% / 100%) — while
`fix_correct` and `no_regression` held at 100%. With the economy lead already
established (smaller corpus, ~30–40% cheaper per trial), humblepowers now
Pareto-dominates superpowers on these tasks.

### Changed

- `verification-before-completion`: a bug fix is **not done without a regression test
  that red-greens against the bug** — the "Bug fixed" completion gate now requires the
  test, not just symptom-gone. A fix's durability is a claim like any other; the
  evidence is a test that fails without the fix.
- `choosing-tools` (the loading bar): a third rule of thumb — **declining a skill is
  not declining its cheapest core**; after a bug fix leave the regression test even
  when the full `test-driven-development` skill isn't worth loading. The bar gates
  ceremony, not cheap insurance.
- `choosing-tools` dispatch injection (`inject_dispatch.py`): the always-on protocol
  gains the regression-test-after-fix line (interactive sessions with
  `HUMBLEPOWERS_DISPATCH_INJECT=1`).

## 0.3.2 — 2026-06-14

`planned-execution` hardening from its first real-feature dogfood
(`2026-06-13-dyno-skilleval-design-build-run`, craft-collection feedback): a
design-locked build whose two-stage review caught two real defects but let a
dead-config runtime bug — a declared `max_turns` never plumbed to its consumer —
pass all three review layers and truncate 8/9 eval trials.

`brainstorming` picks up two refinements from the same dogfood batch
(`humble-vs-super-design`, `dyno-skilleval`).

### Changed

- `planned-execution`: the final review now includes an **integration trace** —
  every config field, limit, flag, or option the plan introduces is followed to a
  consumer and confirmed read end-to-end, not merely declared. Plan-fidelity review
  is blind by construction to wiring the plan itself omitted; this closes that gap.
  The pre-execution self-review gains the matching check (every introduced
  config/limit/flag is consumed by a task).
- `planned-execution`: added authoring/dispatch notes — a **strip-on-save** rule
  (author each import in the same step that first references it, or a format-on-save
  hook removes it before the later step uses it) and a **unit-batching** blessing
  (bite-sized means one action per step, not one subagent per step; batch tightly
  coupled small steps into one coherent unit that still runs the full review loop).
- `brainstorming`: design risk-surfacing now includes **resource-budget adequacy**
  — for work an agent or capped spawn will execute, sanity-check the turn/time/cost
  budget suffices (the exact gap behind the dyno `max_turns` truncation); and the
  question-flow principle softens to **one focused question per turn, batching
  orthogonal decisions for an expert user** via the host's question UI, rather than
  strict one-at-a-time. Both are body-only; the `description` is unchanged.

### Added

- `CHANGELOG.md` (this file) — prior history was git-only, which a CHANGELOG-based
  feedback reconciliation reads as never-shipped (per
  `2026-06-13-feedback-loop-multitool-run#1`).
