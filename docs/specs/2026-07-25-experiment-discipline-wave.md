# Spec — the experiment-discipline wave: re-home, tier-0, visibility, and the detector experiment

- **Date:** 2026-07-25
- **Status:** ready (DoR passed, CONDITIONAL-CERTIFY r4; operator accepts C1-C4 at their named PRs)
- **Audience:** implementing agents + reviewer
- **Output artifact(s):** `plugins/experiment-discipline/` (manifest, README, CHANGELOG, `FREEZE.md`, and the re-homed `skills/experiment-rigor/` tree); edits to `.claude-plugin/marketplace.json`, `README.md`, `.pre-commit-config.yaml`, `.github/workflows/validate.yml`, `evals/config.json`, `scripts/word_budget.json`, `AGENTS.md`, `evals/trigger/holdout/BASELINES.md`, `plugins/humblepowers/CHANGELOG.md`, `plugins/humblepowers/.claude-plugin/plugin.json`, and `plugins/humblepowers/skills/choosing-tools/scripts/router_rules.json`; the new `references/report-skeleton.md`; the activation-line generator and checker in `render.py`; the schema v1.1 `contrasts[]` extension across `schema.json`, `validate.py`, and `SCHEMA.md`; a new tier-0 task and rubric under `evals/tasks/experiment-rigor/`; and the detector experiment under `evals/experiments/act-hint/` (bank, rules, firing-table generator and frozen table, oracle, labeled oracle-validation set, runner, frozen `record.yaml`, derived `report.md`).

## Context

The `experiment-rigor` skill shipped in humblepowers 0.10.0 on this branch, which
has never been opened as a PR — so its residence is still correctable by adding
commits. `docs/adr/0008-experiment-discipline-plugin.md` records the decision to
extract it into a new `experiment-discipline` plugin, widen the scope from
agent-LLM small-n experiments to evaluation acts generally, add a prose-only
tier-0 rung, and adopt a visibility convention. That ADR supersedes the residence
half of `docs/adr/0007-experiment-rigor-delivery.md`; every other v1 invariant
carries over unchanged.

The chain root is in-tree: the founding RG-2×2 record
(`plugins/humblepowers/skills/experiment-rigor/examples/rg-2x2/record.yaml:6`
`rg-2x2-register-gate`) reports its confirmatory `activation` outcome at 0/48 in
both arms while the ritual declaration it asked for was emitted in nearly every
run. That gap is the design constraint for this whole wave: a declaration is not
evidence, so the visibility line must be tied to an artifact (§3), and the
detector's primary outcome must never score a line on its own (§5).

**Construct honesty, stated once and carried throughout.** The detector measures
**the effect of an injected hint delivered at router-realistic firing patterns**.
Firing is computed offline and frozen (§5); the paid run delivers the injection
directly. Whether the live `UserPromptSubmit` hook delivers that same text inside a
production spawn is *not* measured here — it is a named precondition for any future
production rollout of a row, recorded in §6's follow-up and in ADR-0008.

## Goal

Re-home `experiment-rigor` into a new `experiment-discipline` plugin with its
trigger surface byte-identical, add the tier-0 `check` rung and the
artifact-tied visibility line, extend the record schema with the paired-contrast
machinery small-n arm comparisons actually need, and answer — under the
discipline's own measurement-tier gates — whether an advisory evaluation-act hint
changes behavior at router-realistic firing patterns.

## Gate commands

- `uv run --no-project --with pyyaml -- python scripts/run_tests.py` — every
  `test_*.py` under `plugins/` and `evals/`
  (`scripts/run_tests.py:24` `SEARCH_DIRS = ('plugins', 'evals')`).
- `uv run --no-project --with pyyaml -- python scripts/validate_plugins.py` —
  structure, frontmatter, caps, references, word budget; also marketplace/manifest
  description equality (`scripts/validate_plugins.py:78` `description differs from its`).
- `ruff check .` and `ruff format --check .` — CI runs both before the register linter
  and the tests (`.github/workflows/validate.yml:20` `run: ruff check .`), and pre-commit
  runs the autofixing pair locally. This wave adds six Python files, so the divergence
  would otherwise surface only as an unexpected reformat or a CI red on a branch whose
  checklist read green.
- `uv run --no-project python scripts/lint_register.py` — register doctrine
  (`scripts/lint_register.py:34` `DEFAULT_SCOPE = ROOT / 'plugins'`).
- `uv run --no-project python scripts/word_budget.py` — the per-body ratchet.
- `uv run --no-project python scripts/gen_agents_md.py --check` — index freshness.
- `uv run --no-project python scripts/ascii_runtime_lint.py` — the non-ASCII
  runtime-string ratchet (`scripts/ascii_runtime_lint.py:43` `ascii_lint_baseline.json`);
  files absent from the baseline are held at zero, which constrains §3's line
  format and §5's oracle (its language-specific patterns live in JSON data, not in
  Python literals).
- The record gates `validate.py` and `render.py --check` run in pre-commit over
  staged record paths; both hooks' `entry:` and `files:` regexes currently name the
  old location (`.pre-commit-config.yaml:65` `plugins/humblepowers/skills/experiment-rigor`)
  and are repointed in §1.
- Pre-commit hooks **skipped on this machine** under the Windows Application
  Control policy, with the user's standing agreement: `check-merge-conflict`,
  `check-added-large-files`, and `check-json`.
- **One scoped, one-commit exception:** the stage-1 freeze commit in §5 (and the v1
  precedent) skips `experiment-rigor-validate` for that single commit, because a
  record cannot name its own SHA before the commit exists. `SKIP=experiment-rigor-validate git commit`
  is the sanctioned form; stage 2 restores the gate and the record must then pass it.
  This is a per-commit skip, never an addition to the standing skip list.

## Non-goals

- No edit to the skill's frontmatter `description` — byte-identical, so the sealed
  holdout and its birth baseline stay valid; a reseal is out of this wave.
- No skill rename, and no second skill.
- **No edit to `inject_dispatch.py` or `router.py` at all.** The detector never
  drives the live hook: firing is computed offline by a generator that reproduces
  the router's semantics, and the paid run delivers the injection directly. The
  only humblepowers change in this wave remains the router row's id prefix.
- No edit to `evals/harness/claude_runner.py`. Its real surface already suffices:
  the prompt is fed on stdin (`evals/harness/claude_runner.py:296` `input=prompt`),
  so a prompt-prefix injection needs no new parameter, and one plugin dir
  (`evals/harness/claude_runner.py:202` `plugin_dir: str | None`) is all the
  detector loads.
- No LLM judge anywhere in the detector: `verify.py` alone scores the runs, so
  `judge_bias` is recorded controlled and no judging line item appears in the cost.
- No claim about live-hook delivery in production spawns (see Context).
- No JSON-LD stack, no hosted anything, no cross-repo edit.

## Invariants touched

From `docs/adr/0008-experiment-discipline-plugin.md`: the **visibility convention**
and **description-stability under re-home**. Carried over from
`docs/adr/0007-experiment-rigor-delivery.md` and re-anchored at the new path:
record-is-single-source-of-truth, a loud-failing gate per load-bearing rule, the
pre-registration freeze, declared-cells reconciliation, the small-n CI refusal,
threat coverage, and the standing deletion rule. New this wave: **frozen-material
integrity** (every experimental material — bank, rules, firing table, oracle,
labeled validation set — is hashed into the frozen record, so a post-freeze edit is
detectable) and **freeze durability** (a freeze commit stays reachable). Existing
repo invariants this wave moves under: structural marketplace validity and
description sync, register doctrine, the word-budget ratchet, AGENTS.md
derived-artifact integrity, the ASCII runtime ratchet, and the sealed router budgets
(`plugins/humblepowers/skills/choosing-tools/scripts/test_router.py:59`
`id must be plugin:skill`).

## Enforcement status

| Invariant | Status | Gate/mechanism |
|---|---|---|
| structural marketplace validity + description sync | enforced | `scripts/validate_plugins.py` in pre-commit + CI |
| register doctrine | enforced | `scripts/lint_register.py` in pre-commit + CI |
| word-budget ratchet | enforced | `scripts/validate_plugins.py` reading `scripts/word_budget.json` |
| AGENTS.md index freshness | enforced | `scripts/gen_agents_md.py --check` in pre-commit + CI |
| ASCII runtime-string ratchet | enforced | `scripts/ascii_runtime_lint.py` in pre-commit |
| router id well-formedness + sealed budgets | enforced | `test_router.py` under `scripts/run_tests.py` |
| record-is-source / report derived (new path) | enforced | `render.py --check` pre-commit hook, repointed in §1 |
| the v1 record gates (`ER-PREREG`, `ER-RECON`, `ER-STATS`, `ER-SCHEMA`, `ER-THREAT`, `ER-PROBE`, `ER-PARITY`, `ER-ANCHOR`, `ER-XCHECK`, `ER-COMPREHEND`) | enforced | `validate.py` pre-commit hook, repointed in §1 |
| description-stability under re-home | planned | §1 byte-comparison test against a committed pre-move blob |
| freeze durability (the freeze commit stays reachable; a depth-1 clone fails loud, never skips) | planned | §1 keep-ref tag per freeze commit + `fetch-depth: 0` in CI |
| both record hooks select every travelling record path | planned | §1 guard tests over both `files:` regexes, including `evals/.*/record.yaml` |
| visibility line at `probe` and above | planned | §3 `render.py --activation-line` generator + `--check-activation-line` checker |
| visibility line at tier-0 (`inline`) | review-only | no artifact to resolve; §2's tier-0 correct-usage task, and measured in §5/§6 |
| tier-0 skeleton shape | review-only | guidance by design (ADR-0008); measured, not gated |
| paired-contrast integrity (estimate, SE, and interval all recomputed from per-cluster counts) | planned | §4 `ER-STATS` extension recomputing `contrasts[]` via `stats.paired_difference` and the new `stats.paired_interval` |
| frozen-coordinate durability (a record's freeze survives a rename) | planned | §1 lands `plan_frozen_at.path`, its reader in `check_prereg`, and the acceptance-fixture adjustment, and sets the value for the moved record |
| frozen-material integrity (bank, rules, firing table, oracle, labeled set) | planned | §5 material SHAs in the frozen record, re-verified in §6 |
| detector isolation (fresh spawn per run, no shared state) | planned | §5 runner asserted against `--no-session-persistence` |
| detector length control (wide vs inert: same firing rows, same position, estimated tokens within ±5%) | planned | §5 test over the frozen firing table |

## Concept → module map

| Concept introduced/changed | Module / file it lives in |
|---|---|
| New plugin manifest | `plugins/experiment-discipline/.claude-plugin/plugin.json` (to be created) |
| New plugin README | `plugins/experiment-discipline/README.md` (to be created) |
| New plugin CHANGELOG (birth entry) | `plugins/experiment-discipline/CHANGELOG.md` (to be created) |
| Freeze choreography document (restored) | `plugins/experiment-discipline/skills/experiment-rigor/examples/rg-2x2/FREEZE.md` (to be created) |
| Re-homed skill body | `plugins/experiment-discipline/skills/experiment-rigor/SKILL.md` (to be created) |
| Re-homed mechanism (validator, renderer, stats, bridge, tests) | `plugins/experiment-discipline/skills/experiment-rigor/scripts/` (to be created) |
| Frozen-coordinate pin, its reader, and the fixture that exercises it | `plugins/experiment-discipline/skills/experiment-rigor/scripts/test_acceptance_rg2x2.py` (to be created) |
| Re-homed templates, schema, references, dogfood example | `plugins/experiment-discipline/skills/experiment-rigor/templates/` (to be created) |
| Marketplace registration | `.claude-plugin/marketplace.json` |
| Root install/layout documentation | `README.md` |
| Record-gate hook paths | `.pre-commit-config.yaml` |
| CI checkout depth (freeze reachability) | `.github/workflows/validate.yml` |
| Skill→plugin eval mapping | `evals/config.json` |
| Word-budget baseline key | `scripts/word_budget.json` |
| Generated discovery index | `AGENTS.md` |
| Holdout re-home note and provenance re-anchor | `evals/trigger/holdout/BASELINES.md` |
| Router row cross-plugin id | `plugins/humblepowers/skills/choosing-tools/scripts/router_rules.json` |
| humblepowers CHANGELOG + version rollback | `plugins/humblepowers/CHANGELOG.md` |
| Tier-0 `check` rung reference and its boundary rule | `plugins/experiment-discipline/skills/experiment-rigor/references/report-skeleton.md` (to be created) |
| Tier-0 correct-usage task and rubric | `evals/tasks/experiment-rigor/` |
| Activation-line generator + checker | `plugins/experiment-discipline/skills/experiment-rigor/scripts/render.py` (to be created) |
| Schema v1.1 contrast + cluster shapes | `plugins/experiment-discipline/skills/experiment-rigor/templates/schema.json` (to be created) |
| Contrast recomputation gate | `plugins/experiment-discipline/skills/experiment-rigor/scripts/validate.py` (to be created) |
| Detector arm rule variants | `evals/experiments/act-hint/rules/` (to be created) |
| Detector task bank | `evals/experiments/act-hint/bank.json` (to be created) |
| Offline firing-table generator and frozen table | `evals/experiments/act-hint/firing_table.py` (to be created) |
| Detector frozen oracle and its language patterns | `evals/experiments/act-hint/verify.py` (to be created) |
| Oracle-validation labeled set | `evals/experiments/act-hint/oracle_labels.json` (to be created) |
| Detector arm runner | `evals/experiments/act-hint/run_arms.py` (to be created) |
| Detector pre-registration and derived report | `evals/experiments/act-hint/record.yaml` (to be created) |
| Detector finalize step | `evals/experiments/act-hint/finalize.py` (to be created) |

## Settled decisions (bound)

- **Plugin name and skill identity.** Plugin `experiment-discipline`; skill stays
  `experiment-rigor`; frontmatter `description` byte-identical.
- **No reseal is owed.** The sealed holdout measures the *description* surface
  (trigger recall), which is unchanged byte-for-byte; the router's own sealed sets
  contain zero experiment-rigor cases, so the id-prefix edit cannot move them. §1
  adds the re-home note to the holdout row following the precedent at
  `evals/trigger/holdout/BASELINES.md:14` (a row annotated byte-identical), and
  re-anchors that row's provenance cell — which currently names the version this wave
  deletes (`evals/trigger/holdout/BASELINES.md:18` `experiment-rigor`) — to the seal's
  commit SHA plus `experiment-discipline 0.1.0`.
- **CHANGELOG mechanics.** humblepowers 0.9.0/0.10.0 were never released and
  describe a skill humblepowers will not contain; their content relocates to
  `plugins/experiment-discipline/CHANGELOG.md` as the `0.1.0` birth entry (with the
  dangling `FREEZE.md` mention repaired, not carried over). humblepowers rolls back
  to **0.8.0** and gains one entry for its only real change — the router row's
  cross-plugin id — which doubles as the pointer to the new plugin.
- **Tier-0 rung name.** `check`, glossed "the structured check". It never appears
  as a `tier:` field value.
- **Router cross-plugin naming is supported** — verified: ids are opaque
  `plugin:skill` strings and the dataset lookup splits the prefix off
  (`plugins/humblepowers/skills/choosing-tools/scripts/test_router.py:45` `split(':', 1)[1]`).
- **Firing is decomposed from effect** (the structural decision). Arm rule files are
  *inputs* to an offline generator that **drives the real router read-only** — it
  imports `router`, calls `load_rules(<arm rules file>)` (the path parameter the
  function already accepts), `route`, and `hint_line`, and applies the hook's own
  pre-filter constants and skips identically
  (`plugins/humblepowers/skills/choosing-tools/scripts/inject_dispatch.py:52`
  `MIN_WORDS = 4`, its companion character floor, the slash-command skip, and the
  synthetic-prefix skip) — against the frozen bank. Importing is not editing, so this
  sits inside the no-edit non-goal. Fidelity then comes free and by construction rather
  than from an enumeration an implementer could under-copy: the format-category strip,
  the 4000-character truncation, lowercasing, the order-preserving dedup and
  three-word cap on echoed matches, the ASCII collapse that only bites the PT-BR half,
  and the join across candidates are the router's own behavior, not a checklist.
  It emits a per-arm × per-prompt **firing table**: whether an
  injection fires, which candidate ids the arm produces (so displacement is visible,
  not silent), the injected text id, and its estimated token count. A prompt too short
  to clear the hook's floor appears as a visible "no injection in any arm" row rather
  than a silent hole. Firing is therefore mechanical, free, and auditable before a cent
  is spent.
- **Effect is the paid experiment.** The runner delivers each arm's injected text
  **directly**, prepended to the prompt fed on stdin
  (`evals/harness/claude_runner.py:296` `input=prompt`), at a single frozen insertion
  point. No plugin-hook dependency, no harness change, one `--plugin-dir`
  (`plugins/experiment-discipline`, so the skill is loadable). The inert arm is then
  trivially buildable: the same firing rows as wide, a different injected text.
- **Detector runner: the in-repo craft harness**, not a fathom bank — the outcomes are
  properties of the response text, the isolation primitives already exist, and a fathom
  bank would rebuild them cross-repo.
- **Detector spend: 192 runs, ceiling $75.** 4 arms × 24 prompts × 2 repeats. The only
  in-repo cost anchor is a trigger-arm run ($2.67 for 27 read-only 3-turn spawns, about
  $0.099 each), which is a **lower bound on a different profile**, not a like-for-like
  rate: the detector's spawns are task-shaped. Budgeting $0.13–0.31 per run at a turn
  cap of 6 gives an estimate band of about **$25–60**, with no judging line item because
  no judge exists in this design. `run_arms.py --dry-run` prints the plan and projected
  cost before any spend, each spawn carries a per-run `--max-budget-usd` cap, and the
  run halts at the ceiling under §6's fallback. `run.source` is `hand` with a stated
  `hand_reason` (no fathom ledger produces these rows), so `ER-XCHECK`'s
  measurement-tier WARN is a declared posture rather than an accident.

## Numbered sections

### §1 Re-home the skill into the experiment-discipline plugin
One atomic change: a half-moved skill fails every gate at once. Create
`plugins/experiment-discipline/.claude-plugin/plugin.json` (modelled on
engineering-discipline's manifest fields), `plugins/experiment-discipline/README.md`,
and `plugins/experiment-discipline/CHANGELOG.md` carrying the relocated content as
the `0.1.0` birth entry; `git mv` the whole skill tree so that
`plugins/experiment-discipline/skills/experiment-rigor/SKILL.md`,
`plugins/experiment-discipline/skills/experiment-rigor/scripts/`,
`plugins/experiment-discipline/skills/experiment-rigor/templates/`, and the sibling
`references/` and `examples/` directories all land under the new plugin, with the
frontmatter `description` byte-identical. Repoint every consumer: the
`.claude-plugin/marketplace.json` entry (its description must equal the manifest's),
the root `README.md` plugin list, install lines, `--plugin-dir` example and layout
table, both `.pre-commit-config.yaml` record hooks' `entry:` and `files:` regexes —
**preserving the `evals/.*/record.yaml` alternative**, which is what keeps §5's own
pre-registration inside the gate — the `evals/config.json` skill→plugin mapping, the
`scripts/word_budget.json` baseline key
(`scripts/word_budget.json:8` `experiment-rigor/SKILL.md`, value 827), the router
row's id prefix, a regenerated `AGENTS.md`, and the holdout row's re-home note and
provenance re-anchor. Roll `plugins/humblepowers/.claude-plugin/plugin.json` back to
0.8.0 and rewrite its CHANGELOG per the bound mechanics.
Two sweeps the move must complete rather than sample. **FREEZE.md**: restore it as a
real document under the moved example (the choreography it describes is load-bearing
for §5, including the one-commit hook skip and the keep-ref tag) and repair all four
live references — the docstring at
`plugins/humblepowers/skills/experiment-rigor/examples/rg-2x2/finalize.py:7`
`see FREEZE.md`, the **writer** at
`plugins/humblepowers/skills/experiment-rigor/examples/rg-2x2/finalize.py:189`
`See FREEZE.md` (it re-emits the reference into the record on every finalize, so the
generator is fixed first), the emitted header at
`plugins/humblepowers/skills/experiment-rigor/examples/rg-2x2/record.yaml:3`
`See FREEZE.md`, and the relocated CHANGELOG text at
`plugins/humblepowers/CHANGELOG.md:25` `FREEZE.md`. **Freeze durability**: give each
existing freeze commit a lightweight keep-ref tag (starting with v1's `ed3c5a0`),
document the tag step in the restored choreography, and add `fetch-depth: 0` to
`.github/workflows/validate.yml` so the freeze objects the acceptance suite and
`ER-ANCHOR` read are present on CI's clone.
**The move must also pin the frozen coordinate, or it silently breaks the chain-root
record.** `git show <commit>:<path>` does not follow renames, so relocating the RG-2×2
record makes every consumer ask git for the new path at the old commit — which fails,
turning the acceptance suite red and degrading `ER-PREREG` from a real reconstruction
to a measurement-tier WARN on the one record that dogfoods the gate. **PR01 therefore
lands the whole mechanism — the field, its reader, and the fixture that exercises it —
not just the value.** Writing the pin without the reader reproduces exactly the failure
this repairs: the pin sits inert and `ER-PREREG` still degrades. So this section adds
`plan_frozen_at.path` (the record's repo-relative path **at the freeze commit**) to
`templates/schema.json`, teaches `check_prereg` in `scripts/validate.py` to resolve it,
adjusts the reconstruction in `test_acceptance_rg2x2.py` to read the pin the same way,
and sets the value, for the moved record, to its **pre-move humblepowers path**. §4 later layers `contrasts[]` onto the same schema pair, so the order is PR01
then PR04 and `SCHEMA.md`'s sync gate re-runs in both.
Adding the field is legal under the freeze: the pre-registration diff subset is
`design.cells`, the outcomes, and `analysis_plan` — `plan_frozen_at` is the *pointer*
to the frozen content, never part of the pinned content, so writing it does not trip
`ER-PREREG`'s drift check. The resolution rule is **fall back when the pinned lookup
fails**, not merely when the field is absent: a fixture that relocates a pinned record
(the acceptance module builds its temp repo at the repo root while validating the
delivered record, which carries the pin) would otherwise go red. That rule costs
something and the trade is stated rather than left to the implementer — a *wrong* pin
resolves silently through the current path instead of failing loudly, so the pin is a
durability aid, not a second integrity check.
**Model-on:** `plugins/engineering-discipline/.claude-plugin/plugin.json`
**Acceptance criterion:** with no other change the full gate suite exits 0
(`validate_plugins.py`, `lint_register.py`, `word_budget.py`,
`gen_agents_md.py --check`, `ascii_runtime_lint.py`, `run_tests.py`); a test asserts
the moved frontmatter description is byte-identical to a committed pre-move blob
fixture (not a bare `git show`, so a shallow clone cannot make it vacuous); guard
tests assert **both** repointed `files:` regexes match the moved
`examples/rg-2x2/record.yaml` **and** `evals/experiments/act-hint/record.yaml`, and
match no `docs/design/**` path; `git grep -n FREEZE.md` returns only references to a
file that exists; a record whose `plan_frozen_at.path` names its historical location
reconstructs the frozen plan after a rename, while a record omitting the field still
reconstructs from its current path, so every v1.0 record validates unchanged; and no
path under `plugins/humblepowers/` still matches `experiment-rigor` except the router
row's id and the CHANGELOG pointer.
Two criteria are stated as executed checks, because this section's central operation
is a rename and renames are cheap to simulate and expensive to get wrong. **The move
test**, run in a scratch clone, in two stages. *Before the move*, with the field, the
reader and the fixture adjustment in place but nothing relocated, `scripts/run_tests.py`
is **46/46** — this is the stage that catches a pin whose fallback fires only on an
absent field, which turns three tests red inside the acceptance module without any move
at all. *After* `git mv` **and** the `AGENTS.md` regeneration this section already
assigns, the suite is **46/46** again and `validate.py` on the moved chain-root record
reports **exactly one WARN** (the pre-existing `ER-XCHECK` hand-source posture), not
two. Without the pin the moved suite is 44/46 and `ER-PREREG` degrades, which is the
failure this mechanism exists to prevent. **The
depth-1 check:** `run_tests.py` is green on a **full-depth** checkout, which is what
`fetch-depth: 0` guarantees in CI, and the keep-ref tag preserves the freeze commit
across a squash-merge. A depth-1 clone is *expected to fail* the freeze
reconstruction, and **no skip may be added to make it pass** — a shallow-clone skip
would void the only enforcement the freeze-durability invariant has, which is exactly
what the standing deletion rule forbids.

### §2 The tier-0 `check` rung
Add the rung below `probe`: a short body section in `SKILL.md` naming it and its
entry rule, and a new
`plugins/experiment-discipline/skills/experiment-rigor/references/report-skeleton.md`
giving the five-element shape — method, metric, result(s) **with denominators**,
conclusion, and a one-line "what this updates" — with two worked micro-examples and
the explicit statement that this rung has no file, no record, and no validator.
The reference also draws the **boundary the widened scope makes load-bearing**: an
*evaluation act* asks a question whose correct answer is a valuative claim ("is this
effective", "which is better", "is it worth it"); an *execution or lookup request*
asks for an action or a fact whose correct answer is the action's result ("run the
test suite and paste the output", "what is the syntax for this"). The `check` shape
is owed for the former and is ceremony for the latter, and a borderline item is
resolved by asking whether the correct response makes a quality claim. §5's bank is
authored against this rule, so the discipline defines the boundary its own experiment
scores. Entry criteria for the tiers above are unchanged. The body states this rung
as guidance, not a bright line, and the word-budget baseline is bumped in the same
diff naming what the growth displaces.
**Acceptance criterion:** `SKILL.md` documents the four-rung ladder with `check` at
tier-0, its no-file/no-gate status, and the evaluation-act/execution-request
boundary; the new `report-skeleton.md` reference exists and resolves under
`validate_plugins.py`; `lint_register.py` is clean and `word_budget.py` passes
against a bumped baseline whose diff names the displacement; and a **dedicated
tier-0 task** with its own rubric is added under `evals/tasks/experiment-rigor/`
(the existing bank holds one record-producing task, so a tier-0 item on the shared
rubric could only score false) asserting the five elements appear in a response that
opens no record.

### §3 The visibility convention and its generator
Bind the activation line: whenever the frame engages, one austere plain-text line
opens the work product. At `probe` and above it names the record path and is
**generated** — `render.py --activation-line` prints the canonical line for a record
and `--check-activation-line` verifies a pasted line against it (tier and path must
match), so the claim cannot drift from the artifact. At tier-0 the artifact reference
is the literal `inline`; nothing resolves it, so it is review-only and is measured in
§5 and §6 rather than gated. Add the emission rule to the `SKILL.md` body and a
commented line to each tier template, and **bump the word-budget baseline again in
this diff** — §2 bumps for the rung, and this growth is separate.

```text
(a) [experiment-rigor | check -> inline]
    [experiment-rigor | measurement -> evals/experiments/act-hint/record.yaml]
(b) a sober glyph prefix, a middot separator and an arrow, e.g. a hollow diamond
```

Format (a) is the bound default and the only **generated** form: the generator's
literals are runtime-reachable strings under the ASCII ratchet, and `render.py` is
absent from the baseline so it is held at zero findings. Format (b) is therefore
available only as a hand-emitted annotation, never from the generator — a mechanical
consequence, not a taste ruling, so the user's pick is between "(a) everywhere" and
"(a) generated, (b) permitted when a human writes the line by hand".
**Acceptance criterion:** `render.py --activation-line` prints the format-(a) line
for the RG-2×2 record naming its tier and path; `--check-activation-line` exits 1 on
a line whose tier or path disagrees with the record and 0 on the generated one, with
a test covering both directions; `ascii_runtime_lint.py` reports zero findings for
`render.py`; `word_budget.py` passes against this section's own bumped baseline; and
`SKILL.md` plus all three tier templates carry the emission rule.

### §4 Schema v1.1: the paired-contrast machinery
The shipped gate recomputes each arm's interval from raw per-arm counts (the
`ER-STATS` branch at the pre-move coordinate
`plugins/humblepowers/skills/experiment-rigor/scripts/validate.py:547`
`interval = stats.confidence_interval`), which mechanically forces an
independent-trials Wilson interval onto a design whose unit is the prompt cluster.
Extend the schema to v1.1 with the minimum that fixes it: a per-outcome `clusters`
block (per prompt id, per arm: numerator and denominator) and an outcome-level
`contrasts[]` construct — `name`, `arms` (the ordered pair), `estimator:
paired_difference`, `estimate`, `se`, cluster count, and `interval`. `ER-STATS`
recomputes every stated contrast from the cluster block and fails on mismatch at the
existing tolerances. Per-arm Wilson stays for outcomes scored over the **full** cell
set, explicitly demoted to **descriptive**: it is an upper bound on precision, and the
headline precision is quoted on the clustered/paired scale. An outcome scoped to a
subset of cells carries no `arms` block at all (see §5).
Three mechanical details the gate cannot be built without. **The interval needs a
recomputation source**: `stats.PairedDiff` returns a mean and an SE and nothing else,
and `confidence_interval` refuses normal-family methods by name, so this PR adds
`paired_interval` to `stats.py` — a t-interval on the per-cluster deltas, `estimate ±
t(0.975, clusters − 1) × se`, with the quantile recorded in the record — and
`ER-STATS` recomputes `contrasts[].interval` through it. `references/small-n-stats.md`
documents it as an **approximation** with its assumptions named (roughly symmetric
per-cluster deltas, a t reference distribution on few clusters), and every contrast
additionally carries an **exact sign-test p-value** as the distribution-free
robustness bound beside the interval. Its tie rule is fixed here, before the freeze,
because choosing it after seeing the deltas is precisely the latitude naming both
statistics is meant to remove: **a zero per-cluster delta is dropped, and the surviving
effective cluster count is recorded beside the p-value**. Ties are expected to be the
modal cluster under the corrected prior below — with 2 repeats a per-cluster delta
lives in {−1, −0.5, 0, 0.5, 1}, and most prompts will move not at all — so the
effective n is load-bearing information, not a footnote. The p-value itself needs no
gate: it is derivable by hand from the recorded deltas (the effective n and the count
of positives are both in the record), which is the robustness bound's whole point.
**The clusters block needs an adapter**:
`stats.paired_difference` takes the block verbatim (four per-cluster arrays of
numerators and sizes), but `stats.clustered_se(outcomes, cluster_ids)` wants per-trial
0/1 outcomes, so this PR names and tests the lossless expansion from per-cluster
counts to a trial list. **The freeze pointer** is §1's, not this section's:
`plan_frozen_at.path` and its reader land in PR01 (a rename breaks the chain-root
record the moment the tree moves), and this section only inherits them. Update
`schema.json` (the new contrast and cluster field shapes plus `known_versions`),
**and bump `validate._EMBEDDED_SCHEMA['known_versions']` in the same diff** — the
embedded copy is validate.py's fallback when `templates/schema.json` is absent, and
the schema sync test asserts every embedded key equals its `schema.json` counterpart,
so moving one without the other reddens that gate. Regenerate `SCHEMA.md` through its
existing sync gate, and cover the extension with tests including a fixture whose
stated contrast disagrees with its clusters.
**Reuse:** `plugins/humblepowers/skills/experiment-rigor/scripts/stats.py::paired_difference`
(pre-move coordinate; §1 relocates it under `plugins/experiment-discipline/`)
**Acceptance criterion:** `run_tests.py` passes the new schema tests; a record whose
`contrasts[]` entry disagrees with its `clusters` block exits 1 naming `ER-STATS` and
the offending contrast, and the corrected record exits 0; a contrast whose stated
`interval` disagrees with the `paired_interval` recomputation likewise exits 1, and a
sign-test p-value with its effective cluster count is emitted beside every contrast;
the `clustered_se` adapter is covered by a test that expands a counts block to a trial
list and reproduces a known SE; the schema sync test stays green with `known_versions`
bumped in both `schema.json` and `validate._EMBEDDED_SCHEMA` (editing one alone
reddens it, which is the check); a v1.0 record still validates (the extension is
additive and `known_versions` carries both); `SCHEMA.md` regenerates clean under its
sync gate; and all three templates still pass `validate.py --schema-only` at their
declared tiers.

### §5 The detector: firing table, materials, and the frozen pre-registration
Build the experiment and freeze it before any run. Four arms, differing in **which
prompts receive an injection and what text they receive** — only `wide` and `inert`
differ in the text alone, which is why theirs is the contrast that isolates content:
**control** (nothing injected), **narrow** (a
conservative row for the direct evaluation-act register: "is it effective", "which
is better", "is it worth it", "compare A with B", plus PT-BR equivalents), **wide**
(adds the bare "test / evaluate" class, the habituation question), and **inert** (the
confound control: the same firing rows as wide, a neutral house-style text naming no
experiment, evaluation, rigor, or tier).
**The injected text is per-prompt, not a fixed per-arm string.** The generator obtains
it from the real router's own `hint_line` — which echoes the matched words into the
sentence — so `narrow` and `wide` inject text that varies with the prompt that
triggered it, exactly as the live hint would, because it *is* the live composition
path. Each row's text is frozen
**verbatim** in the firing table rather than regenerated at run time. `inert` then
gets a per-prompt neutral text matched to **that prompt's** wide text within ±5% on
**estimated tokens** (the declared approximation is characters ÷ 4, with both the
character and estimated-token counts recorded per row), so the ±5% match is a
per-firing-row property the table carries and a test can check, not a single global
average.
Author, in order: `bank.json` — **24 prompts, 12 genuine evaluation acts and 12
execution/lookup decoys**, authored against §2's boundary rule, every prompt at or
above the hook's word and character floor, half EN and half PT-BR within each class,
with the genuine half carrying the direct-register phrasings the arms can actually
match (a pure-paraphrase bank would be null on this instrument); the four arm rule
files under `evals/experiments/act-hint/rules/`; `firing_table.py` and its frozen
`firing_table.json`; `verify.py` — the oracle; and `oracle_labels.json`. Then freeze: commit the materials and the
record (stage 1, with the one-commit hook skip named in Gate commands), then fill
`plan_frozen_at.commit` and every material SHA.
**The oracle** checks the format-(a) activation line explicitly and the five skeleton
elements structurally, and records the full 2×2 state per run — line-only,
skeleton-only, both, neither — with the scoring pre-registered: on a genuine prompt
only **both** counts correct, so a line emitted without substance scores zero and the
founding case's declaration-without-behavior pattern is measured rather than
rewarded; on a decoy only **neither** counts correct. Its language-specific patterns
live in JSON data beside the bank so `verify.py`'s own literals stay ASCII under the
ratchet. `oracle_labels.json` holds roughly a dozen hand-labeled responses spanning
both languages and all four 2×2 states, and a test asserts the oracle reproduces
those labels; its recall, its specificity, and the set's SHA go into the record.
**Primeability** is named as a threat and mitigated where mechanical: no arm's
injected text may contain the activation-line format or any of the five element names,
asserted by a test over the frozen texts, and the oracle keys on line format and
skeleton structure rather than on evaluation vocabulary. Because the echoed words are
literal spans of the prompt, **the constraint binds the bank as well as the rules** —
a wide pattern whose span reaches a noun can echo an element name such as "method"
straight into the treatment. So the same test runs over the bank, and a violating row
is repaired **before the freeze** by editing the bank prompt or narrowing the pattern,
the same pre-registered shape as the PT-BR firing-rate fallback below.
Design: `design.cells` is **arm × prompt_class — 8 cells of 24** (12 prompts × 2
repeats), `shared_tasks: true`, `N` 192, so the genuine/decoy decomposition is
confirmatory-legal under `ER-RECON` instead of a post-freeze split. **One
confirmatory outcome**, `rigor_disposition`, reported with that decomposition as
first-class cell rows; `skeleton_wellformedness` (a denominator present *and*
numerically consistent with the response's own numbers) is a **secondary scoped to
the genuine cells**, reported through `clusters` + `contrasts[]` **only, carrying no
`arms` block** — `ER-RECON` requires every outcome's arm denominators to sum to `N`,
so a subset-scoped outcome with per-arm rates would fail the gate after the run is
already paid for, and the contrasts-only shape passes clean. Frozen run config: model
string, temperature and sampling, turn cap, the single insertion point, repeat count,
cwd fixture, randomized interleaved arm order under a seeded RNG, and the **tool
allowlist stated explicitly, including whether `Skill` is in it** — that one entry
decides whether control can load the skill it ships with, so it is the difference
between the baseline Part B describes and a different experiment; it is held identical
across arms either way.
The freeze-stage record's `disposition` carries **`total: 192` alone** — `completed`
and `excluded` arrive at finalize (§6), matching the RG-2×2 freeze precedent; the
named Reuse template ships the post-run shape (`completed`/`excluded`/`total`
together), which `ER-RECON` rejects while results are absent, so author the freeze
record from the template's *fields* and this section's *disposition shape*.
Threats, written per contrast rather than blanket: `token_length_confound` is
**residual**, its statement recording that the token-matched inert arm controls it
for `wide − inert` only, that no arm is length-matched to narrow so `narrow − control`
re-inherits the founding case's confound, and that the package contrasts make no
mechanism claim; `custom_candidate_displacement` is controlled by the firing table
recording each arm's candidate list per prompt; `custom_language_delivery` is
residual, naming the uncalibrated PT-BR patterns, with the pre-registered fallback
that if the frozen table shows PT-BR firing below half the EN rate the primary
analysis restricts to EN — a decision taken from the table, which contains no outcome
data. Exclusions are pre-registered: a refusal, truncation, or tool error is excluded
with its reason through the disposition machinery, and **a prompt whose runs are all
excluded drops out of every contrast entirely, with the surviving cluster count
recorded** — `stats.paired_difference` raises on a zero-size cluster rather than
degrading, so the drop-out rule is what keeps a fully-excluded prompt from taking the
analysis down with it.
**Reuse:** `plugins/humblepowers/skills/experiment-rigor/templates/measurement.yaml`
(pre-move coordinate; §1 relocates it under `plugins/experiment-discipline/`)
**Acceptance criterion:** `validate.py evals/experiments/act-hint/record.yaml` exits
0 at measurement tier with the plan frozen and results absent, and the freeze record
reconciles `sum(design.cells[].planned_n) == disposition.total == 192` (the
arm-denominator half of `ER-RECON` is a no-op until results exist and is claimed by
§6); the frozen firing table shows, per arm and per prompt, whether an injection
fires and which candidates that arm produces, with every bank prompt above the hook's
floor and wide and inert firing on an identical row set; **a parity test asserts every
frozen row's candidate list and injected text equal the real router's output for that
prompt under that arm's rules**, which is what makes "router-realistic" a checked
property rather than an asserted one; tests assert inert's estimated token count is
within ±5% of wide's per row, and that neither any injected text **nor any bank
prompt** contains the activation-line format or a skeleton element name; the oracle
reproduces every label in `oracle_labels.json`; every material SHA in the record
matches its committed file;
and `run_arms.py --dry-run` prints the 192-run plan and projected cost without
spending. **Pre-spend shape validation, named as its own gate:** a synthetic fixture
test drives the **complete** record shape — the freeze stage *and* a fully-populated
final stage carrying every outcome, `clusters`, `contrasts[]`, disposition with
exclusions, and threat block — through `validate.py` before a single paid run, so a
reconciliation or stats-shape defect surfaces for free rather than after $25–60 is
spent. This gate exists because both of this round's `ER-RECON` collisions were found
by running a synthetic record past the validator, not by reading the spec.

### §6 Run, analyze, and report the detector
Spend the run, fill the results, and derive the report — stage 2 of the freeze
choreography. `finalize.py` fills the per-cluster counts, the per-arm descriptive
Wilson intervals **for the full-cell confirmatory outcome only** (the genuine-scoped
secondary stays contrasts-only, per §5), the `contrasts[]` entries computed by
`stats.paired_difference` with their `paired_interval` bounds and sign-test p-values,
the observed disposition with its exclusions, and the prior→posterior update linking
this record to the founding RG-2×2 as its chain prior; it is deterministic and
idempotent, and it re-verifies every frozen material SHA before writing, so a
post-freeze edit to bank, rules, table, or oracle fails loudly here. The report is
`render.py`-derived; this section extends `render_report` with the lines the existing
skeleton does not emit — the contrast table, the achieved precision on the clustered
scale, the 2×2 state breakdown including the line-only rate, the descriptive
turn/token tax, and the leading activation line from §3's generator — because the
drift gate compares parsed YAML only and would not notice hand-added prose.
Four interpretations are pre-committed, so no leg is invented after the data: wide
moves and inert does not, so the hint's content carries the effect; wide and inert
both move alike, so the effect is preamble cost and the content is irrelevant;
**inert moves and wide does not**, likewise a preamble effect with content
contributing nothing, and ship no row; or nothing moves beyond its interval, a
recorded null. If the ceiling halts the run, the pre-registered fallback is to
analyze complete prompt-pairs only and report the reduced precision.
**Reuse:** `plugins/humblepowers/skills/experiment-rigor/examples/rg-2x2/finalize.py::finalize_record`
(pre-move coordinate; §1 relocates it under `plugins/experiment-discipline/`)
**Acceptance criterion:** the completed record passes `validate.py` at measurement
tier (exit 0) with results present, the arm-denominator reconciliation now checked,
every stated contrast recomputed from its cluster block and every descriptive
interval recomputed by `stats.py`; `render.py --check` shows no drift against the
committed `report.md`, which carries the contrast table, the clustered-scale
precision, the 2×2 breakdown, and its leading activation line; **`examples/rg-2x2/report.md`
is re-rendered in this same PR**, because `render_report` is one shared renderer and
its drift gate digests only the embedded YAML — extending it silently staleness the
committed RG-2×2 prose while `--check` stays green, so the re-render is the fix and
`--check` is re-run on that pair too; both repointed pre-commit hooks pass on the
staged pairs; and the report names which of the four pre-committed interpretations the
data selected — a recorded null included — and states the live-hook delivery question
as the named precondition for any production rollout of a row.

## PR ↔ section manifest

| PR | Implements section | One concern? |
|---|---|---|
| PR01 | §1 | yes |
| PR02 | §2 | yes |
| PR03 | §3 | yes |
| PR04 | §4 | yes |
| PR05 | §5 | yes |
| PR06 | §6 | yes |

Dependency notes (a DAG, not extra coverage): PR01 lands first — every later path
assumes the new plugin root. PR03 uses the tier-0 rung PR02 adds. PR04's schema
extension must exist before PR05 freezes a record that declares `contrasts[]`. PR06
cannot start until PR05's freeze commit exists, because the pre-registration gate
compares against it.

## Definition of Done (this spec)

- All six sections merged with their acceptance criteria demonstrated in the PR.
- The re-home is behavior-invisible: description byte-identical to the committed
  pre-move blob, holdout row annotated and re-anchored, no reseal owed.
- The full gate suite is green at the new paths on a **full-depth** checkout, which
  `fetch-depth: 0` guarantees in CI; the keep-ref tags preserve each freeze commit
  across a squash-merge, and `plan_frozen_at.path` preserves the frozen *coordinate*
  across the move. A depth-1 clone is expected to fail the freeze reconstruction, and
  no skip is added to make it pass.
- `test_router.py` stays green with the shipped rules byte-unchanged; the detector's
  candidate rows exist only as offline inputs to the firing table.
- The detector's materials are frozen with their SHAs in the record before the run,
  and `finalize.py` re-verifies them after it.
- The detector record is frozen before its run, passes at measurement tier afterwards
  with per-cluster contrasts, and its report is derived, never hand-edited.
- The run stays within the $75 ceiling, with the dry-run count taken before spend.
- humblepowers is back at 0.8.0 with a CHANGELOG entry describing only its own change;
  `experiment-discipline` ships 0.1.0.
- Generated / mirrored / snapshot artifacts downstream of touched surfaces, each with
  its freshness gate: `AGENTS.md` (`gen_agents_md.py --check`, §1);
  `scripts/word_budget.json` (`word_budget.py`, bumped in §1 for the path key, §2 for
  the rung, and §3 for the emission rule — three PRs edit this shared key, in that
  order); `scripts/ascii_lint_baseline.json` (unchanged — new files stay at zero);
  `templates/SCHEMA.md` regenerated from `schema.json` (its sync gate, §4);
  **`validate._EMBEDDED_SCHEMA`, the in-code mirror of `schema.json`** — its
  `known_versions` moves with §4's bump and the schema sync test is its freshness gate,
  reddening if either copy moves alone; and the
  committed `examples/rg-2x2/report.md` and `evals/experiments/act-hint/report.md`
  (`render.py --check`, §1 and §6). No other generated artifacts.

## Experiment design (Part B)

*(Governs §5 and §6 — the detector. §1–§4 are code changes and are not measured here.)*

- **Estimand + unit of analysis:** the paired per-prompt difference in
  `rigor_disposition` between arms. The unit is the **prompt cluster** (24 of them, 12
  per class), not the run: each prompt contributes a per-arm rate over its 2 repeats,
  and the contrast is the mean of per-prompt differences with the task-level paired SE
  from `stats.paired_difference`. **One primary contrast is pre-named in the frozen
  decision rule: `wide − control` on `rigor_disposition`** — the deployable-package
  question, since a shipped row ships its tokens too. `wide − inert` is the named
  confound-separation secondary (the mechanism question). Every other contrast,
  including `narrow − control` and anything on `skeleton_wellformedness`, is
  exploratory and reported as such.
- **Reps / power & MEWD:** 4 arms × 24 prompts × 2 repeats = **192 runs**, 48 per arm,
  but the inferential unit is 24 clusters (12 within a class). On that scale a paired
  contrast's SE is roughly the standard deviation of the per-prompt differences over
  the square root of 24, so a plausible two-sided half-width is about **±0.15 pooled
  and ±0.20 within a class** — the honest MEWD is a large effect, and a difference of
  differences is wider still. The earlier independent-trials figure was computed on the
  wrong unit and is not used. The record reports achieved precision on the clustered
  scale; per-arm Wilson intervals are descriptive only.
- **Blinding + held-constant factors:** the oracle is a deterministic regex frozen by
  hash, carries no arm label, and is validated against a hand-labeled set before use.
  Held equal across arms: prompt text, model string, temperature and sampling, turn
  cap, tool allowlist, cwd fixture, repeat count, insertion point, and the EN/PT-BR
  balance; arm order is randomized and interleaved under a seeded RNG. Held equal
  between wide and inert specifically: the firing row set (identical by construction
  from the same patterns), the insertion point, and estimated token count within ±5%.
- **Correctness oracle (not "ran green"):** a completed run is not a pass. On a genuine
  prompt, correct means the format-(a) activation line **and** the five skeleton
  elements — a line alone scores zero, which is the founding case's failure made
  measurable rather than rewarded. On a decoy, correct means neither. The 2×2 state is
  recorded per run so the line-only rate is visible as a first-class number.
- **Measured-unit causal path:** treatment end — the injected text is prepended to the
  prompt the measured spawn reads on stdin, so the treatment is neither recomputed nor
  inert, and the frozen firing table fixes exactly which prompts receive it.
  Measured-unit end — each spawn gets an isolated credentials-only `CLAUDE_CONFIG_DIR`,
  a restricted tool allowlist, and a neutral cwd fixture containing no expected answer,
  so there is no side channel to the ground truth. Per-repeat isolation is structural:
  the harness spawns fresh with `--no-session-persistence`
  (`evals/harness/claude_runner.py:221` `--no-session-persistence`), so no state carries
  between repeats. The decoys guard the cheapest way to game the genuine half —
  declaring rigor on everything — because that behavior costs decoy correctness.
- **Enforcement of isolation invariants:** the isolated config, the tool allowlist, the
  frozen insertion point, and the seeded interleaved order are enforced by
  `run_arms.py` and asserted by §5's tests; the wide/inert row-set identity and the ±5%
  token match are asserted mechanically over the frozen firing table; material SHAs are
  verified at freeze (§5) and re-verified at finalize (§6); and the shipped
  `router_rules.json` being byte-unchanged is asserted in §5, keeping the sealed router
  budgets out of the blast radius.
- **Pre-registered analysis plan:** fixed in `record.yaml` and committed before the
  first run (§5), with `ci_method: wilson` for the descriptive per-arm rates,
  `estimator: paired_difference` for every contrast, **the t-interval on per-cluster
  deltas as the primary interval and the exact sign test as the distribution-free
  robustness bound reported beside it** (the t reference is an approximation on few
  clusters, and naming both before the run is what stops the friendlier one from being
  chosen after), the named primary and secondary contrasts, the four pre-committed
  interpretations, the exclusion rules including the fully-excluded-prompt drop-out,
  the ceiling-halt fallback, and the single confirmatory outcome's role frozen. §6 may add
  nothing confirmatory: a post-freeze finding is quarantined as exploratory, which
  `ER-PREREG` enforces against the freeze commit.
- **Baseline expectation (what is the control arm actually a control for?):** not a
  no-treatment baseline. **Every arm loads `plugins/experiment-discipline` with the
  `Skill` tool available**, and by run time §2 and §3 have put the tier-0 rung and the
  activation-line emission rule into that skill's body — so the control spawn already
  carries, in its own loaded plugin, a skill that instructs the behavior the oracle
  scores. Control therefore measures **the skill's own trigger surface with no hint**,
  and `wide − control` is the hint's **marginal** effect over a loaded, unhinted skill,
  not "convention versus nothing". The repo holds a measured number for that surface:
  this skill's sealed holdout put its description at 0.33 recall [0.15, 0.58], with the
  lexically adjacent positive at 3/3 (`evals/trigger/holdout/BASELINES.md:18`
  `experiment-rigor`) — measured on the direct evaluation-act register the genuine half
  is deliberately authored in, because that is the register the arms' patterns must
  match. So control is expected **materially above zero** on the genuine half, low but
  not structurally floored, and the hint's effect is incremental over that.
  Two consequences are pre-registered rather than discovered. **The genuine-side
  decision rule is two-sided**: the corrected prior no longer licenses a directional
  bet, and a treated arm can land *below* control if the injected hint displaces the
  model's own dispatch — the router keeps at most two candidates on a hits-descending
  sort, which is the `custom_candidate_displacement` threat this section already names.
  And a non-zero control **compresses the contrast** against a MEWD already declared
  large, which is a spend risk stated up front rather than discovered in §6. The decoy
  side stays two-sided as before: control near perfect, treated arms able to lose
  ground, which is the habituation cost the wide arm exists to price.
- **Feasibility grounding:** the variable this study needs is a realistic firing
  pattern, and it is established **before** any spend rather than assumed: the frozen
  firing table is computed offline with the real router semantics and the hook's own
  floor, so the exact treated set per arm is visible and auditable at review time. If
  the table shows an arm firing on too few genuine prompts to distinguish it from
  control, that is knowable for free, and the pre-registered response is to revise the
  bank *before* the freeze — never after.

## Pre-mortem certification

- **Reviewer:** fresh non-author subagent (opus), round 4 — did not author the spec and ran
  no prior round
- **Verdict:** CONDITIONAL-CERTIFY — 0 BLOCKER, 0 MAJOR, 4 named MINOR conditions (C1–C4 in
  the round-4 artifact), each a two-line spec edit with a determined answer. C4 lands in
  PR01, C2 before PR05, and C1 and C3 before PR05's freeze commit because they are
  statements the frozen record makes about itself
- **Operator:** session orchestrator (accepts C1–C4 and folds each at its named PR
  boundary, from the round-4 artifact's evidence rather than its wording)
- **Certification artifact:** `docs/specs/2026-07-25-experiment-discipline-wave.premortem-r4.md`
- **Date:** 2026-07-25
- **Reviewed against:** the worktree at `feat/experiment-rigor-skill` @ 113cc06; keel
  kit 0.13.0; no external dependency SHAs
- **Post-fold coherence:** three sequential folds — round 1 (FM-1..FM-25) plus the
  external 4-model panel, which restructured the detector around the firing/effect
  decomposition and added §4's contrast machinery; round 2 (R2-1..R2-9), which pinned
  the frozen coordinate through the rename, corrected the depth-1 clone sense, and
  closed three observed record-shape collisions; and round 3 (R3-1..R3-6), which moved
  the frozen-coordinate mechanism into PR01 under fallback-on-failure semantics,
  corrected the control arm's recorded prior from a no-treatment baseline to a
  loaded-skill baseline (making the genuine-side decision rule two-sided), and put the
  firing table on the real router. Round 4 audited all six round-3 findings to RESOLVED
  against current text, re-checked all 58 fold-ledger anchors and all 23 body code cites
  mechanically (exact, zero drift), re-verified every load-bearing repo claim at source
  — `router.load_rules`/`route`/`hint_line`, the hook's floor and skips, `check_prereg`'s
  diff subset, `ER-STATS`/`ER-RECON`/`ER-XCHECK`, `stats.py`, the ASCII baseline, both
  record hooks, the CI steps, and the BASELINES 0.33 / 3-of-3 numbers — and re-ran the
  suite on a fresh clone (46/46). It surfaced no new BLOCKER or MAJOR
- **Failure modes considered & folded in:** FM-1 bank register mix, FM-2 hook length
  floor, FM-3 unbuildable inert arm, FM-4 forbidden humblepowers edits, FM-5 netted
  outcomes, FM-6 forced anti-conservative interval, FM-7 wrong-unit MEWD, FM-8 oracle
  primeability, FM-9 per-contrast threat honesty, FM-10 unenforced contrast selection,
  FM-11 freeze-commit hook skip, FM-12 FREEZE.md sweep including its writer, FM-13 §3
  word budget, FM-14 hook regex guard tests, FM-15 harness composition claims, FM-16
  hook-in-spawn assumption removed by construction, FM-17 CI fetch depth, FM-18 cost
  anchor and phantom judge, FM-19 PT-BR delivery, FM-20 renderer extension, FM-21
  tier-0 task, FM-22 BASELINES precedent and provenance, FM-23 candidate displacement,
  FM-24 vacuous freeze reconciliation, FM-25 stale reuse pointers; plus the panel's
  convergent findings on materials freezing, oracle validation, token-based matching,
  exposure visibility, run-config determinism, exclusions, and the decoy category
  boundary. Round 2 added R2-1 the frozen-coordinate pin through the rename (BLOCKER,
  observed), R2-2 the inverted depth-1 criterion, R2-3 the contrasts-only secondary
  plus pre-spend shape validation, R2-4 the freeze-stage disposition shape, R2-5 the
  paired interval's recomputation source, R2-6 the clusters adapter and the
  fully-excluded prompt, R2-7 the shared-renderer re-render, R2-8 the ruff gates, and
  R2-9 the per-prompt injected text. Round 3 added R3-1 the pin's PR ownership and
  fallback-on-failure semantics (observed: implementing the round-2 wording literally
  turned three acceptance tests red with no move at all), R3-2 the control arm's
  corrected prior and the two-sided genuine-side rule, R3-3 the generator driving the
  real router read-only, R3-4 the embedded-schema mirror, R3-5 the sign test's tie
  rule, and R3-6 the primeability constraint binding the bank — one fold-ledger row
  each below. Round 4 added four MINOR modes that are **named conditions, not yet
  folded**: R4-1 the arm rule files' composition and `custom_candidate_displacement`
  demoted to residual, R4-2 the parity criterion scoped to the router-derived arms,
  R4-3 the control prior's 0.33 transported from a paraphrase-dominated holdout (with
  the no-headroom read added to §6's null leg), and R4-4 the `SCHEMA.md` regeneration
  owed in PR01 (observed: 45/46 without it, 46/46 with it)

### Fold ledger

| Finding | Target section | artifact:line | Confirmed |
|---|---|---|---|
| FM-1 bank register mix fixed numerically; firing auditable pre-spend | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:474` `direct-register phrasings the arms can actually` | yes |
| FM-2 hook length floor reproduced; short prompts are visible table rows | Settled decisions + §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:203` `MIN_WORDS = 4` | yes |
| FM-3 inert arm buildable by construction | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:458` `the same firing rows as wide, a neutral` | yes |
| FM-4 no humblepowers code edits at all | Non-goals | `docs/specs/2026-07-25-experiment-discipline-wave.md:80` `No edit to` | yes |
| FM-5 outcomes de-netted: cells are arm x prompt_class | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:499` `arm × prompt_class` | yes |
| FM-6 per-arm Wilson demoted to descriptive | §4 | `docs/specs/2026-07-25-experiment-discipline-wave.md:400` `demoted to` | yes |
| FM-7 MEWD recomputed on clusters | Part B | `docs/specs/2026-07-25-experiment-discipline-wave.md:661` `inferential unit is 24 clusters` | yes |
| FM-8 oracle primeability named and mitigated | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:490` `Primeability` | yes |
| FM-9 token_length_confound written per contrast | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:523` `re-inherits the founding case` | yes |
| FM-10 one primary contrast pre-named | Part B | `docs/specs/2026-07-25-experiment-discipline-wave.md:654` `One primary contrast is pre-named` | yes |
| FM-11 stage-1 freeze hook skip scoped to one commit | Gate commands | `docs/specs/2026-07-25-experiment-discipline-wave.md:72` `One scoped, one-commit exception` | yes |
| FM-12 FREEZE.md swept at all four sites, generator first | §1 | `docs/specs/2026-07-25-experiment-discipline-wave.md:269` `the relocated CHANGELOG text at` | yes |
| FM-13 section 3 names its own word-budget bump | §3 | `docs/specs/2026-07-25-experiment-discipline-wave.md:366` `bump the word-budget baseline again` | yes |
| FM-14 both hook regexes guarded, evals alternative preserved | §1 | `docs/specs/2026-07-25-experiment-discipline-wave.md:252` `preserving the` | yes |
| FM-15 harness claims rewritten; no harness edit | Non-goals | `docs/specs/2026-07-25-experiment-discipline-wave.md:87` `Its real surface already suffices` | yes |
| FM-16 hook-in-spawn recorded as a named precondition | Context | `docs/specs/2026-07-25-experiment-discipline-wave.md:31` `measured here — it is a named precondition` | yes |
| FM-17 CI fetch-depth 0 + keep-ref tags | §1 | `docs/specs/2026-07-25-experiment-discipline-wave.md:127` `fetch-depth: 0` | yes |
| FM-18 cost anchor a lower bound; phantom judge dropped | Settled decisions | `docs/specs/2026-07-25-experiment-discipline-wave.md:227` `lower bound on a different profile` | yes |
| FM-19 PT-BR delivery threat + ASCII-safe oracle data | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:525` `custom_language_delivery` | yes |
| FM-20 render_report extension claimed with its lines | §6 | `docs/specs/2026-07-25-experiment-discipline-wave.md:570` `this section extends` | yes |
| FM-21 dedicated tier-0 task and rubric | §2 | `docs/specs/2026-07-25-experiment-discipline-wave.md:352` `dedicated` | yes |
| FM-22 BASELINES precedent re-cited, provenance re-anchored | Settled decisions | `docs/specs/2026-07-25-experiment-discipline-wave.md:183` `re-anchors that row's provenance` | yes |
| FM-23 candidate displacement visible in the firing table | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:524` `custom_candidate_displacement` | yes |
| FM-24 freeze reconciliation narrowed to what the validator checks | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:540` `is a no-op until results exist` | yes |
| FM-25 reuse pointers marked pre-move with their post-move home | §4, §5, §6 | `docs/specs/2026-07-25-experiment-discipline-wave.md:390` `pre-move coordinate` | yes |
| Panel: firing/effect decomposition with a frozen exposure table | Settled decisions | `docs/specs/2026-07-25-experiment-discipline-wave.md:210` `It emits a per-arm` | yes |
| Panel: oracle validated against a hand-labeled frozen set | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:549` `reproduces every label` | yes |
| Panel: 2x2 truth table pre-registered; a line alone scores zero | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:483` `counts correct, so a line emitted` | yes |
| Panel: all experimental materials hashed into the frozen record | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:479` `and every material SHA` | yes |
| Panel: run config frozen + per-repeat isolation asserted | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:508` `Frozen run config` | yes |
| Panel: exclusions and the ceiling-halt fallback pre-registered | §5, §6 | `docs/specs/2026-07-25-experiment-discipline-wave.md:529` `Exclusions are pre-registered` | yes |
| Panel: the inert-moves leg pre-committed | §6 | `docs/specs/2026-07-25-experiment-discipline-wave.md:575` `Four interpretations are pre-committed` | yes |
| Panel: decoy category boundary defined by the discipline | §2 | `docs/specs/2026-07-25-experiment-discipline-wave.md:339` `execution or lookup request` | yes |
| Panel: format (b) excluded from the generator on ASCII grounds | §3 | `docs/specs/2026-07-25-experiment-discipline-wave.md:378` `available only as a hand-emitted` | yes |
| Panel: ADR records the firing/effect split and its claim boundary | ADR-0008 | `docs/adr/0008-experiment-discipline-plugin.md:116` `separates` | yes |
| R2-1 freeze pins an immutable coordinate; the move sets it (BLOCKER) | §1 | `docs/specs/2026-07-25-experiment-discipline-wave.md:275` `pin the frozen coordinate` | yes |
| R2-2 depth-1 clone fails loud; no skip may be added | §1 + DoD | `docs/specs/2026-07-25-experiment-discipline-wave.md:326` `no skip may be added` | yes |
| R2-3 genuine-scoped secondary is contrasts-only, no arms block | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:505` `carrying no` | yes |
| R2-3 pre-spend synthetic shape validation of the whole record | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:552` `Pre-spend shape validation` | yes |
| R2-4 freeze-stage disposition carries total alone | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:515` `alone` | yes |
| R2-5 paired_interval gives contrasts[].interval a source | §4 | `docs/specs/2026-07-25-experiment-discipline-wave.md:406` `t-interval on the per-cluster deltas` | yes |
| R2-6 clusters-to-clustered_se adapter named and tested | §4 | `docs/specs/2026-07-25-experiment-discipline-wave.md:421` `clusters block needs an adapter` | yes |
| R2-6 a fully-excluded prompt drops out of every contrast | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:531` `drops out of every contrast entirely` | yes |
| R2-7 rg-2x2 report.md re-rendered when the shared renderer grows | §6 | `docs/specs/2026-07-25-experiment-discipline-wave.md:590` `is re-rendered in this same PR` | yes |
| R2-8 ruff gates added to the checklist | Gate commands | `docs/specs/2026-07-25-experiment-discipline-wave.md:52` `run: ruff check .` | yes |
| R2-9 injected text is per-prompt and frozen verbatim in the table | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:460` `per-prompt, not a fixed per-arm string` | yes |
| R3-1 PR01 lands the pin, its reader, and the fixture (MAJOR) | §1 | `docs/specs/2026-07-25-experiment-discipline-wave.md:280` `lands the whole mechanism` | yes |
| R3-1 fallback fires when the pinned lookup fails, trade stated | §1 | `docs/specs/2026-07-25-experiment-discipline-wave.md:291` `fall back when the pinned lookup` | yes |
| R3-2 control is not a no-treatment baseline; prior corrected (MAJOR) | Part B | `docs/specs/2026-07-25-experiment-discipline-wave.md:709` `no-treatment baseline` | yes |
| R3-1 two-stage move test: 46/46 before and after the move | §1 | `docs/specs/2026-07-25-experiment-discipline-wave.md:314` `with the field` | yes |
| R3-2 genuine-side decision rule becomes two-sided | Part B | `docs/specs/2026-07-25-experiment-discipline-wave.md:723` `decision rule is two-sided` | yes |
| R3-2 frozen run config names whether Skill is in the allowlist | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:511` `including whether` | yes |
| R3-3 the generator drives the real router read-only (MAJOR) | Settled decisions | `docs/specs/2026-07-25-experiment-discipline-wave.md:198` `drives the real router read-only` | yes |
| R3-3 parity test ties every frozen row to the real router's output | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:543` `a parity test asserts` | yes |
| R3-4 embedded-schema mirror bumped in the same diff | §4 | `docs/specs/2026-07-25-experiment-discipline-wave.md:429` `_EMBEDDED_SCHEMA['known_versions']` | yes |
| R3-4 embedded-schema mirror added to the DoD's mirror list | DoD | `docs/specs/2026-07-25-experiment-discipline-wave.md:640` `the in-code mirror of` | yes |
| R3-5 sign-test tie rule fixed before the freeze | §4 | `docs/specs/2026-07-25-experiment-discipline-wave.md:414` `is dropped, and the surviving` | yes |
| R3-6 the primeability constraint binds the bank too | §5 | `docs/specs/2026-07-25-experiment-discipline-wave.md:494` `binds the bank as well as the rules` | yes |
