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
    assert [m.label for m in at.metric][:4] == [
        "Matches",
        "Bookmakers",
        "Value alerts",
        "Arbitrage alerts",
    ]
    assert at.metric[0].value == "3"

    at.slider(key="threshold").set_value(10.0).run()  # raise the alert threshold
    assert not at.exception

    at.segmented_control(key="lang").set_value("zh").run()  # switch to Chinese
    assert not at.exception
    assert [m.label for m in at.metric][:4] == ["比赛", "博彩公司", "价值提醒", "套利提醒"]
    assert at.metric[0].value == "3"  # numbers do not change with the language


def test_dashboard_without_database(tmp_path, monkeypatch):
    monkeypatch.setenv("ODDS_DB", str(tmp_path / "missing.duckdb"))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert "python cli.py ingest" in at.error[0].value


def test_odds_calculator_handles_any_market(raw_dir, tmp_path, monkeypatch):
    db_path = tmp_path / "app.duckdb"
    con = connect(db_path)
    ingest(con, load_dir(raw_dir))
    con.close()
    monkeypatch.setenv("ODDS_DB", str(db_path))

    at = AppTest.from_file(APP, default_timeout=60).run()
    labels = [m.label for m in at.metric]
    assert "Outcomes" in labels and at.metric[labels.index("Outcomes")].value == "10"

    at.text_input(key="calc_odds").set_value("2.0, 1.8").run()  # a two-way market
    labels = [m.label for m in at.metric]
    assert at.metric[labels.index("Overround (bookmaker margin)")].value == "5.56%"

    at.text_input(key="calc_odds").set_value("abc").run()
    assert not at.exception and at.warning
