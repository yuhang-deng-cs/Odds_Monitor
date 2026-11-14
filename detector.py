"""Detect pricing discrepancies (value vs a sharp reference) and cross-book arbitrage.

Runs per (match, snapshot) over historical odds: a replay, not a live system.
"""

import pandas as pd

from odds import devig_power, devig_proportional

OUTCOMES = ("H", "D", "A")
DEVIG = {"proportional": devig_proportional, "power": devig_power}

# Fair-price reference, first one present wins. Pinnacle is the classic low-margin "sharp"
# book. Betfair Exchange is a peer-to-peer market with ~0.6% overround in this data, but its
# quoted prices are BEFORE commission (typically 2-5% of net winnings), so it is used as a
# reference but never as a target for value or arbitrage alerts: those edges would be overstated.
REFERENCE_ORDER = ("Pinnacle", "Betfair Exchange")
EXCHANGES = {"Betfair Exchange"}

ALERT_COLUMNS = [
    "alert_type", "match_id", "match_date", "home", "away", "snapshot",
    "bookmaker", "outcome", "odds", "fair_prob", "edge", "reference",
]  # fmt: skip
DEDUPE_KEY = ["alert_type", "match_id", "snapshot", "bookmaker", "outcome"]


def reference_probs(prices: dict[str, tuple[float, float, float]], method: str = "power"):
    """Return (fair H/D/A probabilities, reference name) for one match snapshot.

    prices maps bookmaker -> (odds_h, odds_d, odds_a). Fallback when no sharp book is present:
    the average of every book's de-vigged probabilities. Known weakness: the book being
    tested is part of its own reference, which shrinks its measured edge.
    """
    devig = DEVIG[method]
    for book in REFERENCE_ORDER:
        if book in prices:
            return devig(prices[book]), book
    all_probs = [devig(odds) for odds in prices.values()]
    avg = [sum(p[i] for p in all_probs) / len(all_probs) for i in range(len(OUTCOMES))]
    return avg, "market_average"


def value_alerts(
    prices: dict[str, tuple[float, float, float]], threshold: float = 0.03, method: str = "power"
) -> list[dict]:
    """Flag (bookmaker, outcome) where expected value vs the reference exceeds threshold.

    edge = fair_prob * odds - 1 is the expected profit per unit staked if the reference
    probabilities are right. Example: fair 0.25 at odds 4.40 -> edge = 0.10 (10%).
    """
    fair, ref = reference_probs(prices, method)
    alerts = []
    for book, odds in sorted(prices.items()):
        if book == ref or book in EXCHANGES:
            continue
        for outcome, p, o in zip(OUTCOMES, fair, odds, strict=True):
            edge = p * o - 1
            if edge > threshold:
                alerts.append(
                    {"alert_type": "value", "bookmaker": book, "outcome": outcome,
                     "odds": o, "fair_prob": p, "edge": edge, "reference": ref}
                )  # fmt: skip
    return alerts


def arbitrage_alert(prices: dict[str, tuple[float, float, float]]) -> dict | None:
    """Flag an arbitrage if the best price per outcome across sportsbooks sums below 1.

    If sum(1/best_odds) = S < 1, staking 1/(odds_i * S) on each outcome returns 1/S whatever
    happens, so the guaranteed return on total stake is edge = 1/S - 1.
    """
    books = {b: o for b, o in prices.items() if b not in EXCHANGES}
    if not books:
        return None
    best = []  # (odds, bookmaker) per outcome; ties go to the alphabetically first book
    for i in range(len(OUTCOMES)):
        best.append(max(((o[i], b) for b, o in sorted(books.items())), key=lambda t: t[0]))
    total = sum(1 / o for o, _ in best)
    if total >= 1:
        return None
    return {
        "alert_type": "arbitrage",
        "bookmaker": "|".join(f"{out}:{b}@{o}" for out, (o, b) in zip(OUTCOMES, best, strict=True)),
        "outcome": "ALL",
        "odds": None,
        "fair_prob": total,  # stored as the sum of implied probs of the best prices
        "edge": 1 / total - 1,
        "reference": "best_price",
    }


def detect(odds: pd.DataFrame, threshold: float = 0.03, method: str = "power") -> pd.DataFrame:
    """Run value and arbitrage checks for every (match, snapshot) and return deduped alerts.

    odds needs: match_id, match_date, home, away, bookmaker, snapshot, odds_h, odds_d, odds_a.
    """
    rows = []
    for (match_id, snapshot), group in odds.groupby(["match_id", "snapshot"], sort=True):
        prices = {
            r.bookmaker: (r.odds_h, r.odds_d, r.odds_a) for r in group.itertuples(index=False)
        }
        context = {
            "match_id": match_id,
            "snapshot": snapshot,
            "match_date": group["match_date"].iloc[0],
            "home": group["home"].iloc[0],
            "away": group["away"].iloc[0],
        }
        found = value_alerts(prices, threshold, method)
        arb = arbitrage_alert(prices)
        if arb:
            found.append(arb)
        rows.extend({**context, **a} for a in found)

    alerts = pd.DataFrame(rows, columns=ALERT_COLUMNS)
    # Dedupe: one alert per key, keeping the largest edge (e.g. if input rows were duplicated).
    alerts = alerts.sort_values("edge", ascending=False).drop_duplicates(DEDUPE_KEY)
    return alerts.reset_index(drop=True)
