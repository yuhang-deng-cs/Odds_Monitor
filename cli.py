"""Command-line entry point: python cli.py <command>; see `python cli.py --help`.

Historical replay prototype: every command works on stored historical odds, nothing live.
"""

import argparse
import logging
from pathlib import Path

import pandas as pd

import calibration
import clv
import db
import liability
import queries
import report
from detector import DEVIG, detect
from load import load_dir

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)


def cmd_ingest(args: argparse.Namespace) -> None:
    con = db.connect(args.db)
    inserted = db.ingest(con, load_dir(args.raw_dir))
    total = {t: db.count_rows(con, t) for t in inserted}
    print(f"inserted: {inserted} | totals now: {total}")


def cmd_margins(args: argparse.Namespace) -> None:
    print(queries.margins(db.connect(args.db)).to_string(index=False))


def cmd_moves(args: argparse.Namespace) -> None:
    df = queries.moves(db.connect(args.db), limit=args.limit, bookmaker=args.bookmaker)
    print("open->close moves (2 snapshots only: a proxy for steam moves, not tick data)")
    print(df.to_string(index=False))


def cmd_alerts(args: argparse.Namespace) -> None:
    con = db.connect(args.db)
    alerts = detect(queries.odds_with_matches(con), threshold=args.threshold, method=args.method)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    alerts.to_csv(args.out, index=False)
    new = db.save_alerts(con, alerts)

    print(f"{len(alerts)} alerts (threshold {args.threshold:.1%}, {args.method} de-vig)")
    print(alerts.groupby(["alert_type", "snapshot", "reference"]).size().to_string())
    print(f"\nwritten to {args.out}; {new} new rows stored in DuckDB (rest already seen)")
    print(f"\ntop {args.top} by edge:")
    shown = alerts.head(args.top).drop(columns=["match_id"])
    print(shown.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


def cmd_clv(args: argparse.Namespace) -> None:
    odds = queries.odds_with_matches(db.connect(args.db))
    alerts = detect(odds, threshold=args.threshold, method=args.method)
    summary, _ = clv.performance(odds, alerts, args.method)
    checked, confirmed = clv.exchange_check(odds, alerts, args.threshold, args.method)
    print("Closing line value and flat 1-unit backtest of value alerts (real results)")
    print("roi range: 95% bootstrap, resampling whole matches")
    print(summary.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print(
        f"\nsecond opinion: {confirmed} of {checked} Pinnacle-graded alerts also clear the "
        "threshold against Betfair Exchange"
    )


def cmd_exposure(args: argparse.Namespace) -> None:
    odds = queries.odds_with_matches(db.connect(args.db))
    sim = liability.simulate(odds, book=args.book, limit=args.limit, threshold=args.threshold,
                             method=args.method, seed=args.seed)  # fmt: skip
    print(f"SIMULATED bets at {args.book}'s real closing prices (stakes are made up)")
    print(liability.summarise(sim).to_string(index=False, float_format=lambda x: f"{x:,.0f}"))
    cols = ["match_date", "home", "away", "sharp_on", "stake_h", "stake_d", "stake_a",
            "worst_case", "result", "actual_pnl"]  # fmt: skip
    print(f"\n{args.top} largest worst-case losses:")
    worst = sim.nsmallest(args.top, "worst_case")[cols]
    print(worst.to_string(index=False, float_format=lambda x: f"{x:,.0f}"))


def cmd_calibrate(args: argparse.Namespace) -> None:
    odds = queries.odds_with_matches(db.connect(args.db))
    summary, reliability = calibration.run(odds, args.out_dir)
    print("Calibration of de-vigged reference probabilities (lower is better)")
    print(summary.to_string(index=False, float_format=lambda x: f"{x:.5f}"))
    print("\nReliability table (all outcomes pooled):")
    print(reliability.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print(
        f"\nwritten to {args.out_dir}/ (calibration.png, calibration_summary.csv, reliability.csv)"
    )


def cmd_report(args: argparse.Namespace) -> None:
    out = report.write_report(
        db.connect(args.db), args.out, threshold=args.threshold, method=args.method
    )
    print(f"report written to {out.resolve()} (open it in any browser)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Odds monitor (historical replay prototype)")
    parser.add_argument("--db", type=Path, default=db.DEFAULT_DB, help="DuckDB file")
    parser.add_argument("-v", "--verbose", action="store_true", help="show loader logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="load CSVs from data/raw into DuckDB (idempotent)")
    p.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("margins", help="average margin per bookmaker")
    p.set_defaults(func=cmd_margins)

    p = sub.add_parser("moves", help="largest open->close price moves")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--bookmaker", default=None, help='e.g. "Bet365"')
    p.set_defaults(func=cmd_moves)

    p = sub.add_parser("alerts", help="value edges vs sharp reference, and arbitrage")
    p.add_argument("--threshold", type=float, default=0.03, help="min edge, 0.03 = 3%%")
    p.add_argument("--method", choices=sorted(DEVIG), default="power")
    p.add_argument("--out", type=Path, default=Path("reports/alerts.csv"))
    p.add_argument("--top", type=int, default=15, help="how many alerts to print")
    p.set_defaults(func=cmd_alerts)

    p = sub.add_parser("clv", help="closing line value and backtest of value alerts")
    p.add_argument("--threshold", type=float, default=0.03, help="min edge, 0.03 = 3%%")
    p.add_argument("--method", choices=sorted(DEVIG), default="power")
    p.set_defaults(func=cmd_clv)

    p = sub.add_parser("exposure", help="SIMULATED bookmaker liability per match")
    p.add_argument("--book", default=liability.DEFAULTS["book"], help="whose prices are 'ours'")
    p.add_argument("--limit", type=float, default=liability.DEFAULTS["limit"])
    p.add_argument("--threshold", type=float, default=0.03, help="sharp bettors' min edge")
    p.add_argument("--method", choices=sorted(DEVIG), default="power")
    p.add_argument("--seed", type=int, default=liability.DEFAULTS["seed"])
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(func=cmd_exposure)

    p = sub.add_parser("calibrate", help="Brier/log loss, reliability table and plot")
    p.add_argument("--out-dir", type=Path, default=Path("reports"))
    p.set_defaults(func=cmd_calibrate)

    p = sub.add_parser("report", help="one-page HTML report for non-technical readers")
    p.add_argument("--threshold", type=float, default=0.03, help="min edge, 0.03 = 3%%")
    p.add_argument("--method", choices=sorted(DEVIG), default="power")
    p.add_argument("--out", type=Path, default=Path("reports/report.html"))
    p.set_defaults(func=cmd_report)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose or args.command == "ingest" else logging.WARNING,
        format="%(levelname)s %(message)s",
    )
    args.func(args)


if __name__ == "__main__":
    main()
