# humblepowers

Superpowers-derived process disciplines in a calibrated register. Same powers,
no shouting.

[obra/superpowers](https://github.com/obra/superpowers) ships genuinely
valuable disciplines wrapped in a deliberate persuasion layer — imperative
register, importance banners, a meta-skill demanding invocation before any
response. That layer buys activation with salience instead of fit: it distorts
tool selection across the whole installed toolkit and forces neighboring tools
into a register arms race. humblepowers replicates the disciplines and
replaces the mechanism: calibrated trigger descriptions that compete on fit, a
central fit-ranking dispatch protocol, a register linter, and behavioral evals
gating every skill from birth.

## Skills

| skill | kind | job |
|---|---|---|
| choosing-tools | keystone | Fit-ranking dispatch: which installed skill, if any, owns a task |
| skill-authoring | keystone | Calibration doctrine for writing and revising skills; replaces persuasion-based authoring |
| test-driven-development | rigid port | Red-green-refactor: production code only against a test seen failing |
| systematic-debugging | rigid port | Four-phase root-cause-first protocol; three failed fixes is an architecture signal |
| brainstorming | flexible port | Idea to agreed design before implementation; decomposition for bundled requests |
| verification-before-completion | rigid port | Evidence before completion claims; red-green regression checks; verify delegated work |
| receiving-code-review | flexible port | Technical evaluation of incoming feedback; clarify-first; no performative agreement |
| planned-execution | rigid port | Midweight lane: executable-cold plan contract + per-task subagent loop with two-stage review |

All eight skills ship with trigger datasets and sealed holdouts.

## Install

```text
/plugin install humblepowers@craft-collection
```

**humblepowers replaces superpowers — never install both.** Five skill names
collide outright once the ported disciplines land, and two dispatch layers
would compete for the same decisions, re-creating exactly the selection noise
this plugin removes. Uninstall superpowers first.

## What was deliberately left out

Deduplicated against craft-collection and the Claude Code harness:

| upstream capability | owner |
|---|---|
| requesting code review | `/code-review`, session-workflow:review-panel |
| governed series planning / execution | keel, convoy (planned-execution covers the midweight lane in-pack) |
| ad-hoc parallel agent dispatch | harness Agent tool |
| git worktrees | harness-native worktree isolation |
| finishing a branch | folded into verification-before-completion |

Governed multi-PR machinery stays out of the pack by design; planned-execution
hands off to it the moment work wants gates and dependency DAGs.

## Optional hook (off by default)

| behaviour | enable with |
|---|---|
| Per-prompt lexical dispatch router: a UserPromptSubmit hook runs deterministic word-boundary regexes (`router_rules.json`, calibrated against `evals/trigger/*.json`) over a substantive human prompt and injects a short `<toolkit-dispatch>` block naming at most two candidate skills, with the matched words shown; silent on no match, on slash-commands, on short follow-ups, and on subagent-completion notices. | `HUMBLEPOWERS_DISPATCH_PROMPT_INJECT=1` |
| Disable the router — with nothing else to inject, this silences the hook entirely. | `HUMBLEPOWERS_DISPATCH_ROUTER=0` |

The hook fails open (any error or timeout means silence, never a blocked
prompt), keeps payloads ASCII, and logs each decision (router hits, whether a
hint shipped) to a size-capped local NDJSON (`dispatch-log.ndjson` in its state
dir); read it back with `inject_dispatch.py --health`. Router calibration
numbers are dev-set numbers by construction — the trigger datasets are also the
calibration corpus; seal a fresh holdout before citing generalization. Router
rules are English-lexicon; prompts in other languages match only on loanwords
(pipeline, backfill, dashboard, ETL).

**Retired in 0.8.0.** The generic dispatch *protocol* injection (both the
session-start `HUMBLEPOWERS_DISPATCH_INJECT` full-protocol print and the
per-prompt tiered cadence with `HUMBLEPOWERS_DISPATCH_FULL_EVERY` /
`_FULL_MINUTES` knobs) is gone: a 2026-07 content A/B measured the 8-step block
as no better than no injection, and the wall-clock / prompt-count cadence was
never validated. Only the concrete-candidate router hint — the one shape the
A/B favored — survives.

## Register linter

`scripts/lint_register.py` (repo root) gates **every plugin's** markdown in
pre-commit and CI: imperative-obedience phrases, importance banners, and runs
of three or more consecutive all-caps words outside code fail the commit. The
register doctrine governs the shared selection pool — a coercive description
distorts selection whichever plugin ships it — so the linter runs marketplace-
wide, not only over humblepowers. One rule is narrower: `non-negotiable` is
flagged only in a skill's frontmatter description (where it is a salience buy);
in body prose it is legitimate domain terminology (data-engineering-discipline's
"four non-negotiables"), so it is allowed there. The linter mechanically enforces
the *detectable subset* of the skill-authoring register rules; the rest of the
doctrine (calibration, negative space, evidence requirements) remains judgment
the linter cannot check.

## Measured behavior (0.2.0–0.3.0 — 2026-06-10/11, claude-sonnet-4-6, dispatch inject enabled)

Numbers come from local eval runs; the raw per-run records (`evals/report/`,
gitignored) are not committed, so the tables below are the surviving record —
re-measure with the session-workflow `evaluate-skill` engine to reproduce.

| skill | recall dev → holdout | specificity dev → holdout | correct-usage | WITH vs WITHOUT |
|---|---|---|---|---|
| brainstorming | 0.88 → 0.88 | 1.00 → 1.00 | — | — |
| receiving-code-review | 0.75 → 0.88 | 1.00 → 1.00 | — | — |
| choosing-tools | 0.75 → 0.75 | 1.00 → 0.75 | — | — |
| skill-authoring | 0.38 → 0.25 ¹ | 1.00 → 1.00 | — | — |
| systematic-debugging | 0.25 → 0.62 ¹ | 1.00 → 1.00 | 0.33–0.67 (n=3) | WITH 0.67 / tie 0.33 |
| test-driven-development | 0.00 → 0.12 ¹ | 1.00 → 1.00 | 0.00 ² | WITH 0.83 / WITHOUT 0.17 |
| verification-before-completion | 0.00 → 0.00 ¹ | 1.00 → 1.00 | **1.00 pass** | WITH 0.33 / tie 0.50 |
| planned-execution | 0.25 → 0.12 ¹ | 1.00 → 1.00 | 0.67 (n=3) | **WITH 1.00 sweep** ³ |

No skill shows a wholesale dev→holdout collapse, though three cells do drop
(choosing-tools specificity 1.00 → 0.75, skill-authoring recall 0.38 → 0.25,
planned-execution recall 0.25 → 0.12) — drops within the wide confidence
intervals these small sets carry (dev n = 8 per side; holdout n = 4 positives
/ 2 negatives, so a single held-out query moves recall by 0.25). Descriptions
were never tuned against the dev sets; treat the direction, not the point
values, as the signal.

¹ The trigger arm allows no Write/Edit/Bash tools, so disciplines that
activate *during real work* under-measure there (and Write-less runs that spin
to timeout count as misses — e.g. 7/12 errored runs for skill-authoring).
Activation measured in the working (grading) arm instead: TDD 0.50–0.83,
systematic-debugging 0.67, verification 0.33. Treat trigger recall as the
meaningful gate only for the conversational skills.

² Strict rubric: an *executed* failing run before implementation and an
executed green run after, within an 8-turn budget. The pairwise preference for
the skill arm is decisive (0.83 vs 0.17) even where the bright-line evidence
gate fails.

³ All six pairwise orderings preferred the WITH arm, at 0.00 Skill-tool
activation — the pack's presence (inject protocol + descriptions in context)
improves plan quality even when the skill is never explicitly invoked.

### Register ablation (same tasks, superpowers 5.1.0 arm vs humblepowers arm)

The imperative register buys *consultation*, not *compliance*: superpowers'
always-on inject lifts Skill activation to 1.00 on every skill (vs
humblepowers 0.33–0.67 with its calibrated inject), but compliance does not
move with it: TDD correct-usage is 0.00 on both arms (the executed-red/green
evidence rubric fails identically regardless of register),
verification-before-completion is 1.00 on both, and systematic-debugging's
rubric score is *lower* under superpowers (0.29 vs 0.75–0.79) with elevated
error runs (heavier context: 14 skills + banner inject). Verdict per axis:
selection pressure — register works; discipline adherence — register does
nothing the content didn't already do. The per-arm records were local eval
output (`evals/report/grading.json`, gitignored) and have since been
overwritten by later runs — the summary above is the surviving record; to
reproduce, re-run the grading arm against a superpowers 5.1.0 install.

## Attribution and license

Process content derived from
[obra/superpowers](https://github.com/obra/superpowers), Copyright (c) 2025
Jesse Vincent, MIT License. The register, dispatch architecture, and authoring
doctrine are replaced; the ported disciplines keep their upstream constraint
sets, and several reference examples are reproduced near-verbatim. This
plugin's [LICENSE](LICENSE) carries both license texts (ours and the upstream
third-party notice).
