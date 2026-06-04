# Skill Evaluation Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (the integration tasks spawn real agents and benefit from checkpoints) or superpowers:subagent-driven-development for the isolated pure-logic tasks. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build a self-contained, CLI-only Python harness that evaluates the plugin skills across trigger accuracy, correct usage, auto-activation, and with/without result quality — all via the `claude` CLI on the subscription (no Anthropic API, no Node).

**Architecture:** A shared `claude_runner` (subprocess → `claude -p`, toggling `--plugin-dir`/`--bare`) feeds `run_triggers` (axes 1 & 3) and `grade_tasks`+`judge` (axes 2 & 4); `aggregate` emits a scorecard. The pure logic (stream parsing, stats, judge JSON extraction, scoring) is unit-tested on canned data; the subprocess/agent integration is validated by smoke runs behind an early go/no-go gate.

**Tech Stack:** Python 3.13 **stdlib only** (`json`, `subprocess`, `math`, `statistics`, `argparse`, `pathlib`, `re`); the `claude` CLI for every agent and judge run. Tests are stdlib-runnable (`python test_x.py`), matching the plugin repo's convention.

**Reference:** [docs/specs/2026-06-04-eval-harness-design.md](../specs/2026-06-04-eval-harness-design.md). Datasets use `.json` (not `.yaml`) to keep the harness stdlib-only.

---

## Conventions

- All harness code under `evals/harness/`; datasets under `evals/{trigger,tasks}/`; outputs under `evals/report/`.
- Pure functions are unit-tested; integration (real `claude -p`) is validated by smoke runs with explicit acceptance criteria.
- After each task: run its test/smoke, then commit (Conventional Commits).
- Work on a branch `build/eval-harness` (created at execution start), not `main`.

---

## Phase 0 — Scaffold

### Task 0.1: Directories + config + gitignore

**Files:** Create `evals/config.json`, `evals/harness/__init__.py` (empty), `evals/.gitignore`

- [ ] `evals/config.json`:

```json
{
  "agent_model": "claude-sonnet-4-6",
  "judge_model": "claude-sonnet-4-6",
  "agent_repeats": 3,
  "judge_repeats": 1,
  "max_turns": 8,
  "max_budget_usd": 0.50,
  "timeout_seconds": 300,
  "allowed_tools_trigger": "Skill,Read,Glob,Grep",
  "allowed_tools_task": "Skill,Read,Glob,Grep,Write,Edit,Bash",
  "gates": { "trigger_recall": 0.8, "trigger_specificity": 0.9, "correct_usage": 0.7 },
  "plugin_of_skill": {
    "journaling-sessions": "session-workflow",
    "context-handoff": "session-workflow",
    "data-engineering-discipline": "engineering-discipline"
  }
}
```

- [ ] `evals/.gitignore` → `report/` (generated outputs are not committed).
- [ ] **Commit:** `chore(evals): scaffold harness config`

---

## Phase 1 — Pure foundations (TDD)

### Task 1.1: `stats.py`

**Files:** Create `evals/harness/stats.py`, `evals/harness/test_stats.py`

- [ ] **Step 1 — failing test:**

```python
from stats import wilson_interval, majority

def test_wilson_known_values():
    lo, hi = wilson_interval(8, 10)          # 80% of 10
    assert 0.49 < lo < 0.50 and 0.94 < hi < 0.95
    lo, hi = wilson_interval(0, 0)           # no data -> (0,1)
    assert (lo, hi) == (0.0, 1.0)

def test_majority():
    assert majority([True, True, False]) is True
    assert majority([False, False, True]) is False
    assert majority([]) is None
```

- [ ] **Step 2:** `python test_stats.py` → FAIL (module missing).
- [ ] **Step 3 — implement** (stdlib `math` only):

```python
from __future__ import annotations
import math

def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% CI for a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))

def pass_rate(successes: int, n: int) -> float:
    return successes / n if n else 0.0

def majority(votes: list[bool]) -> bool | None:
    if not votes:
        return None
    return sum(votes) * 2 > len(votes)
```

- [ ] **Step 4:** `python test_stats.py` → `ok`.
- [ ] **Commit:** `feat(evals): stats helpers (Wilson CI, majority)`

### Task 1.2: `claude_runner.parse_stream`

**Files:** Create `evals/harness/claude_runner.py` (parser + `AgentRun` only this task), `evals/harness/test_parse_stream.py`

- [ ] **Step 1 — failing test** (canned NDJSON exercises plugin load, Skill detection, result):

```python
import json
from claude_runner import parse_stream

LINES = [
  json.dumps({"type":"system","subtype":"init","plugins":[{"name":"session-workflow"}],"plugin_errors":[]}),
  json.dumps({"type":"assistant","message":{"content":[
      {"type":"tool_use","name":"Skill","input":{"name":"session-workflow:journaling-sessions"}}]}}),
  json.dumps({"type":"result","result":"done","total_cost_usd":0.01,"num_turns":2,"is_error":False}),
]

def test_parses_activation_and_result():
    run = parse_stream(LINES)
    assert "journaling-sessions" in " ".join(run.activated_skills)
    assert run.plugin_loaded("session-workflow") and not run.plugin_errors
    assert run.cost_usd == 0.01 and run.num_turns == 2 and run.is_error is False

def test_tolerates_garbage_lines():
    run = parse_stream(["not json", ""] + LINES)
    assert run.activated_skills
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3 — implement** `AgentRun` dataclass + `parse_stream(lines)`: iterate lines, `json.loads` each in a try/except (skip undecodable); collect `plugins`/`plugin_errors` from any `system/init`; for any object containing a `tool_use` block (search nested `content` lists) with `name=="Skill"`, record the `input.name`/`input.skill`/`input.command` value into `activated_skills`; from the `result` event take `result`, `total_cost_usd`, `num_turns`, `is_error`. Add `plugin_loaded(name)` and `activated(target)` (substring match) helpers.
- [ ] **Step 4:** `python test_parse_stream.py` → `ok`.
- [ ] **Commit:** `feat(evals): defensive stream-json parser + AgentRun`

### Task 1.3: `judge.extract_verdict`

**Files:** Create `evals/harness/judge.py` (extraction helper only this task), `evals/harness/test_judge.py`

- [ ] **Step 1 — failing test** (judge replies are messy text with JSON inside):

```python
from judge import extract_verdict

def test_extracts_fenced_json():
    txt = 'Here is my assessment:\n```json\n{"score":0.8,"pass":true,"reason":"ok"}\n```\n'
    v = extract_verdict(txt)
    assert v["score"] == 0.8 and v["pass"] is True

def test_extracts_bare_json_object():
    v = extract_verdict('prose {"score": 0.4, "pass": false, "reason": "x"} more')
    assert v["pass"] is False

def test_returns_none_on_no_json():
    assert extract_verdict("no json here") is None
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3 — implement** `extract_verdict(text)`: try fenced ```json block first (regex), else find the first balanced `{...}` substring; `json.loads`; return dict or `None`. Stdlib `re`/`json`.
- [ ] **Step 4:** `python test_judge.py` → `ok`.
- [ ] **Commit:** `feat(evals): judge verdict JSON extraction`

---

## Phase 2 — Runner subprocess + the go/no-go smoke gate

### Task 2.1: `claude_runner.run_agent` (subprocess + retry)

**Files:** Modify `evals/harness/claude_runner.py`

- [ ] Add `run_agent(prompt, *, plugin_dir=None, allowed_tools, model, max_turns, max_budget_usd, timeout, stream=True) -> AgentRun`:
  - Build the command per spec §7.1 (always `--bare --no-session-persistence --permission-mode bypassPermissions`; `--output-format stream-json --verbose` when `stream`, else `--output-format json`; add `--plugin-dir` when given). Prompt via `subprocess.run(..., input=prompt, capture_output=True, text=True, encoding='utf-8', timeout=timeout)`.
  - On `stream`, `parse_stream(stdout.splitlines())`; else parse the single JSON object into an `AgentRun` (no activation info).
  - Retry transient failures (exit≠0 with no result, or stderr matching 429/529/5xx/overloaded/network) with exponential backoff + jitter (ported from `pr-pilot-main/src/pr_pilot/claude.py`); never retry timeouts.
- [ ] No unit test (subprocess); validated by Task 2.2.
- [ ] **Commit:** `feat(evals): claude_runner.run_agent subprocess + retry`

### Task 2.2: SMOKE — validate the assumptions ⛔ CHECKPOINT

**Files:** Create `evals/harness/smoke.py` (throwaway-but-kept manual check)

- [ ] `smoke.py` runs three real checks and prints PASS/FAIL for each:
  1. **plugin loads:** `run_agent("Say hi.", plugin_dir="plugins/session-workflow", allowed_tools="Read", ...)` → `run.plugin_loaded("session-workflow")` and no `plugin_errors`.
  2. **skill fires & is detected:** a journaling-style prompt (a short fake "session" then "journal this") with `plugin_dir="plugins/session-workflow"` → `run.activated("journaling-sessions")` is True.
  3. **judge returns parseable JSON:** call the Task-3 `judge_pointwise` prototype (or an inline `run_agent` with a grading prompt) → `extract_verdict(...)` is not None.
- [ ] Run: `python evals/harness/smoke.py`
- [ ] **CHECKPOINT — stop and report results.** Acceptance: all three PASS. If (1) fails → `--bare`+`--plugin-dir` incompatible; switch to a non-bare baseline or settings-based loading. If (2) fails → fall back to transcript-JSONL inspection or, if headless auto-activation is genuinely weak, pivot the usage axes to **explicit `/skill` invocation** and record that as the headline finding. If (3) fails → tighten the judge prompt / add a JSON-only instruction. **Do not proceed to Phase 3+ until the path is confirmed.**
- [ ] **Commit:** `test(evals): assumption smoke checks`

---

## Phase 3 — Triggering (axes 1 & 3)

### Task 3.1: Trigger datasets

**Files:** Create `evals/trigger/{journaling-sessions,context-handoff,data-engineering-discipline}.json`

- [ ] Each file: a JSON list of `{ "query": "...", "should_trigger": true|false, "note": "..." }`, ~8 positives (formal + casual + **implicit** phrasings + edge cases; substantive, never trivial one-step) and ~8 negatives (near-misses, adjacent domains). Seed from the existing `plugins/*/evals/*.json` samples and expand. Example positives/negatives are enumerated in spec §8.
- [ ] **Commit:** `feat(evals): trigger datasets for 3 skills`

### Task 3.2: `run_triggers.py`

**Files:** Create `evals/harness/run_triggers.py`, `evals/harness/test_run_triggers.py`

- [ ] **Step 1 — failing test** for the pure scorer (inject a fake runner so no agents spawn):

```python
from run_triggers import score_skill

def fake_run(query, repeats):           # returns trigger count k out of `repeats`
    return 3 if "journal" in query else 0

def test_scoring_recall_specificity():
    queries = [{"query":"journal this","should_trigger":True},
               {"query":"what's 2+2","should_trigger":False}]
    r = score_skill(queries, repeats=3, trigger_counter=fake_run)
    assert r["recall"] == 1.0 and r["specificity"] == 1.0
    assert "recall_ci" in r and "specificity_ci" in r
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3 — implement** `score_skill(queries, repeats, trigger_counter)`: for each query call `trigger_counter(query, repeats)` → k; positives' mean k/repeats = recall, negatives' mean (1−k/repeats) = specificity; attach Wilson CIs (`stats.wilson_interval` over summed successes/trials). Add the real `trigger_counter` that calls `run_agent(..., plugin_dir=plugin_of_skill[skill])` and counts `run.activated(skill)`. CLI: `python run_triggers.py <skill> [--limit N] [--dry-run]` → writes `report/triggers.json`, prints recall/specificity ±CI vs gates.
- [ ] **Step 4:** `python test_run_triggers.py` → `ok`.
- [ ] **Commit:** `feat(evals): trigger runner + scorer`

### Task 3.3: Real trigger run (one skill)

- [ ] `python evals/harness/run_triggers.py journaling-sessions --limit 4` → sanity-check the numbers and the `triggers.json` shape before scaling. (No commit — verification step.)

---

## Phase 4 — Grading (axes 2 & 4)

### Task 4.1: Task datasets + rubrics

**Files:** Create `evals/tasks/<skill>/{tasks.json,rubric.json}` and `fixtures/` for the 3 skills

- [ ] `tasks.json`: list of `{ "id", "prompt", "fixture": "fixtures/x.md"|null }` (3–5 per skill, from spec §8).
- [ ] `rubric.json`: list of `{ "id", "text", "weight" }` criteria encoding the skill's discipline (spec §7.4 examples — including journaling's "no private system/project names leaked").
- [ ] Fixtures: the session transcript / handoff scenario / pipeline-diff inputs.
- [ ] **Commit:** `feat(evals): task prompts, rubrics, fixtures for 3 skills`

### Task 4.2: `judge.py` — pointwise + pairwise

**Files:** Modify `evals/harness/judge.py`, `evals/harness/test_judge.py`

- [ ] **Step 1 — failing test** for aggregation over canned verdicts (inject a fake judge call):

```python
from judge import aggregate_pointwise, decide_pairwise

def test_aggregate_pointwise_majority_and_agreement():
    verdicts = [{"score":0.8,"pass":True}, {"score":0.9,"pass":True}, {"score":0.2,"pass":False}]
    agg = aggregate_pointwise(verdicts)
    assert agg["pass"] is True and abs(agg["score"]-0.633) < 0.01 and abs(agg["agreement"]-0.667) < 0.01

def test_decide_pairwise_requires_order_agreement():
    assert decide_pairwise("A","B")["winner"] == "A"     # A won both orders
    assert decide_pairwise("A","B_then_A_says_first")["winner"] == "tie"  # disagreement -> tie
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3 — implement:**
  - `judge_pointwise(task, output, rubric, *, model, repeats)`: render the grading prompt (criteria list + task + output, demanding strict JSON `{"criteria":[...],"score","pass","reason"}`), call `run_agent(prompt, plugin_dir=None, allowed_tools="", model=model, stream=False)` `repeats`×, `extract_verdict` each, `aggregate_pointwise` (mean score, majority pass, agreement fraction).
  - `judge_pairwise(task, out_a, out_b, criterion, *, model)`: render an A/B prompt; call once as (A,B) and once as (B,A); `decide_pairwise` returns the winner only if both orders agree, else `tie`.
  - Keep `aggregate_pointwise` / `decide_pairwise` as pure functions (tested).
- [ ] **Step 4:** `python test_judge.py` → `ok`.
- [ ] **Commit:** `feat(evals): judge pointwise + pairwise (swap-order)`

### Task 4.3: `grade_tasks.py`

**Files:** Create `evals/harness/grade_tasks.py`, `evals/harness/test_grade_tasks.py`

- [ ] **Step 1 — failing test** for orchestration shape (inject fake runner + judge): assert that for one task it produces a record with `with_pass`, `pairwise_winner`, and per-arm cost, over `agent_repeats`.
- [ ] **Step 2/3:** implement `grade_skill(skill, tasks, rubric, cfg, runner, judge)`: for each task × `agent_repeats`, run WITH (`plugin_dir`) and WITHOUT (`--bare`, `plugin_dir=None`) arms; `judge_pointwise(with_output)` → axis 2; `judge_pairwise(with, without)` → axis 4; collect into `report/grading.json`. CLI: `python grade_tasks.py <skill> [--limit] [--dry-run]`.
- [ ] **Step 4:** test passes.
- [ ] **Commit:** `feat(evals): grade_tasks orchestrator`

### Task 4.4: Real grading run (one task)

- [ ] `python evals/harness/grade_tasks.py context-handoff --limit 1` → sanity-check `grading.json` + judge agreement. (Verification step.)

---

## Phase 5 — Aggregate + docs

### Task 5.1: `aggregate.py`

**Files:** Create `evals/harness/aggregate.py`, `evals/harness/test_aggregate.py`

- [ ] **Step 1 — failing test:** feed sample `triggers.json` + `grading.json` dicts → assert the scorecard rows carry recall/specificity ±CI, correct-usage pass-rate ±CI + agreement, with/without win-rate, and gate PASS/FAIL flags.
- [ ] **Step 2/3:** implement `build_scorecard(triggers, grading, gates)` (pure) + a CLI that reads `report/*.json` and writes `report/scorecard.md`.
- [ ] **Step 4:** test passes.
- [ ] **Commit:** `feat(evals): aggregate scorecard`

### Task 5.2: `README.md`

**Files:** Create `evals/README.md`

- [ ] Document: prerequisites (just `python` + `claude` CLI logged in — **no API key, no Node**), how to run each stage, `--dry-run`/`--limit`, the cost note, the deferred κ judge-validation step, and the Task-2.2 assumptions/findings.
- [ ] **Commit:** `docs(evals): harness README`

---

## Phase 6 — Full focused run

### Task 6.1: Run + review

- [ ] `--dry-run` across all 3 skills to print the spawn count + budget estimate.
- [ ] Run `run_triggers.py` and `grade_tasks.py` for all 3 skills, then `aggregate.py`.
- [ ] Review `report/scorecard.md`; fold findings back into skill descriptions/rubrics (separate change). Commit the datasets/harness; `report/` stays gitignored.
- [ ] **Commit:** `test(evals): first focused run datasets finalized`

---

## Self-Review

**Spec coverage:** §6 layout → Phase 0 + files across phases. §7.1 runner → T1.2/T2.1. §7.2 triggers → Phase 3. §7.3 judge+grade → Phase 4. §7.4 judge rigor (swap-order, agreement) → T4.2. §7.5 aggregate/stats → T1.1/T5.1. §8 datasets → T3.1/T4.1. §9 cost guards (`--dry-run`/`--limit`, budget) → config + CLIs. §11 assumptions → **T2.2 gate**. §12 build sequence → phase order. No gaps.

**Placeholder scan:** pure-logic tasks carry real test + impl code; integration tasks carry precise specs + smoke acceptance (the honest substitute for unit tests on subprocess code, flagged up front). No TBDs.

**Type consistency:** `AgentRun`, `parse_stream`, `run_agent`, `wilson_interval`, `majority`, `extract_verdict`, `aggregate_pointwise`, `decide_pairwise`, `score_skill`, `grade_skill`, `build_scorecard` each defined once and referenced consistently. `plugin_of_skill` config keys match the three skill names throughout.
