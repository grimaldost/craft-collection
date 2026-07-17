# evaluate-skill feedback — eval harness under a TLS-proxy remote environment

- **Date:** 2026-07-17
- **Tool/version:** session-workflow 0.16.0 (exercised from the working tree)
- **Context:** ran the trigger/holdout/task harness heavily this session —
  llm-signature trigger eval, a 6-skill dev sweep, 4 sealed holdouts, 4
  correct-usage tasks, and a fresh-holdout A/B (B0 untuned vs B1 tuned) across
  three skills. Environment: managed remote Claude Code, auth via environment
  (no `~/.claude/.credentials.json`), egress through a TLS-re-terminating proxy.
- **Outcome:** the harness produced usable, gate-comparable numbers throughout,
  but two environment mismatches and one missing affordance cost real time and
  variance.

## What worked

- **The N28a error surfacing earned its keep.** With 17–25 of 30–48 runs
  erroring on proxy TLS, the strict-vs-`recall_excl_errors` split and the
  errored-before-activation counts were the difference between a readable result
  and a discarded one. `all_runs_errored` correctly discarded nothing here.
- **Isolated-config A/B arms** stayed clean — the WITH/WITHOUT plugin-dir
  distinction and default-deny tool access held; specificity never spuriously
  collapsed.
- **`holdout_check`'s dev-vs-holdout overfit verdict** framed the reseal work
  correctly (dev recall vs held-out, "within dev CI / DROP").

## Friction

- **[HIGH] The `_TRANSIENT` retry regex misses this environment's dominant error
  class.** `claude_runner.py:26` matches `429|529|overloaded|rate.?limit|5\d\d|
  ECONNRESET|ETIMEDOUT|connection reset`, but the errors here were
  `Self-signed certificate detected` (proxy TLS), `Prompt is too long`, and
  `[TIMEOUT after 300s]` — none retried. Result: 40–55% of runs errored on
  several batches, inflating CI width and depressing pooled recall (e.g.
  python-engineering dev 0.71 pooled vs 0.85 excl-err from the same run).
  Minutes lost re-reasoning around noise across ~10 batches.
- **[LOW] `smoke.py` check 0 false-fails under env-based auth.** "isolated
  config is credentials-only" prints `copied=[]` and FAILS when there is no
  `~/.claude/.credentials.json` because auth is injected by the environment.
  Checks 1–4 (authed spawn, plugin load, activation, judge, no-write) all pass,
  so the config is correctly isolated and authed — but the red FAIL reads as a
  go/no-go abort. Cost me a diagnostic detour before concluding it was benign.

## Misses

- **[MED] No custom-dataset path on `run_triggers` / `holdout_check`
  (phase: harness API).** To A/B a *fresh* holdout against the untuned vs tuned
  description on the current tree, I had to write a bespoke `ab_holdout.py`
  around `run_skill` — both CLIs hard-resolve `evals/trigger/<skill>.json` /
  `evals/trigger/holdout/<skill>.json`. A reseal A/B (the exact workflow
  skill-authoring's holdout rule prescribes) is therefore not first-class.
- **[LOW] Reseal A/B pollutes `report/*.json` if done via the built-in CLIs
  (phase: harness API).** `run_triggers` writes `report/triggers.json` for the
  skill; running it twice (untuned then tuned) clobbers the first. My bespoke
  runner sidestepped this by not writing a report at all — but that means the
  A/B numbers live only in logs, not in the report the aggregator reads.

## Vacuous gates

- None observed. The gates that ran (`run_tests`, `validate_plugins`, word
  budget, register lint, AGENTS.md freshness) each caught real things this
  session (the 23→24 skill-count assertion; a three-conjunction all-caps run in
  a doc).

## Proposed promotions / changes

1. **[HIGH]** proxy/TLS + prompt-length + timeout errors are transient-class in
   a managed remote env but unmatched by the retry regex → widen
   `_TRANSIENT` (or add an env-configurable extra pattern) to include
   `self-signed certificate|certificate verify|prompt is too long|TIMEOUT after`,
   with a capped backoff, so the dominant infra error class retries instead of
   scoring as no-activation. Home: `evals/harness/claude_runner.py`.
2. **[MED]** reseal A/Bs are a first-class need (skill-authoring mandates them)
   but the harness can only run the on-disk dataset → add `--dataset PATH` to
   `run_triggers.py` and `holdout_check.py` (and a `--no-report` flag), so an
   untuned-vs-tuned run on an arbitrary holdout needs no bespoke script. Home:
   `evals/harness/run_triggers.py`, `holdout_check.py`.
3. **[LOW]** `smoke.py` check 0 asserts credential-file copy, but env-based auth
   is a valid isolated-and-authed state → treat "no credentials file + checks
   1–4 green" as PASS-with-note, not FAIL. Home: `evals/harness/smoke.py`.

## Cost (eval runs this session)

Approx list-equivalent, subscription auth: llm-signature triggers ×2 ≈ $2.9;
Phase-B B0 (3 holdouts) ≈ $3.4; B1+dev (3 holdouts + 3 dev) ≈ $8.5. Proxy
errors mean 40–55% of spawns produced no measurement — the widened retry
(proposal #1) would recover most of that spend.
