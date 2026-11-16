"""Did the alerts hold up? Closing Line Value (CLV) and a flat-stake backtest.

CLV is the industry's standard check on a price or a bet: compare the odds you took (or
offered) early with the fair probability at the CLOSE, when the market has the most
information. If early odds o beat the closing fair probability p_close, i.e.
clv = o * p_close - 1 > 0, the price was "too generous" and the market later moved against it.

From a sportsbook's side the same number reads the other way round: an early price of ours
with positive CLV is a price the sharp money would have taken off us.

Historical replay only: results and prices are real, no bets were placed.
"""

import numpy as np
import pandas as pd

from detector import EXCHANGES, OUTCOMES, reference_probs

BOOTSTRAP_SAMPLES = 2000


def closing_fair(odds: pd.DataFrame, method: str = "power") -> pd.DataFrame:
    """Fair H/D/A probabilities per match from the CLOSING snapshot's sharp reference."""
    rows = []
    close = odds[odds["snapshot"] == "close"]
    for match_id, g in close.groupby("match_id", sort=True):
        prices = {r.bookmaker: (r.odds_h, r.odds_d, r.odds_a) for r in g.itertuples(index=False)}
        probs, ref = reference_probs(prices, method)
        rows.append(
            {
                "match_id": match_id,
                "close_reference": ref,
                **dict(zip(OUTCOMES, probs, strict=True)),
            }
        )
    return pd.DataFrame(rows, columns=["match_id", "close_reference", *OUTCOMES])


def _add_clv_and_pnl(bets: pd.DataFrame, fair: pd.DataFrame, results: pd.Series) -> pd.DataFrame:
    """bets needs match_id, outcome, odds. Adds close_fair_prob, clv, won and pnl (1-unit stake).

    CLV only exists for early prices: a bet placed AT the close has no later price to beat, so
    rows with snapshot == "close" get clv = NaN.
    """
    long_fair = fair.melt(id_vars="match_id", value_vars=list(OUTCOMES), var_name="outcome",
                          value_name="close_fair_prob")  # fmt: skip
    out = bets.merge(long_fair, on=["match_id", "outcome"], how="left")
    out["clv"] = out["odds"] * out["close_fair_prob"] - 1
    if "snapshot" in out:
        out.loc[out["snapshot"] == "close", "clv"] = np.nan
    out["won"] = out["match_id"].map(results) == out["outcome"]
    out["pnl"] = np.where(out["won"], out["odds"] - 1, -1.0)
    return out


def bootstrap_roi_ci(bets: pd.DataFrame, seed: int = 0) -> tuple[float, float]:
    """95% percentile bootstrap interval of ROI, resampling whole MATCHES with replacement.

    Bets on the same match are not independent (one odd price can trigger alerts at several
    books for the same outcome), so resampling single bets would give a too-narrow interval.
    ROI of a resample = total pnl / total bets of the matches drawn.
    """
    per_match = bets.groupby("match_id")["pnl"].agg(["sum", "size"]).to_numpy()
    if len(per_match) < 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(per_match), size=(BOOTSTRAP_SAMPLES, len(per_match)))
    rois = per_match[idx, 0].sum(axis=1) / per_match[idx, 1].sum(axis=1)
    return float(np.percentile(rois, 2.5)), float(np.percentile(rois, 97.5))


BET_COLUMNS = ["match_id", "bookmaker", "snapshot", "outcome", "odds"]
CHECK_ORDER = ("confirmed", "rejected", "no second source")


def _summarise(d: pd.DataFrame) -> dict[str, float]:
    """Counts, CLV (early bets only) and flat-stake ROI with its match-level bootstrap range."""
    has_clv = d["clv"].notna().any()
    lo, hi = bootstrap_roi_ci(d)
    return {
        "n": len(d),
        "n_early": int((d["snapshot"] == "open").sum()),
        "n_clv": int(d["clv"].notna().sum()),
        "avg_clv": d["clv"].mean() if has_clv else float("nan"),
        "beat_close_pct": (d["clv"].dropna() > 0).mean() if has_clv else float("nan"),
        "roi": d["pnl"].mean() if len(d) else float("nan"),
        "roi_ci_low": lo,
        "roi_ci_high": hi,
    }


def performance(
    odds: pd.DataFrame, alerts: pd.DataFrame, method: str = "power"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (summary, per-bet detail).

    Groups compared:
    - early value alerts: the detector's flags on early odds -> CLV is measurable;
    - closing value alerts: flagged at the close -> no later price, so CLV is not defined;
    - exchange-confirmed alerts (both snapshots): Pinnacle AND Betfair Exchange agree there is
      an edge, i.e. the "require two sharp sources" rule; CLV from the early ones only;
    - baseline: EVERY early sportsbook price (all books, all outcomes). Its CLV should sit
      near minus the margin; alerts are only useful if they clearly beat it.
    roi is the realised profit per unit staked with a flat 1-unit stake on the real results.
    """
    fair = closing_fair(odds, method)
    results = odds.drop_duplicates("match_id").set_index("match_id")["result"]

    value = alerts[alerts["alert_type"] == "value"]
    confirmed = value[value["confirmed"].fillna(False).astype(bool)]
    early = odds[(odds["snapshot"] == "open") & ~odds["bookmaker"].isin(EXCHANGES)]
    baseline = early.melt(
        id_vars=["match_id", "bookmaker"], value_vars=["odds_h", "odds_d", "odds_a"],
        var_name="outcome", value_name="odds",
    ).assign(outcome=lambda d: d["outcome"].str[-1].str.upper(), snapshot="open")  # fmt: skip

    groups = {
        "early value alerts": value[value["snapshot"] == "open"],
        "closing value alerts": value[value["snapshot"] == "close"],
        "exchange-confirmed alerts": confirmed,
        "all early prices (baseline)": baseline,
    }
    rows, details = [], []
    for name, bets in groups.items():
        d = _add_clv_and_pnl(bets[BET_COLUMNS], fair, results)
        rows.append({"group": name, **_summarise(d)})
        if name != "all early prices (baseline)":
            details.append(d.assign(group=name))
    detail = pd.concat(details, ignore_index=True) if details else pd.DataFrame()
    return pd.DataFrame(rows), detail


def by_exchange_check(
    odds: pd.DataFrame, alerts: pd.DataFrame, method: str = "power"
) -> pd.DataFrame:
    """Value alerts split by snapshot and by what the second sharp source said:
    confirmed (Betfair Exchange agrees), rejected (it doesn't), or no second source
    (no exchange price, or the alert was not graded against Pinnacle)."""
    fair = closing_fair(odds, method)
    results = odds.drop_duplicates("match_id").set_index("match_id")["result"]
    value = alerts[alerts["alert_type"] == "value"]
    check = value["confirmed"].map(
        lambda c: CHECK_ORDER[2] if pd.isna(c) else CHECK_ORDER[0] if c else CHECK_ORDER[1]
    )
    rows = []
    for snapshot in ("open", "close"):
        for status in CHECK_ORDER:
            bets = value[(value["snapshot"] == snapshot) & (check == status)]
            if not bets.empty:
                d = _add_clv_and_pnl(bets[BET_COLUMNS], fair, results)
                rows.append({"snapshot": snapshot, "check": status, **_summarise(d)})
    columns = ["snapshot", "check", "n", "n_early", "n_clv", "avg_clv", "beat_close_pct",
               "roi", "roi_ci_low", "roi_ci_high"]  # fmt: skip
    return pd.DataFrame(rows, columns=columns)


def exchange_check(alerts: pd.DataFrame) -> tuple[int, int]:
    """Second opinion: of value alerts graded against Pinnacle that also had a Betfair Exchange
    price, how many still clear the threshold against the exchange? Returns (checked, confirmed).

    Reads the detector's `confirmed` column; alerts with no second sharp source are not counted.
    """
    flags = alerts.loc[alerts["alert_type"] == "value", "confirmed"].dropna().astype(bool)
    return len(flags), int(flags.sum())
