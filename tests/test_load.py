import logging

import pandas as pd

from load import LONG_COLUMNS, load_dir


def test_long_format_and_invalid_rows_dropped(raw_dir, caplog):
    with caplog.at_level(logging.INFO):
        long = load_dir(raw_dir)
    assert list(long.columns) == LONG_COLUMNS
    # 3 matches x 2 books (Bet365, Pinnacle) x 2 snapshots = 12; minus 2 bad Bet365 open rows
    assert len(long) == 10
    assert set(long["bookmaker"]) == {"Bet365", "Pinnacle"}  # Max is an aggregate, excluded
    assert (long[["odds_h", "odds_d", "odds_a"]] > 1).all().all()
    assert "dropped 1 missing, 1 with odds <= 1" in caplog.text


def test_bad_row_only_drops_that_bookmaker(raw_dir):
    long = load_dir(raw_dir)
    arsenal = long[long["home"] == "Arsenal"]
    # Bet365 open is invalid, but Bet365 close and both Pinnacle snapshots survive
    assert len(arsenal) == 3
    assert not ((arsenal["bookmaker"] == "Bet365") & (arsenal["snapshot"] == "open")).any()


def test_match_id_and_parsing(raw_dir):
    long = load_dir(raw_dir)
    row = long[long["home"] == "Man City"].iloc[0]
    assert row["match_id"] == "E0_2024-08-10_Man_City_Chelsea"
    assert row["season"] == "2425"
    assert row["date"] == pd.Timestamp("2024-08-10")


def test_loader_is_deterministic(raw_dir):
    pd.testing.assert_frame_equal(load_dir(raw_dir), load_dir(raw_dir))
