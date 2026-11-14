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
    out = capsys.readouterr().out
    assert "Pinnacle" in out and "alerts (threshold 3.0%" in out and "base rates" in out
    assert (tmp_path / "alerts.csv").exists()
    assert (tmp_path / "reports" / "calibration.png").exists()
