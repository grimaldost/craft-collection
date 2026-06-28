# Eval harness — dataset formats, methodology, and gotchas

The engine in `scripts/` is stdlib-only Python. It spawns `claude -p --output-format
stream-json` subprocesses, parses whether the Skill tool fired and what was produced,
and judges output with an LLM. This file is the authoring + mechanism reference.

## 1. The `evals/` layout and the four files you write

```
evals/
  config.json
  trigger/<skill>.json
  tasks/<skill>/tasks.json
  tasks/<skill>/rubric.json
  tasks/<skill>/fixtures/*.md      # optional
  harness/*.py                     # this skill's scripts/, copied here
  report/                          # generated: triggers.json, grading.json, scorecard.md
```

### config.json

```json
{
  "agent_model": "claude-sonnet-4-6",
  "judge_model": "claude-sonnet-4-6",
  "agent_repeats": 3,
  "judge_repeats": 1,
  "max_turns": 8,
  "max_budget_usd": 0.50,
  "timeout_seconds": 300,
  "trigger_max_turns": 3,
  "trigger_routing_frame": "",
  "allowed_tools_trigger": "Skill,Read,Glob,Grep",
  "allowed_tools_task": "Skill,Read,Glob,Grep,Write,Edit,Bash",
  "gates": { "trigger_recall": 0.8, "trigger_specificity": 0.9, "correct_usage": 0.7 },
  "command_first_skills": ["review-panel"],
  "plugin_of_skill": { "my-skill": "my-plugin" }
}
```

- `plugin_of_skill` maps each skill to the plugin dir under `plugins/` that contains
  it — the WITH arm loads that plugin with `--plugin-dir plugins/<plugin>`.
- `agent_repeats` is how many times each prompt/task runs (3 is a sane default;
  higher tightens the CIs). `gates` are the pass/fail thresholds.
- `command_first_skills` are slash-invoked skills whose auto-recall is reported as
  informational, not gated (they are meant to be invoked, not to auto-fire).
- `trigger_max_turns` caps the trigger arm (default 3 — enough for a skill to fire,
  cheap). `trigger_routing_frame`, when non-empty, is passed as `--append-system-prompt`
  to every trigger spawn: a flail-damping lever that frames the run as a routing check,
  so a non-firing positive answers briefly instead of burning turns trying to do the
  task with no tools. **Default empty (off): it changes spawn behavior, so validate it
  with a live re-run — error-run rate drops while recall/specificity hold — before
  making it a default.**
- Exclude a `disable-model-invocation: true` skill from `plugin_of_skill` entirely —
  it cannot auto-activate by design, so the trigger axis does not apply.

### trigger/<skill>.json — a list of labelled prompts (aim for ~8 positive + ~8 negative)

```json
[
  { "query": "What skills and slash commands do I have installed?", "should_trigger": true,  "note": "canonical inventory" },
  { "query": "What Python libraries should I install?",            "should_trigger": false, "note": "near-miss: PyPI libs, not the CC toolkit" }
]
```

The **negatives are the hard part** — make them *near-misses* (share vocabulary with
the positives but are genuinely out of scope), not trivially unrelated. Cheap
negatives ("capital of France") inflate specificity without testing it.

A positive may carry `"expected_hard": true` (with a `note` documenting why): its miss
is an accepted model-behavior boundary, not a description gap — e.g. a bare imperative
("write a dogfooding feedback report for keel") the model executes directly instead of
routing to the Skill. It is scored and reported as **recall (expected-hard)** but
EXCLUDED from the gated recall, so tuning rounds stop re-spending on immovable queries
while a regression on them stays visible. `run_triggers.py` validates the dataset
before running — well-formedness, `expected_hard` only on a noted positive, no
duplicate queries — and fails fast on a malformed file.

### tasks/<skill>/tasks.json and rubric.json

```json
// tasks.json — each task is one prompt (+ optional fixture file prepended)
[ { "id": "migrate", "prompt": "Plan and carry out this migration.", "fixture": "fixtures/migration.md" } ]

// rubric.json — weighted criteria the WITH-output is scored against
[ { "id": "pins-baseline", "weight": 2, "text": "Declares the baseline contract being protected before changing anything." } ]
```

Write rubric criteria as **observable behaviors a judge can check from the output**,
not vibes. Weight the load-bearing ones higher. Keep criteria *scenario-generic* if a
task is reused across migrate/investigate-style prompts, or a migrate-only criterion
will be unsatisfiable elsewhere and depress the score unfairly.

## 2. The three axes and how they are computed

- **Triggering** (`run_triggers.py`): runs each `query` headless with the plugin
  loaded, `allowed_tools_trigger`. **Recall** = positives that fired / positives
  (`expected_hard` positives are excluded from this gated number and reported as
  `recall_hard`). **Specificity** = negatives that stayed quiet / negatives. Per-query
  rates over `agent_repeats`. Wilson CIs on both.
- **Correct-usage** (`grade_tasks.py`, WITH arm): a pointwise LLM judge scores the
  WITH-skill output against the rubric; the score is recomputed from rubric weights ×
  the judge's met-flags (not the judge's gestalt number). Pass = score ≥ gate.
- **With/without** (`grade_tasks.py`): a **swap-order pairwise** judge sees WITH vs
  WITHOUT in both orders; a side wins only if it wins *both* orderings, else tie.
  This cancels the judge's position bias.

`aggregate.py` merges `report/triggers.json` + `report/grading.json` into
`report/scorecard.md`.

## 3. Isolation — the mechanism that makes baselines trustworthy

Each run gets a temp `CLAUDE_CONFIG_DIR` with the real config's top-level files (auth
+ settings) copied in but **no `plugins/` dir** — an authenticated yet skill-free
baseline. Do **not** use `--bare`; it strips the subscription login.

**The contamination trap (read this twice):** a `--plugin-dir` run caches the plugin
*into its `CLAUDE_CONFIG_DIR`*. So if the WITH and WITHOUT arms share one config dir,
the WITHOUT (baseline) arm inherits the cached plugin — the skill leaks into its own
control. Symptom: the skill looks worthless or negative. **Fix: WITH and WITHOUT use
separate config dirs**; the WITHOUT dir is never touched by `--plugin-dir`, so it
stays genuinely skill-free. (This once made a skill look like it lost 78%.)

## 4. Output capture — judge what the skill produced, wherever it landed

A skill's deliverable is often **not** the final assistant message — it may write
entries to a file, or stream them as an intermediate message and end on a terse "done,
N entries." If you judge only `result_text`, that skill scores ~0 on quality while
working perfectly. The engine assembles the judged output from **all assistant text
blocks + Write/Edit/MultiEdit tool contents + on-disk files**, capped. If you adapt
the engine, preserve that — output-token volume is also a robust proxy for "did real
work happen" vs "emitted a one-line confirmation."

## 5. Other gotchas

- **Frontmatter colon-space**: a `": "` (colon-space) inside a single-line
  `description:` plain scalar silently breaks the YAML, so the skill never loads and
  recall collapses to 0.00 (even an exact-match prompt fires 0/3). Use an em-dash, or
  a `>` folded block (colons are safe there). The eval surfaces this instantly.
- **Headless slash commands**: `/foo` typed into `claude -p` is literal text — it
  does not expand — so slash-command triggers read as misses headless even when they
  fire interactively. Treat slash-trigger misses as artifacts; lean on natural-language
  triggers, and mark the skill `command_first`.
- **Empty-cwd trigger artifact**: the trigger arm runs in an isolated, empty temp
  cwd (clean-room isolation). A skill whose trigger inherently references operating
  on *the files in the working directory* — audit/review a repo, sweep a corpus —
  cannot fire there: the model sees no files and asks "which repo?" instead of
  routing, so its recall reads ~0 as an artifact, not a description defect. Measure
  such a skill with the trigger eval pointed at a *populated* cwd (a fixture
  corpus), or confirm activation by a manual run in a real tree. (Observed:
  `corpus-review` scored 0/8 in the empty cwd, yet fired and correctly out-selected
  its `review-panel` / `code-review` siblings 2/3 on the same positives once the cwd
  held a real repo.) A compounding limit for a *heavy* orchestration skill: once it
  does fire in a populated cwd, completing the fan-out needs Task/subagents
  (disallowed in the trigger arm), so the run flails to the `trigger_max_turns` cap
  and is scored as errored rather than as a fire (`corpus-review`'s populated-cwd
  holdout errored 19/21 this way). Such a skill is not cleanly auto-gateable on
  trigger recall here — confirm activation by direct observation, and gate it via
  the grading arm or a raised turn cap.
- **Stale deny-tool names**: `disallowed_tools_trigger` must list only tools the
  *current* CLI knows. A removed or renamed tool (e.g. `MultiEdit`, now folded into
  `Edit`) makes the spawn error with "deny rule matches no known tool" — counted as
  an errored run, silently shrinking the sample. Keep the deny-list current, or have
  the runner drop unknown names before spawning.
- **Cost**: a full run is roughly `(trigger prompts × repeats) + (tasks × repeats ×
  5)` spawns. Budget it and show the user before firing. Use `--concurrency` (each
  spawn is subprocess-bound, so threads parallelize well); transient 429/5xx are
  retried with backoff inside `run_agent`.
- **Variance**: headless activation is non-deterministic. A single-run recall delta
  under ~0.15 is usually noise — check the Wilson CIs, and re-run if a decision hangs
  on it.
