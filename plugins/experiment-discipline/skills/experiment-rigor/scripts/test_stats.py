"""Tests for stats.py — the experiment-rigor statistics core (§1).

Runnable with pytest or `python test_stats.py` (the repo's run_tests.py runs the
latter from this dir and requires an `ok:` sentinel on success). Stdlib only.

Reference values are pinned three ways, each an independent second derivation so
a transcription slip in stats.py cannot be masked by reusing its own code path:
  1. closed-form edge cases (Clopper-Pearson 0/n and n/n; Beta(1,.) posteriors)
     computed here from first principles and pinned tight (BISECT-tolerance);
  2. self-consistency against the *defining* equation (at the returned Clopper-
     Pearson root the binomial tail equals alpha/2; at the returned Beta credible
     bound the integer-parameter binomial identity equals the target mass) — this
     validates the interior, not just the edges;
  3. one published literature anchor per method at a human-checkable tolerance.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import stats

# ---------------------------------------------------------------------------
# Independent second-derivation helpers (NOT importing stats' internals).
# ---------------------------------------------------------------------------


def _pmf(i: int, n: int, p: float) -> float:
    return math.comb(n, i) * p**i * (1 - p) ** (n - i)


def _upper_tail(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    return sum(_pmf(i, n, p) for i in range(k, n + 1))


def _lower_tail(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    return sum(_pmf(i, n, p) for i in range(0, k + 1))


def _beta_cdf_int(x: float, a: int, b: int) -> float:
    """Regularized incomplete beta I_x(a,b) for integer a,b, via the binomial
    identity I_x(a,b) = P(Y >= a), Y ~ Binomial(a+b-1, x). A separate derivation
    from stats._beta_cdf used only to check the credible-interval mass."""
    return _upper_tail(a, a + b - 1, x)


def _wilson_ref(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """The Wilson score interval closed form, written a second time here."""
    z = NormalDist().inv_cdf(1 - alpha / 2)
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (center - half, center + half)


def _approx(a: float, b: float, atol: float = stats.ATOL, rtol: float = stats.RTOL) -> bool:
    return math.isclose(a, b, abs_tol=atol, rel_tol=rtol)


# ---------------------------------------------------------------------------
# Wilson
# ---------------------------------------------------------------------------


def test_wilson_matches_independent_closed_form():
    for k, n in [(0, 10), (1, 10), (5, 10), (8, 10), (10, 10), (0, 1), (1, 1), (2, 20)]:
        lo, hi = stats.wilson(k, n)
        rlo, rhi = _wilson_ref(k, n)
        # Wilson is clamped to [0, 1]; clamp the reference the same way.
        assert _approx(lo, max(0.0, rlo)), f'wilson lo {k}/{n}: {lo} vs {rlo}'
        assert _approx(hi, min(1.0, rhi)), f'wilson hi {k}/{n}: {hi} vs {rhi}'


def test_wilson_literature_anchor():
    # Published Wilson 95% interval for 8/10 ~ (0.4901, 0.9433). Cf. Brown, Cai &
    # DasGupta (2001) "Interval Estimation for a Binomial Proportion"; matches R
    # binom::binom.confint(8, 10, methods="wilson"). Human-checkable anchor.
    lo, hi = stats.wilson(8, 10)
    assert math.isclose(lo, 0.4901, abs_tol=1e-3), lo
    assert math.isclose(hi, 0.9433, abs_tol=1e-3), hi


def test_wilson_symmetry():
    # wilson(n-k, n) is the mirror of wilson(k, n): lo(n-k) == 1 - hi(k).
    for k, n in [(3, 10), (8, 20), (1, 5)]:
        lo_k, hi_k = stats.wilson(k, n)
        lo_m, hi_m = stats.wilson(n - k, n)
        assert _approx(lo_m, 1 - hi_k), f'{k}/{n} symmetry lo'
        assert _approx(hi_m, 1 - lo_k), f'{k}/{n} symmetry hi'


def test_wilson_k0_kn_bounds():
    lo0, _ = stats.wilson(0, 10)
    _, hi_n = stats.wilson(10, 10)
    assert lo0 == 0.0, lo0  # exact zero for k=0
    assert hi_n == 1.0, hi_n  # exact one for k=n


# ---------------------------------------------------------------------------
# Clopper-Pearson
# ---------------------------------------------------------------------------


def test_clopper_pearson_edge_closed_forms():
    # Exact known reference intervals. For k=0 the CP upper solves (1-p)^n =
    # alpha/2 -> hi = 1 - (alpha/2)^(1/n); for k=n the lower solves p^n = alpha/2
    # -> lo = (alpha/2)^(1/n). Clopper & Pearson (1934).
    n, alpha = 10, 0.05
    lo0, hi0 = stats.clopper_pearson(0, n, alpha)
    assert lo0 == 0.0, lo0
    assert _approx(hi0, 1 - (alpha / 2) ** (1 / n)), hi0  # ~0.30850
    lon, hin = stats.clopper_pearson(n, n, alpha)
    assert hin == 1.0, hin
    assert _approx(lon, (alpha / 2) ** (1 / n)), lon  # ~0.69150


def test_clopper_pearson_defining_equation():
    # The interior is validated against the DEFINING tail equations (the true
    # reference): at the lower bound P(X>=k)=alpha/2; at the upper P(X<=k)=alpha/2.
    for k, n in [(3, 10), (7, 20), (1, 5), (12, 48), (36, 48)]:
        lo, hi = stats.clopper_pearson(k, n)
        assert _approx(_upper_tail(k, n, lo), 0.025), f'CP lo defn {k}/{n}: {_upper_tail(k, n, lo)}'
        assert _approx(_lower_tail(k, n, hi), 0.025), f'CP hi defn {k}/{n}: {_lower_tail(k, n, hi)}'


def test_clopper_pearson_wider_than_wilson():
    # CP is the conservative exact interval; it contains the Wilson interval.
    for k, n in [(3, 10), (12, 48), (2, 20)]:
        cp_lo, cp_hi = stats.clopper_pearson(k, n)
        w_lo, w_hi = stats.wilson(k, n)
        assert cp_lo <= w_lo + stats.ATOL, f'{k}/{n} CP lo not <= Wilson lo'
        assert cp_hi >= w_hi - stats.ATOL, f'{k}/{n} CP hi not >= Wilson hi'


def test_clopper_pearson_symmetry_and_determinism():
    for k, n in [(3, 10), (12, 48)]:
        lo_k, hi_k = stats.clopper_pearson(k, n)
        lo_m, hi_m = stats.clopper_pearson(n - k, n)
        assert _approx(lo_m, 1 - hi_k)
        assert _approx(hi_m, 1 - lo_k)
    # Deterministic: identical bytes across two calls (fixed bisection).
    assert stats.clopper_pearson(3, 10) == stats.clopper_pearson(3, 10)


# ---------------------------------------------------------------------------
# beta_binomial (within-experiment posterior)
# ---------------------------------------------------------------------------


def test_beta_binomial_posterior_params_and_mean():
    post = stats.beta_binomial(8, 10)  # Beta(1,1) prior -> Beta(9, 3)
    assert post.alpha_post == 9 and post.beta_post == 3, post
    assert _approx(post.mean, 9 / 12), post.mean


def test_beta_binomial_edge_closed_form():
    # Beta(1,1) prior, k=0 -> Beta(1, n+1). F(x)=1-(1-x)^(n+1), so the equal-tailed
    # 95% bounds have closed forms. Independent reference.
    n, alpha = 10, 0.05
    post = stats.beta_binomial(0, n)
    lo_ref = 1 - (1 - alpha / 2) ** (1 / (n + 1))
    hi_ref = 1 - (alpha / 2) ** (1 / (n + 1))
    assert _approx(post.low, lo_ref), (post.low, lo_ref)
    assert _approx(post.high, hi_ref), (post.high, hi_ref)


def test_beta_binomial_credible_mass_self_consistent():
    # At the returned bounds the integer-parameter Beta CDF (via the binomial
    # identity) equals the target tail mass — the defining reference.
    for k, n in [(3, 10), (36, 48), (18, 48), (1, 5)]:
        post = stats.beta_binomial(k, n)
        a, b = post.alpha_post, post.beta_post
        assert _approx(_beta_cdf_int(post.low, a, b), 0.025), f'bb lo mass {k}/{n}'
        assert _approx(_beta_cdf_int(post.high, a, b), 0.975), f'bb hi mass {k}/{n}'


def test_beta_binomial_symmetry_and_determinism():
    p1 = stats.beta_binomial(3, 10)
    p2 = stats.beta_binomial(7, 10)  # mirror under the symmetric Beta(1,1) prior
    assert _approx(p2.low, 1 - p1.high)
    assert _approx(p2.high, 1 - p1.low)
    assert stats.beta_binomial(36, 48) == stats.beta_binomial(36, 48)  # deterministic


def test_beta_binomial_rejects_non_integer_prior():
    # The binomial-sum identity for the Beta CDF is exact ONLY for integer params.
    for bad in [(0.5, 1), (1, 2.0), (0, 1), (1, 0)]:
        try:
            stats.beta_binomial(3, 10, prior_alpha=bad[0], prior_beta=bad[1])
        except ValueError:
            continue
        raise AssertionError(f'expected ValueError for prior {bad}')


def test_rg_2x2_footprint_move():
    # The founding case: footprint outcome, 36/48 with the gate vs 18/48 without,
    # as a within-experiment Beta-Binomial update (Beta(1,1) prior).
    with_gate = stats.beta_binomial(36, 48)
    without_gate = stats.beta_binomial(18, 48)
    assert with_gate.alpha_post == 37 and with_gate.beta_post == 13
    assert without_gate.alpha_post == 19 and without_gate.beta_post == 31
    # Direction: the gate arm's posterior sits strictly above the no-gate arm's,
    # with the 95% credible intervals fully separated.
    assert with_gate.mean > without_gate.mean
    assert with_gate.low > without_gate.high, (with_gate, without_gate)


# ---------------------------------------------------------------------------
# Method dispatch — the load-bearing refusal of the CLT/normal path
# ---------------------------------------------------------------------------


def test_normal_method_raises():
    # PR2's validator relies on this refusal: no CLT/normal interval exists.
    for method in ['normal', 'wald', 'clt', 'gaussian', 'z']:
        try:
            stats.confidence_interval(12, 48, method=method)
        except ValueError:
            continue
        raise AssertionError(f'expected ValueError for method {method!r}')


def test_unknown_method_raises():
    for method in ['bootstrap', 'jeffreys', 'agresti_coull', '']:
        try:
            stats.confidence_interval(12, 48, method=method)
        except ValueError:
            continue
        raise AssertionError(f'expected ValueError for unknown method {method!r}')


def test_confidence_interval_dispatch_matches_direct():
    assert stats.confidence_interval(8, 10, 'wilson') == stats.wilson(8, 10)
    assert stats.confidence_interval(8, 10, 'clopper_pearson') == stats.clopper_pearson(8, 10)
    post = stats.beta_binomial(8, 10)
    ci = stats.confidence_interval(8, 10, 'beta_binomial')
    assert ci == stats.Interval(post.low, post.high)


# ---------------------------------------------------------------------------
# Paired / clustered SE for the shared-task structure
# ---------------------------------------------------------------------------

# RG-2x2 shared-task structure: 6 tasks reused across arms, 8 runs per task
# (6*8 = 48 per arm). A defensible per-task split of the with-gate arm's 36/48
# with realistic task-difficulty heterogeneity (the published case reports only
# the 36/48 aggregate; PR5 owns the real per-task record).
_WITH_GATE_BY_TASK = [8, 8, 8, 6, 4, 2]  # sums to 36
_TASK_SIZE = 8


def _outcomes_and_clusters(successes_by_task, size):
    outcomes, clusters = [], []
    for t, s in enumerate(successes_by_task):
        outcomes += [1] * s + [0] * (size - s)
        clusters += [t] * size
    return outcomes, clusters


def test_clustered_se_exceeds_naive_se():
    outcomes, clusters = _outcomes_and_clusters(_WITH_GATE_BY_TASK, _TASK_SIZE)
    naive = stats.naive_se(36, 48)
    clustered = stats.clustered_se(outcomes, clusters)
    assert clustered > naive, f'clustered {clustered} !> naive {naive}'
    # Exact regression pin (independent recompute of the sandwich variance on this
    # fixture, successes [8,8,8,6,4,2]): G/(G-1)*sum(y_g - p_hat*m_g)^2 / total^2.
    assert clustered == 0.12909944487358055, clustered


def test_clustered_se_length_mismatch_raises():
    try:
        stats.clustered_se([1, 0, 1], [0, 0])
    except ValueError:
        return
    raise AssertionError('expected ValueError on length mismatch')


def test_paired_difference_on_shared_tasks():
    with_gate = [8, 8, 8, 6, 4, 2]  # 36
    without_gate = [4, 4, 3, 3, 2, 2]  # 18
    sizes = [_TASK_SIZE] * 6
    diff = stats.paired_difference(with_gate, sizes, without_gate, sizes)
    assert diff.n_clusters == 6
    assert _approx(diff.mean_diff, (36 - 18) / 48)  # equal sizes -> equals aggregate
    assert diff.se > 0
    # Exact regression pin: sd(per-task rate diffs, ddof=1) / sqrt(6) on this fixture.
    assert diff.se == 0.09128709291752768, diff.se
    # deterministic
    assert stats.paired_difference(with_gate, sizes, without_gate, sizes) == diff


# ---------------------------------------------------------------------------
# The counts -> trials adapter (schema v1.1)
# ---------------------------------------------------------------------------


def test_expand_cluster_counts_reproduces_the_known_clustered_se():
    # The adapter is the bridge between the record's `clusters` block (per-cluster
    # counts) and clustered_se (per-trial 0/1 outcomes). Expanding the same fixture
    # the hand-built helper above expands must give the same trial list AND reproduce
    # the SE pinned independently in test_clustered_se_exceeds_naive_se.
    outcomes, ids = stats.expand_cluster_counts(_WITH_GATE_BY_TASK, [_TASK_SIZE] * 6)
    hand_outcomes, hand_ids = _outcomes_and_clusters(_WITH_GATE_BY_TASK, _TASK_SIZE)
    assert outcomes == hand_outcomes, (outcomes, hand_outcomes)
    assert list(ids) == hand_ids, (ids, hand_ids)
    assert stats.clustered_se(outcomes, ids) == 0.12909944487358055


def test_expand_cluster_counts_is_lossless_under_re_collapse():
    # Losslessness stated as a round trip: re-collapsing the trial list by label
    # recovers the (successes, size) pair of every cluster, including a 0/n cluster
    # and unequal cluster sizes.
    numerators, sizes = [3, 0, 4, 2], [4, 5, 4, 2]
    labels = ['p1', 'p2', 'p3', 'p4']
    outcomes, ids = stats.expand_cluster_counts(numerators, sizes, labels=labels)
    assert len(outcomes) == sum(sizes) == len(ids)
    collapsed: dict[str, list[int]] = {}
    for o, c in zip(outcomes, ids, strict=True):
        cell = collapsed.setdefault(c, [0, 0])
        cell[0] += o
        cell[1] += 1
    assert collapsed == {'p1': [3, 4], 'p2': [0, 5], 'p3': [4, 4], 'p4': [2, 2]}


def test_expand_cluster_counts_validates_its_input():
    for args in ([[1], [2, 3]], [[5], [4]], [[-1], [4]], [[1], [0]], [[], []]):
        try:
            stats.expand_cluster_counts(*args)
        except ValueError:
            continue
        raise AssertionError(f'expand_cluster_counts accepted {args}')
    try:
        stats.expand_cluster_counts([1, 2], [4, 4], labels=['only_one'])
    except ValueError:
        return
    raise AssertionError('expand_cluster_counts accepted a short label list')


def test_cluster_deltas_is_the_one_definition_paired_difference_averages():
    a, b, sizes = [4, 3, 1], [2, 2, 2], [4, 4, 4]
    deltas = stats.cluster_deltas(a, sizes, b, sizes)
    assert deltas == [0.5, 0.25, -0.25], deltas
    assert _approx(stats.paired_difference(a, sizes, b, sizes).mean_diff, sum(deltas) / 3)


# ---------------------------------------------------------------------------
# Student-t: the stdlib-only quantile behind paired_interval (schema v1.1)
# ---------------------------------------------------------------------------

# Published two-sided 95% critical values t(0.975, df) as printed in any statistics
# table -- an external anchor, independent of anything stats.py computes.
_T_975 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    10: 2.228,
    24: 2.064,
    30: 2.042,
    60: 2.000,
    100: 1.984,
}


def test_student_t_quantile_matches_the_published_table():
    for df, ref in _T_975.items():
        q = stats.student_t_quantile(0.975, df)
        assert math.isclose(q, ref, abs_tol=5e-4), f't(0.975, {df}) = {q} vs published {ref}'


def test_student_t_cdf_matches_independent_closed_forms():
    # df=1 is Cauchy: F(t) = 1/2 + atan(t)/pi. df=2 has the elementary closed form
    # F(t) = 1/2 + t / (2*sqrt(2 + t^2)). Both written here from first principles,
    # so the recursion's two base cases are checked against something outside it.
    for t in (-3.4, -0.7, 0.0, 0.9, 5.2):
        assert _approx(stats._t_cdf(t, 1), 0.5 + math.atan(t) / math.pi), t
        assert _approx(stats._t_cdf(t, 2), 0.5 + t / (2 * math.sqrt(2 + t * t))), t


def test_student_t_quantile_symmetry_and_normal_limit():
    assert stats.student_t_quantile(0.5, 5) == 0.0
    assert _approx(stats.student_t_quantile(0.025, 5), -stats.student_t_quantile(0.975, 5))
    # Heavier tails on fewer df, converging DOWN to the normal quantile from above.
    z = NormalDist().inv_cdf(0.975)
    assert stats.student_t_quantile(0.975, 2) > stats.student_t_quantile(0.975, 30)
    assert stats.student_t_quantile(0.975, 500) > z
    assert stats.student_t_quantile(0.975, 500) - z < 0.01


def test_student_t_quantile_validates_its_input():
    for p, df in [(0.0, 5), (1.0, 5), (-0.2, 5), (0.975, 0), (0.975, -1), (0.975, 2.5)]:
        try:
            stats.student_t_quantile(p, df)
        except ValueError:
            continue
        raise AssertionError(f'student_t_quantile accepted ({p}, {df})')


def test_student_t_quantile_refuses_a_p_it_cannot_bracket():
    # The bracket search is bounded. A p so close to 1 that the quantile sits past
    # that bound must RAISE rather than return the bracket end, which would be a
    # wrong number wearing the shape of an answer (it returned 1099511627776.0).
    try:
        stats.student_t_quantile(1 - 1e-13, 1)
    except ValueError as exc:
        assert 'bracket' in str(exc), exc
        return
    raise AssertionError('student_t_quantile returned a value it could not bracket')


def test_student_t_cdf_never_leaves_the_unit_interval():
    # The summed series lands a few ulp outside [0, 1] in the far tails at large df
    # (measured -2.2e-16 and 1.0000000000000002); a CDF must not report a
    # probability outside its own range.
    for df in (1, 2, 7, 200, 999, 1000):
        for t in (-1e6, -60.0, -1.0, 0.0, 1.0, 60.0, 1e6):
            value = stats._t_cdf(t, df)
            assert 0.0 <= value <= 1.0, (df, t, value)


# ---------------------------------------------------------------------------
# paired_interval and the exact sign test (schema v1.1)
# ---------------------------------------------------------------------------


def test_paired_interval_is_estimate_plus_or_minus_t_times_se():
    diff = stats.paired_difference(
        [8, 8, 8, 6, 4, 2], [_TASK_SIZE] * 6, [4, 4, 3, 3, 2, 2], [_TASK_SIZE] * 6
    )
    band = stats.paired_interval(diff.mean_diff, diff.se, diff.n_clusters)
    assert band.df == 5
    assert math.isclose(band.quantile, _T_975[5], abs_tol=5e-4), band.quantile
    half = band.quantile * diff.se
    assert _approx(band.low, diff.mean_diff - half)
    assert _approx(band.high, diff.mean_diff + half)
    # Wider than the normal interval it deliberately is not: the whole point of the
    # t reference on 6 clusters is that it does not pretend to large-sample precision.
    assert band.high - band.low > 2 * NormalDist().inv_cdf(0.975) * diff.se


def test_paired_interval_bounds_are_not_clamped():
    # A rate difference lives in [-1, 1], but clamping would silently redefine the
    # stated interval; a bound outside the range is left visible instead.
    band = stats.paired_interval(0.9, 0.4, 3)
    assert band.high > 1.0, band


def test_paired_interval_validates_its_input():
    bad_args = [
        (0.1, 0.05, 1),  # one cluster: no df
        (0.1, 0.05, 0),
        (0.1, 0.05, 2.0),  # a float cluster count
        (0.1, -0.05, 5),  # a negative SE
        (0.1, True, 5),  # a bool SE -- rejected like a bool cluster count
        (0.1, float('nan'), 5),  # NaN compares false against every bound
        (0.1, float('inf'), 5),
    ]
    for args in bad_args:
        try:
            stats.paired_interval(*args)
        except ValueError:
            continue
        raise AssertionError(f'paired_interval accepted {args}')
    try:
        stats.paired_interval(0.1, 0.05, 5, alpha=0.0)
    except ValueError:
        return
    raise AssertionError('paired_interval accepted alpha 0.0')


def test_sign_test_drops_ties_and_reports_the_effective_n():
    # Deltas: 4 positive, 1 negative, 1 zero. The tie rule drops the zero, so the
    # exact test is Binomial(5, 1/2) at 4 positives:
    #   p = 2 * P(X >= 4) = 2 * (C(5,4) + C(5,5)) / 2^5 = 2 * 6/32 = 0.375.
    result = stats.sign_test([0.5, 0.25, 0.0, 0.25, 0.5, -0.25])
    assert result.effective_n == 5 and result.positive == 4, result
    assert _approx(result.p_value, 2 * 6 / 32), result.p_value


def test_sign_test_unanimous_and_fully_tied():
    # Six unanimous clusters: p = 2 * (1/2)^6 = 0.03125.
    assert _approx(stats.sign_test([0.5] * 6).p_value, 2 / 64)
    assert _approx(stats.sign_test([-0.5] * 6).p_value, 2 / 64)
    # Everything tied: nothing survives, so the honest answer is p = 1 on n_eff = 0,
    # not a pass.
    assert stats.sign_test([0.0, 0.0, 0.0]) == stats.SignTest(1.0, 0, 0)


def test_sign_test_is_hand_derivable_from_the_recorded_counts():
    # The bound needs no gate because a reader can redo it: effective n and the
    # positive count are both recoverable from the per-cluster counts.
    a, b, sizes = [4, 3, 4, 2, 3, 1], [2, 2, 4, 1, 1, 2], [4] * 6
    result = stats.sign_test(stats.cluster_deltas(a, sizes, b, sizes))
    assert (result.effective_n, result.positive) == (5, 4), result
    assert _approx(result.p_value, 0.375), result.p_value


# ---------------------------------------------------------------------------
# Power / precision helper (Miller's before-spend sizing)
# ---------------------------------------------------------------------------


def test_min_detectable_effect_exact_binomial():
    res = stats.min_detectable_effect(48, baseline=0.5, alpha=0.05, power=0.80)
    assert 0.0 < res.mde < 0.5, res
    assert res.achieved_power >= 0.80 - stats.ATOL, res
    assert 0 <= res.critical_count <= 48
    # Exact regression pin: the two-sided level-0.05 rejection region on n=48 at
    # baseline 0.5 is X >= 32 (smallest c with P(X>=c | 48, 0.5) <= 0.025).
    assert res.critical_count == 32, res


def test_min_detectable_effect_shrinks_with_n():
    small = stats.min_detectable_effect(48).mde
    large = stats.min_detectable_effect(192).mde
    assert large < small, (small, large)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_input_validation():
    for fn in (stats.wilson, stats.clopper_pearson):
        for k, n in [(-1, 10), (11, 10), (0, 0), (3, -2)]:
            try:
                fn(k, n)
            except ValueError:
                continue
            raise AssertionError(f'{fn.__name__} accepted bad ({k},{n})')
    for bad_alpha in [0.0, 1.0, -0.1, 1.5]:
        try:
            stats.wilson(3, 10, alpha=bad_alpha)
        except ValueError:
            continue
        raise AssertionError(f'accepted bad alpha {bad_alpha}')
    # cluster_ids length must equal denominator on beta_binomial.
    try:
        stats.beta_binomial(3, 10, cluster_ids=[0, 1, 2])
    except ValueError:
        pass
    else:
        raise AssertionError('accepted mismatched cluster_ids length')


if __name__ == '__main__':
    import sys

    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
            except Exception as exc:  # report any failure; never emit the ok: sentinel
                failed += 1
                print(f'FAIL {name}: {exc!r}')
    if failed:
        print(f'{failed} test(s) failed')
        sys.exit(1)
    print('ok: all stats tests passed')
