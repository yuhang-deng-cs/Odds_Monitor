import numpy as np
import pandas as pd
import pytest
from test_clv import _odds

import liability


def test_book_pnl_worked_example():
    # 100 on home at 2.0, nothing else: book loses 100 if home wins, keeps 100 otherwise.
    pnl = liability.book_pnl(np.array([100.0, 0, 0]), np.array([2.0, 3.0, 4.0]))
    assert pnl.tolist() == [-100.0, 100.0, 100.0]


ODDS = _odds([
    ("m1", "Pinnacle", "close", 2.00, 3.60, 4.00, "A"),
    ("m1", "Ours", "close", 1.80, 3.40, 6.00, "A"),  # away far above fair -> sharp money
    ("m2", "Pinnacle", "close", 1.50, 4.20, 7.00, "H"),
    ("m2", "Ours", "close", 1.45, 4.00, 6.50, "H"),  # all below fair -> no sharp money
])  # fmt: skip


def test_simulate_one_row_per_match_and_consistent_pnl():
    sim = liability.simulate(ODDS, book="Ours", handle=1000, sharp_stake=500, limit=1500)
    assert sim["match_id"].tolist() == ["m1", "m2"]
    assert sim["sharp_on"].tolist() == ["A", ""]
    ours = {"m1": [1.80, 3.40, 6.00], "m2": [1.45, 4.00, 6.50]}
    for r in sim.itertuples():
        stakes = np.array([r.stake_h, r.stake_d, r.stake_a])
        pnl = stakes.sum() - stakes * np.array(ours[r.match_id])
        assert [r.pnl_if_h, r.pnl_if_d, r.pnl_if_a] == pytest.approx(pnl)
        assert r.worst_case == pytest.approx(pnl.min())
        assert r.actual_pnl == pytest.approx(pnl["HDA".index(r.result)])
        assert r.breach == (pnl.min() < -1500)
    m2 = sim.iloc[1]
    assert m2.stake_h + m2.stake_d + m2.stake_a == pytest.approx(1000)  # recreational only


def test_simulate_is_deterministic_and_skips_matches_without_reference():
    a = liability.simulate(ODDS, book="Ours", seed=7)
    b = liability.simulate(ODDS, book="Ours", seed=7)
    pd.testing.assert_frame_equal(a, b)
    only_ours = ODDS[ODDS["bookmaker"] == "Ours"]
    assert liability.simulate(only_ours, book="Ours").empty


def test_summary_totals():
    sim = liability.simulate(ODDS, book="Ours", handle=1000, sharp_stake=500)
    s = dict(liability.summarise(sim).values)
    assert s["matches"] == 2 and s["matches with sharp bets"] == 1
    assert s["total stakes (simulated)"] == pytest.approx(2500)
    assert s["actual profit on real results"] == pytest.approx(sim["actual_pnl"].sum())
