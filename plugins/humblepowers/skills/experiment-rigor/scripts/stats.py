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
  paired_difference(a_successes, a_sizes,
      b_successes, b_sizes)                  -> PairedDiff       (shared-task path)
  min_detectable_effect(n, baseline=0.5,
      alpha=0.05, power=0.80,
      alternative='two-sided')              -> PowerResult      (before-spend sizing)

Conventions
  numerator/successes k, denominator/n are integer counts (0 <= k <= n, n >= 1).
  alpha is the two-sided miss rate; intervals carry mass 1 - alpha, alpha/2 per tail.
  cluster_ids: one label per trial (len == denominator); tasks reused across arms.
  Equality tolerances the validator recomputes against: ATOL / RTOL below.
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
    if not (len(a_sizes) == len(b_successes) == len(b_sizes) == n_g):
        raise ValueError('per-cluster arrays must share one length (the same tasks in both arms)')
    if n_g < 2:
        raise ValueError('paired difference needs at least 2 shared clusters')
    if any(s <= 0 for s in a_sizes) or any(s <= 0 for s in b_sizes):
        raise ValueError('cluster sizes must be positive')
    diffs = [a_successes[g] / a_sizes[g] - b_successes[g] / b_sizes[g] for g in range(n_g)]
    mean = math.fsum(diffs) / n_g
    var = math.fsum((d - mean) ** 2 for d in diffs) / (n_g - 1)
    return PairedDiff(mean, math.sqrt(var / n_g), n_g)


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
