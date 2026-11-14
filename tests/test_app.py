"""Smoke test for the Streamlit dashboard (skipped if streamlit is not installed)."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from db import connect, ingest  # noqa: E402
from load import load_dir  # noqa: E402

APP = str(Path(__file__).parents[1] / "app.py")


def test_dashboard_renders(raw_dir, tmp_path, monkeypatch):
    db_path = tmp_path / "app.duckdb"
    con = connect(db_path)
    ingest(con, load_dir(raw_dir))
    con.close()
    monkeypatch.setenv("ODDS_DB", str(db_path))

    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert [m.label for m in at.metric] == [
        "Matches",
        "Bookmakers",
        "Value alerts",
        "Arbitrage alerts",
    ]
    assert at.metric[0].value == "3"

    at.slider[0].set_value(10.0).run()  # raise the alert threshold
    assert not at.exception


def test_dashboard_without_database(tmp_path, monkeypatch):
    monkeypatch.setenv("ODDS_DB", str(tmp_path / "missing.duckdb"))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert "python cli.py ingest" in at.error[0].value
