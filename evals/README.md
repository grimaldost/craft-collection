# Skill evaluation harness

A self-contained, **CLI-only** harness that measures whether the plugin skills
(1) **trigger** in the right scenarios, (2) **don't** fire on near-misses,
(3) are **used correctly** when they fire, and (4) **improve results** versus no
skill. Every agent run and every judge call goes through the `claude` CLI on the
subscription — **no Anthropic API key, no Node, no promptfoo.** Pure-Python,
stdlib only.

## Coverage

Every auto-triggering skill in both plugins has a trigger dataset under
`trigger/` (most also have correct-usage tasks under `tasks/`). `refresh-stack`
is intentionally **excluded** — it sets `disable-model-invocation: true` (it is
the manual-only `/refresh-stack` command), so auto-activation is not-applicable
by design rather than a failure, and its real behavior needs live PyPI/changelog
access a headless run can't supply. `command_first_skills` in `config.json`
lists skills whose low auto-recall is expected (slash-first invocation) and
reported as informational rather than gated.

## Prerequisites

- `python` 3.13+ (stdlib only — nothing to `pip install`).
- The `claude` CLI on `PATH`, **logged in** (`/login`, subscription auth).
  The harness copies your credential into a throwaway config; it never mutates
  your real `~/.claude`.

That's it. No environment variables, no API key.

## How isolation works (the load-bearing trick)

Each run uses a temp `CLAUDE_CONFIG_DIR` containing **only `.credentials.json`**
from `~/.claude` — authenticated and nothing else. No `CLAUDE.md` (it carries real
repo paths and discipline text that contaminate both arms — a trigger-arm spawn
once followed those breadcrumbs and wrote into a real repo), no `settings.json`
(permission grants), no `history.jsonl`, no `plugins/` dir. The two A/B arms then
differ by exactly one thing:

- **WITHOUT arm** — that clean config, no `--plugin-dir`. Zero skills.
- **WITH arm** — clean config **+ `--plugin-dir plugins/<plugin>`**. Only the one
  target plugin's skills load.

Tool access is the other half of isolation: spawns run in headless default-deny
(**no** `--permission-mode bypassPermissions` — bypass auto-approves every tool
and turns `--allowed-tools` into decoration), so only the arm's explicit
allowlist is usable, and trigger arms additionally pass
`--disallowed-tools` (`disallowed_tools_trigger` in `config.json`) as
belt-and-braces. `smoke.py` asserts both properties on real spawns.

`--bare` is **not** used: it strips the config-bound subscription login. Skill
activation is detected from `--output-format stream-json` (a `tool_use` event that
names the `Skill` tool); on a spawn timeout the partial stream is still parsed, so
a skill that fired before the kill counts as fired (error runs can otherwise only
under-count activations, never invent them). See `harness/claude_runner.py`.

## Layout

```
evals/
  config.json            models, repeats, budgets, gates, plugin_of_skill map
  trigger/<skill>.json   ~8 should-trigger (incl. implicit) + ~8 should-not, each
  tasks/<skill>/         tasks.json + rubric.json + fixtures/  (axes 2 & 4)
  harness/
    claude_runner.py     spawner + stream parser + retry + isolation + map_concurrent
    run_triggers.py      axes 1 & 3: recall / specificity (+ Wilson CI) vs gates
    judge.py             LLM-judge: pointwise (rubric) + pairwise (swap-order)
    grade_tasks.py       axes 2 & 4: WITH vs WITHOUT, judged
    aggregate.py         merge -> report/scorecard.md
    stats.py             wilson_interval / pass_rate / majority
    run_all.py           drive the whole focused run end to end
    test_*.py            stdlib-runnable unit tests for the pure logic
  report/                generated triggers.json / grading.json / scorecard.md (gitignored)
```

## Running it

```bash
# unit tests (pure logic; no agents, no cost)
cd evals/harness && for t in test_*.py; do python "$t"; done

# cheap previews (no spawns)
python evals/harness/run_triggers.py journaling-sessions --dry-run
python evals/harness/grade_tasks.py  journaling-sessions --dry-run

# one skill, small slice
python evals/harness/run_triggers.py journaling-sessions --limit 4 --concurrency 6
python evals/harness/grade_tasks.py  context-handoff      --limit 1 --concurrency 4

# the whole focused run (all covered skills, triggers + grading + scorecard)
python evals/harness/run_all.py --concurrency 6
```

Outputs land in `report/`: `triggers.json`, `grading.json`, and the rendered
`scorecard.md`. `report/` is gitignored — datasets and harness are the committed
artifacts.

### Cost & guards

Every spawn carries `--max-budget-usd` and `--max-turns` (see `config.json`).
Each runner prints an upfront spawn count and a ceiling, and supports `--dry-run`
(plan only) and `--limit` (cap). The full focused run is ~250 `claude -p` spawns
(~144 trigger + ~105 grading); empirically ~$15–25 and ~30 min wall at
`--concurrency 6`. Lower `--repeats`, `--limit` the set, or drop `--concurrency`
to trim.

Run **one runner at a time**: `report/triggers.json` and `report/grading.json` are
merged read-modify-write only when a runner finishes, so two same-type runners in
parallel can clobber each other's entry. A `--limit`/`--repeats` partial run
likewise **overwrites** that skill's full entry (the runner prints a NOTE when it
is about to).

## What the numbers mean

- **Recall** — of the should-trigger queries, the fraction of runs that fired the
  skill. Gate: ≥ `gates.trigger_recall`. Errored runs (timeout/budget) count as
  misses in this strict number; when any non-firing positive run errored, the
  runner also prints **recall excl. errored runs** — those runs carry no evidence
  about the description either way (`errors_no_activation` per query in
  `triggers.json`).
- **Action-discipline skills** (`action_discipline_skills` in `config.json` —
  TDD, systematic-debugging, verification-before-completion, skill-authoring):
  the trigger arm deliberately denies Write/Edit/Bash, so skills that activate
  *during real work* are structurally unmeasurable there — an agent asked to
  "implement X" with no working tools answers in prose and consults nothing.
  Their trigger-arm recall is reported as **(info)**, and the gated recall proxy
  is the grading arm's **activation rate** (the WITH arm of `grade_tasks`, where
  the agent actually works); the scorecard carries that gate in the Activation
  column. Evidence for the split: identical machinery measures conversational
  skills at 0.75–0.88 recall while TDD floors at 0.00 with 0.50–0.83 task-arm
  activation (2026-06-10, humblepowers).
- **Specificity** — of the should-NOT queries, the fraction that correctly stayed
  quiet. Gate: ≥ `gates.trigger_specificity`.
- **Correct-usage** — pointwise pass-rate of the WITH-arm output against the
  skill's per-criterion discipline rubric. Gate: ≥ `gates.correct_usage`.
- **WITH / WITHOUT win-rate** — swap-order pairwise: the skill output wins only
  when both A/B orderings agree (else a tie), to control position bias.
- All rates carry a **Wilson 95% CI**; with 3 repeats a CI this wide is expected —
  treat single-run numbers as directional, not final.

## Judge rigor & its limits

The judge is another `claude -p` call (no plugin) returning strict JSON. Mitigations
baked in: the pointwise **score is recomputed from rubric weights × the judge's
per-criterion met-flags** (not the model's arithmetic); pairwise runs **both
orderings** and requires agreement; `judge_repeats` can be raised and the reported
**agreement** number read before trusting a result.

**Known limit:** the CLI has no `--temperature`, so the judge can't be pinned to
temp-0. **Deferred (by design):** a human gold-set + Cohen's κ validation of the
judge before any number becomes a hard release gate. Until then these gates are
**directional signals for tuning**, not pass/fail release criteria.

## Validated assumptions (smoke gate)

`harness/smoke.py` confirmed the three load-bearing assumptions on real runs:
the clean copied-credential config is authenticated and `--plugin-dir` loads the
plugin cleanly; headless agents **do** auto-activate skills and the activation is
detectable in stream-json; and the CLI judge returns parseable JSON. The smoke
gate also caught a real plugin bug (a redundant `hooks` manifest key causing a
"Duplicate hooks file detected" error), since fixed.

## Reading the feedback-loop skills' numbers

- `tool-feedback`'s `tf-implicit` task is a deliberate obliqueness probe. If its
  per-task `with_activation_rate` comes back low (< ~0.7), read its correct-usage
  contribution as a *triggering* miss (cross-check the trigger eval) rather than
  a discipline failure.
- `feedback-triage` has a single grading task, so at `agent_repeats: 3` its
  correct-usage CI is very wide — treat the gate verdict as directional until
  more tasks or repeats exist. (A second, incremental-triage task wants a
  per-task rubric, which the engine's one-rubric-per-skill schema does not yet
  support — recorded 2026-06-09.)
