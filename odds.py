"""Pure odds maths: implied probability, overround, and margin removal (de-vig).

All odds are decimal odds (e.g. 2.50 means a 1-unit stake returns 2.50 in total).
"""

from collections.abc import Sequence


def implied_prob(decimal_odds: float) -> float:
    """Raw implied probability of decimal odds (still includes the bookmaker margin)."""
    if decimal_odds <= 1.0:
        raise ValueError(f"decimal odds must be > 1, got {decimal_odds}")
    return 1.0 / decimal_odds


def overround(odds: Sequence[float]) -> float:
    """Bookmaker margin: sum of implied probabilities minus 1 (0.0556 means 5.56%).

    Negative overround across the best prices of several books means an arbitrage exists.
    """
    return sum(implied_prob(o) for o in odds) - 1.0


def devig_proportional(odds: Sequence[float]) -> list[float]:
    """Remove margin by scaling implied probabilities so they sum to 1.

    Every outcome loses the same *relative* share of its probability. That is biased under the
    favourite-longshot bias: in practice bookmakers put more of their margin on longshots
    (longshots are overbet by the public), so proportional de-vig leaves longshots with too
    much probability and favourites with too little.
    """
    raw = [implied_prob(o) for o in odds]
    total = sum(raw)
    return [p / total for p in raw]


def devig_power(odds: Sequence[float], tol: float = 1e-12, max_iter: int = 200) -> list[float]:
    """Remove margin with the power method: p_i = q_i ** k, with k chosen so sum(p_i) = 1.

    q_i = 1/odds_i are the raw implied probabilities (each < 1). If the book has a positive
    margin then k > 1. Because q ** k / q = q ** (k - 1), raising to a power above 1 shrinks
    small probabilities (longshots) proportionally more than large ones (favourites), which
    matches the favourite-longshot bias better than proportional de-vig.

    k is found by bisection: f(k) = sum(q_i ** k) - 1 is strictly decreasing in k,
    f(0) = n - 1 > 0, and f(k) -> -1 as k grows, so a root always exists.
    """
    raw = [implied_prob(o) for o in odds]
    if len(raw) < 2:
        raise ValueError("need at least two outcomes")

    def f(k: float) -> float:
        return sum(q**k for q in raw) - 1.0

    lo, hi = 0.0, 1.0
    while f(hi) > 0:  # widen the bracket until the root is inside [lo, hi]
        lo, hi = hi, hi * 2.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    k = (lo + hi) / 2.0
    probs = [q**k for q in raw]
    total = sum(probs)  # ~1 already; renormalise away the last bit of bisection error
    return [p / total for p in probs]


def devig_shin(odds: Sequence[float], tol: float = 1e-12, max_iter: int = 200) -> list[float]:
    """Remove margin with Shin's (1993) model, the standard method in betting research.

    Shin assumes a share z of the money comes from insiders who know the winner, so the book
    protects itself by padding every price, and longshots most. Given raw implied
    probabilities q_i with sum S, the fair probabilities are

        p_i(z) = (sqrt(z**2 + 4 * (1 - z) * q_i**2 / S) - z) / (2 * (1 - z))

    and z (0 <= z < 1) is chosen so that sum(p_i) = 1. At z = 0 the sum is sqrt(S) > 1 and it
    falls as z grows, so bisection on [0, 1) finds it. z itself is an estimate of how much
    insider money the book is pricing in. For two outcomes Shin equals removing the same
    absolute amount from each probability.
    """
    raw = [implied_prob(o) for o in odds]
    if len(raw) < 2:
        raise ValueError("need at least two outcomes")
    total = sum(raw)
    if total <= 1.0:  # no margin to remove (or an arbitrage): the model does not apply
        return [q / total for q in raw]

    def probs(z: float) -> list[float]:
        return [((z * z + 4 * (1 - z) * q * q / total) ** 0.5 - z) / (2 * (1 - z)) for q in raw]

    lo, hi = 0.0, 1.0 - 1e-9
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        if sum(probs(mid)) > 1.0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    p = probs((lo + hi) / 2.0)
    return [x / sum(p) for x in p]  # renormalise away the last bit of bisection error


def fair_price_table(odds: Sequence[float]) -> list[dict[str, float]]:
    """One row per outcome for ANY market size (3-way football, a 12-runner race, ...).

    Columns: odds, implied (raw 1/odds, margin included), proportional, power and Shin fair
    probabilities, and the power fair odds (1 / fair probability).
    """
    implied = [implied_prob(o) for o in odds]
    prop, power, shin = devig_proportional(odds), devig_power(odds), devig_shin(odds)
    return [
        {"odds": o, "implied": q, "proportional": pp, "power": pw, "shin": sh, "fair_odds": 1 / pw}
        for o, q, pp, pw, sh in zip(odds, implied, prop, power, shin, strict=True)
    ]
