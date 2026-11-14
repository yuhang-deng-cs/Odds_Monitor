"""Smoke test for the Streamlit dashboard (skipped if streamlit is not installed)."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

import download
from db import connect, ingest
from load import load_dir

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


def test_dashboard_builds_database_on_first_run(raw_dir, tmp_path, monkeypatch):
    """A fresh deploy has no database: the app downloads (faked here) and ingests once."""
    monkeypatch.setattr(download, "download_season", lambda season, out_dir: False)
    db_path = tmp_path / "fresh.duckdb"  # its raw/ folder is the raw_dir fixture
    monkeypatch.setenv("ODDS_DB", str(db_path))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception and not at.error
    assert db_path.exists() and at.metric[0].value == "3"


def test_dashboard_reports_failed_download(tmp_path, monkeypatch):
    def offline(season, out_dir):
        raise download.DownloadError("network error")

    monkeypatch.setattr(download, "download_season", offline)
    monkeypatch.setenv("ODDS_DB", str(tmp_path / "missing.duckdb"))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert "network error" in at.error[0].value and "python cli.py download" in at.error[0].value


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
