# Design: consolidate-knowledge effectiveness eval (4-arm, multi-session, seeded)

**Date:** 2026-06-06
**Author:** Grimaldo Stanzani
**Status:** Approved design — pending spec review, then pilot (p1) build

---

## 1. Goal

Measure, with **fresh headless agents across simulated session boundaries**, whether
`consolidate-knowledge` produces cross-session memory that makes a *later, real* task
go better than three alternatives:

- **cold** — no memory carried at all (the floor);
- **remember** — the published `remember` handoff note (recency-tiered session state);
- **journal-only** — the raw `journaling-sessions` entries carried forward *without*
  the consolidation pass.

The headline number is **`consolidate − journal-only`**: the marginal value of the
consolidation pass *itself*, holding the journaling capture constant. When that gap is
zero or negative, the linked transcripts are the primary signal for *improving the
skill* (did it drop a load-bearing specific, promote a platitude, botch supersession?).

## 2. What we are actually testing — and the confound we remove

- `consolidate-knowledge` is a **downstream distillation pass over journaling-sessions
  entries**, not a capture tool. Its arm is therefore the pipeline *journal-each-session
  → consolidate-at-checkpoint*, not the skill in isolation.
- A "session" is a **fresh `claude -p` agent** with no conversation carryover. Memory
  survives **only as files on disk** in that arm's folder. This is what makes the test
  a real cross-session test rather than one long context.
- We **seed identical session histories** for every arm. Each arm still genuinely runs
  *its own* capture/consolidate step on that shared input, but the raw events are held
  constant — so a difference in the probe outcome is attributable to the **memory
  mechanism**, not to one arm happening to do better project work. Removing that
  confound is the whole reason for seeding (vs. letting arms do live, diverging work).

## 3. Confirmed decisions

| # | Decision |
|---|---|
| Metric | **Primary = downstream probe-task quality** (blind swap-order pairwise). **Diagnostics** = memory-artifact quality, objective fact-recall, and context-size-to-payoff. |
| History | **Seeded, identical** per-session fixtures across all arms; only the memory tool differs. |
| Arms | **4** — `cold`, `remember`, `journal-only`, `consolidate`. (`free-notes` deferred to round 2.) |
| Remember | The **published `remember:remember` v0.7.3** — minimal <20-line State/Next/Context handoff, single file overwritten each session. The reproducible, installable comparator. |
| Rollout | **Spec → build harness → `p1` pilot (~$5, go/no-go) → full grid.** |
| Reuse | The existing `evals/harness/` engine: `claude_runner` (stream-json spawner), `judge` (pointwise rubric + swap-order pairwise), `stats` (Wilson CI), `token_probe`, and the **per-arm config-dir isolation**. |

## 4. Operating principles

- **Fresh agent per session; file-only carryover.** No `--continue`, no shared session.
  The only state crossing a session boundary is the arm's on-disk memory artifact(s).
- **Per-arm separate `CLAUDE_CONFIG_DIR`** — the harness's nastiest trap. A `--plugin-dir`
  run caches the plugin into its config dir; share one dir and the skill leaks into the
  baseline (once made a skill look like it *lost* 78%). `cold` loads no plugin;
  `journal-only`/`consolidate` load `session-workflow`; `remember` loads `remember`.
- **Identical seeded input across arms** — byte-for-byte the same `session-NN.md`.
- **Each arm's probe reads only its own natural artifact** — distilled-but-small
  (consolidate) vs. raw-but-voluminous (journal-only) is the *real* tradeoff, so we do
  **not** cap tokens. Context size becomes a reported secondary metric.
- **Rates with Wilson 95% CIs**, never a bare pass/fail — headless activation and an
  un-temp-0 judge are both stochastic. Pairwise judging runs **both orderings** and
  counts a win only if both agree.
- **Improvement is reading-driven** — the scorecard links every probe run where
  `consolidate` lost or tied, so tuning the skill starts from transcripts, not vibes.

## 5. Arms and per-arm protocol (the heart)

For every project, all four arms ingest the same `history/session-NN.md` sequence. Per
session, a fresh agent runs that arm's **capture step**, writing into `arms/<arm>/mem/`.

| Arm | Plugin loaded | Per-session capture step | Checkpoint | Probe agent inherits |
|---|---|---|---|---|
| `cold` | none | *(none — input discarded)* | — | nothing |
| `remember` | `remember` | run `remember` → rewrite `mem/remember.md` (reads prior first) | — | `mem/remember.md` |
| `journal-only` | `session-workflow` | run `journaling-sessions` → append `mem/entries/session-NN.md` | — | all `mem/entries/*.md` |
| `consolidate` | `session-workflow` | run `journaling-sessions` → append `mem/entries/session-NN.md` | after last session, run `consolidate-knowledge` over all entries → `mem/guidance.md` | **only** `mem/guidance.md` (raw entries withheld) |

**Phases per (arm × project):**

1. **Build** — for `session-01..NN`: spawn fresh agent → capture step → write artifact.
2. **Consolidate checkpoint** (`consolidate` arm only) — one fresh agent runs
   `consolidate-knowledge` across the accumulated entries.
3. **Probe** — one fresh agent gets *only* the arm's inherited artifact + `probe/task.md`,
   and performs the task. Capture assistant text + Write/Edit + on-disk output.
4. **Recall probe** (diagnostic) — same memory loadout, asked `probe/facts.json` Q&A.

**Capture is explicitly invoked, not auto-triggered.** Whether these skills *fire on
their own* is `evaluate-skill`'s axis; here we drive the capture/consolidate step
directly (instruct the agent to run it) so headless auto-activation noise cannot
confound the consolidation-*quality* signal we are after.

## 6. Project slate — each stresses a different consolidate mechanism

Same shape every project: a seeded **4–6 session history** → one **live probe task** →
a fact-recall set. Each is engineered so a *specific* consolidate-knowledge value-prop
decides the outcome. All content is **fictional/generic** (no proprietary material).

### p1 — supersession *(pilot)*

A decision is made early and **reversed later on new evidence**; the probe requires
acting on the *current* decision.

- *History:* S1 chooses approach **X** for a business-day/holiday calculation, with
  rationale. S2–S3 build around X. S4 discovers X is wrong for a region's calendar and
  **switches to Y; X is now forbidden.**
- *Probe:* "Add a feature that schedules payments avoiding non-business days." Correct
  output uses **Y** and avoids X.
- *Hypotheses:* `consolidate` should record Y *superseding* X → correct. `remember`'s
  latest handoff may also carry Y. `journal-only` likely surfaces **both** X and Y and
  equivocates. `cold` fails.

### p2 — reinforcement / clustering

The **same class of gotcha recurs** across sessions in different guises; the probe is a
*new* instance.

- *History:* three sessions each hit a different symptom of one root cause (e.g.
  timezone/DST off-by-one in three unrelated features).
- *Probe:* a fourth feature that would trip the same root cause.
- *Hypotheses:* `consolidate` should have **promoted the generalization** (the rule) →
  pre-empts it. `journal-only` has three scattered specifics and may not connect them.
  `remember` keeps only recent state. `cold` fails.

### p3 — signal-in-noise / promotion gate

Sessions **thick with generic best-practice chatter**, hiding 2–3 specific,
non-reconstructable constraints; the probe depends on a buried constraint.

- *History:* lots of "write tests, validate inputs" filler + a load-bearing specific
  (e.g. "the upstream feed publishes at 02:00 UTC and is empty before then").
- *Probe:* a task that is only correct if the specific constraint is honored.
- *Hypotheses:* `consolidate`'s **gate keeps the specific, kills the platitude** →
  surfaces it. `journal-only` buries it in noise. `remember`'s terse note may or may not
  have kept it. `cold` fails.

### p4 — cross-session synthesis *(optional, round 2)*

Two facts from **different sessions** that only bite when combined; tests clustering +
synthesis across sessions.

## 7. Architecture

```
 seeded history/                per-arm, fresh agent per session            per-arm artifact
 session-01..NN.md  ──┐
                      ├─► orchestrate_sessions.py ─► claude_runner (build) ─► arms/<arm>/mem/...
                      │        │   (per-arm CLAUDE_CONFIG_DIR + plugin)
                      │        └─► consolidate checkpoint (consolidate arm) ─► mem/guidance.md
                      │
 probe/task.md ───────┴─► claude_runner (probe, memory-only) ─► arms/<arm>/probe_out/
                                                   │
                          judge.py (claude -p, no plugin):
                          · pairwise swap-order: consolidate vs {cold,remember,journal-only}   (PRIMARY)
                          · pointwise rubric on each arm's probe output                        (diagnostic)
                          · fact-recall scoring vs facts.json                                  (diagnostic)
                          · pointwise artifact-quality on each arm's mem artifact              (diagnostic)
                                                   │
                          aggregate.py ─► report/scorecard.md  (per-project + pooled, Wilson CIs,
                                          context-size + cost/turns, "why consolidate lost" transcript links)
```

## 8. Repository layout

```
evals/                               # existing canonical harness (repo root) — REUSED IN PLACE
  harness/
    claude_runner.py  judge.py  stats.py  token_probe.py   # reused (imported, not copied)
    orchestrate_sessions.py          # NEW: build→checkpoint→probe→recall driver, per-arm isolation
    score_consolidate.py             # NEW: pairwise(consolidate vs each) + pointwise + recall + artifact
    aggregate_consolidate.py         # NEW: per-project + pooled scorecard with CIs + transcript links
  consolidate/                       # NEW: this eval's config + datasets + generated arms
    config.json                      # arms→{plugin,config policy}, models, repeats, budgets, gates
    projects/
      p1-supersession/
        history/  session-01.md … session-04.md     # identical seeded input for every arm
        probe/
          task.md                # the live probe prompt
          rubric.json            # weighted criteria for the probe OUTPUT (pointwise)
          facts.json             # objective recall Q&A (the superseded decision, the buried constraint)
          artifact-rubric.json   # criteria for judging the memory ARTIFACT itself
        arms/{cold,remember,journal-only,consolidate}/   # mem/ + probe_out/ (generated, gitignored)
      p2-reinforcement/  …   p3-signal-in-noise/  …
    report/   scorecard.md  +  build.json / probe.json / grading.json
```

The new orchestrator/scorer/aggregator sit **beside** the existing engine in
`evals/harness/` and import `claude_runner` / `judge` / `stats` / `token_probe`
directly (no copy). The generated `arms/**` trees are build output — add them to
`evals/.gitignore`; only `config.json`, `history/`, and `probe/` are checked in.

## 9. Component specs

### 9.1 `orchestrate_sessions.py` (NEW)
- `run_arm(project, arm, *, repeats)` → for each session fixture, build a fresh
  `claude_runner.run_agent` call with the arm's `--plugin-dir` (or none) and a
  **dedicated `CLAUDE_CONFIG_DIR`**; the prompt embeds the session fixture + a terse
  "run your capture step into this path" instruction; assert the artifact changed.
- `checkpoint(project)` for the `consolidate` arm only.
- `probe(project, arm)` — memory-only agent on `task.md`; `recall(project, arm)` on
  `facts.json`. Writes `report/build.json` + `report/probe.json`.
- `--dry-run` prints the full spawn plan + estimate; `--only p1` / `--arm` / `--limit`.

### 9.2 Reused in place from `evals/harness/`
- `claude_runner.py` — stream-json spawner, output capture (text + Write/Edit + on-disk),
  retry/backoff. **Output capture is load-bearing** here: capture steps write to files.
- `judge.py` — `judge_pairwise` (swap-order) for the primary; `judge_pointwise` for the
  rubric and artifact diagnostics. `stats.py` — Wilson CI. `token_probe.py` — the
  context-size metric on each arm's inherited artifact.

### 9.3 `score_consolidate.py` (NEW)
- **Pairwise (primary):** for each comparator C in {cold, remember, journal-only},
  `judge_pairwise(task, consolidate_out, C_out, criterion="better completes the task")`
  in both orders; win only if both agree.
- **Pointwise:** each arm's probe output vs `rubric.json`.
- **Recall:** score the recall answers vs `facts.json` (judge-checked; exact-ish answers
  may also string-match).
- **Artifact quality:** `judge_pointwise(artifact, artifact-rubric)` — captures durable
  specifics, kills platitudes, marks supersession, keeps the "scar".

### 9.4 `aggregate_consolidate.py` (NEW)
- Per-project and pooled: pairwise win-rates ±CI, pointwise/recall/artifact per arm,
  **context tokens** of each arm's inherited artifact, cost/turns. Emits the
  **"why consolidate lost / tied"** list with paths to the offending probe transcripts.

## 10. Dataset authoring bar (per project)

- **history/** — each `session-NN.md` reads like a real session's substance (decisions +
  rationale, a bug + fix, the reversal/recurrence/buried-specific the project tests),
  not a bullet outline. ~150–400 words each.
- **probe/task.md** — a concrete task whose *correct* completion provably depends on a
  fact established in the history; a cold agent should plausibly get it wrong.
- **rubric.json / artifact-rubric.json** — observable criteria a judge can check, load-
  bearing ones weighted higher (mirrors the existing harness rubric format).
- **facts.json** — `[{q, expected, note}]`; the questions target exactly the
  supersession / generalization / buried-specific the project is built around.

## 11. Metrics & scorecard

- **Primary:** `consolidate` pairwise win-rate vs each comparator, **per project** (which
  *mechanism* it wins on) and **pooled**, with Wilson CIs. The marquee cell is
  `consolidate vs journal-only`.
- **Diagnostics:** pointwise probe-rubric score per arm; fact-recall accuracy per arm;
  artifact-quality per arm; **context-size-to-payoff** (consolidate should win quality
  *per token*); cost/turns.
- **Improvement signal:** linked transcripts for every lost/tied probe.

## 12. Cost & guards

- **Pilot (`p1`, 4 arms, 1 repeat):** build `4×(≤4 sessions)` + 1 checkpoint + 4 probe +
  4 recall ≈ **~25 agent spawns** + judging (3 pairwise × 2 orders + 4 pointwise + 4
  recall + 4 artifact ≈ ~18) → **~45 spawns, ≈ $4–6** on Sonnet.
- **Full (3 projects, 4 arms, 3 repeats):** ≈ `3 × 3 × (25 + 18)` ≈ **~390 spawns,
  ≈ $30–70**.
- Every spawn carries `--max-budget-usd` + `--max-turns`; orchestrator prints an upfront
  estimate, supports `--dry-run`, `--limit`, `--only`, and `--concurrency`. Both pilot
  and full run are **gated behind an explicit go-ahead**.

## 13. Non-goals (YAGNI for round 1)

- No `free-notes` arm, no `p4`, no **live** (diverging) history — all round 2.
- No *incremental* consolidation — one end-of-series checkpoint (matches the skill's
  "run periodically over an accumulated corpus" design).
- No CI wiring, no judge κ gold-set validation, single model tier (Sonnet) to start.
- No editing `consolidate-knowledge` inside this harness — findings feed a *separate*
  skill-tuning pass.

## 14. Key assumptions to validate in the pilot

The design hinges on these; the `p1` pilot must confirm them or the design adapts:

1. **File-only carryover works headless** — a fresh probe agent, given only a memory
   file path, actually reads and uses it (no session continuity needed).
2. **The seeded history creates a real signal** — the supersession in `p1` is
   recoverable from the artifacts; arms genuinely diverge on the probe.
3. **`consolidate` yields a smaller-but-sufficient artifact** — guidance.md is materially
   shorter than the raw entries yet retains the load-bearing specific.
4. **The probe discriminates** — `cold` clearly underperforms and the ceiling is not so
   low/high that every arm ties. If everyone ties, the probe is too easy/hard — retune.
5. **Pairwise judge agreement is sane** on probe outputs (both-orderings concur often
   enough to trust the win-rate).

## 15. Build sequence

1. `orchestrate_sessions.py` skeleton + `--dry-run` plan (no spawns); import the
   in-place `evals/harness/` modules (`claude_runner`, `judge`, `stats`, `token_probe`).
2. Author `p1` datasets (history ×4, probe task, rubric, facts, artifact-rubric).
3. Wire per-arm config dirs + plugin selection; **smoke one arm end-to-end** (build →
   probe) to validate assumptions 1 & 3.
4. Run the `p1` pilot — 4 arms × 1 repeat; **eyeball the artifacts and probe outputs**
   before trusting any judge number (assumptions 2 & 4).
5. `score_consolidate.py` + `aggregate_consolidate.py` → first `p1` scorecard
   (assumption 5).
6. **Go/no-go.** If the signal is real: author `p2`/`p3`, raise repeats to 3, run the
   full grid, then fold findings into a `consolidate-knowledge` tuning pass.
