"""Interactive dashboard for non-technical users: streamlit run app.py

Reads the DuckDB file built by `python cli.py ingest` (read-only) and reuses the same
detector, calibration and report helpers as the CLI, so the numbers always agree.
Historical replay only: nothing is live and no bets are placed.
"""

import os
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

import calibration
import queries
from detector import DEVIG, detect
from report import BLUE, OUTCOME_NAMES, friendly_alerts, friendly_moves

DB_PATH = Path(os.environ.get("ODDS_DB", "data/odds.duckdb"))
ORANGE = "#eb6834"

st.set_page_config(page_title="Odds Monitor", page_icon="📊", layout="wide")


@st.cache_data
def load_data(db_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read odds and all open->close moves once; filtering happens in memory."""
    con = duckdb.connect(db_path, read_only=True)
    try:
        odds = queries.odds_with_matches(con)
        moves = queries.moves(con, limit=1_000_000)
    finally:
        con.close()
    return odds, moves


@st.cache_data
def run_alerts(odds: pd.DataFrame, threshold: float, method: str) -> pd.DataFrame:
    return detect(odds, threshold=threshold, method=method)


@st.cache_data
def run_calibration(odds: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary, preds = calibration.evaluate(odds)
    rel = pd.concat(
        [
            calibration.reliability_table(preds[k]).assign(series=k)
            for k in ("open/power", "close/power")
        ]
    )
    return summary, rel


def margins_table(odds: pd.DataFrame, snapshot: str) -> pd.DataFrame:
    """Same formula as the SQL 'margins' query, applied to the filtered rows."""
    o = odds[odds["snapshot"] == snapshot]
    margin = (1 / o["odds_h"] + 1 / o["odds_d"] + 1 / o["odds_a"] - 1) * 100
    return (
        o.assign(margin=margin)
        .groupby("bookmaker")
        .agg(
            avg_margin_pct=("margin", "mean"),
            median_margin_pct=("margin", "median"),
            n_matches=("margin", "size"),
        )  # fmt: skip
        .round(2)
        .reset_index()
        .sort_values("avg_margin_pct")
    )


def bar_chart(df: pd.DataFrame, x: str, y: str, x_title: str, tooltip: list) -> alt.Chart:
    """Horizontal bars, smallest at the top, with a hover tooltip."""
    return (
        alt.Chart(df)
        .mark_bar(color=BLUE, cornerRadiusEnd=4, height={"band": 0.7})
        .encode(
            x=alt.X(f"{x}:Q", title=x_title),
            y=alt.Y(f"{y}:N", sort="x", title=None),
            tooltip=tooltip,
        )
        .properties(height=max(160, 28 * len(df)))
    )


# ---------- page ----------

st.title("Odds Monitor")
st.info(
    "**Historical replay.** Past Premier League odds from football-data.co.uk. "
    "A prototype: nothing here is live and no bets are placed.",
    icon="ℹ️",
)

if not DB_PATH.exists():
    st.error(f"No database at {DB_PATH}. Run `python cli.py ingest` first.")
    st.stop()

odds_all, moves_all = load_data(str(DB_PATH))

with st.sidebar:
    st.header("Filters")
    seasons = sorted(odds_all["season"].unique())
    season_sel = st.multiselect(
        "Seasons", seasons, default=seasons, format_func=lambda s: f"20{s[:2]}/{s[2:]}"
    )
    books = sorted(odds_all["bookmaker"].unique())
    book_sel = st.multiselect("Bookmakers", books, default=books)
    st.caption("Removing Pinnacle shows what happens when the sharp reference is missing.")
    st.header("Alert settings")
    threshold = st.slider("Minimum expected edge (%)", 1.0, 10.0, 3.0, 0.5) / 100
    method = st.radio(
        "Margin removal method", sorted(DEVIG), index=sorted(DEVIG).index("power"),
        help="How the bookmaker margin is stripped out to get fair chances.",
    )  # fmt: skip

odds = odds_all[odds_all["season"].isin(season_sel) & odds_all["bookmaker"].isin(book_sel)]
moves = moves_all[moves_all["season"].isin(season_sel) & moves_all["bookmaker"].isin(book_sel)]
if odds.empty:
    st.warning("No data for these filters. Select at least one season and bookmaker.")
    st.stop()

alerts = run_alerts(odds, threshold, method)
value = alerts[alerts["alert_type"] == "value"]
arbs = alerts[alerts["alert_type"] == "arbitrage"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Matches", f"{odds['match_id'].nunique():,}")
c2.metric("Bookmakers", odds["bookmaker"].nunique())
c3.metric("Value alerts", f"{len(value):,}")
c4.metric("Arbitrage alerts", f"{len(arbs):,}")

tab_m, tab_mv, tab_a, tab_c = st.tabs(
    ["Bookmaker margins", "Price moves", "Alerts", "Are odds accurate?"]
)

with tab_m:
    st.subheader("Which bookmakers charge the most?")
    st.write(
        "Every bookmaker builds a profit margin into its odds. **Lower margin = better prices "
        "for customers.** Betfair Exchange is a betting exchange (prices before commission)."
    )
    snap = st.radio("Odds", ["close", "open"], horizontal=True,
                    format_func={"close": "Closing", "open": "Early"}.get)  # fmt: skip
    m = margins_table(odds, snap)
    st.altair_chart(
        bar_chart(m, "avg_margin_pct", "bookmaker", "Average margin (%)",
                  ["bookmaker", "avg_margin_pct", "median_margin_pct", "n_matches"]),
        width="stretch",
    )  # fmt: skip
    st.dataframe(m, hide_index=True, width="stretch")

with tab_mv:
    st.subheader("Where did the odds move most before kick-off?")
    st.write(
        "Change in each outcome's chance (margin removed) between the early and closing odds. "
        "Only two snapshots per match, so this is a rough view, not minute-by-minute data."
    )
    n = st.slider("How many to show", 5, 100, 20)
    top = moves.reindex(moves["prob_move_pp"].abs().sort_values(ascending=False).index).head(n)
    st.dataframe(friendly_moves(top), hide_index=True, width="stretch")

with tab_a:
    st.subheader("Which prices looked out of line?")
    st.write(
        f"A **value alert** means a bookmaker's price beat the fair price by more than "
        f"**{threshold:.1%}** expected edge. Fair prices come from Pinnacle, else Betfair "
        "Exchange, else the bookmaker average. An **arbitrage** means the best prices across "
        "bookmakers lock in a profit whatever happens. Alerts are flags to check, not "
        "guaranteed profit: some come from stale or wrong prices."
    )
    if value.empty:
        st.write("No value alerts at this threshold.")
    else:
        counts = value["bookmaker"].value_counts().rename_axis("bookmaker").reset_index()
        st.altair_chart(
            bar_chart(counts, "count", "bookmaker", "Number of value alerts",
                      ["bookmaker", "count"]).encode(y=alt.Y("bookmaker:N", sort="-x", title=None)),
            width="stretch",
        )  # fmt: skip
        st.dataframe(friendly_alerts(alerts, "value"), hide_index=True, width="stretch")
    st.markdown(f"**Arbitrages ({len(arbs)})**")
    st.dataframe(friendly_alerts(alerts, "arbitrage"), hide_index=True, width="stretch")
    st.download_button(
        "Download all alerts (CSV)", alerts.to_csv(index=False), "alerts.csv", "text/csv"
    )

with tab_c:
    st.subheader("Are the odds a good forecast?")
    st.write(
        "If odds are accurate, outcomes given a 25% chance should happen about 25% of the "
        "time. Points on the dashed line mean perfectly accurate odds. Hover a point to see "
        "how many cases it is based on: the top bins have few cases, so they are noisy."
    )
    summary, rel = run_calibration(odds)
    rel = rel.rename(columns={"mean_predicted": "predicted", "observed_freq": "observed"})
    diagonal = (
        alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]}))
        .mark_line(strokeDash=[4, 4], color="#9a9994")
        .encode(x="x:Q", y="y:Q")
    )
    lines = (
        alt.Chart(rel)
        .mark_line(point=alt.OverlayMarkDef(size=70), strokeWidth=2)
        .encode(
            x=alt.X("predicted:Q", title="Predicted chance", scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("observed:Q", title="How often it happened", scale=alt.Scale(domain=[0, 1])),
            color=alt.Color(
                "series:N",
                title=None,
                scale=alt.Scale(range=[ORANGE, BLUE]),
                legend=alt.Legend(orient="top-left"),
            ),
            tooltip=[
                "series",
                alt.Tooltip("predicted:Q", format=".1%"),
                alt.Tooltip("observed:Q", format=".1%"),
                "n",
                "bin",
            ],
        )  # fmt: skip
        .properties(height=420)
    )
    st.altair_chart(diagonal + lines, width="stretch")
    st.write("**Accuracy scores** (lower is better; 'base rates' = always guessing the usual "
             "home/draw/away split):")  # fmt: skip
    st.dataframe(
        summary.round(5).rename(columns={"brier": "Brier score", "log_loss": "Log loss"}),
        hide_index=True, width="stretch",
    )  # fmt: skip

st.caption(
    "Outcomes: "
    + ", ".join(f"{k} = {v}" for k, v in OUTCOME_NAMES.items() if k != "ALL")
    + ". Data: football-data.co.uk. See README for method and limitations."
)
