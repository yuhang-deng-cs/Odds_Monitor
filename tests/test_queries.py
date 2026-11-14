import pytest

from db import connect, ingest
from load import load_dir
from queries import margins, moves


@pytest.fixture
def con(raw_dir, tmp_path):
    con = connect(tmp_path / "q.duckdb")
    ingest(con, load_dir(raw_dir))
    return con


def test_margins_per_bookmaker(con):
    df = margins(con)
    ps_open = df[(df.bookmaker == "Pinnacle") & (df.snapshot == "open")].iloc[0]
    assert ps_open.n_matches == 3
    # Tightest of the 3 matches is Man City, Pinnacle open 1.53/4.50/6.90:
    # 1/1.53 + 1/4.5 + 1/6.9 - 1 = 2.07%
    assert ps_open.min_margin_pct == pytest.approx(2.07, abs=0.01)


def test_moves_uses_lag_open_to_close(con):
    df = moves(con, limit=100)
    row = df[(df.home == "Man City") & (df.bookmaker == "Pinnacle") & (df.outcome == "A")].iloc[0]
    assert (row.open_odds, row.close_odds) == (6.90, 7.40)
    assert row.prob_move_pp < 0  # odds drifted out -> probability fell
    # Bet365 open for Arsenal was invalid, so there is no open->close pair to compare
    assert df[(df.home == "Arsenal") & (df.bookmaker == "Bet365")].empty
    # sorted by size of move
    assert df.prob_move_pp.abs().is_monotonic_decreasing


def test_moves_bookmaker_filter_and_limit(con):
    df = moves(con, limit=2, bookmaker="Pinnacle")
    assert len(df) == 2
    assert set(df.bookmaker) == {"Pinnacle"}
