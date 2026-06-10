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

All seven skills ship with trigger datasets and sealed holdouts.

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
| writing / executing plans | your planning tool (keel, pr-pilot, harness plan mode) |
| subagent orchestration | harness Agent tool, pr-pilot |
| git worktrees | harness-native worktree isolation |
| finishing a branch | folded into verification-before-completion |

No planning or orchestration skills ship here; pair the pack with your
planning tool of choice.

## Optional hook (off by default)

| behaviour | enable with |
|---|---|
| Compact dispatch protocol injected at session start | `HUMBLEPOWERS_DISPATCH_INJECT=1` |

## Register linter

`scripts/lint_register.py` (repo root) gates this plugin's markdown in
pre-commit and CI: imperative-obedience phrases, importance banners, and runs
of three or more consecutive all-caps words outside code fail the commit. The
linter is the mechanical enforcement of the skill-authoring doctrine.

## Measured behavior (0.2.0 — 2026-06-10, claude-sonnet-4-6, dispatch inject enabled)

| skill | recall dev → holdout | specificity dev → holdout | correct-usage | WITH vs WITHOUT |
|---|---|---|---|---|
| brainstorming | 0.88 → 0.88 | 1.00 → 1.00 | — | — |
| receiving-code-review | 0.75 → 0.88 | 1.00 → 1.00 | — | — |
| choosing-tools | 0.75 → 0.75 | 1.00 → 0.75 | — | — |
| skill-authoring | 0.38 → 0.25 ¹ | 1.00 → 1.00 | — | — |
| systematic-debugging | 0.25 → 0.62 ¹ | 1.00 → 1.00 | 0.33–0.67 (n=3) | WITH 0.67 / tie 0.33 |
| test-driven-development | 0.00 → 0.12 ¹ | 1.00 → 1.00 | 0.00 ² | WITH 0.83 / WITHOUT 0.17 |
| verification-before-completion | 0.00 → 0.00 ¹ | 1.00 → 1.00 | **1.00 pass** | WITH 0.33 / tie 0.50 |

No skill shows a dev→holdout collapse — descriptions were never tuned against
the dev sets, and unseen-prompt behavior matches measured behavior.

¹ The trigger arm allows no Write/Edit/Bash tools, so disciplines that
activate *during real work* under-measure there (and Write-less runs that spin
to timeout count as misses — e.g. 7/12 errored runs for skill-authoring).
Activation measured in the working (grading) arm instead: TDD 0.50–0.83,
systematic-debugging 0.67, verification 0.33. Treat trigger recall as the
meaningful gate only for the conversational skills.

² Strict rubric: an *executed* failing run before implementation and an
executed green run after, within an 8-turn budget. The pairwise preference for
the skill arm is decisive (0.83 vs 0.17) even where the bright-line evidence
gate fails. Whether an imperative register would do better on identical tasks
is the open register-ablation question — the task suites here are built to run
that A/B (same tasks, superpowers arm vs humblepowers arm).

## Attribution

Process content derived from
[obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent
(MIT). The register, dispatch architecture, and authoring doctrine are
replaced; the ported disciplines keep their upstream constraint sets.
