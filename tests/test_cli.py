import cli


def _run(*argv: str) -> None:
    args = cli.build_parser().parse_args(list(argv))
    args.func(args)


def test_all_commands_run_end_to_end(raw_dir, tmp_path, capsys):
    db_args = ["--db", str(tmp_path / "cli.duckdb")]
    _run(*db_args, "ingest", "--raw-dir", str(raw_dir))
    _run(*db_args, "ingest", "--raw-dir", str(raw_dir))
    assert "inserted: {'matches': 0, 'odds_snapshots': 0}" in capsys.readouterr().out

    _run(*db_args, "margins")
    _run(*db_args, "moves", "--limit", "5")
    _run(*db_args, "alerts", "--out", str(tmp_path / "alerts.csv"))
    _run(*db_args, "calibrate", "--out-dir", str(tmp_path / "reports"))
    _run(*db_args, "clv")
    _run(*db_args, "exposure", "--book", "Bet365")
    _run("devig", "2.0", "1.8")
    out = capsys.readouterr().out
    assert "Pinnacle" in out and "alerts (threshold 3.0%" in out and "base rates" in out
    assert "all early prices (baseline)" in out and "second opinion" in out
    assert "SIMULATED bets at Bet365" in out
    assert "2 outcomes, overround 5.56%" in out
    assert (tmp_path / "alerts.csv").exists()
    assert (tmp_path / "reports" / "calibration.png").exists()


def test_report_command_writes_html(raw_dir, tmp_path, capsys):
    db_args = ["--db", str(tmp_path / "cli.duckdb")]
    _run(*db_args, "ingest", "--raw-dir", str(raw_dir))
    out = tmp_path / "report.html"
    _run(*db_args, "report", "--out", str(out))
    page = out.read_text(encoding="utf-8")
    assert "Historical replay" in page
    assert "Which bookmakers charge the most?" in page
    assert "哪家博彩公司抽水最多？" in page  # Chinese text is in the page, hidden by CSS
    assert '<html lang="en">' in page and 'id="lang"' in page  # English by default + switch
    assert "Did the alerts hold up?" in page and "Simulated: our exposure" in page
    assert page.count("data:image/png;base64,") == 3  # margins, alerts, calibration
