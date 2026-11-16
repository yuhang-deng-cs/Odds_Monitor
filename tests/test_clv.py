import math

import numpy as np
import pandas as pd
import pytest

import clv
from odds import devig_power


def _odds(rows):
    """rows: (match_id, bookmaker, snapshot, h, d, a, result)."""
    return pd.DataFrame(
        [
            {"match_id": m, "season": "2425", "match_date": pd.Timestamp("2024-08-17"),
             "home": "X", "away": "Y", "bookmaker": b, "snapshot": s,
             "odds_h": h, "odds_d": d, "odds_a": a, "result": r}
            for m, b, s, h, d, a, r in rows
        ]
    )  # fmt: skip


ODDS = _odds([
    ("m1", "Pinnacle", "close", 2.00, 3.60, 4.00, "A"),
    ("m1", "Pinnacle", "open", 2.05, 3.50, 3.90, "A"),
    ("m1", "Ours", "open", 1.80, 3.40, 6.00, "A"),
    ("m1", "Betfair Exchange", "open", 2.10, 3.70, 4.10, "A"),
])  # fmt: skip


def _alert(odds, outcome="A", snapshot="open", book="Ours", ref="Pinnacle", confirmed=None):
    return pd.DataFrame([{
        "alert_type": "value", "match_id": "m1", "snapshot": snapshot, "bookmaker": book,
        "outcome": outcome, "odds": odds, "fair_prob": 0.25, "edge": 0.5, "reference": ref,
        "confirmed": confirmed,
    }])  # fmt: skip


def test_closing_fair_uses_closing_reference():
    fair = clv.closing_fair(ODDS)
    expected = devig_power([2.00, 3.60, 4.00])
    assert fair.loc[0, "close_reference"] == "Pinnacle"
    assert fair.loc[0, ["H", "D", "A"]].tolist() == pytest.approx(expected)


def test_clv_and_pnl_for_one_alert():
    summary, detail = clv.performance(ODDS, _alert(6.0))
    p_close = devig_power([2.00, 3.60, 4.00])[2]
    row = detail.iloc[0]
    assert row["clv"] == pytest.approx(6.0 * p_close - 1)  # beat the close: price was generous
    assert row["won"] and row["pnl"] == pytest.approx(5.0)  # 1 unit at 6.0 on the winning away
    early = summary.set_index("group").loc["early value alerts"]
    assert early["n"] == 1 and early["beat_close_pct"] == 1.0
    # baseline = every early sportsbook price: Pinnacle + Ours, 3 outcomes each (exchange excluded)
    assert summary.set_index("group").loc["all early prices (baseline)", "n"] == 6


def test_closing_alerts_have_no_clv():
    summary, _ = clv.performance(ODDS, _alert(4.4, snapshot="close"))
    assert math.isnan(summary.set_index("group").loc["closing value alerts", "avg_clv"])


def test_bootstrap_resamples_matches():
    same = pd.DataFrame({"match_id": ["a", "b", "c"], "pnl": [1.0, 1.0, 1.0]})
    assert clv.bootstrap_roi_ci(same) == pytest.approx((1.0, 1.0))
    one = pd.DataFrame({"match_id": ["a", "a"], "pnl": [1.0, -1.0]})
    assert all(np.isnan(clv.bootstrap_roi_ci(one)))  # one match: no interval


def test_exchange_second_opinion_counts():
    alerts = pd.concat([_alert(6.0, confirmed=True), _alert(4.0, confirmed=False), _alert(5.0)])
    assert clv.exchange_check(alerts) == (2, 1)  # the alert with no second source is not counted


def test_confirmed_alerts_get_their_own_backtest_row():
    alerts = pd.concat([_alert(6.0, confirmed=True), _alert(4.4, snapshot="close", confirmed=True)])
    summary, _ = clv.performance(ODDS, alerts)
    row = summary.set_index("group").loc["exchange-confirmed alerts"]
    assert row["n"] == 2
    p_close = devig_power([2.00, 3.60, 4.00])[2]
    assert row["avg_clv"] == pytest.approx(6.0 * p_close - 1)  # CLV from the early alert only
