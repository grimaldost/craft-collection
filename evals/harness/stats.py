"""Small statistics helpers for the eval harness. Stdlib `math` only."""

from __future__ import annotations

import math


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% CI for a binomial proportion. (0,1) when n == 0."""
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
    """True if more than half the votes are True; None for an empty list."""
    if not votes:
        return None
    return sum(votes) * 2 > len(votes)
