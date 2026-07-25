"""Exact small-n binomial statistics for the experiment-rigor discipline (§1).

Contract: stdlib only, Python 3.13+, deterministic across platforms, no rounding
inside (full precision out — 4-decimal record rounding is a record-level concern).
There is NO CLT/normal (Wald) interval: `confidence_interval` refuses `method`
'normal' and any unknown method with a ValueError. PR2's validator relies on that
refusal, so it is explicit and tested.

Public API
  wilson(k, n, alpha=0.05)                  -> Interval        (closed form)
  clopper_pearson(k, n, alpha=0.05)         -> Interval        (exact, bisection)
  beta_binomial(numerator, denominator,
      prior_alpha=1, prior_beta=1,
      paired=False, cluster_ids=None,
      alpha=0.05)                           -> BetaPosterior   (within-experiment)
  confidence_interval(k, n, method='wilson', alpha=0.05,
      prior_alpha=1, prior_beta=1)          -> Interval        (dispatch + refusal)
  naive_se(successes, n)                     -> float
  clustered_se(outcomes, cluster_ids)        -> float           (cluster-robust)
  expand_cluster_counts(numerators, sizes,
      labels=None)                           -> (outcomes, cluster_ids)  (adapter)
  cluster_deltas(a_successes, a_sizes,
      b_successes, b_sizes)                  -> list[float]     (per-cluster deltas)
  paired_difference(a_successes, a_sizes,
      b_successes, b_sizes)                  -> PairedDiff       (shared-task path)
  paired_interval(estimate, se, n_clusters,
      alpha=0.05)                            -> PairedInterval  (t-interval, v1.1)
  sign_test(deltas)                          -> SignTest        (exact, zeros dropped)
  student_t_quantile(p, df)                  -> float           (stdlib closed form)
  min_detectable_effect(n, baseline=0.5,
      alpha=0.05, power=0.80,
      alternative='two-sided')              -> PowerResult      (before-spend sizing)

Conventions
  numerator/successes k, denominator/n are integer counts (0 <= k <= n, n >= 1).
  alpha is the two-sided miss rate; intervals carry mass 1 - alpha, alpha/2 per tail.
  cluster_ids: one label per trial (len == denominator); tasks reused across arms.
  Equality tolerances the validator recomputes against: ATOL / RTOL below.

The paired scale (schema v1.1). `paired_interval` is the one APPROXIMATION in this
module and is labelled as such: it is a t-interval on the per-cluster deltas, so it
assumes roughly symmetric deltas and a t reference distribution on few clusters. It
is not exact the way wilson / clopper_pearson / beta_binomial are, which is why every
contrast also carries `sign_test` -- the exact, distribution-free robustness bound.
See references/small-n-stats.md.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Hashable, Sequence
from statistics import NormalDist
from typing import NamedTuple

# Validator recomputation tolerances (stats.py output vs 4-dp record values).
ATOL = 1e-9
RTOL = 1e-6
# Internal root-finder tolerance — an order of magnitude tighter than ATOL, so
# every returned bound is stable well inside what the validator compares against.
BISECT_TOL = 1e-14
BISECT_MAX_ITER = 200
# Largest t the quantile inverse will bracket; past it, p is indistinguishable
# from 1 in double precision and the request is refused rather than answered.
_QUANTILE_BRACKET_MAX = 1e12


class Interval(NamedTuple):
    low: float
    high: float


class BetaPosterior(NamedTuple):
    alpha_post: int  # prior_alpha + k
    beta_post: int  # prior_beta + (n - k)
    mean: float
    low: float
    high: float


class PairedDiff(NamedTuple):
    mean_diff: float  # mean over shared tasks of (arm_a rate - arm_b rate)
    se: float  # task-level standard error of that mean difference
    n_clusters: int


class PairedInterval(NamedTuple):
    low: float
    high: float
    quantile: float  # t(1 - alpha/2, df) -- recorded so the interval is hand-checkable
    df: int  # n_clusters - 1


class SignTest(NamedTuple):
    p_value: float  # exact two-sided sign-test p-value
    effective_n: int  # clusters surviving the tie rule (a zero delta is dropped)
    positive: int  # surviving clusters whose delta is > 0


class PowerResult(NamedTuple):
    mde: float  # minimum detectable effect = p1 - baseline
    p1: float  # smallest alternative rate reaching the target power
    critical_count: int  # rejection region is X >= critical_count
    achieved_power: float
    n: int
    alpha: float
    power_target: float
    alternative: str


# --- validation -------------------------------------------------------------


def _validate_kn(k: int, n: int) -> None:
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError(f'n must be a positive integer, got {n!r}')
    if not isinstance(k, int) or isinstance(k, bool) or k < 0 or k > n:
        raise ValueError(f'k must be an integer in [0, {n}], got {k!r}')


def _validate_alpha(alpha: float) -> None:
    if not 0.0 < alpha < 1.0:
        raise ValueError(f'alpha must be in (0, 1), got {alpha!r}')


# --- binomial tails and the integer-parameter Beta CDF ----------------------


def _pmf(i: int, n: int, p: float) -> float:
    return math.comb(n, i) * p**i * (1 - p) ** (n - i)


def _upper_tail(k: int, n: int, p: float) -> float:
    """P(X >= k), X ~ Binomial(n, p). Increasing in p."""
    return math.fsum(_pmf(i, n, p) for i in range(k, n + 1))


def _lower_tail(k: int, n: int, p: float) -> float:
    """P(X <= k), X ~ Binomial(n, p). Decreasing in p."""
    return math.fsum(_pmf(i, n, p) for i in range(0, k + 1))


def _beta_cdf(x: float, a: int, b: int) -> float:
    """Regularized incomplete beta I_x(a, b) for POSITIVE INTEGER a, b.

    For integer parameters the Beta(a, b) CDF equals a binomial tail:
        I_x(a, b) = P(Y >= a),  Y ~ Binomial(a + b - 1, x).
    That is why integer priors make the credible interval exact — the CDF is a
    finite sum of binomial terms (math.comb), no incomplete-beta / scipy needed.
    Increasing in x, so a credible bound is found by bisection on this sum.
    """
    return _upper_tail(a, a + b - 1, x)


def _bisect(
    func: Callable[[float], float],
    target: float,
    increasing: bool,
    lo: float = 0.0,
    hi: float = 1.0,
) -> float:
    """Return x in [lo, hi] with func(x) == target, func monotone. Fixed
    tolerance and iteration cap make the result deterministic across platforms."""
    for _ in range(BISECT_MAX_ITER):
        mid = (lo + hi) / 2
        if (func(mid) < target) == increasing:
            lo = mid
        else:
            hi = mid
        if hi - lo < BISECT_TOL:
            break
    return (lo + hi) / 2


# --- interval methods -------------------------------------------------------


def wilson(k: int, n: int, alpha: float = 0.05) -> Interval:
    """Wilson score interval (closed form). The default method. This is an exact
    score interval, not the refused CLT/Wald interval; the normal quantile enters
    only as the fixed score constant z, not as a large-sample approximation."""
    _validate_kn(k, n)
    _validate_alpha(alpha)
    z = NormalDist().inv_cdf(1 - alpha / 2)
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    # k=0 and k=n have exact bounds 0 and 1; pin them past floating residue.
    low = 0.0 if k == 0 else max(0.0, center - half)
    high = 1.0 if k == n else min(1.0, center + half)
    return Interval(low, high)


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> Interval:
    """Exact Clopper-Pearson interval via binomial tail inversion (bisection).

    Lower bound solves P(X >= k) = alpha/2 (increasing in p); upper bound solves
    P(X <= k) = alpha/2 (decreasing in p). Edges collapse to closed forms: k=0
    pins lo=0, k=n pins hi=1.
    """
    _validate_kn(k, n)
    _validate_alpha(alpha)
    lo = 0.0 if k == 0 else _bisect(lambda p: _upper_tail(k, n, p), alpha / 2, increasing=True)
    hi = 1.0 if k == n else _bisect(lambda p: _lower_tail(k, n, p), alpha / 2, increasing=False)
    return Interval(lo, hi)


def beta_binomial(
    numerator: int,
    denominator: int,
    prior_alpha: int = 1,
    prior_beta: int = 1,
    paired: bool = False,
    cluster_ids: Sequence[Hashable] | None = None,
    alpha: float = 0.05,
) -> BetaPosterior:
    """Within-experiment Beta-Binomial posterior for one arm.

    Posterior is Beta(prior_alpha + k, prior_beta + n - k); the pinned default
    prior is Beta(1, 1) (uniform). The equal-tailed credible interval is exact
    because the integer-parameter Beta CDF is a binomial tail sum (see _beta_cdf).

    `paired` and `cluster_ids` are accepted as structural declarations of the
    shared-task design; they do NOT alter this within-arm posterior (the
    integer-parameter interval is on the aggregate count). Between-arm dependence
    is a standard-error concern handled by clustered_se / paired_difference, not
    the posterior. cluster_ids, when given, must carry one label per trial.
    """
    _validate_kn(numerator, denominator)
    _validate_alpha(alpha)
    if (
        not isinstance(prior_alpha, int)
        or isinstance(prior_alpha, bool)
        or not isinstance(prior_beta, int)
        or isinstance(prior_beta, bool)
        or prior_alpha < 1
        or prior_beta < 1
    ):
        raise ValueError(
            'prior_alpha and prior_beta must be positive integers '
            '(the binomial-sum Beta-CDF identity is exact only for integer parameters)'
        )
    if cluster_ids is not None and len(cluster_ids) != denominator:
        raise ValueError(
            f'cluster_ids length {len(cluster_ids)} != denominator {denominator} '
            '(one cluster label per trial)'
        )
    a = prior_alpha + numerator
    b = prior_beta + (denominator - numerator)
    mean = a / (a + b)
    low = _bisect(lambda x: _beta_cdf(x, a, b), alpha / 2, increasing=True)
    high = _bisect(lambda x: _beta_cdf(x, a, b), 1 - alpha / 2, increasing=True)
    return BetaPosterior(a, b, mean, low, high)


_REFUSED_NORMAL = frozenset({'normal', 'wald', 'clt', 'gaussian', 'z'})


def confidence_interval(
    k: int,
    n: int,
    method: str = 'wilson',
    alpha: float = 0.05,
    prior_alpha: int = 1,
    prior_beta: int = 1,
) -> Interval:
    """Dispatch to an allowed interval method and refuse the rest.

    Allowed (Q2): 'wilson' (default), 'clopper_pearson', 'beta_binomial'. Any
    CLT/normal request or unknown method raises ValueError — the load-bearing
    refusal the small-n discipline is built on.
    """
    if method == 'wilson':
        return wilson(k, n, alpha)
    if method == 'clopper_pearson':
        return clopper_pearson(k, n, alpha)
    if method == 'beta_binomial':
        post = beta_binomial(k, n, prior_alpha, prior_beta, alpha=alpha)
        return Interval(post.low, post.high)
    if method in _REFUSED_NORMAL:
        raise ValueError(
            f'method {method!r} (CLT/normal approximation) is deliberately unavailable: '
            'small-n binomial inference uses wilson, clopper_pearson, or beta_binomial'
        )
    raise ValueError(
        f'unknown CI method {method!r}; allowed: wilson, clopper_pearson, beta_binomial'
    )


# --- standard errors for the shared-task structure --------------------------


def naive_se(successes: int, n: int) -> float:
    """SE of a proportion assuming independent trials: sqrt(p(1-p)/n)."""
    _validate_kn(successes, n)
    p = successes / n
    return math.sqrt(p * (1 - p) / n)


def clustered_se(outcomes: Sequence[int], cluster_ids: Sequence[Hashable]) -> float:
    """Cluster-robust SE of the overall proportion when trials are grouped by task.

    outcomes: 0/1 per trial; cluster_ids: task label per trial (same length).
    Linearized (sandwich) variance for the intercept-only proportion:
        V = G/(G-1) * sum_g (y_g - p_hat*m_g)^2 / (sum_g m_g)^2
    with G clusters, y_g successes and m_g trials in cluster g. Exceeds naive_se
    when tasks differ in difficulty (positive intra-cluster correlation).
    """
    if len(outcomes) != len(cluster_ids):
        raise ValueError(
            f'outcomes ({len(outcomes)}) and cluster_ids ({len(cluster_ids)}) must be equal length'
        )
    if not outcomes:
        raise ValueError('need at least one trial')
    groups: dict[Hashable, list[int]] = {}
    for o, c in zip(outcomes, cluster_ids, strict=True):
        if o not in (0, 1):
            raise ValueError(f'outcomes must be 0/1, got {o!r}')
        g = groups.setdefault(c, [0, 0])
        g[0] += o
        g[1] += 1
    n_g = len(groups)
    if n_g < 2:
        raise ValueError('clustered SE needs at least 2 clusters')
    total = sum(m for _, m in groups.values())
    successes = sum(y for y, _ in groups.values())
    p_hat = successes / total
    ss = math.fsum((y - p_hat * m) ** 2 for y, m in groups.values())
    var = (n_g / (n_g - 1)) * ss / (total * total)
    return math.sqrt(var)


def expand_cluster_counts(
    numerators: Sequence[int],
    sizes: Sequence[int],
    labels: Sequence[Hashable] | None = None,
) -> tuple[list[int], list[Hashable]]:
    """LOSSLESS expansion of a per-cluster counts block into the per-trial form
    `clustered_se` consumes: (outcomes, cluster_ids).

    The record's `clusters` block stores per prompt id, per arm, a numerator and a
    denominator; `clustered_se(outcomes, cluster_ids)` wants one 0/1 outcome and one
    cluster label per trial. This is the adapter between the two, and it is lossless
    by construction: cluster g contributes numerators[g] ones then
    sizes[g] - numerators[g] zeros, all labelled labels[g], so re-collapsing the
    output by label recovers the input counts exactly. Trial ORDER inside a cluster
    is not recoverable from counts and is not information the SE uses -- the
    sandwich variance depends only on the per-cluster (successes, size) pair.

    labels default to the cluster index; pass the prompt ids to keep the record's
    own labels on the trials.
    """
    n_g = len(numerators)
    if len(sizes) != n_g:
        raise ValueError(f'numerators ({n_g}) and sizes ({len(sizes)}) must be equal length')
    if n_g == 0:
        raise ValueError('need at least one cluster')
    ids: Sequence[Hashable] = range(n_g) if labels is None else labels
    if len(ids) != n_g:
        raise ValueError(f'labels ({len(ids)}) must carry one label per cluster ({n_g})')
    outcomes: list[int] = []
    cluster_ids: list[Hashable] = []
    for g in range(n_g):
        k, m = numerators[g], sizes[g]
        if not isinstance(m, int) or isinstance(m, bool) or m < 1:
            raise ValueError(
                f'cluster {ids[g]!r}: denominator must be a positive integer, got {m!r}'
            )
        if not isinstance(k, int) or isinstance(k, bool) or k < 0 or k > m:
            raise ValueError(f'cluster {ids[g]!r}: numerator {k!r} out of [0, {m}]')
        outcomes += [1] * k + [0] * (m - k)
        cluster_ids += [ids[g]] * m
    return outcomes, cluster_ids


def cluster_deltas(
    a_successes: Sequence[int],
    a_sizes: Sequence[int],
    b_successes: Sequence[int],
    b_sizes: Sequence[int],
) -> list[float]:
    """The per-cluster rate differences d_g = a_g/m_g - b_g/n_g, in input order.

    The one place the delta is defined; `paired_difference` averages it and
    `sign_test` counts its signs, so the estimate and its robustness bound cannot
    disagree about what a delta is.
    """
    n_g = len(a_successes)
    if not (len(a_sizes) == len(b_successes) == len(b_sizes) == n_g):
        raise ValueError('per-cluster arrays must share one length (the same tasks in both arms)')
    if any(s <= 0 for s in a_sizes) or any(s <= 0 for s in b_sizes):
        raise ValueError('cluster sizes must be positive')
    return [a_successes[g] / a_sizes[g] - b_successes[g] / b_sizes[g] for g in range(n_g)]


def paired_difference(
    a_successes: Sequence[int],
    a_sizes: Sequence[int],
    b_successes: Sequence[int],
    b_sizes: Sequence[int],
) -> PairedDiff:
    """Paired between-arm difference on shared tasks (the same tasks in each arm).

    Each argument is per-cluster (per-task) and same length G >= 2. The per-task
    rate difference is d_g = a_successes[g]/a_sizes[g] - b_successes[g]/b_sizes[g];
    the returned SE is sd(d_g, ddof=1)/sqrt(G) — the task-level paired SE, which
    removes between-task variance that an unpaired two-sample SE would carry.
    """
    n_g = len(a_successes)
    if n_g < 2:
        raise ValueError('paired difference needs at least 2 shared clusters')
    diffs = cluster_deltas(a_successes, a_sizes, b_successes, b_sizes)
    mean = math.fsum(diffs) / n_g
    var = math.fsum((d - mean) ** 2 for d in diffs) / (n_g - 1)
    return PairedDiff(mean, math.sqrt(var / n_g), n_g)


# --- the paired scale: t-interval and the exact sign test (schema v1.1) ------


def _t_cdf(t: float, df: int) -> float:
    """Student-t CDF P(T <= t) for a POSITIVE INTEGER df, in CLOSED FORM.

    The stdlib carries no Student-t distribution, and scipy/numpy are outside this
    module's contract, so the CDF is summed here from the finite elementary series
    that exists for integer df (Abramowitz & Stegun 26.7.3 for odd df, 26.7.4 for
    even df). With theta = atan(t / sqrt(df)):

        odd  df: 1/2 + (theta + sin(theta) * SUM_j a_j cos^(2j+1)(theta)) / pi,
                 a_0 = 1, a_j = a_(j-1) * 2j/(2j+1),   j = 0 .. (df-3)/2
        even df: 1/2 + sin(theta) * SUM_j b_j cos^(2j)(theta) / 2,
                 b_0 = 1, b_j = b_(j-1) * (2j-1)/(2j), j = 0 .. (df-2)/2

    df = 1 degenerates to the Cauchy CDF 1/2 + atan(t)/pi (the odd sum is empty),
    which is the tightest check on the recursion's base case. No approximation and
    no df ceiling: the series is finite and exact at every integer df, so nothing
    here has to fail loudly outside a tabled range.
    """
    if not isinstance(df, int) or isinstance(df, bool) or df < 1:
        raise ValueError(f'df must be a positive integer, got {df!r}')
    if t < 0:
        return 1.0 - _t_cdf(-t, df)
    theta = math.atan(t / math.sqrt(df))
    sin_t, cos_t = math.sin(theta), math.cos(theta)
    cos2 = cos_t * cos_t
    if df % 2 == 1:
        term, acc = cos_t, 0.0
        for j in range((df - 1) // 2):
            if j > 0:
                term *= (2 * j) / (2 * j + 1) * cos2
            acc += term
        value = 0.5 + (theta + sin_t * acc) / math.pi
    else:
        term, acc = 1.0, 0.0
        for j in range(df // 2):
            if j > 0:
                term *= (2 * j - 1) / (2 * j) * cos2
            acc += term
        value = 0.5 + 0.5 * sin_t * acc
    # A summed series lands a few ulp outside [0, 1] in the far tails at large df
    # (measured -2.2e-16 and 1.0000000000000002). A CDF must not report a
    # probability outside its own range, so the residue is clamped here.
    return min(1.0, max(0.0, value))


def student_t_quantile(p: float, df: int) -> float:
    """The p-quantile of Student's t on `df` degrees of freedom.

    Inverts `_t_cdf` by the module's fixed bisection, so the value is deterministic
    across platforms and needs no pinned table (and therefore no df ceiling to fail
    loudly at). Symmetric: q(p) = -q(1-p), and q(0.5) = 0.

    The bracket search is bounded at 1e12. A p so close to 1 that the quantile sits
    past that bound RAISES rather than returning the bracket end, which would be a
    silently wrong number wearing the shape of an answer.
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f'p must be in (0, 1), got {p!r}')
    if not isinstance(df, int) or isinstance(df, bool) or df < 1:
        raise ValueError(f'df must be a positive integer, got {df!r}')
    if p == 0.5:
        return 0.0
    if p < 0.5:
        return -student_t_quantile(1.0 - p, df)
    hi = 1.0
    while _t_cdf(hi, df) < p and hi < _QUANTILE_BRACKET_MAX:
        hi *= 2.0
    if _t_cdf(hi, df) < p:
        raise ValueError(
            f'cannot bracket the t quantile for p={p!r} at df={df}: it lies beyond '
            f't={_QUANTILE_BRACKET_MAX:g}, so p is indistinguishable from 1 here'
        )
    return _bisect(lambda t: _t_cdf(t, df), p, increasing=True, lo=0.0, hi=hi)


def paired_interval(
    estimate: float,
    se: float,
    n_clusters: int,
    alpha: float = 0.05,
) -> PairedInterval:
    """t-interval on the per-cluster deltas: estimate +/- t(1 - alpha/2, G-1) * se.

    This is the headline precision for a paired contrast, quoted on the clustered
    scale rather than the per-arm one. It is an APPROXIMATION, unlike every other
    interval in this module: it assumes the per-cluster deltas are roughly symmetric
    and takes a t reference distribution on few clusters. `sign_test` is the exact,
    distribution-free bound that travels beside it for exactly that reason.

    The bounds are NOT clamped to [-1, 1]. A rate difference cannot leave that range,
    but clamping would silently redefine the interval the record states it computed;
    a bound outside it is a visible signal that the t approximation is straining.
    """
    if not isinstance(n_clusters, int) or isinstance(n_clusters, bool) or n_clusters < 2:
        raise ValueError(f'paired interval needs at least 2 clusters, got {n_clusters!r}')
    if isinstance(se, bool) or not isinstance(se, (int, float)) or not math.isfinite(se) or se < 0:
        # NaN in particular: it compares false against every bound, so without the
        # isfinite guard it would slide through and return NaN bounds as if computed.
        raise ValueError(f'se must be a finite non-negative number, got {se!r}')
    _validate_alpha(alpha)
    df = n_clusters - 1
    q = student_t_quantile(1 - alpha / 2, df)
    half = q * float(se)
    return PairedInterval(float(estimate) - half, float(estimate) + half, q, df)


def sign_test(deltas: Sequence[float]) -> SignTest:
    """Exact two-sided sign test over per-cluster deltas -- the distribution-free
    robustness bound beside `paired_interval`.

    TIE RULE (fixed by the schema, not by the analyst, and not after seeing the
    data): a ZERO delta is DROPPED, and the surviving effective cluster count is
    reported so the reader sees how much of the design the test actually spoke for.
    Under the null the surviving signs are Binomial(effective_n, 1/2), so
    p = min(1, 2 * min(P(X <= positives), P(X >= positives))) is exact.

    With every delta zero there is nothing left to test and p is 1.0 on 0 effective
    clusters -- an honest "this says nothing", not a pass.
    """
    surviving = [d for d in deltas if d != 0]
    n_eff = len(surviving)
    positive = sum(1 for d in surviving if d > 0)
    if n_eff == 0:
        return SignTest(1.0, 0, 0)
    lower = _lower_tail(positive, n_eff, 0.5)
    upper = _upper_tail(positive, n_eff, 0.5)
    return SignTest(min(1.0, 2.0 * min(lower, upper)), n_eff, positive)


# --- power / precision (Miller: power analysis before spend) ----------------


def min_detectable_effect(
    n: int,
    baseline: float = 0.5,
    alpha: float = 0.05,
    power: float = 0.80,
    alternative: str = 'two-sided',
) -> PowerResult:
    """Minimum detectable increase over `baseline` for n trials per cell, exact
    binomial. The rejection region is X >= c, where c is the smallest count whose
    upper tail under `baseline` is within the level (alpha/2 two-sided, alpha
    one-sided 'greater'); the MDE is the smallest alternative rate p1 whose power
    P(X >= c | n, p1) reaches `power`. No normal approximation is used.
    """
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError(f'n must be a positive integer, got {n!r}')
    if not 0.0 <= baseline < 1.0:
        raise ValueError(f'baseline must be in [0, 1), got {baseline!r}')
    _validate_alpha(alpha)
    if not 0.0 < power < 1.0:
        raise ValueError(f'power must be in (0, 1), got {power!r}')
    if alternative == 'two-sided':
        tail = alpha / 2
    elif alternative == 'greater':
        tail = alpha
    else:
        raise ValueError(f"alternative must be 'two-sided' or 'greater', got {alternative!r}")
    critical = next((c for c in range(n + 1) if _upper_tail(c, n, baseline) <= tail), n + 1)
    if critical > n:
        raise ValueError(f'n={n} too small to form a level-{alpha} rejection region')
    p1 = _bisect(lambda p: _upper_tail(critical, n, p), power, increasing=True, lo=baseline, hi=1.0)
    achieved = _upper_tail(critical, n, p1)
    return PowerResult(p1 - baseline, p1, critical, achieved, n, alpha, power, alternative)
