# Small-n statistics for evals

LLM-eval cells are small — tens of trials per condition, not thousands. At that
size the large-sample shortcuts fail quietly: a normal (Wald) interval gives
bounds outside [0, 1] and understates uncertainty, and a single draw per cell
reports noise as signal. `stats.py` exposes only exact small-n methods; the
validator (`ER-STATS`) recomputes every stated interval against them and refuses
the approximations. This note records the rules those scripts enforce.

## Five rules, adapted from Miller

Adapted for LLM evals from Evan Miller's guidance on adding error bars to evals.

1. **A confidence interval, always.** A bare point estimate hides the sample
   size. Every rate reported at measurement or decision tier carries a structured
   interval (`ci.method`, `ci.low`, `ci.high`); the validator recomputes it and
   fails when the stated bounds disagree.
2. **Cluster the standard error on the randomization unit.** When the same tasks
   appear in both arms, or many questions sit inside one document, the effective
   sample size is the number of clusters — tasks — not the number of questions.
   `clustered_se(outcomes, cluster_ids)` labels each trial by its task and returns
   the cluster-robust SE, which exceeds the naive SE whenever tasks differ in
   difficulty. Declaring `paired: false` on a shared-task design without a
   `clustered_se` or an explicit `unclustered_reason` fails the gate.
3. **Analyze paired differences when arms share tasks.** Compare the two arms
   within each shared task and average the per-task differences
   (`paired_difference`); this removes between-task variance that an unpaired
   two-sample comparison leaves in, tightening the interval on the same data.
   The record states this as a `contrasts[]` entry over a `clusters` block, and
   the validator recomputes it — see "The paired scale" below.
4. **Buy repeats before precision — epochs and resampling.** Nondeterminism is
   measured, not assumed away: draw each condition several times (epochs) so
   sampling variance enters the interval. Resampling over tasks and draws
   separates model variance from question variance.
5. **Power analysis before spend.** Size n so the smallest effect worth acting on
   is detectable. `min_detectable_effect(n, baseline, power=0.80)` returns the
   smallest true rate an n-per-cell design can distinguish from the baseline at
   the target power; a null result from an underpowered run is uninformative, not
   evidence of no effect. Run this before spending, not after a flat result.

## The exact-methods rule — no CLT below 30

Below a cell denominator of 30, the CLT / normal (Wald) approximation is refused.
`confidence_interval(k, n, method=...)` raises a `ValueError` on `'normal'` (and
on `wald`, `clt`, `gaussian`, `z`), so a small-n record cannot request one. The
allowed methods are exact at any n:

- **`wilson`** (default) — the closed-form score interval; well-behaved near 0 and
  1 and the sensible default for a proportion. The normal quantile enters only as
  the fixed score constant, not as a large-sample approximation of the tails.
- **`clopper_pearson`** — the exact interval by binomial-tail inversion;
  conservative, and the choice when strict coverage matters.
- **`beta_binomial`** — the Bayesian credible interval from a Beta posterior (see
  below); exact for integer priors.

The floor of 30 lives in `schema.json` as `small_n_floor`; the validator names
the small-n rule when a refused method is requested at a denominator under it.

## The paired scale — and the one approximation in the module

A per-arm interval prices independent trials. When the same prompts are scored in
every arm the randomization unit is the prompt cluster, not the trial, so
recomputing each arm from raw counts forces an independent-trials interval onto a
clustered design — a Wilson band that is systematically too narrow. Schema v1.1
records the clustered scale directly: `results.<outcome>.clusters` holds a
numerator and a denominator per prompt id per arm, and
`results.<outcome>.contrasts[]` states the comparison over it — the ordered arm
pair, the estimator, the estimate, its SE, the cluster count, an interval, and a
sign test. `ER-STATS` recomputes every stated contrast from the cluster block.

**The per-arm Wilson interval stays, demoted to descriptive.** For an outcome
scored over the full cell set it still recomputes and still fails when wrong; it
is simply not the headline. Read it as an *upper bound on precision* — the
tightest band the data could support if every trial were independent, which they
are not — and quote the contrast's interval as the result.

**`paired_interval` is an approximation, and the only one here.** It is the
t-interval on the per-cluster deltas, `estimate ± t(0.975, clusters − 1) × se`,
and the interval records the `t_quantile` it used so the arithmetic is checkable
by hand. Its assumptions are worth naming because at these sizes they are not
free: the per-cluster deltas are taken to be roughly symmetric, and a t reference
distribution is taken to hold on very few clusters. Neither assumption is needed
by `clopper_pearson` (exact-conservative, by binomial-tail inversion) or by the
Beta-Binomial credible interval (exact for integer priors). With two repeats per
prompt a per-cluster delta lives in {−1, −0.5, 0, 0.5, 1}, which is about as far
from a smooth symmetric distribution as a quantity gets.

**So an exact sign test is required beside every contrast.** It is
distribution-free — it assumes only that clusters are independent and that, under
the null, each is as likely to move one way as the other — and it is therefore the
robustness bound on the t-interval's optimism. Its tie rule is fixed by the schema
rather than chosen after seeing the deltas, which is the whole point of naming both
statistics up front: **a zero per-cluster delta is dropped**, and the surviving
effective cluster count is reported beside the p-value. Ties are expected to be the
modal cluster — most prompts will not move at all — so the effective n is
load-bearing information, not a footnote: a p-value on 3 surviving clusters out of
12 is a different claim from the same p-value on 12 of 12.

The record **states** the triple — `sign_test.p_value`, `sign_test.effective_n`,
`sign_test.positive` — and `ER-STATS` recomputes all three from the cluster block.
Stated rather than merely printed, because a number that lives only in a report's
prose is a number no gate reads: the drift and parity gates re-parse the embedded
typed block, so a p-value outside that block can be edited to anything and still
pass. `validate.py` also echoes the recomputed triple as an `INFO` line, which
confirms the arithmetic and hands a record still being authored the values it has
to write down — but the check is the recomputation, not the echo. It stays
hand-checkable either way: the effective n and the count of positive deltas both
follow from the recorded per-cluster counts.

An outcome scored over only *some* of the declared cells carries **no `arms` block
at all** — just its clusters and its contrasts. The presence of `arms` is how the
validator tells the two scopes apart: with it, the outcome is held to the
full-cell-set reconciliation; without it, no full-cell-set rule applies and no
per-arm rate is stated to be believed.

## The Beta(1, 1) prior and its sensitivity

The within-experiment posterior for one arm is `Beta(prior_alpha + k, prior_beta
+ n - k)`. The pinned prior is `Beta(1, 1)` — uniform on [0, 1], adding one
notional success and one notional failure. Integer priors keep the credible
interval exact: the integer-parameter Beta CDF is a finite binomial-tail sum
(`math.comb`), so no incomplete-beta routine is needed.

Sensitivity: at small n the prior visibly moves the posterior. Report the
interval under `Beta(1, 1)` and, when the result is close to a decision boundary,
note how it shifts under a Jeffreys `Beta(0.5, 0.5)` or an informative prior — the
prior is a declared choice, not a silent default. On 0 of 10 the uniform prior
gives a posterior mean of 1/12, not 0; that pull toward the center is the prior
doing its job and is worth naming when it changes the reading.

## The within-experiment-only boundary

The Beta-Binomial posterior pools counts **within one experiment** — one
randomization, one task set, one model, one window. It never pools counts across
experiments. Different tasks, models, and dates are not exchangeable trials, so
summing numerators and denominators across runs would manufacture false
precision.

Belief moves across experiments through a qualitative GRADE link instead: the
downstream record carries `updates.prior.source_id` to the upstream record, a
`certainty` from the four-level enum (`high`, `moderate`, `low`, `very_low`), and
`downgrade_reasons[]` naming what cost certainty (nondeterminism, indirectness,
imprecision, inconsistency). `render.py --chain` walks these links into a
root-first lineage view. The chain is a reasoned certainty update, never an
arithmetic pool.
