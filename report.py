"""Build one self-contained HTML report for non-technical readers.

Everything (charts as embedded PNGs, tables, CSS) lives in a single file that opens in any
browser with no server and no internet. The numbers come from the same functions the CLI uses.
"""

import base64
import html
import io
from datetime import date
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import pandas as pd

import calibration
import queries
from detector import detect

OUTCOME_NAMES = {"H": "Home win", "D": "Draw", "A": "Away win", "ALL": "All outcomes"}
INK, INK_2, GRID, SURFACE, BLUE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#2a78d6"


def gather(
    con: duckdb.DuckDBPyConnection, threshold: float = 0.03, method: str = "power"
) -> dict[str, object]:
    """Collect every table the report (and the dashboard) shows."""
    odds = queries.odds_with_matches(con)
    summary, preds = calibration.evaluate(odds)
    return {
        "odds": odds,
        "margins": queries.margins(con),
        "moves": queries.moves(con, limit=10),
        "alerts": detect(odds, threshold=threshold, method=method),
        "calibration": summary,
        "reliability": {k: calibration.reliability_table(preds[k]) for k in ("open/power", "close/power")},
        "threshold": threshold,
        "method": method,
    }  # fmt: skip


# ---------- charts (matplotlib -> PNG -> base64 so the HTML is a single file) ----------


def _style(ax: plt.Axes) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=INK_2, length=0)


def hbar_figure(labels: list[str], values: list[float], xlabel: str, fmt: str) -> plt.Figure:
    """Horizontal bar chart, largest at the bottom, value printed at each bar end."""
    fig, ax = plt.subplots(figsize=(7, 0.38 * len(labels) + 0.9), facecolor=SURFACE)
    _style(ax)
    ax.barh(labels, values, color=BLUE, height=0.6)
    for y, v in enumerate(values):
        ax.text(v, y, " " + fmt.format(v), va="center", color=INK, fontsize=9)
    ax.set_xlabel(xlabel, color=INK_2)
    ax.set_xlim(0, max(values) * 1.15 if values else 1)
    fig.tight_layout()
    return fig


def margin_figure(margins: pd.DataFrame, snapshot: str = "close") -> plt.Figure:
    m = margins[margins["snapshot"] == snapshot].sort_values("avg_margin_pct", ascending=False)
    return hbar_figure(
        m["bookmaker"].tolist(), m["avg_margin_pct"].tolist(), "Average margin (%)", "{:.2f}%"
    )


def alerts_by_book_figure(alerts: pd.DataFrame) -> plt.Figure:
    counts = alerts[alerts["alert_type"] == "value"]["bookmaker"].value_counts(ascending=True)
    return hbar_figure(counts.index.tolist(), counts.tolist(), "Number of value alerts", "{:.0f}")


def _png(fig: plt.Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ---------- friendly tables ----------


def friendly_moves(moves: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Date": pd.to_datetime(moves["match_date"]).dt.strftime("%d %b %Y"),
        "Match": moves["home"] + " v " + moves["away"],
        "Bookmaker": moves["bookmaker"],
        "Outcome": moves["outcome"].map(OUTCOME_NAMES),
        "Early odds": moves["open_odds"].map("{:.2f}".format),
        "Closing odds": moves["close_odds"].map("{:.2f}".format),
        "Change in chance": moves["prob_move_pp"].map("{:+.1f} pts".format),
        "Final result": moves["result"].map(OUTCOME_NAMES),
    })  # fmt: skip


def friendly_alerts(alerts: pd.DataFrame, alert_type: str) -> pd.DataFrame:
    a = alerts[alerts["alert_type"] == alert_type]
    out = pd.DataFrame({
        "Date": pd.to_datetime(a["match_date"]).dt.strftime("%d %b %Y"),
        "Match": a["home"] + " v " + a["away"],
        "Odds taken": a["snapshot"].map({"open": "Early", "close": "Closing"}),
    })  # fmt: skip
    if alert_type == "value":
        out["Bookmaker"] = a["bookmaker"]
        out["Outcome"] = a["outcome"].map(OUTCOME_NAMES)
        out["Odds offered"] = a["odds"].map("{:.2f}".format)
        out["Fair chance"] = a["fair_prob"].map("{:.1%}".format)
        out["Expected edge"] = a["edge"].map("{:.1%}".format)
        out["Compared with"] = a["reference"].str.replace("_", " ")
    else:
        out["Best prices used"] = a["bookmaker"].str.replace("|", ", ").str.replace(":", " ")
        out["Locked-in return"] = a["edge"].map("{:.2%}".format)
    return out


def _table(df: pd.DataFrame) -> str:
    return '<div class="scroll">' + df.to_html(index=False, border=0, escape=True) + "</div>"


# ---------- page ----------


def build_html(data: dict[str, object]) -> str:
    """Render the report as one HTML string."""
    odds: pd.DataFrame = data["odds"]
    margins: pd.DataFrame = data["margins"]
    moves: pd.DataFrame = data["moves"]
    alerts: pd.DataFrame = data["alerts"]
    calib: pd.DataFrame = data["calibration"]
    rel: dict[str, pd.DataFrame] = data["reliability"]

    value = alerts[alerts["alert_type"] == "value"]
    arbs = alerts[alerts["alert_type"] == "arbitrage"]
    seasons = sorted(odds["season"].unique())
    close_m = margins[margins["snapshot"] == "close"].sort_values("avg_margin_pct")
    books = close_m[close_m["bookmaker"] != "Betfair Exchange"]  # exchanges are not bookmakers
    cheapest, dearest = books.iloc[0], books.iloc[-1]
    top_move = moves.iloc[0]
    quarter = rel["close/power"].query("bin == '(0.2, 0.3]'").iloc[0]
    best = calib[calib["method"] != "base rates"].sort_values("log_loss").iloc[0]
    base = calib[calib["method"] == "base rates"].iloc[0]
    season_txt = ", ".join(f"20{s[:2]}/{s[2:]}" for s in seasons)
    # Wording is derived from the numbers, never assumed.
    gap = abs(quarter.observed_freq - quarter.mean_predicted)
    verdict = "They do" if gap < 0.03 else "Not exactly"
    ll = calib.set_index(["snapshot", "method"])["log_loss"]
    close_better = ll[("close", "power")] < ll[("open", "power")]
    timing = (
        "Closing odds were more accurate than early odds, as expected"
        if close_better
        else "Surprisingly, early odds were at least as accurate as closing odds"
    )

    tiles = [
        (f"{odds['match_id'].nunique():,}", "matches analysed"),
        (str(odds["bookmaker"].nunique()), "bookmakers compared"),
        (f"{len(value):,}", "value alerts"),
        (f"{len(arbs):,}", "arbitrage alerts"),
    ]
    tiles_html = "".join(
        f'<div class="tile"><div class="num">{n}</div><div class="lbl">{lbl}</div></div>'
        for n, lbl in tiles
    )
    e = html.escape
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Odds Monitor Report</title>
<style>
:root {{ --bg:{SURFACE}; --ink:{INK}; --ink2:{INK_2}; --line:{GRID}; --accent:{BLUE};
        --note:#fff6e0; color-scheme: light; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
       font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
main {{ max-width:980px; margin:0 auto; padding:24px 16px 64px; }}
h1 {{ font-size:1.8rem; margin:0 0 4px; }} h2 {{ font-size:1.3rem; margin:40px 0 6px; }}
.sub {{ color:var(--ink2); margin:0 0 20px; }}
.banner {{ background:var(--note); border-radius:8px; padding:10px 14px; font-size:.95rem; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin:20px 0; }}
.tile {{ border:1px solid var(--line); border-radius:10px; padding:14px 16px; background:#fff; }}
.num {{ font-size:1.9rem; font-weight:650; }} .lbl {{ color:var(--ink2); font-size:.9rem; }}
.explain {{ color:var(--ink2); max-width:70ch; }}
.key {{ font-weight:600; color:var(--ink); }}
img {{ max-width:100%; height:auto; display:block; margin:12px 0; }}
img.narrow {{ max-width:min(520px, 100%); }}
.scroll {{ overflow-x:auto; margin:12px 0; }}
table {{ border-collapse:collapse; font-size:.88rem; white-space:nowrap; }}
th {{ text-align:left; color:var(--ink2); font-weight:600; border-bottom:2px solid var(--line); padding:6px 10px; }}
td {{ border-bottom:1px solid var(--line); padding:6px 10px; }}
footer {{ margin-top:48px; color:var(--ink2); font-size:.85rem; }}
</style></head>
<body><main>
<h1>Odds Monitor</h1>
<p class="sub">Premier League {e(season_txt)} &middot; built {date.today():%d %b %Y}</p>
<p class="banner"><strong>Historical replay.</strong> This looks back at past odds published by
football-data.co.uk. It is a prototype: nothing here is live and no bets were placed.</p>
<div class="tiles">{tiles_html}</div>

<h2>Which bookmakers charge the most?</h2>
<p class="explain">Every bookmaker builds a profit margin into its odds. A lower margin means
better prices for customers. At closing time, <span class="key">{e(cheapest.bookmaker)}</span> had the
lowest average margin ({cheapest.avg_margin_pct:.2f}%) and <span class="key">{e(dearest.bookmaker)}</span>
the highest ({dearest.avg_margin_pct:.2f}%). Betfair Exchange is shown for comparison: it is a
betting exchange, not a bookmaker, and its prices are before commission.</p>
<img alt="Bar chart of average closing margin per bookmaker" src="data:image/png;base64,{_png(margin_figure(margins))}">

<h2>Where did the odds move most before kick-off?</h2>
<p class="explain">Odds change as news and money arrive. This compares the early odds with the
closing odds, measured as the change in the outcome's chance after the margin is removed.
The biggest move was <span class="key">{e(top_move.home)} v {e(top_move.away)}</span>: the
{OUTCOME_NAMES[top_move.outcome].lower()} at {e(top_move.bookmaker)} went from {top_move.open_odds:.2f}
to {top_move.close_odds:.2f} ({top_move.prob_move_pp:+.1f} percentage points).
With only two snapshots per match, this is a rough view, not minute-by-minute data.</p>
{_table(friendly_moves(moves))}

<h2>Which prices looked out of line?</h2>
<p class="explain">A <span class="key">value alert</span> means a bookmaker offered noticeably better
odds than the sharpest available price suggested was fair (more than
{data["threshold"]:.0%} expected edge). Fair prices come from Pinnacle, or Betfair Exchange when
Pinnacle is missing. An alert is a flag for a person to check, not guaranteed profit: some come
from stale or wrong prices, including the reference price itself.</p>
<img alt="Bar chart of value alerts per bookmaker" src="data:image/png;base64,{_png(alerts_by_book_figure(alerts))}">
<p class="explain">The 15 biggest value alerts:</p>
{_table(friendly_alerts(alerts, "value").head(15))}

<p class="explain">An <span class="key">arbitrage</span> is when the best prices at different
bookmakers are so far apart that backing every outcome locks in a profit whatever the result.
{len(arbs)} were found; the typical locked-in return was only
{arbs["edge"].median():.2%}, and most would vanish once timing gaps and stake limits are considered.</p>
{_table(friendly_alerts(alerts, "arbitrage").head(10))}

<h2>Are the odds a good forecast?</h2>
<p class="explain">If odds are accurate, outcomes given a 25% chance should happen about 25% of
the time. {verdict}: when the closing fair price put an outcome between 20% and 30%
(average {quarter.mean_predicted:.1%}), it happened {quarter.observed_freq:.1%} of the time across
{int(quarter.n):,} cases. Points close to the dashed line mean accurate odds. The most accurate
version was the <span class="key">{e(best.snapshot)}</span> odds with the {e(best.method)} method
(log loss {best.log_loss:.4f}; lower is better), against {base.log_loss:.4f} for simply guessing the
usual home/draw/away rates. {timing}, but the differences between versions are small.</p>
<img alt="Calibration chart: predicted chance against how often it happened" class="narrow"
 src="data:image/png;base64,{_png(calibration.reliability_figure(rel))}">

<footer>Data: football-data.co.uk. Method details and limitations are in the project README.
Alert settings: threshold {data["threshold"]:.0%}, {e(data["method"])} margin removal.</footer>
</main></body></html>
"""


def write_report(con: duckdb.DuckDBPyConnection, out: Path, **kwargs: object) -> Path:
    """Gather data, render HTML and write it to out."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(gather(con, **kwargs)), encoding="utf-8")
    return out
