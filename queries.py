"""Load named SQL queries from queries.sql and run them against DuckDB."""

import re
from pathlib import Path

import duckdb
import pandas as pd

SQL_FILE = Path(__file__).with_name("queries.sql")


def load_queries(path: Path = SQL_FILE) -> dict[str, str]:
    """Split queries.sql into {name: sql} using '-- name: <name>' markers."""
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"^-- name: (\w+)\s*$", text, flags=re.MULTILINE)
    # blocks = [preamble, name1, sql1, name2, sql2, ...]
    return {
        name: sql.strip().rstrip(";") for name, sql in zip(blocks[1::2], blocks[2::2], strict=True)
    }


def run(con: duckdb.DuckDBPyConnection, name: str, **params: object) -> pd.DataFrame:
    """Run a named query with $-style parameters and return a DataFrame."""
    sql = load_queries()[name]
    return con.execute(sql, params or None).df()


def margins(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return run(con, "margins")


def moves(
    con: duckdb.DuckDBPyConnection, limit: int = 20, bookmaker: str | None = None
) -> pd.DataFrame:
    return run(con, "moves", limit=limit, bookmaker=bookmaker)


def odds_with_matches(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return run(con, "odds_with_matches")
