# Design: Skill evaluation harness

**Date:** 2026-06-04
**Author:** Grimaldo Stanzani
**Status:** Approved design — pending spec review, then implementation plan

---

## 1. Goal

Measure, with fresh headless agents, whether the plugin skills (1) **trigger** in
the right scenarios, (2) are **used correctly** when they fire, (3) **auto-activate
without being asked**, and (4) **improve results** vs. no skill. Hybrid harness:
Anthropic `skill-creator` methodology for triggering, `promptfoo` for graded
output and the with/without A/B, a thin shared runner + glue for the rest.

## 2. Scope

**Focused first:** three trigger-ambiguous skills — `journaling-sessions`,
`context-handoff`, `data-engineering-discipline`. ~16 trigger queries + 3–5 task
prompts each, 3 repeats, **Sonnet** judge. Built to extend to all six skills and
to CI later, but the first run is deliberately cheap.

## 3. Confirmed decisions

| # | Decision |
|---|---|
| A | **Custom Python promptfoo provider** (`call_api`) wrapping the shared runner, so with/without is a clean `--plugin-dir`/`--bare` flag — over promptfoo's built-in `claude-agent-sdk` provider. |
| B | **Defer judge-validation** (human gold set + Cohen's κ) to a later pass; first run uses a temp-0 rubric judge with position-bias mitigation only. |
| C | Harness lives at **`skill-collection/evals/`**. |
| scope | Focused-first (3 skills, 3 repeats, Sonnet judge). |

## 4. Operating principles

- **Fresh agent per test**, no contamination: `--no-session-persistence`, and
  both A/B arms run `--bare` so nothing but the one plugin differs.
- **Reuse pr-pilot's patterns, don't import them**: copy the `subprocess` +
  JSON-parse + retry/backoff approach from `pr-pilot-main/src/pr_pilot/claude.py`;
  pr-pilot stays an independent sibling.
- **Stdlib-first harness** (Wilson CI computed inline, no scipy); promptfoo via
  `npx` (no install); judge via promptfoo's Anthropic provider.
- **Report rates with confidence intervals, not single pass/fail** — activation
  and trajectories are stochastic.

## 5. Architecture

```
prompt ─► claude_runner (claude -p --bare [--plugin-dir X] --output-format stream-json)
             │  parses: system/init (plugin loaded?) + Skill tool_use (which skill fired) + result/cost
             ├─► run_triggers.py     ── axes 1 & 3 (does the right Skill fire? P/R + Wilson CI)
             └─► promptfoo provider   ── axes 2 & 4 (llm-rubric correct-usage; select-best with/without)
                                          │
                          aggregate.py ◄──┘  merge → pass-k gates, CIs, with/without delta → report
```

## 6. Repository layout

```
evals/
├── README.md                       # how to run, prerequisites (ANTHROPIC_API_KEY for judge)
├── harness/
│   ├── claude_runner.py            # shared agent spawner + stream-json parser + retry
│   ├── run_triggers.py             # axes 1 & 3 runner + scorer
│   ├── aggregate.py                # Wilson CI, pass-k gates, merged report
│   ├── stats.py                    # wilson_interval(), pass_rate() — stdlib only
│   ├── promptfoo_provider.py       # custom call_api provider wrapping claude_runner
│   └── test_*.py                   # stdlib-runnable tests for the pure logic
├── trigger/                        # axes 1 & 3 datasets (skill-creator format)
│   ├── journaling-sessions.json    # [{query, should_trigger, note}]  (~8 pos incl. implicit / ~8 neg)
│   ├── context-handoff.json
│   └── data-engineering-discipline.json
├── tasks/                          # axes 2 & 4 datasets
│   ├── journaling-sessions/    { tasks.yaml, rubric.md, fixtures/ }
│   ├── context-handoff/        { tasks.yaml, rubric.md, fixtures/ }
│   └── data-engineering-discipline/ { tasks.yaml, rubric.md, fixtures/ }
├── promptfooconfig.yaml            # with/without providers + assertions + --repeat
└── report/                         # generated markdown/HTML
```

(The Phase-8 `plugins/*/evals/*.json` remain as lightweight shipped samples; the
canonical, expanded trigger sets live here in `evals/trigger/`.)

## 7. Component specs

### 7.1 `claude_runner.py` (the shared spawner)

`run_agent(prompt, *, plugin_dir=None, allowed_tools, model, max_turns, max_budget_usd, timeout) -> AgentRun`

- Builds: `claude -p --output-format stream-json --verbose --permission-mode bypassPermissions --no-session-persistence --bare --model <model> --max-turns <n> --max-budget-usd <b> --allowed-tools <tools>`; adds `--plugin-dir <plugin_dir>` only on the WITH arm. Prompt via stdin.
- Parses the NDJSON stream **defensively** (event shapes vary by CLI version):
  - `system`/`init` event → `plugins_loaded`, `plugin_errors` (fail the run if the target plugin errored).
  - any `tool_use` block with name `Skill` → record the activated skill id from its input (match the target skill name as a substring, tolerant of plugin namespacing like `session-workflow:journaling-sessions`).
  - `result` event → `result_text`, `total_cost_usd`, `num_turns`, `is_error`.
- Returns `AgentRun(activated_skills: set[str], result_text, cost_usd, num_turns, is_error, raw_events)`.
- **Retry** transient failures (429/529/5xx/network/zero-turn) with exponential backoff + jitter, ported from pr-pilot; never retry timeouts.
- Pure-ish: the stream parser `parse_stream(lines) -> AgentRun` is a separate, unit-tested function (no subprocess), so tests feed canned NDJSON.

### 7.2 `run_triggers.py` (axes 1 & 3)

- Loads `evals/trigger/<skill>.json` (skill-creator format). Query-quality bar:
  realistic, substantive, concrete details; **no trivial one-step queries** (they
  never trigger regardless of description). Positives include casual + **implicit**
  phrasings (axis 3); negatives are near-misses / adjacent domains.
- For each query, run the WITH arm **3×** (`run_agent(..., plugin_dir=plugins/<plugin-of-skill>)`); a query "triggered" if the target skill is in `activated_skills` on a run. Compute per-query **trigger rate** (k/3).
- Aggregate per skill: **recall** (mean trigger rate over positives), **specificity** (mean 1−trigger-rate over negatives), with **Wilson 95% CIs** (`stats.wilson_interval`). Per-skill gate: recall ≥ 0.8 and specificity ≥ 0.9 (tunable).
- Output `evals/report/triggers.json` per skill/query/run. When a skill misses its gate, the report names it and recommends running **skill-creator's `run_loop`** optimizer on its trigger set (on-demand, not automatic).

### 7.3 Graded output — promptfoo (axes 2 & 4)

- `promptfooconfig.yaml`: two providers via the **custom Python provider**
  (`file://harness/promptfoo_provider.py`), labelled `with-skill`
  (`config.plugin_dir = plugins/<x>`) and `without-skill` (`config.plugin_dir = null`).
  Provider `call_api(prompt, options, context)` calls `run_agent`, returns
  `{output: result_text, tokenUsage, cost}`.
- `tests` come from `evals/tasks/<skill>/tasks.yaml` (prompt + fixture refs).
  Assertions:
  - **`llm-rubric`** (pointwise, **temperature-0 Sonnet** judge via
    `provider: anthropic:messages:claude-sonnet-4-6` with `config.temperature: 0`),
    `value` = the per-criterion rubric from `rubric.md`, with an explicit
    **`threshold`** (avoid the "0/1 rubric without threshold always passes" trap).
    This is axis 2 (correct usage).
  - **`select-best`** across the two providers' outputs — axis 4 (with vs.
    without). Run **both orderings** and require agreement (position-bias
    mitigation).
- `--repeat 3`. Emit `-o evals/report/grading.json` (+ JUnit).
- **Prerequisite:** the judge needs `ANTHROPIC_API_KEY`; the agent runs use the
  existing `claude` CLI auth. Documented in `evals/README.md`.

### 7.4 Judge rigor (the "master-agent-eval helper")

- Rubrics are **analytic, one criterion per rule of the skill's discipline**
  (e.g. journaling: "produced ENTRY_START/END envelopes", "one idea per entry",
  "anti-patterns captured", "reasoning inline", "multi-pass ran", "**no private
  system/project names leaked**").
- Temp-0 judge; **position-bias mitigation** by swapping order on `select-best`
  and permuting rubric-level order across repeats.
- **Deferred (Decision B):** the human gold-set + Cohen's κ judge validation.
  `evals/README.md` documents the procedure as the next rigor step before any
  number is used as a hard gate.

### 7.5 `aggregate.py` + `stats.py`

- `stats.py`: `wilson_interval(successes, n, z=1.96) -> (lo, hi)` and helpers,
  stdlib `math` only; unit-tested against known values.
- `aggregate.py`: merge `triggers.json` + promptfoo `grading.json` → a per-skill
  scorecard (trigger recall/specificity ±CI; correct-usage pass-rate ±CI;
  with/without win-rate + cost/turns delta), apply pass-k gates
  (3-repeat → "≥2/3" or report the rate), and render
  `evals/report/scorecard.md`.

## 8. Test data (focused-first)

Per skill: ~8 should-trigger (incl. implicit) + ~8 should-not, plus 3–5 task
prompts with fixtures and a `rubric.md`.

- **journaling-sessions** — fixture: a substantive multi-decision session
  transcript. Tasks: "journal this", an end-of-session implicit cue. Rubric: the
  six discipline checks above. Negatives: "consolidate my old journals" (downstream
  pass), trivial Q&A.
- **context-handoff** — fixture: a context-laden mid-task scenario. Tasks:
  "/subtask …", "fork this to focus on X". Rubric: correct mode, facts-not-refs,
  concrete specifics, fenced block + REINTEGRATION_NOTE, self-contained.
  Negatives: "run these two in parallel now" (Task tool), trivial questions.
- **data-engineering-discipline** — fixture: a pipeline-refactor diff + a
  "numbers changed" report. Tasks: migrate / refactor / investigate. Rubric:
  pinned baseline/contract, named the non-negotiables, proposed parity checks, no
  silent semantic change. Negatives: throwaway notebook exploration, a CLI-parsing
  task.

## 9. Cost & guards

Focused run ≈ 144 trigger spawns (3×~16×3) + ~72 task spawns (3×~4×3×2 arms) +
~100 Sonnet judge calls. Every `run_agent` carries `--max-budget-usd` and
`--max-turns`; the harness prints an upfront estimate and supports
`--dry-run` (list planned runs without spawning) and `--limit` (cap spawns).

## 10. Non-goals (YAGNI for the first run)

- No judge κ gold-set validation yet (Decision B).
- No all-six-skill coverage yet (focused-first).
- No CI wiring yet — first run is local; the promptfoo config is CI-ready for later.
- No automatic description optimization — `run_loop` is invoked by hand only when a
  skill misses its trigger gate.

## 11. Key assumptions to validate first (step 2 smoke run)

The harness hinges on three research-derived assumptions; the step-2 smoke run
must confirm all three, or the design adapts:

- **`--bare` + `--plugin-dir` coexist** — bare mode still loads the one
  explicitly-passed plugin, and its skills' descriptions reach the system prompt
  so they can auto-activate.
- **Skill activation is detectable** in `--output-format stream-json` (a
  `tool_use` event names the `Skill` tool with the skill id). If not, fall back to
  transcript JSONL inspection or an output-signature heuristic.
- **Headless agents auto-activate skills at all** — eager skill invocation may
  behave differently headless. If activation is weak even for clear positives,
  that itself is a finding worth reporting (and shifts emphasis toward explicit
  `/skill` invocation for the correct-usage axes).

## 12. Build sequence

1. `stats.py` (+ test) → `claude_runner.py` parser (+ test on canned NDJSON).
2. `claude_runner.py` subprocess + retry; smoke one real `--bare --plugin-dir` run.
3. `trigger/*.json` datasets (3 skills) → `run_triggers.py` → first trigger numbers.
4. `tasks/*` datasets + rubrics → `promptfoo_provider.py` + `promptfooconfig.yaml`
   → first graded A/B.
5. `aggregate.py` → `scorecard.md`; `evals/README.md`.
6. Full focused run; review the scorecard; fold findings back into skill
   descriptions/rubrics.
```
