# Odds Monitor: historical-replay prototype

> **Prototype for learning and interview discussion. It replays historical odds. It is not a
> live system, places no bets, and does no real trading.**

A small Python CLI that loads historical Premier League 1X2 odds, removes the bookmaker margin
("de-vig"), compares bookmakers against a sharp reference, flags pricing discrepancies and
arbitrage, checks calibration, and stores everything in DuckDB.

## Data
- **Source:** [football-data.co.uk](https://football-data.co.uk/englandm.php), Premier League (`E0`),
  seasons 2023/24, 2024/25, 2025/26: 1,140 matches.
- `scripts/download_data.py` fetches `https://football-data.co.uk/mmz4281/<season>/E0.csv` (URL pattern
  checked against the index page) into `data/raw/E0_<season>.csv`. It skips files that already exist,
  pauses between requests and fails clearly on errors.
- Bookmaker codes come from the site's `notes.txt` and are mapped explicitly in `load.py`
  (e.g. `BFD` = Betfair *draw* but `BFDH` = *Betfred* home; `VC` and `BV` are both BetVictor).
  `Max`/`Avg` are market aggregates, so they are excluded.
- **Snapshots:** the non-`C` columns are football-data's "pre-closing" odds, labelled `open` here
  (they are *not* a true market open). `C` columns are closing odds.

## Run it
```bash
python -m venv .venv && .venv/Scripts/activate      # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/download_data.py                     # -> data/raw/
python cli.py ingest      # load + validate CSVs into data/odds.duckdb (idempotent: re-run inserts 0 rows)
python cli.py margins     # average/median/min margin per bookmaker and snapshot, ranked
python cli.py moves --limit 20 [--bookmaker Pinnacle]   # largest open->close moves (LAG)
python cli.py alerts [--threshold 0.03] [--method power|proportional]  # -> reports/alerts.csv + DuckDB
python cli.py calibrate   # -> reports/calibration.png, calibration_summary.csv, reliability.csv
pytest && ruff check .
```

## How it works
| Module | What it does |
|---|---|
| `odds.py` | implied probability, overround, proportional and power de-vig (bisection for `k`) |
| `load.py` | reads CSVs, drops bad matches/odds (missing or ≤ 1) and logs the counts; wide → long (one row per match × bookmaker × snapshot) |
| `db.py` | DuckDB tables `matches`, `odds_snapshots`, `alerts`; natural primary keys + `ON CONFLICT DO NOTHING` |
| `queries.sql` | margins (`RANK()` window), open→close moves (`LAG()` over snapshots) |
| `detector.py` | fair probs from **Pinnacle → Betfair Exchange → bookmaker average**; value edge `fair_prob × odds − 1 > threshold`; arbitrage when `Σ 1/best_odds < 1` |
| `calibration.py` | Brier score and log loss for {open, close} × {proportional, power} on the same matches, plus a base-rate baseline, reliability table and plot |

## Results on the three seasons (from the actual run)
- **Ingest:** 15,054 odds rows kept, 1,666 dropped (missing prices; none had odds ≤ 1).
- **Margins (closing, average):** Betfair Exchange 0.56%, Pinnacle 2.96%, 1xBet 3.03%, Bet365 5.51%, Ladbrokes 6.51%.
- **Alerts (3%, power):** 187 total: 153 value alerts (113 at close, 40 at open) across 111 matches, and 34 arbitrages
  (median guaranteed return 0.39%, max 3.38%).
- **Calibration (1,140 matches):** close beats open, and power beats proportional, but only slightly:
  log loss 0.96520 (open/proportional) → 0.95986 (close/power), against 1.07225 for the base-rate baseline.
  These differences are small and **not tested for significance**.

## Assumptions and known limitations
- **Two snapshots only:** "moves" is a proxy for steam, not tick data; there is no timing within the window.
- **Snapshot times differ between books**, so some "arbitrages" and edges are timing artefacts or stale quotes.
- **The reference can be wrong.** Leeds v Newcastle (30/08/2025): Pinnacle's closing home price was 3.16 while
  Betfair Exchange and seven bookmakers were at 3.25–3.90. That single price produced six "value" alerts and an arb.
- Pinnacle is missing after 08/01/2026. 150 open snapshots use Betfair Exchange (prices before commission,
  so it is never an alert *target*) and 20 use the bookmaker average (which includes the book being tested).
- An edge against the closing line is not proven profit: no stake limits, account restrictions or settlement costs.
- `ON CONFLICT DO NOTHING` keeps the first version of a row; corrected source data would need `DO UPDATE` or versioned rows.
- Reliability bins above 0.8 hold few outcomes (50 and 10 at open), so those points are noisy.

## What I'd change for production
- **Live feed ingestion:** a streaming consumer (e.g. a bookmaker API or odds aggregator) writing timestamped ticks, not CSVs.
- **Out-of-order and duplicate events:** idempotent upserts keyed on (event, book, market, source timestamp), with
  a watermark so late ticks never overwrite newer prices.
- **Stale-feed detection:** track last-update time per book/market and suppress alerts on prices older than N seconds.
- **Reference sanity check:** require two sharp sources to agree (e.g. Pinnacle vs exchange) before alerting.
- **Rate limits:** a token bucket per provider, backoff with jitter, and caching.
- **Alert deduplication:** keep the dedupe key, but re-alert only when the edge changes materially; add a cooldown and route alerts to a queue/chat.
- **Monitoring the monitor:** metrics for feed lag, rows per minute, alert rate and job health, and alerting when
  the pipeline goes quiet. A monitor that silently stops is worse than none.
