# Design: Skill evaluation harness (self-contained, CLI-only)

**Date:** 2026-06-04
**Author:** Grimaldo Stanzani
**Status:** Approved design (revised — promptfoo dropped) — pending spec review, then plan

---

## 1. Goal

Measure, with fresh headless agents, whether the plugin skills (1) **trigger** in
the right scenarios, (2) are **used correctly** when they fire, (3) **auto-activate
without being asked**, and (4) **improve results** vs. no skill. Everything runs
through the **`claude` CLI on the existing subscription** — no Anthropic API key,
no Node/promptfoo. A self-contained Python harness drives the agent runs, the
trigger detection, the LLM-judge, and the scorecard.

## 2. Scope

**Focused first:** three trigger-ambiguous skills — `journaling-sessions`,
`context-handoff`, `data-engineering-discipline`. ~16 trigger queries + 3–5 task
prompts each, 3 agent-repeats, **Sonnet** judge (via CLI). Built to extend to all
six skills later; the first run is deliberately cheap.

## 3. Confirmed decisions

| # | Decision |
|---|---|
| A′ | **Self-contained CLI harness — no promptfoo, no Anthropic API.** Agents and judge both run via `claude -p` (subscription auth). We reimplement the small slice of grading we need (pointwise rubric + pairwise swap-order). |
| Judge | Runs at the CLI's **default sampling** (no temp-0). Offset with a strict-JSON rubric, optional K-repeat majority, and a reported **judge self-agreement** number. |
| B | **Defer judge-validation** (human gold set + Cohen's κ) to a later pass. |
| C | Harness lives at **`skill-collection/evals/`**. |
| scope | Focused-first (3 skills, 3 agent-repeats, Sonnet judge, judge-repeat=1 to start). |

## 4. Operating principles

- **CLI-only:** every LLM call — agent runs *and* judging — goes through
  `claude -p` on the subscription. Zero API key, zero Node.
- **Fresh agent per test**, no contamination: `--no-session-persistence`; both A/B
  arms run `--bare` so nothing but the one plugin differs.
- **Reuse pr-pilot's patterns, don't import them**: copy the subprocess +
  JSON-parse + retry/backoff approach from `pr-pilot-main/src/pr_pilot/claude.py`.
- **Stdlib-first** (Wilson CI inline, no scipy; JSON/CSV only).
- **Report rates with confidence intervals, not single pass/fail** — activation,
  trajectories, and an un-temp-0 judge are all stochastic.

## 5. Architecture

```
                 ┌────────────────────────────────────────────┐
prompt ─────────►│ claude_runner: claude -p --bare [--plugin-dir X]│
                 │   --output-format stream-json                 │
                 │   parses: plugin-loaded? · Skill fired? · result/cost │
                 └───────────────┬───────────────┬──────────────┘
                                 │               │
        run_triggers.py ◄────────┘               └────────► grade_tasks.py
        (axes 1 & 3: did the right                          (axes 2 & 4:
         Skill fire? P/R + Wilson CI)                        with vs --bare)
                                                                  │
                                                   judge.py (claude -p, no plugin):
                                                   · pointwise rubric  (axis 2)
                                                   · pairwise swap-order (axis 4)
                                 ┌────────────────────────────────┘
                    aggregate.py ► scorecard.md (CIs, pass-k gates, with/without delta)
```

The judge is just another `claude_runner` call (no plugin, `--bare`) with a
grading prompt that returns strict JSON.

## 6. Repository layout

```
evals/
├── README.md                       # how to run; prereq = just python + claude CLI (no API key, no Node)
├── harness/
│   ├── claude_runner.py            # shared agent/judge spawner + stream-json parser + retry
│   ├── run_triggers.py             # axes 1 & 3 runner + scorer
│   ├── judge.py                    # LLM-judge via claude -p: judge_pointwise(), judge_pairwise()
│   ├── grade_tasks.py              # axes 2 & 4 orchestrator (with/without arms → judge)
│   ├── aggregate.py                # merge → Wilson CI, pass-k gates, scorecard
│   ├── stats.py                    # wilson_interval(), pass_rate(), majority() — stdlib only
│   └── test_*.py                   # stdlib-runnable tests for the pure logic
├── trigger/                        # axes 1 & 3 datasets (skill-creator format)
│   ├── journaling-sessions.json    # [{query, should_trigger, note}] (~8 pos incl. implicit / ~8 neg)
│   ├── context-handoff.json
│   └── data-engineering-discipline.json
├── tasks/                          # axes 2 & 4 datasets
│   ├── journaling-sessions/    { tasks.yaml, rubric.json, fixtures/ }
│   ├── context-handoff/        { tasks.yaml, rubric.json, fixtures/ }
│   └── data-engineering-discipline/ { tasks.yaml, rubric.json, fixtures/ }
├── config.json                     # models, repeats, budgets, gates
└── report/                         # generated triggers.json, grading.json, scorecard.md
```

(The Phase-8 `plugins/*/evals/*.json` remain lightweight shipped samples; the
canonical expanded trigger sets live here in `evals/trigger/`. `rubric.json` is a
list of criteria, not prose, so the judge prompt and the scorer share one source.)

## 7. Component specs

### 7.1 `claude_runner.py` (shared spawner — agents AND judge)

`run_agent(prompt, *, plugin_dir=None, allowed_tools, model, max_turns, max_budget_usd, timeout, stream=True) -> AgentRun`

- Builds `claude -p [--output-format stream-json --verbose | --output-format json] --permission-mode bypassPermissions --no-session-persistence --bare --model <m> --max-turns <n> --max-budget-usd <b> --allowed-tools <tools>`; adds `--plugin-dir <plugin_dir>` only on the WITH arm. Prompt via stdin.
- `stream=True` (agent runs): parse NDJSON **defensively** — `system/init` (plugin loaded? `plugin_errors`?), any `tool_use` with name `Skill` (record activated skill id; substring-match the target, tolerant of `plugin:skill` namespacing), `result` (text, cost, turns, is_error).
- `stream=False` (judge runs): `--output-format json`, take `result` text.
- Returns `AgentRun(activated_skills, result_text, cost_usd, num_turns, is_error, raw)`.
- **Retry** transient failures (429/529/5xx/network/zero-turn) with backoff+jitter, ported from pr-pilot; never retry timeouts.
- `parse_stream(lines) -> AgentRun` is a separate, unit-tested pure function fed canned NDJSON.

### 7.2 `run_triggers.py` (axes 1 & 3) — unchanged from prior design

- Load `evals/trigger/<skill>.json`. Query bar: realistic, substantive, concrete;
  **no trivial one-step queries**. Positives include casual + **implicit**
  phrasings (axis 3); negatives are near-misses / adjacent domains.
- Each query → WITH arm **3×**; "triggered" if the target skill ∈ `activated_skills`.
  Per-skill **recall** (mean over positives), **specificity** (mean over negatives),
  with **Wilson 95% CIs**. Gate: recall ≥ 0.8, specificity ≥ 0.9 (tunable).
- On a miss, the report recommends running skill-creator's `run_loop` (interactive,
  uses the session — no API key) to tune the description.

### 7.3 `judge.py` + `grade_tasks.py` (axes 2 & 4) — replaces promptfoo

`rubric.json` per skill = a list of criteria, each `{id, text, weight}`, encoding
the skill's discipline (one criterion per rule).

**`judge.py` (LLM-judge via `claude -p`, no plugin, `--bare`):**
- `judge_pointwise(task, output, rubric, *, model, repeats=1) -> Verdict`
  — grading prompt embeds the task, the agent output, and the criteria; the judge
  must return **strict JSON** `{"criteria":[{"id","met":bool,"evidence"}], "score":0..1, "pass":bool, "reason"}`.
  Run `repeats` times; aggregate (majority `met`/`pass`, mean `score`); report
  **agreement** (fraction concurring). Robust JSON extraction from the CLI text.
- `judge_pairwise(task, output_a, output_b, criterion, *, model) -> {winner, agreement}`
  — present A/B, ask which better satisfies the criterion → `{"winner":"A|B|tie","reason"}`.
  **Run both orderings** (swap A/B) and require agreement; disagreement → `tie`
  (position-bias mitigation, since we can't pin temp-0).

**`grade_tasks.py` (orchestrator):**
- For each skill × task (from `tasks.yaml` + `fixtures/`), 3 agent-repeats:
  run the **WITH** arm (`--plugin-dir`) and the **WITHOUT** arm (`--bare`).
  - Axis 2: `judge_pointwise` on the **WITH** output vs. the rubric → correct-usage
    pass-rate.
  - Axis 4: `judge_pairwise(with, without)` swap-order → win-rate for the skill.
- Emit `evals/report/grading.json` (per task/repeat: rubric verdict, pairwise
  winner, cost/turns for both arms).

### 7.4 Judge rigor (the "master-agent-eval helper")

- Analytic **per-criterion** rubric (the skill's discipline; e.g. journaling:
  "ENTRY_START/END envelopes", "one idea per entry", "anti-patterns captured",
  "reasoning inline", "multi-pass ran", "**no private system/project names leaked**").
- Position-bias mitigation by swapping order on pairwise and (optionally) permuting
  criterion order across judge-repeats.
- **No temp-0** (CLI limitation) → raise `judge_repeats` (config) and read the
  reported agreement before trusting a number.
- **Deferred (Decision B):** human gold-set + Cohen's κ judge validation; documented
  in `evals/README.md` as the next rigor step before any number becomes a hard gate.

### 7.5 `aggregate.py` + `stats.py`

- `stats.py`: `wilson_interval(successes, n, z=1.96)`, `pass_rate()`, `majority()` —
  stdlib `math` only; unit-tested against known values.
- `aggregate.py`: merge `triggers.json` + `grading.json` → per-skill scorecard
  (trigger recall/specificity ±CI; correct-usage pass-rate ±CI + judge agreement;
  with/without win-rate + cost/turns delta), apply pass-k gates (3 repeats → "≥2/3"
  or report the rate), render `evals/report/scorecard.md`.

## 8. Test data (focused-first) — unchanged

Per skill ~8 should-trigger (incl. implicit) + ~8 should-not, plus 3–5 task prompts
with fixtures and a `rubric.json`.

- **journaling-sessions** — fixture: a substantive multi-decision session transcript.
  Tasks: "journal this", an end-of-session implicit cue. Rubric: the six discipline
  checks above. Negatives: "consolidate my old journals" (downstream pass), trivial Q&A.
- **context-handoff** — fixture: a context-laden mid-task scenario. Tasks: "/subtask …",
  "fork this to focus on X". Rubric: correct mode, facts-not-refs, concrete specifics,
  fenced block + REINTEGRATION_NOTE, self-contained. Negatives: "run these two in
  parallel now" (Task tool), trivial questions.
- **data-engineering-discipline** — fixture: a pipeline-refactor diff + a "numbers
  changed" report. Tasks: migrate / refactor / investigate. Rubric: pinned
  baseline/contract, named the non-negotiables, proposed parity checks, no silent
  semantic change. Negatives: throwaway notebook exploration, a CLI-parsing task.

## 9. Cost & guards

Focused run ≈ 144 trigger spawns (3×~16×3) + ~72 task spawns (3×~4×3×2 arms) +
judging: ~72 pointwise (`judge_repeats=1`) + ~36 pairwise × 2 orderings ≈ 72 →
**~360 `claude -p` spawns total**, all on the subscription (judge calls are CLI
processes, so heavier/slower than an API call). Every spawn carries
`--max-budget-usd` + `--max-turns`; the harness prints an upfront estimate and
supports `--dry-run` (list planned runs) and `--limit` (cap spawns). Lower
`judge_repeats`/agent-repeats or grade fewer tasks to cut cost.

## 10. Non-goals (YAGNI for the first run)

- No promptfoo, no Node, **no Anthropic API**.
- No temp-0 judge (CLI can't); mitigated by repeats + agreement reporting.
- No judge κ gold-set validation yet (Decision B).
- No all-six-skill coverage yet (focused-first).
- No CI wiring yet — first run is local; harness writes JSON so CI can consume later.
- No automatic description optimization — `run_loop` invoked by hand on a trigger miss.

## 11. Key assumptions to validate first (step-2 smoke run)

The harness hinges on these; the step-2 smoke run must confirm them or the design adapts:

- **`--bare` + `--plugin-dir` coexist** — bare mode still loads the one passed
  plugin, and its skills' descriptions reach the system prompt so they can
  auto-activate.
- **Skill activation is detectable** in `--output-format stream-json` (a `tool_use`
  event names the `Skill` tool with the skill id). Else fall back to transcript
  JSONL or an output-signature heuristic.
- **Headless agents auto-activate skills at all** — if activation is weak even for
  clear positives, that itself is a finding (and shifts the usage axes toward
  explicit `/skill` invocation).
- **The CLI judge returns parseable JSON reliably** and its self-agreement across
  repeats is high enough to trust — checked on a couple of grading prompts before
  building out `grade_tasks.py`.

## 12. Build sequence

1. `stats.py` (+ test) → `claude_runner.parse_stream` (+ test on canned NDJSON).
2. `claude_runner.py` subprocess + retry; **smoke one real `--bare --plugin-dir` run**
   to validate §11 (plugin loads, a skill fires and is detected) **and** one
   `judge.py` call (JSON parses, agreement sane).
3. `trigger/*.json` (3 skills) → `run_triggers.py` → first trigger numbers.
4. `tasks/*` + `rubric.json` → `judge.py` + `grade_tasks.py` → first graded A/B.
5. `aggregate.py` → `scorecard.md`; `evals/README.md`.
6. Full focused run; review the scorecard; fold findings back into skill
   descriptions/rubrics.
```
