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
gating every auto-triggering skill from birth.

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
| choosing-models | flexible | Capacity dispatch: which model and effort a delegated or priced task should run on |
| refresh-models | manual-only command | `/refresh-models` — detect model-lineup drift against `models.toml` and propose a reviewable changeset |

Nine of the ten skills ship with trigger datasets and sealed holdouts;
`refresh-models` is manual-only (`disable-model-invocation: true`), so
auto-activation is not applicable.

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

## Dispatch hook (on by default)

A UserPromptSubmit hook runs deterministic word-boundary regexes
(`router_rules.json`, calibrated against `evals/trigger/*.json`) over a
substantive human prompt and injects a short `<toolkit-dispatch>` block naming at
most two candidate skills, each with its own activation test. Silent on no match,
on slash-commands, on short follow-ups, and on subagent-completion notices.

It ships **on**: an enforcement hook whose gate nobody sets has never run, and
the no-match path returns zero with no output, so a default-on hook costs a
subprocess and nothing else. Opt out in the `env` block of your settings file
(`~/.claude/settings.json` for every project, `<repo>/.claude/settings.json` for
one):

```json
{ "env": { "HUMBLEPOWERS_DISPATCH_PROMPT_INJECT": "0" } }
```

`HUMBLEPOWERS_DISPATCH_ROUTER=0` disables the router itself, which silences the
hook the same way — there is nothing else to inject.

Two things keep the hint honest. It names each candidate by its **activation
test** — one question the reader can answer no to — rather than by the words that
matched, because a bare lexical token is something the matched skill's own
description explicitly does not rest on. And it drops a candidate whose skill is
not installed here: five of the ten routed rows name skills in sibling plugins,
so on a single-plugin install the hint used to recommend skills that were not
there. Directory names are also removed from the prompt before matching, so a
project called `something-pipeline` does not fire the data rule for the life of
that project.

The hook fails open (any error or timeout means silence, never a blocked
prompt), keeps payloads ASCII, and logs each decision (router hits, candidates
dropped as not installed, whether a hint shipped) to a size-capped local NDJSON
(`dispatch-log.ndjson` in its state dir); read it back with
`inject_dispatch.py --health`. Router calibration
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

## Verification gate (off by default, opt in)

A SubagentStop hook
(`skills/verification-before-completion/scripts/subagent_gate.py`) blocks a
subagent's **first** stop once and returns a discipline reconsideration —
"are you actually confident this is correct, or are you assuming it is?" — then
lets every later stop through. One shot per `(session_id, agent_id)`, so the
block cannot loop and concurrent subagents do not share a counter; it fails open
on any error, because a hook that cannot decide must never be the reason a
subagent cannot stop.

Arm it in the `env` block of your settings file:

```json
{ "env": { "HUMBLEPOWERS_VERIFICATION_SUBAGENT_GATE": "1" } }
```

It ships **off**, unlike the dispatch hint, and the asymmetry is deliberate: a
hint costs a few tokens, while this one blocks a stop in every subagent in your
environment. What funds it today is one bank — three tiers, two tasks, nine
repeats per cell — where the same wording moved the rate at which delegated work
left a regression check behind by **+0.22 (haiku) / +0.56 (sonnet) / +0.44
(opus, 90% CI [+0.11, +0.78])**, at a false-positive rate of 0/12 on trivial
edits where verification work would have been over-scope. That is enough to
offer, not enough to impose; default-on waits on a replication with a different
task family.

Read those numbers with two scope limits attached. **Both arms behind them ran
with no skill body mounted** — the measured contrast is gate-vs-no-gate in a bare
delegated session, so it does not say what the gate adds *on top of* the
discipline this plugin already ships as prose. And the replication commissioned
to re-measure the gate here — including its false-positive rate and a
shape-matched placebo control — **was never bought**: no gate trial and no
placebo trial exists in this codebase's ledgers. The mechanism is offered as
unmeasured-here and inherited-from-elsewhere, which is why it is opt-in and why
it fails open.

Two things about the wording are worth knowing before editing it. It names no
artifact — no test, no check, no "add one now" — and a prescriptive sibling
measured on the same bank, which did name one, wrote a test on **every** trivial
code edit and was rejected on that alone. So the words are the treatment, and
`test_subagent_gate.py` pins them byte-for-byte.

`HUMBLEPOWERS_VERIFICATION_GATE_SKIP_MODELS` (comma-separated substrings, e.g.
`opus`) no-ops the gate when the stop payload names a matching model. It is
**provisional**: no measurement licenses any particular value, the payload key
it reads is unconfirmed across harness versions, and an absent model gates
rather than skips. It exists because a tier fact, if one is ever measured, is
implementable here and nowhere else — the harness cannot condition a skill's
activation on a subagent's model, so the same claim written into a skill
description would be a sentence nothing can act on. Left unset, the hook behaves
exactly like the fixture that was measured.

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
