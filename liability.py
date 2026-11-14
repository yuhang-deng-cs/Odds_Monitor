"""SIMULATED sportsbook exposure: what would our book's liability look like per match?

The prices and results are real (one bookmaker's closing odds plays "our book"); the BETS ARE
SIMULATED, because football-data.co.uk has no bet or stake data. Nothing here is real trading.

Per match, two kinds of simulated customers bet at our closing prices:
- recreational: a fixed handle split across H/D/A roughly in line with the fair chances, with
  random noise (lognormal) so some matches end up lopsided, as real books do;
- sharp: a fixed extra stake on any outcome where our price beats the sharp reference by more
  than the alert threshold, i.e. exactly where the detector says we are mispriced.

For each outcome we compute the book's P&L if that outcome wins:
    pnl_if[i] = total stakes - stake[i] * odds[i]
The worst of the three is the match's liability. An exposure alert fires when it is below
-limit, the kind of check a trader uses to cut a price or limit stakes before kick-off.
"""

import numpy as np
import pandas as pd

from detector import DEVIG, OUTCOMES, reference_probs

DEFAULTS = {"book": "Bet365", "handle": 10_000.0, "sharp_stake": 2_000.0, "limit": 10_000.0,
            "threshold": 0.03, "method": "power", "seed": 0}  # fmt: skip
NOISE_SIGMA = 0.5  # spread of recreational money around the fair split


def book_pnl(stakes: np.ndarray, prices: np.ndarray) -> np.ndarray:
    """Book's profit if each outcome wins: everything staked minus that outcome's payout."""
    return stakes.sum() - stakes * prices


def simulate(
    odds: pd.DataFrame,
    book: str = DEFAULTS["book"],
    handle: float = DEFAULTS["handle"],
    sharp_stake: float = DEFAULTS["sharp_stake"],
    limit: float = DEFAULTS["limit"],
    threshold: float = DEFAULTS["threshold"],
    method: str = DEFAULTS["method"],
    seed: int = DEFAULTS["seed"],
) -> pd.DataFrame:
    """One row per match where `book` has a closing price. Deterministic for a given seed."""
    if method not in DEVIG:
        raise ValueError(f"unknown method {method!r}")
    rng = np.random.default_rng(seed)
    close = odds[odds["snapshot"] == "close"]
    rows = []
    for match_id, g in close.groupby("match_id", sort=True):
        ours = g[g["bookmaker"] == book]
        others = g[g["bookmaker"] != book]
        if ours.empty or others.empty:
            continue
        # The reference never includes our own price, otherwise we would partly grade ourselves.
        prices = {
            r.bookmaker: (r.odds_h, r.odds_d, r.odds_a) for r in others.itertuples(index=False)
        }
        fair, ref = reference_probs(prices, method)
        fair = np.array(fair)
        our = ours[["odds_h", "odds_d", "odds_a"]].to_numpy()[0]

        weights = fair * rng.lognormal(0.0, NOISE_SIGMA, size=3)
        rec = handle * weights / weights.sum()
        edge = fair * our - 1  # the customer's expected edge at our price
        sharp = np.where(edge > threshold, sharp_stake, 0.0)

        pnl_rec, pnl_sharp = book_pnl(rec, our), book_pnl(sharp, our)
        pnl = pnl_rec + pnl_sharp
        result = OUTCOMES.index(g["result"].iloc[0])
        rows.append({
            "match_id": match_id,
            "match_date": g["match_date"].iloc[0],
            "home": g["home"].iloc[0],
            "away": g["away"].iloc[0],
            "result": OUTCOMES[result],
            "reference": ref,
            **{f"stake_{o.lower()}": s for o, s in zip(OUTCOMES, rec + sharp, strict=True)},
            "sharp_on": "".join(o for o, s in zip(OUTCOMES, sharp, strict=True) if s > 0),
            **{f"pnl_if_{o.lower()}": p for o, p in zip(OUTCOMES, pnl, strict=True)},
            "worst_case": pnl.min(),
            "expected_pnl": float(fair @ pnl),
            "actual_pnl": pnl[result],
            "actual_pnl_recreational": pnl_rec[result],
            "actual_pnl_sharp": pnl_sharp[result],
            "expected_pnl_sharp": float(fair @ pnl_sharp),
            "breach": pnl.min() < -limit,
        })  # fmt: skip
    return pd.DataFrame(rows)


def summarise(sim: pd.DataFrame) -> pd.DataFrame:
    """Headline numbers as a (metric, value) table."""
    handle = sim[["stake_h", "stake_d", "stake_a"]].to_numpy().sum()
    rows = [
        ("matches", len(sim)),
        ("total stakes (simulated)", handle),
        ("expected profit at fair prices", sim["expected_pnl"].sum()),
        ("actual profit on real results", sim["actual_pnl"].sum()),
        ("  of which recreational bets", sim["actual_pnl_recreational"].sum()),
        ("  of which sharp bets", sim["actual_pnl_sharp"].sum()),
        ("matches with sharp bets", int((sim["sharp_on"] != "").sum())),
        ("expected profit on sharp bets", sim["expected_pnl_sharp"].sum()),
        ("exposure alerts (worst case below limit)", int(sim["breach"].sum())),
        ("largest worst-case loss", sim["worst_case"].min()),
    ]
    return pd.DataFrame(rows, columns=["metric", "value"])
