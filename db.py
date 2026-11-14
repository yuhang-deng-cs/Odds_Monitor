"""DuckDB storage: schema creation and idempotent ingest.

Idempotency comes from natural primary keys plus INSERT ... ON CONFLICT DO NOTHING:
re-ingesting the same files inserts zero new rows.
"""

from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_DB = Path("data/odds.duckdb")

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id   VARCHAR PRIMARY KEY,   -- e.g. E0_2025-08-15_Liverpool_Bournemouth
    season     VARCHAR NOT NULL,
    match_date DATE    NOT NULL,
    home       VARCHAR NOT NULL,
    away       VARCHAR NOT NULL,
    result     VARCHAR NOT NULL CHECK (result IN ('H', 'D', 'A'))
);
CREATE TABLE IF NOT EXISTS odds_snapshots (
    match_id  VARCHAR NOT NULL,
    bookmaker VARCHAR NOT NULL,
    snapshot  VARCHAR NOT NULL CHECK (snapshot IN ('open', 'close')),
    odds_h    DOUBLE  NOT NULL CHECK (odds_h > 1),
    odds_d    DOUBLE  NOT NULL CHECK (odds_d > 1),
    odds_a    DOUBLE  NOT NULL CHECK (odds_a > 1),
    PRIMARY KEY (match_id, bookmaker, snapshot)
);
CREATE TABLE IF NOT EXISTS alerts (
    alert_type VARCHAR NOT NULL,      -- 'value' or 'arbitrage'
    match_id   VARCHAR NOT NULL,
    snapshot   VARCHAR NOT NULL,
    bookmaker  VARCHAR NOT NULL,      -- for arbitrage: the books used, e.g. 'H:Bet365|D:...'
    outcome    VARCHAR NOT NULL,      -- 'H'/'D'/'A', or 'ALL' for arbitrage
    odds       DOUBLE,
    fair_prob  DOUBLE,
    edge       DOUBLE  NOT NULL,      -- value: fair_prob*odds-1; arbitrage: guaranteed return
    reference  VARCHAR NOT NULL,      -- which fair-price source was used
    PRIMARY KEY (alert_type, match_id, snapshot, bookmaker, outcome)  -- the dedupe key
);
"""


def connect(path: Path = DEFAULT_DB) -> duckdb.DuckDBPyConnection:
    """Open (or create) the database file and make sure the tables exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute(SCHEMA)
    return con


def count_rows(con: duckdb.DuckDBPyConnection, table: str) -> int:
    return con.execute(f"SELECT count(*) FROM {table}").fetchall()[0][0]


def ingest(con: duckdb.DuckDBPyConnection, long: pd.DataFrame) -> dict[str, int]:
    """Insert matches and odds from the long DataFrame; return new rows inserted per table.

    ON CONFLICT DO NOTHING means the first version of a row wins. If a source file were
    corrected later, we would need DO UPDATE (or versioned rows) instead; see README.
    """
    before = {t: count_rows(con, t) for t in ("matches", "odds_snapshots")}
    con.register("incoming", long)
    con.execute(
        """
        INSERT INTO matches
        SELECT DISTINCT match_id, season, CAST(date AS DATE), home, away, result
        FROM incoming
        ON CONFLICT DO NOTHING
        """
    )
    con.execute(
        """
        INSERT INTO odds_snapshots
        SELECT match_id, bookmaker, snapshot, odds_h, odds_d, odds_a
        FROM incoming
        ON CONFLICT DO NOTHING
        """
    )
    con.unregister("incoming")
    return {t: count_rows(con, t) - n for t, n in before.items()}


def save_alerts(con: duckdb.DuckDBPyConnection, alerts: pd.DataFrame) -> int:
    """Insert alerts, skipping ones already stored (same dedupe key); return new rows."""
    if alerts.empty:
        return 0
    before = count_rows(con, "alerts")
    con.register("new_alerts", alerts)
    con.execute(
        """
        INSERT INTO alerts
        SELECT alert_type, match_id, snapshot, bookmaker, outcome, odds, fair_prob, edge, reference
        FROM new_alerts
        ON CONFLICT DO NOTHING
        """
    )
    con.unregister("new_alerts")
    return count_rows(con, "alerts") - before
