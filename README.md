# Odds Monitor

**English** | [中文](README.zh-CN.md)

[![CI](https://github.com/yuhang-deng-cs/Odds_Monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/yuhang-deng-cs/Odds_Monitor/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.13-blue)
![DuckDB](https://img.shields.io/badge/storage-DuckDB-yellow)
![Streamlit](https://img.shields.io/badge/dashboard-Streamlit-red)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Bookmaker odds comparison, margin removal, discrepancy alerts, closing-line-value checks,
simulated sportsbook exposure and calibration, replayed on three seasons of historical Premier
League data.**

> ⚠️ **Prototype: historical replay only.** It analyses past odds published by
> football-data.co.uk. It is not connected to any live feed, places no bets and does no real
> trading. Built as a learning and interview project.

![HTML report preview](docs/report_preview.png)

## Key findings
Real numbers from the three seasons (details and caveats in [Results](#results-on-the-three-seasons)):
- **Margins range from 0.56% to 6.51%.** Average closing margin: Betfair Exchange 0.56%, Pinnacle 2.96%, Bet365 5.51%, Ladbrokes 6.51%.
- **Most "value" is one sharp book disagreeing.** Of 119 Pinnacle-graded alerts with an exchange price, only 21 still cleared 3% against Betfair Exchange. Requiring both to agree is the obvious fix: the 3 early ones all beat the close (CLV +4.9%), but 21 bets prove nothing about profit yet (−45%, range −89% … +13%).
- **Closing-odds alerts lost money:** −43% per unit staked (95% range −70% … −6%). Early alerts beat the close 60% of the time vs 20% for a typical early price, but on only 40 bets.
- **As a simulated sportsbook** on Bet365's closing prices, expected profit was 5.2% of stakes (close to its 5.51% margin), 4.5% on the real results, and 75 of 1,140 matches breached a 10,000-unit exposure limit.
- **Arbitrage is rare and thin:** 34 cases, median locked-in return 0.39%.

## What it does
| Question | How it answers it |
|---|---|
| How much margin does each bookmaker charge? | Overround per bookmaker and snapshot, ranked with a SQL window function |
| What is the *fair* probability of each outcome? | Removes the margin ("de-vig": proportional, power or Shin) from a sharp reference: **Pinnacle → Betfair Exchange → bookmaker average** |
| Which prices are out of line? | Flags a bookmaker when `fair_prob × odds − 1` exceeds a threshold (default 3%) |
| Is there a cross-book arbitrage? | Best price per outcome across bookmakers; flags when `Σ 1/best_odds < 1` |
| Where did the market move? | Early → closing price change per match/bookmaker/outcome using `LAG()` |
| Did the alerts hold up? | **Closing line value (CLV)** of early alerts vs a baseline of every early price, a flat-stake backtest on real results with a match-level bootstrap interval, and a second-opinion check: each alert is marked *confirmed* when Betfair Exchange agrees, and confirmed alerts are backtested separately |
| If we were the bookmaker, what could one match cost us? | **Simulated** bets at one bookmaker's real closing prices: per-outcome liability, worst case per match, exposure alerts above a limit, and the cost of sharp money on mispriced prices |
| Are the odds a good forecast? | Brier score, log loss and a reliability chart: proportional vs power vs Shin de-vig, early vs closing odds |

There are three ways to look at the results:
1. **CLI:** commands that print tables (for analysts).
2. **HTML report:** one self-contained page with charts and plain-language explanations. It opens in any browser and can be emailed (for non-technical readers).
3. **Streamlit dashboard:** an interactive version with season/bookmaker filters, an alert-threshold slider, an exposure-limit input, hover tooltips and an odds calculator for any market size (e.g. a horse race).

Both the report and the dashboard have an **English / 中文 language switch** (English by default).

## Quick start
Requires Python 3.11+ (developed on 3.13).
```bash
python -m venv .venv
.venv\Scripts\activate             # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt

python cli.py download             # 3 Premier League seasons -> data/raw/
python cli.py ingest               # load into data/odds.duckdb
python cli.py report               # -> reports/report.html, open it in a browser
```

> **Windows PowerShell:** if activation fails with "running scripts is disabled", run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or skip activation and call the
> environment directly: `.\.venv\Scripts\python.exe cli.py report`. A
> `ModuleNotFoundError: No module named 'duckdb'` means the command ran outside the venv.

### CLI commands
```bash
python cli.py download                  # fetch the season CSVs (skips files already there)
python cli.py ingest                    # validate CSVs and load into DuckDB (idempotent: re-run inserts 0 rows)
python cli.py margins                   # average / median / min margin per bookmaker, ranked
python cli.py moves --limit 20 --bookmaker Pinnacle    # largest early -> closing moves
python cli.py alerts --threshold 0.03 --method power   # -> reports/alerts.csv (incl. 'confirmed') + DuckDB
python cli.py clv --method shin          # any command with --method takes proportional / power / shin
python cli.py clv                       # closing line value + backtest of the value alerts
python cli.py exposure --book Bet365 --limit 10000     # SIMULATED liability per match
python cli.py devig 3.0 4.5 6.0 8.0 10.0 13.0          # margin + fair prices for ANY market (e.g. a race)
python cli.py calibrate                 # -> reports/calibration.png, calibration_summary.csv, reliability.csv
python cli.py report                    # -> reports/report.html (non-technical summary)
```

### Interactive dashboard
```bash
streamlit run app.py                    # opens http://localhost:8501
```
On a fresh checkout (or a fresh cloud deploy) the dashboard downloads the data and builds the
database itself on first run, so `streamlit run app.py` is all it needs. It reads the DuckDB file read-only. Untick Pinnacle in the sidebar to see how the
alerts change when the sharp reference is missing.

## Data
- **Source:** [football-data.co.uk](https://football-data.co.uk/englandm.php), Premier League (`E0`),
  seasons 2023/24, 2024/25 and 2025/26: **1,140 matches**. Data files are not committed; the
  download script recreates them.
- `python cli.py download` (`download.py`) fetches `https://football-data.co.uk/mmz4281/<season>/E0.csv` (pattern checked
  against the index page). It skips files that exist, pauses between requests, reports the HTTP status and
  fails clearly on errors.
- **Bookmaker codes** follow the site's `notes.txt` and are mapped explicitly in `load.py`. Column names
  are ambiguous: `BFD` is Betfair *draw* but `BFDH` is *Betfred* home, and `VC`/`BV` are both BetVictor.
  `Max`/`Avg` are market aggregates, not bookmakers, so they are excluded.
- **Snapshots:** non-`C` columns are football-data's "pre-closing" odds, labelled `open`/"early" here
  (not a true market open); `C` columns are closing odds.

## Project structure
```
odds.py            implied prob, overround, proportional / power / Shin de-vig (bisection, no scipy)
load.py            read CSVs, validate (drop missing / odds <= 1, log counts), wide -> long
db.py              DuckDB schema (matches, odds_snapshots, alerts), idempotent ingest
queries.sql/.py    named SQL: margins (RANK), moves (LAG), odds joined with matches
detector.py        value edges vs sharp reference, cross-book arbitrage, dedupe
clv.py             closing line value, flat-stake backtest, match-level bootstrap, exchange check
liability.py       simulated sportsbook book: per-outcome liability, worst case, exposure alerts
i18n.py            English / Chinese labels shared by report and dashboard
calibration.py     Brier, log loss, reliability table and plot
report.py          self-contained HTML report (charts embedded as PNG)
download.py        polite, idempotent downloader (validates each file before saving)
app.py             Streamlit dashboard (builds the database on first run)
cli.py             argparse entry point
tests/             pytest suite (62 tests, synthetic data, no network)
.github/workflows/ CI: ruff lint + format check and pytest on Python 3.11 and 3.13
```

## Results on the three seasons
From the actual run (`python cli.py ...`):
- **Ingest:** 15,054 odds rows kept, 1,666 dropped for missing prices (none had odds ≤ 1).
- **Average closing margin:** Betfair Exchange 0.56% · Pinnacle 2.96% · 1xBet 3.03% · Bet365 5.51% · Ladbrokes 6.51%.
- **Alerts (3% threshold, power de-vig):** 153 value alerts across 111 matches (113 on closing odds, 40 on early odds),
  and 34 arbitrages with a median locked-in return of just 0.39%.
- **Calibration (same 1,140 matches):**

  | odds | method | Brier | log loss |
  |---|---|---|---|
  | early | proportional | 0.57411 | 0.96520 |
  | early | power | 0.57400 | 0.96463 |
  | early | Shin | 0.57399 | 0.96471 |
  | closing | proportional | 0.57036 | 0.96044 |
  | closing | power | **0.57016** | **0.95986** |
  | closing | Shin | 0.57020 | 0.96000 |
  | baseline | always predict base rates | 0.64907 | 1.07225 |

  Closing beats early, and power and Shin both beat proportional while being practically tied with each other.
  The gaps are small and **not tested for significance**.
- **Did the alerts hold up?** (`python cli.py clv`)

  | group | n | bets with CLV | avg CLV | beat the close | return per unit | 95% range |
  |---|---|---|---|---|---|---|
  | early value alerts | 40 | 40 | −0.6% | 60% | +15.4% | −54% … +99% |
  | closing value alerts | 113 | 0 | – | – | −43.0% | −70% … −6% |
  | exchange-confirmed alerts (3 early + 18 closing) | 21 | 3 | +4.9% | 100% | −44.7% | −89% … +13% |
  | all early prices (baseline) | 20,421 | 20,421 | −6.2% | 20% | −6.4% | −9% … −4% |

  Early alerts beat a typical early price by a wide margin (60% vs 20% beat the close) but on average
  not the close itself; their backtest is far too small to separate skill from luck. Closing alerts
  **lost money even allowing for luck**. The second-opinion check explains why: of 119 alerts graded
  against Pinnacle that also had an exchange price, only **21** still cleared 3% against Betfair Exchange,
  so most alerts are Pinnacle alone disagreeing with the market. The *exchange-confirmed* row backtests just
  those 21 (3 early, 18 closing): the early ones all beat the close, but 21 bets cannot show whether the
  two-source rule makes money. Intervals resample whole matches, because one odd price can trigger several
  alerts at once.
- **Simulated exposure** (`python cli.py exposure`, Bet365 closing prices as "ours", 10,000 recreational
  units per match, +2,000 sharp stake where our price beats fair by > 3%, limit 10,000):
  expected profit 591,402 on 11,422,000 staked (5.2%, close to Bet365's 5.51% margin), 517,448 on the real
  results; **75 of 1,140 matches** breached the limit. Sharp money hit 11 matches with an expected cost of
  1,525; on the real results the book won 22,000 on them, which with 11 bets is luck. *Stakes are simulated;
  prices and results are real.*

## Design choices
- **Power vs proportional de-vig:** proportional removes margin equally in relative terms, but bookmakers load
  more margin onto longshots (the favourite–longshot bias). Power (`p = q^k`) shrinks small probabilities more.
  **Shin** models a share `z` of insider money and solves for it; on two outcomes it reduces to taking the same
  absolute amount off each side (a test checks this). On this data power and Shin are practically tied.
- **Idempotency:** natural primary keys plus `INSERT … ON CONFLICT DO NOTHING`. Alerts use the key
  `(type, match, snapshot, bookmaker, outcome)`, which also deduplicates them.
- **Betfair Exchange** is used as a fair-price reference but never as an alert target, because its quoted prices
  are before commission and would overstate edges.
- **Moves are measured in de-vigged probability**, so a bookmaker simply widening its margin does not look like a move.
- **Two points of view on one alert.** For a bettor a value alert is an opportunity; for a sportsbook it is one
  of *our* prices that sharp customers will target. The exposure simulation makes that link explicit: sharp
  stakes arrive exactly where the detector fires.
- **CLV before P&L.** Realised profit on a few hundred bets is mostly noise; closing line value is the
  standard faster signal of whether a price was right. Both are reported, with honest intervals.
- **Not tied to football.** The de-vig and margin functions take any number of outcomes, so the same code
  prices a 10-runner horse race: try `python cli.py devig ...` or the dashboard's *Odds calculator* tab
  (pre-filled with an illustrative race, not real data; tested in `tests/test_odds.py`).
  Racing would add place markets, scratchings (Rule 4 deductions) and each-way terms on top.

## Known limitations
- **Two snapshots per match only.** "Moves" is a rough proxy for steam, not tick data.
- **Snapshot times differ between bookmakers**, so some arbitrages and edges are timing artefacts or stale quotes.
- **The reference can be wrong.** Leeds v Newcastle (30/08/2025): Pinnacle's closing home price was 3.16 while
  Betfair Exchange and seven bookmakers were at 3.25–3.90. That single price produced six value alerts and an arbitrage.
- **Pinnacle is missing after 08/01/2026.** Of those matches, 150 early snapshots use Betfair Exchange and 20 use the bookmaker
  average (which includes the book being tested, shrinking its edge).
- An edge against the reference is not proven profit: no stake limits, account restrictions or costs are modelled.
- **The exposure numbers are a simulation.** The data has no bets; stake sizes, noise level and the sharp rule
  are assumptions, and only the prices and results are real.
- The CLV and backtest samples are small (40 early alerts, 113 closing alerts), so intervals are wide.
- `ON CONFLICT DO NOTHING` keeps the first version of a row; corrected source data would need `DO UPDATE` or versioning.
- Reliability bins above 80% hold few outcomes, so those points are noisy.

## What I'd change for production
- **Live feed ingestion:** a streaming consumer writing timestamped ticks instead of CSV batches.
- **Out-of-order and duplicate events:** upserts keyed on (event, book, market, source timestamp) with a watermark,
  so late ticks never overwrite newer prices.
- **Stale-feed detection:** track last update per book and market; suppress alerts on prices older than N seconds.
- **Reference sanity check:** route only alerts that two sharp sources agree on (the `confirmed` flag already
  computes this) and keep collecting them until the sample is large enough to judge.
- **Rate limits:** a token bucket per provider, exponential backoff with jitter, caching.
- **Alert deduplication:** keep the dedupe key, but re-alert only on a material edge change; add cooldowns and routing.
- **Monitoring the monitor:** feed lag, rows per minute, alert rate and job health, and alarms when the pipeline goes quiet.

## Testing
```bash
pytest          # 62 tests: worked examples, de-vig sums (incl. a 10-runner race), loader validation,
                # Shin de-vig, idempotent ingest, SQL window queries, arbitrage/mispricing detection,
                # two-source confirmation, CLV and
                # bootstrap, liability maths, calibration, downloader, CLI, dashboard (incl.
                # language switch and first-run database build)
ruff check . && ruff format --check .
```
The same checks run on every push via GitHub Actions.

## Licence and credits
Code: [MIT](LICENSE). Odds and results data: [football-data.co.uk](https://www.football-data.co.uk/); it is not
redistributed here, and its use is subject to their terms.
