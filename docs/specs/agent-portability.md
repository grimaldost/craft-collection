# Spec — Multi-agent portability of the craft-collection plugins

- **Date:** 2026-07-16
- **Status:** ready (DoR passed)
- **Audience:** maintainer + implementing agents (one PR per numbered section)
- **Output artifact(s):** `AGENTS.md`, `scripts/gen_agents_md.py`, `scripts/check_uv_hygiene.py`, `.pre-commit-hooks.yaml`, `adapters/pre-commit/craft-floor.yaml`, `plugins/engineering-discipline/hooks/harness_adapters.py`, `evals/harness/claude_runner.py` plus the runner-seam edits in the harness and evaluate-skill script copies (§8), the `.pre-commit-config.yaml` and `.github/workflows/validate.yml` freshness-gate entries (§2), `docs/portability.md`, reworded SKILL.md bodies
- **Phases:** Decide+Specify this round (Decompose: the PR manifest below is the plan; Implement/Gate/Review/Reflect: future waves)

## Context

The three plugins couple to Claude Code at four layers — packaging, hooks,
discovery, and harness-specific wording — while ~90% of their value (23 skills
in the open Agent Skills format) is already harness-neutral. The decisions
governing this work are recorded in `docs/adr/0001-single-source-portable-core.md`
(single source + generated adapters), `docs/adr/0002-agents-md-generated-index.md`
(AGENTS.md as the universal discovery surface),
`docs/adr/0003-hooks-core-adapter-precommit-floor.md` (hook core/adapter split and
the enforcement ladder), `docs/adr/0004-distribution-git-clone-mcp-deferred.md`
(git clone as the off-CC channel), `docs/adr/0005-capability-conditional-language.md`
(capability-conditional skill wording), and
`docs/adr/0006-eval-runner-abstraction.md` (runner seam; claims carry their
measurement scope).

Evidence of the coupling this spec removes or ladders:
`plugins/session-workflow/skills/review-panel/SKILL.md:4` `Claude Code only`
hard-gates a skill body on the harness name;
`plugins/engineering-discipline/hooks/hooks.json:11` `${CLAUDE_PLUGIN_ROOT}` shows
the CC-only hook envelope;
`plugins/session-workflow/skills/toolkit-awareness/scripts/scan_toolkit.py:409`
`'claude', 'plugin', 'list'` shells out to the CC CLI (with graceful degradation
already in place);
`plugins/session-workflow/skills/evaluate-skill/scripts/claude_runner.py:5`
`claude -p` pins the eval harness to one backend. The pure cores this spec
builds on already exist:
`plugins/engineering-discipline/hooks/ruff_format.py:31` `def ruff_commands`,
`plugins/engineering-discipline/hooks/uv_enforce.py:69` `def verdict`,
`plugins/session-workflow/skills/toolkit-awareness/scripts/scan_toolkit.py:37`
`def _read_frontmatter`, and
`plugins/session-workflow/skills/evaluate-skill/scripts/claude_runner.py:3`
`parse_stream`.

## Goal

Any agent that can read files and run commands can discover, load, and benefit
from the craft skills — with the efficiency mechanisms preserved: progressive
disclosure via a generated index, and mechanical enforcement via an explicit
degradation ladder (act-time → commit-time → advisory). Claude Code behavior is
unchanged.

## Gate commands

- `uv run --no-project -- python scripts/lint_register.py` (register doctrine)
- `uv run --no-project --with pyyaml -- python scripts/validate_plugins.py` (structure + description caps + word budget vs `scripts/word_budget.json`)
- `uv run --no-project -- python scripts/run_tests.py` (every `test_*.py`, no pytest)
- `ruff check .` and `ruff format --check .` (per `ruff.toml`, 100-col, single quotes)
- After §2 lands: `uv run --no-project -- python scripts/gen_agents_md.py --check` (freshness of `AGENTS.md`)
- Trigger evals (and holdouts where sealed) for every §3–§5-touched skill that has a dataset — each section's criterion names the scope: the evaluate-skill harness under `evals/` (run manually; results recorded in the PR description)

## Non-goals

- No MCP server this wave (deferred with a named revisit trigger — `docs/adr/0004-distribution-git-clone-mcp-deferred.md`).
- No second eval-runner backend and no trigger measurements on non-CC harnesses (`docs/adr/0006-eval-runner-abstraction.md`); claims stay scoped to where they were measured.
- No multi-harness config detectors in `scan_toolkit.py` (speculative until a target harness is committed; discovery off-CC is served by `AGENTS.md`).
- No change to Claude Code packaging, hook wiring, or marketplace flow.
- No per-harness variant copies of any skill (forbidden by `docs/adr/0001-single-source-portable-core.md`).

## Invariants touched

Register doctrine and the word-budget ratchet (both gate every skill-body edit
in §3–§5); structural marketplace validity; the derived-artifact integrity
invariant introduced by `docs/adr/0001-single-source-portable-core.md`; adapter
thinness (`docs/adr/0003-hooks-core-adapter-precommit-floor.md`); measurement-scope
on portability claims (`docs/adr/0006-eval-runner-abstraction.md`).

## Enforcement status

| Invariant | Status | Gate/mechanism |
|---|---|---|
| register doctrine (calibrated register in skill text) | enforced | `scripts/lint_register.py` in pre-commit + CI |
| word budget (skill bodies vs baseline) | enforced | `scripts/validate_plugins.py` reading `scripts/word_budget.json`, in pre-commit + CI |
| structural marketplace validity | enforced | `scripts/validate_plugins.py` in pre-commit + CI |
| derived-artifact integrity (generated files never hand-edited) | planned | §2 freshness gate (`gen_agents_md.py --check` in pre-commit + CI) |
| trigger-eval gates on skill-text changes | review-only | evaluate-skill harness under `evals/`, run manually per touched skill |
| adapter thinness (logic in core, not adapters) | review-only | review checklist item (`docs/method/review-checklist.md`) |
| measurement scope on portability claims | review-only | review checklist item |

## Concept → module map

| Concept introduced/changed | Module / file it lives in |
|---|---|
| Universal discovery index | `AGENTS.md` (to be created) |
| Index generator | `scripts/gen_agents_md.py` (to be created) |
| Frontmatter parsing (reused, single implementation) | `plugins/session-workflow/skills/toolkit-awareness/scripts/scan_toolkit.py` |
| Capability-conditional skill wording | `plugins/session-workflow/skills/review-panel/SKILL.md` (and the peers listed in §3–§5) |
| Hook adapter seam | `plugins/engineering-discipline/hooks/harness_adapters.py` (to be created) |
| Consumer enforcement floor (pre-commit) | `adapters/pre-commit/craft-floor.yaml` (to be created) |
| uv hygiene floor check | `scripts/check_uv_hygiene.py` (to be created) |
| Eval runner seam | `evals/harness/claude_runner.py` (sync source; mirrored to `plugins/session-workflow/skills/evaluate-skill/scripts/` per `evals/harness/test_scripts_in_sync.py`) |
| Consumer hook packaging | `.pre-commit-hooks.yaml` (to be created) |
| Portability guide + installation matrix | `docs/portability.md` (to be created) |

## Numbered sections

### §1 AGENTS.md generator and first generated index
Create `scripts/gen_agents_md.py`: walks `plugins/*/skills/*/SKILL.md`,
`plugins/*/commands/*.md`, and `plugins/*/output-styles/*.md`; emits a repo-root
`AGENTS.md` with (a) a "GENERATED — do not hand-edit" banner naming the
generator, (b) a compact dispatch preamble (rank candidates by description fit;
load a skill body only when its expected benefit clearly exceeds its context
cost; at most one process discipline at a time), and (c) one line per artifact —
name, trigger description from frontmatter, repo-relative path — grouped by
plugin, with commands and the output style as pointer entries. Output is
deterministic (stable ordering, no timestamps) so regeneration is diff-clean.
**Reuse:** `plugins/session-workflow/skills/toolkit-awareness/scripts/scan_toolkit.py::_read_frontmatter`
loaded via importlib from the plugin tree — the parser stays single-sourced in
the plugin (which must remain standalone when installed), and the repo-level
generator imports it by path rather than copying it.
**Acceptance criterion:** running the generator twice yields a byte-identical
`AGENTS.md` listing all 23 skills, the `anchor` command, and the `step-digest`
output style, each with a non-empty description and an existing path; the
output carries no trailing whitespace and ends with exactly one newline (so
the pre-commit hygiene fixers and the §2 gate never fight over the bytes);
`evals/harness/test_gen_agents_md.py` (that directory, not `scripts/`, is
where `run_tests.py` discovers tests) asserts count, determinism, hygiene, and
banner presence, and appears in `run_tests.py` output.

### §2 Freshness gate for generated artifacts
Wire `scripts/gen_agents_md.py --check` (exit 1 when the committed `AGENTS.md`
differs from a fresh render) into `.pre-commit-config.yaml` as a local hook and
into `.github/workflows/validate.yml` as a CI step. This mechanizes the
derived-artifact integrity invariant from
`docs/adr/0001-single-source-portable-core.md`: a hand edit or a stale index
fails the gate, and the fix is always "re-run the generator".
**Acceptance criterion:** a deliberate one-character edit to `AGENTS.md` makes
`pre-commit run --all-files` and the CI job fail with a message naming the
generator; regenerating clears both.

### §3 Capability-conditional pass — session-workflow
Rewrite the harness-gated wording per
`docs/adr/0005-capability-conditional-language.md` in the session-workflow
skills: `plugins/session-workflow/skills/review-panel/SKILL.md` (drop the
"Claude Code only" gates at lines 4 and 97 in favor of "requires spawning
fresh-context subagents; without that capability, run each lens sequentially in
a clean context and accept the loss of concurrency", keeping the CC-specific
Workflow/Agent-tool mechanics as a mechanism footnote);
`plugins/session-workflow/skills/compaction-survival/SKILL.md` (state the
protocol against "context reset" generically — manual anchor re-read where no
re-injection hook exists; the SessionStart matcher
`plugins/session-workflow/hooks/hooks.json:22` `compact|resume` stays as the CC
mechanism note); `plugins/session-workflow/skills/toolkit-awareness/SKILL.md`
(inventory sources ladder: CC CLI when present, else the generated `AGENTS.md`,
else a directory scan); and `plugins/session-workflow/skills/evaluate-skill/SKILL.md`
(name the runner backend as CC-only today, per
`docs/adr/0006-eval-runner-abstraction.md`). The touched set includes the
plugin README's own harness-gated lines
(`plugins/session-workflow/README.md:29` and `:34` still read "Claude Code
only"), and any frontmatter-description edit regenerates `AGENTS.md` in the
same PR — an obligation from PR01 onward, mechanized when §2's gate lands. Conditional text replaces absolute text first;
where replacement-in-place would force cutting load-bearing prose (nearly
every body sits at zero `scripts/word_budget.json` headroom), the
pre-authorized fallback is the ratchet's own escape valve — a reviewed
baseline bump that names what the growth displaces.
**Acceptance criterion:** no load-bearing instruction in the four bodies gates
on a harness name (grep for "Claude Code only" returns no hits outside
mechanism footnotes); register linter and word budget pass; trigger evals
pass for the touched skills, and holdout evals where a sealed holdout exists
(review-panel and evaluate-skill have trigger sets but no holdouts today);
eval results recorded in the PR.

### §4 Capability-conditional pass — humblepowers
Same policy applied to `plugins/humblepowers/skills/choosing-tools/SKILL.md`
(the "in-context skill listing" fallback generalizes to "the harness's skill
listing or the repo's `AGENTS.md` index"),
`plugins/humblepowers/skills/planned-execution/SKILL.md` and its
`subagent-prompts.md` (subagent dispatch becomes the capability ladder:
fresh-context subagents when available, else sequential clean-context
execution), and `plugins/humblepowers/skills/choosing-models/SKILL.md` (routing
advice references its `models.toml` data rather than assuming CC model
switching). Word-budget and register constraints — including the
reviewed-baseline-bump fallback and the same-PR `AGENTS.md` regeneration
obligation — as in §3.
**Acceptance criterion:** the three bodies carry capability-conditional
phrasing with CC mechanics demoted to footnotes; register linter, word budget,
and the touched skills' trigger evals (plus holdouts, which all three have)
pass, with results recorded in the PR.

### §5 Capability-conditional pass — engineering-discipline
Same policy applied to
`plugins/engineering-discipline/skills/python-engineering/SKILL.md` and
`plugins/engineering-discipline/skills/refresh-stack/SKILL.md`: hook-dependent
statements ("the hook formats on every edit") gain the enforcement-ladder
phrasing from `docs/adr/0003-hooks-core-adapter-precommit-floor.md` — act-time
on a hook-capable harness, else the pre-commit floor of §7, else advisory.
The data-engineering-discipline skill is already harness-neutral; it is
re-read and touched only if a gated phrase is found. Word-budget and register
constraints — including the reviewed-baseline-bump fallback and the same-PR
`AGENTS.md` regeneration obligation — as in §3.
**Acceptance criterion:** both bodies describe enforcement via the ladder
instead of assuming a hook fired; register linter and word budget pass;
python-engineering's trigger and holdout evals pass with results recorded in
the PR; refresh-stack is exempt by name — it is `disable-model-invocation:
true` with no trigger dataset, so no eval run is owed for it.

### §6 Hook adapter seam
Create `plugins/engineering-discipline/hooks/harness_adapters.py`: it
**imports and wraps** the extraction and decision functions where they already
live (`target_file` and `ruff_commands` in `ruff_format.py`, `verdict` and
`cwd_is_uv_project` in `uv_enforce.py`, `_load_payload` in `stop_nudge.py` —
nothing is relocated out of the hook modules: the existing tests import the
ruff/uv symbols by name, and `_load_payload` stays put for the same
no-relocation stability) plus a documented extension point — an adapter is a
function from a harness payload to the core call and a mapping from the core
verdict to that harness's blocking convention. The existing hook files keep
their CLI entry points and CC behavior byte-for-byte (same stdin, same exit
codes, same messages); existing hook tests stay green untouched, and new tests
cover the adapter functions directly.
**Acceptance criterion:** `scripts/run_tests.py` passes with the three existing
hook test files unmodified; `harness_adapters.py` has its own tests; a diff of
hook behavior on the CC payload fixtures shows no change.

### §7 Consumer pre-commit floor
Create the commit-time tier of the enforcement ladder as a consumable package:
(a) `scripts/check_uv_hygiene.py` — fails when a uv-managed project (detected
the same way as `plugins/engineering-discipline/hooks/uv_enforce.py:69`'s
`def verdict` core, via `cwd_is_uv_project`) contains pip/poetry/virtualenv
residue: `requirements.txt` alongside `uv.lock`, a committed `Pipfile`, or a
tracked `venv/`; (b) a repo-root `.pre-commit-hooks.yaml` exporting that check
as a hook id, so a consumer references this repository as a pre-commit `repo:`
by URL — the delivery mechanism, since a local `entry:` would resolve against
the consumer's root where the script does not exist; and (c)
`adapters/pre-commit/craft-floor.yaml` — the copy-pasteable consumer config
combining `ruff-format` + `ruff` (mirroring `.pre-commit-config.yaml:30`
`id: ruff-format`) with the exported hygiene hook, its comments naming the
act-time CC hook each entry substitutes for. Tests live in `evals/harness/`
(the repo's home for scripts-targeting tests), since `scripts/run_tests.py`
discovers only `plugins/` and `evals/`.
**Acceptance criterion:** `evals/harness/test_check_uv_hygiene.py` covers
clean and dirty fixture trees and appears in `run_tests.py` output; in a
scratch fixture consumer repo, `pre-commit run --all-files` with
`craft-floor.yaml` installed resolves and executes every entry, hygiene hook
included.

### §8 Eval runner seam
Refactor the eval runner per `docs/adr/0006-eval-runner-abstraction.md`: define
an `AgentRunner` protocol (spawn a prompt in an isolated context; return an
`AgentRun`) and move the `claude -p` specifics into a `ClaudeRunner`
implementation of it. The edit surface is `evals/harness/claude_runner.py` —
the sync **source** per `evals/harness/test_scripts_in_sync.py`, which holds
`plugins/session-workflow/skills/evaluate-skill/scripts/` as a byte-identical
mirror of the seven SYNCED engine files (`aggregate.py`, `claude_runner.py`,
`grade_tasks.py`, `judge.py`, `run_all.py`, `run_triggers.py`, `stats.py`).
Edit in `evals/harness/`, update the call sites there (`run_triggers.py`,
`grade_tasks.py`, `judge.py` accept the protocol type), then re-copy every
changed SYNCED file to the plugin mirror in the same PR — the PR's one concern
is the seam; the two-tree diff is the sync gate's requirement, not scope creep.
Pure parts (`parse_stream`, `build_command`, `AgentRun`) are untouched. No
second backend is added.
**Acceptance criterion:** existing evaluate-skill runner tests and
`test_scripts_in_sync.py` pass; the harness's call sites reference the
protocol; constructing the CC backend is one line at the composition root.

### §9 Portability guide and installation matrix
Create `docs/portability.md`: the per-harness installation matrix (Claude Code
via marketplace; any other agent via `git clone` + `AGENTS.md`, per
`docs/adr/0004-distribution-git-clone-mcp-deferred.md`), the enforcement
degradation ladder with what each tier does and does not guarantee, manual
usage of the `anchor` command
(`plugins/session-workflow/commands/anchor.md:2` `Snapshot the run's control anchor`)
and the `step-digest` style
(`plugins/session-workflow/output-styles/step-digest.md:2` `step-digest`) on
harnesses without commands/output-styles (both are plain markdown an agent can
be pointed at), the measurement-scope statement ("designed for any
agents.md-reading harness; trigger behavior measured on Claude Code"), and the
named MCP revisit trigger. README links to it from the install section, and
each plugin's CHANGELOG carries its entry for this wave's changes in the same
PR that lands them.
**Acceptance criterion:** `docs/portability.md` exists covering matrix, ladder,
commands/output-style manual use, measurement scope, and the MCP trigger;
README links to it; `validate_plugins.py` passes, and
`scripts/lint_register.py docs/` is run explicitly in the PR (the linter's
default scope is `plugins/` only, so a bare invocation never sees `docs/`).

## PR ↔ section manifest

| PR | Implements section | One concern? |
|---|---|---|
| PR01 | §1 | yes |
| PR02 | §2 | yes |
| PR03 | §3 | yes |
| PR04 | §4 | yes |
| PR05 | §5 | yes |
| PR06 | §6 | yes |
| PR07 | §7 | yes |
| PR08 | §8 | yes |
| PR09 | §9 | yes |

Dependency notes (a DAG, not extra coverage): PR02 depends on PR01; PR03–PR05
reference the index PR01 creates and the ladder PR07 names, but are textually
independent and can land in any order after PR01; PR09 lands last so the guide
describes shipped reality.

## Definition of Done (this spec)

- All nine sections merged with their acceptance criteria demonstrated in the
  PR descriptions (eval runs included for §3–§5).
- `AGENTS.md` freshness gate green in pre-commit and CI; a stale-index commit
  is demonstrably rejected (§2's criterion).
- Claude Code behavior regression-checked: hook payload fixtures byte-identical
  (§6), runner tests unchanged (§8), no marketplace/packaging diffs.
- Each plugin's CHANGELOG entry for this wave landed in the same PR as the
  change it describes (release-notes-in-wave).
- Generated / mirrored / snapshot artifacts downstream of touched surfaces:
  `AGENTS.md` (freshness gate: `gen_agents_md.py --check`, §2); the
  `plugins/session-workflow/skills/evaluate-skill/scripts/` mirror of the
  seven SYNCED engine files (freshness gate:
  `evals/harness/test_scripts_in_sync.py`, re-copied in §8's PR); the
  `scripts/word_budget.json` baselines for any §3–§5 body whose count moves —
  shrinking may lower a baseline deliberately, and a growth lands only as the
  §3 fallback: a reviewed bump naming what it displaces — otherwise none.

## Pre-mortem certification

- **Reviewer:** pre-mortem-review-r2 (fresh subagent, non-author; round 1 by pre-mortem-review, also fresh and non-author)
- **Verdict:** CERTIFIED — round 2 resolution audit: FM-1..FM-9 all RESOLVED, zero new findings under the rising bar, three non-blocking advisories (ADV-1 header artifact list completeness, ADV-2 `.pre-commit-hooks.yaml` needs `language: script` since the repo is not pip-installable, ADV-3 soften §6's over-broad test-import justification) recorded here for the implementing PRs
- **Certification artifact:** docs/specs/agent-portability.premortem.md
- **Date:** 2026-07-16
- **Reviewed against:** the live tree at this commit; no external dependency SHAs (gates executed read-only: word_budget, lint_register, validate_plugins; keel kit 0.13.1)
- **Post-fold coherence:** author re-read post-fold and reconciled two fold-introduced inconsistencies (gate-commands eval scope; AGENTS.md-regeneration timing vs PR ordering) without moving ledger anchors; round-2 reviewer independently re-verified coherence (sections vs gate commands vs DoD vs manifest) and all nine ledger anchors
- **Failure modes considered & folded in:** FM-1 sync-twin edit surface (BLOCKER), FM-2 word-budget zero-headroom fallback, FM-3 consumer hook delivery, FM-4 vacuous test homing, FM-5 phantom eval datasets, FM-6 relocation-breaks-tests, FM-7 generated-byte hygiene, FM-8 vacuous docs/ lint, FM-9 README drift + regeneration obligation — one fold-ledger row each below
- **Note:** the only body edit after the certified pass is the Status line (draft → ready), recording this gate's own outcome; a B2 revision WARN against the saved Spec-hash reflects that single line and is the honest record, not drift
- **Advisory folds (2026-07-16, post-implementation):** ADV-1 folded — the Output artifact(s) header now names the §8 runner seam and the §2 gate wiring; ADV-3 folded — §6's test-import justification narrowed so it no longer over-claims for `_load_payload`; ADV-2 required no spec edit (`language: script` shipped in `.pre-commit-hooks.yaml`)

### Fold ledger

| Finding | Target section | artifact:line | Confirmed |
|---|---|---|---|
| FM-1 sync-twin edit surface + 7-file re-copy + sync gate in acceptance | §8 | `docs/specs/agent-portability.md:247` `evals/harness/test_scripts_in_sync.py` | yes |
| FM-2 reviewed baseline-bump fallback pre-authorized | §3 (referenced by §4, §5) | `docs/specs/agent-portability.md:162` `baseline bump that names what the growth displaces` | yes |
| FM-3 consumer delivery via `.pre-commit-hooks.yaml` + fixture-repo acceptance | §7 | `docs/specs/agent-portability.md:226` | yes |
| FM-4 tests homed in `evals/harness/` + run_tests output asserted | §1, §7 | `docs/specs/agent-portability.md:123` | yes |
| FM-5 eval criteria scoped to existing datasets; refresh-stack exempted | §3, §5 | `docs/specs/agent-portability.md:201` `refresh-stack is exempt by name` | yes |
| FM-6 adapters wrap in place; nothing relocated | §6 | `docs/specs/agent-portability.md:206` `**imports and wraps**` | yes |
| FM-7 generated-byte hygiene pinned | §1 | `docs/specs/agent-portability.md:121` `exactly one newline` | yes |
| FM-8 explicit `lint_register.py docs/` run | §9 | `docs/specs/agent-portability.md:279` | yes |
| FM-9 plugin README in touched set + same-PR AGENTS.md regeneration | §3–§5 | `docs/specs/agent-portability.md:156` | yes |
