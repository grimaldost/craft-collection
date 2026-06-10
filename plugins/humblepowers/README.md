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

Arriving through 0.2.x as derived ports, each with datasets and sealed
holdouts: test-driven-development, systematic-debugging, brainstorming,
verification-before-completion, receiving-code-review. Each port ships with an
explicit retained/removed ledger against its upstream source.

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

## Attribution

Process content derived from
[obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent
(MIT). The register, dispatch architecture, and authoring doctrine are
replaced; the ported disciplines keep their upstream constraint sets.
