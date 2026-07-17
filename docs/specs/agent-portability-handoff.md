# Hand-off — agent-portability: what remains

- **Date:** 2026-07-16
- **Branch:** `dev/agent-portability` (on GitHub; based on
  `claude/craft-plugins-ai-compatibility-t8xceo`, which carries the certified
  spec + ADRs)
- **Spec:** `docs/specs/agent-portability.md` — status *ready (DoR passed)*,
  pre-mortem CERTIFIED (round 2); certification artifacts sit alongside it.
- **State:** all nine sections (§1–§9) implemented, one commit per section
  (`PR01/§1` … `PR09/§9`); every offline gate green at HEAD — 31/31 tests,
  ruff lint+format, register lint, word budget, structural validator,
  `gen_agents_md.py --check`.

Resume with: `git fetch origin && git checkout dev/agent-portability`, then
`uv run --no-project -- python scripts/run_tests.py` to confirm a green base.

## 1. Blocking before merge to main — run the evals (§3–§5 criteria)

The only unmet acceptance criteria in the implemented sections. This
environment has no authenticated `claude` CLI; each §3–§5 commit message
carries the same flag. On a machine where `claude` is logged in:

| Skill (touched by) | Trigger dataset | Sealed holdout |
|---|---|---|
| review-panel (§3) | yes | no (trigger-only) |
| compaction-survival (§3) | yes | yes |
| toolkit-awareness (§3) | yes | yes |
| evaluate-skill (§3) | yes | no (trigger-only) |
| choosing-tools (§4) | yes | yes |
| python-engineering (§5) | yes | yes |

refresh-stack is exempt by name (`disable-model-invocation: true`, no
dataset). planned-execution/choosing-models were not edited (§4 verified them
already neutral) — no eval owed.

Run per skill from the repo root (see `evals/README.md` and `evals/config.json`
for budgets/repeats; scores gate against `evals/trigger/holdout/BASELINES.md`):

```bash
uv run --no-project -- python evals/harness/run_triggers.py <skill>
uv run --no-project -- python evals/harness/grade_tasks.py <skill>   # correct-usage, where a task exists
```

Record the numbers in the merge PR description (the acceptance criterion), and
treat any recall drop below the holdout gate as a §3–§5 wording regression to
fix, not a baseline to bump.

## 2. Small verifications cheap to do locally

- `uv tool run pre-commit run --all-files` — the full hook chain (including
  the new `agents-md-fresh`) has only been exercised per-hook here, not as one
  mutating run (round-2 pre-mortem flagged this as unverified-offline).
- §7 floor against GitHub-by-URL: the fixture-consumer run here referenced the
  repo by local path. After this branch (or main) is on GitHub, repeat with
  `repo: https://github.com/grimaldost/craft-collection` + `rev: <SHA>`; then
  pin `adapters/pre-commit/craft-floor.yaml`'s `rev:` from `main` to a real
  tag/SHA.
- A quick manual smoke on one non-CC harness (Codex/Gemini/Cursor): open the
  repo, confirm the agent picks skills from `AGENTS.md` and can follow one
  SKILL.md end to end. This is a smoke, not the measurement (see §4 below).

## 3. Non-blocking advisories from the round-2 pre-mortem

Recorded in the spec's certification block; fold if worth the touch:

- **ADV-1:** the spec's `Output artifact(s)` header omits the §8 edit surface
  and §2 gate wiring (cosmetic completeness).
- **ADV-2:** already implemented (`language: script` shipped in
  `.pre-commit-hooks.yaml`) — no action.
- **ADV-3:** soften §6's "the existing tests import those symbols by name"
  (over-broad for `_load_payload`) — wording only.

## 4. The no-degradation A/B (the certification you asked for)

Goal: certify that the reworded plugins produce virtually the same response
quality as the current version — across model strengths and task scopes. Under
the method this is the next round: an **experiment spec** (Decide+Specify with
the eval/experiment DoR items in `docs/method/definition-of-ready.md` Part B —
estimand, reps/power, blinding, correctness oracle, pre-registered analysis),
blind pre-mortem, then the run. Sketch to start from:

- **Arms:** `main` (current) × `dev/agent-portability` (new), same model, same
  repeats; per touched skill run triggers, holdouts, and correct-usage
  (rubric judge + with/without baseline, Wilson 95% CIs — all already in
  `evals/harness/`).
- **Estimand:** per-skill delta in trigger recall / specificity and in
  correct-usage pass rate; "no degradation" = the new arm's CI overlaps the
  old arm's and recall stays at/above the holdout gate.
- **Model-strength grid:** repeat on 2–3 tiers via the runner's `model`
  parameter (`evals/config.json` sets the default).
- **Task-scope axis:** the tasks under `evals/tasks/` already span scopes; add
  scenarios only if a scope you care about is missing.
- **Multiple agent configurations beyond CC:** requires a second
  `AgentRunner` backend (the §8 seam exists for exactly this; ADR-0006 named
  it follow-up). Until one lands, off-CC parity remains a design claim —
  `docs/portability.md` states this scope honestly; don't claim measured
  parity without it.
- **Budget note:** dozens of headless spawns per skill × 2 arms × tiers —
  price it with `evals/config.json`'s per-run budget before firing.

## 5. Merge & release mechanics

- Merge shape is your call: the branch is already one-commit-per-§, so either
  a single PR (commits tell the story) or cherry-picked per-§ PRs match the
  spec's manifest.
- Versions/CHANGELOGs already bumped in-wave: session-workflow 0.15.0,
  humblepowers 0.6.0, engineering-discipline 0.2.0. After merge, CC installs
  pick up the update on `claude plugin update` (version-gated).
- After merge: close the loop per the method — run
  `docs/method/reflection-triage.md` over this wave (the recorded deviations
  below are its first inputs) and, if you keep the dogfooding loop, file a
  tool-feedback report into this repo's intake.

## 6. Deviations recorded during implementation (honest record)

1. §3–§5 evals not run in the implementing environment (item 1 above) — the
   one open acceptance criterion.
2. §9's register lint on `docs/` was scoped to the authored docs
   (`docs/portability.md`, `docs/adr`, `docs/method`, the spec): the verbatim
   pre-mortem artifacts trip the all-caps rule ("FM-9 MINOR …") and are
   non-editable records. Same intent, narrower scope than the literal
   criterion.
3. §4/§5 were smaller than specced: planned-execution, choosing-models,
   refresh-stack, and data-engineering-discipline were verified already
   harness-neutral and left untouched (the spec allowed exactly this for
   data-engineering-discipline; the others follow the same verified-no-edit
   logic).
4. Word-budget baselines bumped for six bodies (the fold's pre-authorized
   fallback), each named in its commit: compaction-survival 1391→1409,
   evaluate-skill 825→850, review-panel 1120→1129, toolkit-awareness 477→515,
   choosing-tools 762→771, python-engineering 2261→2314.
5. `.gitignore` now tracks `docs/adr|specs|method|portability.md` (the rest of
   `docs/` stays local-only, per the original policy's intent).

---

## Continuation — 2026-07-16, remote session (items closed and what they found)

Status per item above, worked in a managed remote environment where the
`claude` CLI **is** authenticated:

1. **Evals (item 1): run and recorded** — full results, environment notes,
   and attribution in `docs/specs/agent-portability-eval-run.md`; sealed
   holdout rows appended to `evals/trigger/holdout/BASELINES.md` (one per
   sanctioned read, per N29a). Short version: compaction-survival matches its
   baseline at 1.00/1.00 and evaluate-skill triggers pass at 0.96;
   python-engineering triggers pass on error-excluded recall (0.85);
   specificity is 1.00 everywhere; the three other sealed holdouts birth at
   0.00 recall on intent-paraphrase positives. A same-instrument pre/post-wave
   A/B (plus byte-comparison of all six descriptions) shows **none of the
   under-gate numbers is attributable to the wave** — the §3–§5 wording-
   regression clause has nothing to bite on. Follow-up named there:
   description tuning for toolkit-awareness / choosing-tools /
   python-engineering on dev evidence, then reseal + re-baseline.
2. **Cheap verifications (item 2):** full `pre-commit run --all-files` chain
   is green as one mutating run. The §7 floor was re-run against
   `https://github.com/grimaldost/craft-collection` by `rev:` SHA — clone,
   build, dirty-fixture fail, clean-fixture pass all correct — and
   `adapters/pre-commit/craft-floor.yaml` now pins that verified SHA (re-pin
   to a release tag at merge; the pre-portability plugin tags can't serve).
   The non-CC harness smoke remains open (no such harness installed here).
3. **Advisories (item 3): folded** — ADV-1 and ADV-3 are in the spec with the
   fold recorded in its certification block; ADV-2 had already shipped.
4. **The A/B experiment (item 4): still yours to spec**, with two measured
   inputs from this run to fold into its design: (a) correct-usage currently
   conflates activation with rubric-compliance — `with_activation_rate` was
   0.00 on every task, so the metric scores default behavior wherever the
   task prompt doesn't trip the trigger; (b) the intent-paraphrase holdouts
   expose a routing gap (ownership/dispatch/audit phrasings) that trigger
   tuning would target — spec the estimand so tuning and no-degradation
   claims don't read against the same sealed sets.
5. **Merge mechanics (item 5): untouched**, still your call.
