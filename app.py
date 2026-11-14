"""Interactive dashboard for non-technical users: streamlit run app.py

Reads the DuckDB file built by `python cli.py ingest` (read-only) and reuses the same
detector, CLV, liability, calibration and report helpers as the CLI, so the numbers always
agree. Historical replay only: nothing is live and no bets are placed. A switch at the top
shows the page in English (default) or Chinese.
"""

import os
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

import calibration
import clv
import db
import download
import i18n
import liability
import queries
from detector import DEVIG, detect
from load import load_dir
from odds import fair_price_table, overround
from report import (
    BLUE,
    friendly_alerts,
    friendly_exposure,
    friendly_exposure_summary,
    friendly_moves,
    friendly_performance,
)

DB_PATH = Path(os.environ.get("ODDS_DB", "data/odds.duckdb"))
ORANGE = "#eb6834"
RACE_EXAMPLE = "3.0 4.5 6.0 8.0 10.0 13.0 17.0 21.0 34.0 51.0"  # illustrative, not real

# UI text: key -> (English, Chinese)
TEXT = {
    "replay": ("**Historical replay.** Past Premier League odds from football-data.co.uk. A prototype: nothing here is live and no bets are placed.",
               "**历史回放。**数据为 football-data.co.uk 的英超历史赔率。这是一个原型：没有实时数据，也没有真实下注。"),
    "no_db": ("Could not build the database at {path}: {err}. Run `python cli.py download` and `python cli.py ingest`.",
              "无法在 {path} 建立数据库：{err}。请运行 `python cli.py download` 和 `python cli.py ingest`。"),
    "first_run": ("First run: downloading three Premier League seasons and building the database (about 10 seconds)…",
                  "首次运行：正在下载三个英超赛季并建立数据库（约 10 秒）……"),
    "filters": ("Filters", "筛选"), "seasons": ("Seasons", "赛季"), "bookmakers": ("Bookmakers", "博彩公司"),
    "pinnacle_tip": ("Removing Pinnacle shows what happens when the sharp reference is missing.",
                     "去掉 Pinnacle 可以看到缺少专业参考价时会发生什么。"),
    "alert_settings": ("Alert settings", "提醒设置"),
    "min_edge": ("Minimum expected edge (%)", "最低预期优势（%）"),
    "method": ("Margin removal method", "去水方法"),
    "method_help": ("How the bookmaker margin is stripped out to get fair chances.", "如何去掉博彩公司的利润率，得到公平概率。"),
    "empty": ("No data for these filters. Select at least one season and bookmaker.", "当前筛选没有数据，请至少选择一个赛季和一家博彩公司。"),
    "m_matches": ("Matches", "比赛"), "m_books": ("Bookmakers", "博彩公司"),
    "m_value": ("Value alerts", "价值提醒"), "m_arbs": ("Arbitrage alerts", "套利提醒"),
    "tab_margins": ("Bookmaker margins", "博彩公司利润率"), "tab_moves": ("Price moves", "赔率变动"),
    "tab_alerts": ("Alerts", "提醒"), "tab_perf": ("Alert check (CLV)", "提醒检验（CLV）"),
    "tab_exposure": ("Our exposure (simulated)", "风险敞口（模拟）"), "tab_calib": ("Are odds accurate?", "赔率准确吗"),
    "tab_calc": ("Odds calculator (any market)", "赔率计算器（任意盘口）"),
    "calc_h": ("Margin and fair prices for any market", "任意盘口的利润率与公平赔率"),
    "calc_p": ("The same margin-removal code used on the football data works for any number of outcomes, so it can price a horse race as well as home/draw/away. Type decimal odds separated by spaces or commas. The pre-filled prices are an **illustrative 10-runner race, not real data**.",
               "足球数据使用的同一套去水代码适用于任意数量的结果，所以既能处理主/平/客，也能处理一场赛马。输入用空格或逗号分隔的小数赔率。预填的赔率是一个**示例 10 匹马赛事，不是真实数据**。"),
    "calc_input": ("Decimal odds", "小数赔率"),
    "calc_bad": ("Enter at least two decimal odds above 1.0, e.g. 3.0 4.5 6.0", "请输入至少两个大于 1.0 的小数赔率，例如 3.0 4.5 6.0"),
    "calc_over": ("Overround (bookmaker margin)", "超额率（博彩公司利润率）"), "calc_n": ("Outcomes", "结果数"),
    "calc_note": ("Compare the two methods: power removes relatively more margin from the longshots at the bottom and less from the favourite at the top (the favourite–longshot bias).",
                  "对比两种方法：power 法从底部的冷门身上去掉更多利润率，从顶部的热门身上去掉更少（即热门-冷门偏差）。"),
    "runner": ("Runner", "编号"), "c_odds": ("Odds", "赔率"), "c_implied": ("Implied (with margin)", "隐含概率（含水）"),
    "c_prop": ("Fair: proportional", "公平概率：比例法"), "c_power": ("Fair: power", "公平概率：power 法"),
    "c_fair_odds": ("Fair odds (power)", "公平赔率（power）"),
    "perf_what": ("**What is CLV?** Example: a bookmaker offered 4.40 early; at kick-off the sharp market rated the outcome a 25% chance (fair odds 4.00). CLV = 4.40 × 0.25 − 1 = **+10%**: the early price was too generous and the market corrected it. Positive CLV over many bets is the standard sign of a good bettor, and for a sportsbook, of a price that sharp customers will pick off.",
                  "**什么是 CLV？**举例：某博彩公司早盘开出 4.40；开赛时专业市场认为该结果有 25% 的概率（公平赔率 4.00）。CLV = 4.40 × 0.25 − 1 = **+10%**：说明早盘价格给得太高，后来被市场修正了。长期正的 CLV 是判断职业玩家水平的标准指标；对博彩公司来说，则意味着这个价格会被职业玩家利用。"),
    "margins_h": ("Which bookmakers charge the most?", "哪家博彩公司抽水最多？"),
    "margins_p": ("Every bookmaker builds a profit margin into its odds. **Lower margin = better prices for customers.** Betfair Exchange is a betting exchange (prices before commission).",
                  "每家博彩公司都会在赔率中加入利润率。**利润率越低，对玩家越有利。**Betfair Exchange 是投注交易所（赔率未扣佣金）。"),
    "odds": ("Odds", "赔率"), "avg_margin": ("Average margin (%)", "平均利润率（%）"),
    "moves_h": ("Where did the odds move most before kick-off?", "开赛前哪些赔率变动最大？"),
    "moves_p": ("Change in each outcome's chance (margin removed) between the early and closing odds. Only two snapshots per match, so this is a rough view, not minute-by-minute data.",
                "早盘到收盘之间每个结果去水后概率的变化。每场只有两个时间点，所以只是粗略视角，不是逐分钟数据。"),
    "how_many": ("How many to show", "显示条数"),
    "alerts_h": ("Which prices looked out of line?", "哪些赔率明显偏离市场？"),
    "alerts_p": ("A **value alert** means a bookmaker's price beat the fair price by more than **{thr}** expected edge. Fair prices come from Pinnacle, else Betfair Exchange, else the bookmaker average. An **arbitrage** means the best prices across bookmakers lock in a profit whatever happens. Alerts are flags to check, not guaranteed profit: some come from stale or wrong prices.",
                 "**价值提醒**表示某家博彩公司的赔率比公平赔率高出 **{thr}** 以上的预期优势。公平概率依次取自 Pinnacle、Betfair Exchange 或博彩公司平均值。**套利**表示各家最佳赔率组合起来无论结果如何都能锁定利润。提醒只是需要核查的信号，不代表一定盈利：有些来自过时或错误的报价。"),
    "book_view": ("**From the sportsbook's side** the same alert is a warning: one of *our* prices that sharp customers would target. A trading team would review or move that price before kick-off.",
                  "**站在庄家角度**，同一条提醒就是风险警告：这是*我们自己*会被职业玩家盯上的赔率。交易团队应在开赛前复核或调整该价格。"),
    "no_value": ("No value alerts at this threshold.", "该阈值下没有价值提醒。"),
    "n_alerts": ("Number of value alerts", "价值提醒数量"), "arbs": ("Arbitrages", "套利"),
    "download": ("Download all alerts (CSV)", "下载全部提醒（CSV）"),
    "perf_h": ("Did the alerts hold up?", "这些提醒经得起检验吗？"),
    "perf_p": ("**Closing line value (CLV)** asks whether an early price was still generous at the close, when the market knew most: CLV = early odds × closing fair chance − 1. The baseline is every early price; alerts are only useful if they clearly beat it. *Return per unit* stakes 1 unit on every alert using the real results; the 95% range comes from resampling whole matches.",
               "**收盘价值（CLV）**检验早盘赔率到收盘（市场信息最充分）时是否仍然偏高：CLV = 早盘赔率 × 收盘公平概率 − 1。基准是全部早盘赔率；提醒只有明显优于基准才有用。*每单位回报*是按真实赛果、每条提醒下注 1 单位的结果；95% 区间按整场比赛重抽样得到。"),
    "second": ("Second opinion: of **{c}** alerts graded against Pinnacle that also had a Betfair Exchange price, only **{k}** still cleared the threshold against the exchange.",
               "第二参考源复核：在以 Pinnacle 为参考、且有 Betfair Exchange 报价的 **{c}** 条提醒中，只有 **{k}** 条相对交易所仍超过阈值。"),
    "exp_h": ("If we were the bookmaker: how much could one match cost us?", "如果我们是庄家：一场比赛最多会亏多少？"),
    "exp_sim": ("**Simulated bets.** Prices and results are real; the bets are made up because the data has no stake information.",
                "**模拟投注。**赔率和赛果是真实的；投注是模拟的，因为数据中没有投注金额。"),
    "exp_p": ("The chosen bookmaker's closing prices play *our* prices. Recreational customers stake a fixed amount per match, split roughly by the fair chances with random noise; a sharp customer adds a stake wherever our price beats fair by more than the alert threshold. **Worst case** is the book's result if the most expensive outcome wins; an exposure alert fires when it is beyond the limit.",
              "用所选博彩公司的收盘赔率扮演*我们的*赔率。普通玩家每场投注固定金额，大致按公平概率分配并加入随机波动；当我们的赔率比公平赔率高出提醒阈值时，职业玩家会额外下注。**最坏情况**是赔付最多的结果发生时庄家的盈亏；超过限额即触发敞口警报。"),
    "our_book": ("Our prices (bookmaker)", "我方赔率（博彩公司）"),
    "limit": ("Exposure limit per match (units)", "每场敞口限额（单位）"),
    "worst_axis": ("Worst-case result per match (units)", "每场最坏情况盈亏（单位）"),
    "n_matches": ("Matches", "比赛数"), "worst10": ("Matches with the largest worst-case loss", "最坏情况亏损最大的比赛"),
    "calib_h": ("Are the odds a good forecast?", "赔率是好的预测吗？"),
    "calib_p": ("If odds are accurate, outcomes given a 25% chance should happen about 25% of the time. Points on the dashed line mean perfectly accurate odds. Hover a point to see how many cases it is based on: the top bins have few cases, so they are noisy.",
                "如果赔率准确，被赋予 25% 概率的结果应该大约 25% 的时候发生。点落在虚线上表示完全准确。把鼠标移到点上可以看到样本数：高概率区间样本少，因此波动大。"),
    "predicted": ("Predicted chance", "预测概率"), "observed": ("How often it happened", "实际发生频率"),
    "scores": ("**Accuracy scores** (lower is better; 'base rates' = always guessing the usual home/draw/away split):",
               "**准确度得分**（越低越好；“base rates” = 总是按主/平/客的历史比例猜测）："),
    "footer": ("Data: football-data.co.uk. See README for method and limitations.", "数据：football-data.co.uk。方法与局限见 README。"),
}  # fmt: skip

st.set_page_config(page_title="Odds Monitor", page_icon=":material/monitoring:", layout="wide")


@st.cache_resource(show_spinner=False)
def build_database(db_path: str) -> None:
    """First run (e.g. a fresh cloud deploy): download the CSVs and ingest them once.

    Builds into a temporary file and renames it, so no session ever reads a half-built database.
    """
    target = Path(db_path)
    raw_dir = target.parent / "raw"
    download.download(download.DEFAULT_SEASONS, raw_dir)
    partial = target.with_suffix(".building")
    partial.unlink(missing_ok=True)
    con = db.connect(partial)
    try:
        db.ingest(con, load_dir(raw_dir))
    finally:
        con.close()
    partial.replace(target)


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
def run_performance(odds: pd.DataFrame, alerts: pd.DataFrame, threshold: float, method: str):
    return clv.performance(odds, alerts, method)[0], clv.exchange_check(
        odds, alerts, threshold, method
    )


@st.cache_data
def run_exposure(
    odds: pd.DataFrame, book: str, limit: float, threshold: float, method: str
) -> pd.DataFrame:
    return liability.simulate(odds, book=book, limit=limit, threshold=threshold, method=method)


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
        )
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

head_l, head_r = st.columns([5, 1], vertical_alignment="bottom")
with head_r:
    lang = st.segmented_control(
        "Language / 语言", ["en", "zh"], default="en", required=True, key="lang",
        format_func={"en": "English", "zh": "中文"}.get, label_visibility="collapsed",
    )  # fmt: skip


def tx(key: str, **fmt: object) -> str:
    """Text for the current language."""
    text = TEXT[key][0 if lang == "en" else 1]
    return text.format(**fmt) if fmt else text


def local(df: pd.DataFrame) -> pd.DataFrame:
    """Translate raw column names (identity in English)."""
    return df.rename(columns=i18n.columns(list(df.columns), lang))


head_l.title("Odds Monitor")
st.info(tx("replay"), icon=":material/history:")

if not DB_PATH.exists():
    try:
        with st.spinner(tx("first_run")):
            build_database(str(DB_PATH))
    except (download.DownloadError, OSError) as exc:
        st.error(tx("no_db", path=DB_PATH, err=exc))
        st.stop()

odds_all, moves_all = load_data(str(DB_PATH))

with st.sidebar:
    st.header(tx("filters"))
    seasons = sorted(odds_all["season"].unique())
    season_sel = st.multiselect(
        tx("seasons"),
        seasons,
        default=seasons,
        format_func=lambda s: f"20{s[:2]}/{s[2:]}",
        key="seasons",
    )
    books = sorted(odds_all["bookmaker"].unique())
    book_sel = st.multiselect(tx("bookmakers"), books, default=books, key="books")
    st.caption(tx("pinnacle_tip"))
    st.header(tx("alert_settings"))
    threshold = st.slider(tx("min_edge"), 1.0, 10.0, 3.0, 0.5, key="threshold") / 100
    method = st.radio(
        tx("method"),
        sorted(DEVIG),
        index=sorted(DEVIG).index("power"),
        help=tx("method_help"),
        key="method",
    )

odds = odds_all[odds_all["season"].isin(season_sel) & odds_all["bookmaker"].isin(book_sel)]
moves = moves_all[moves_all["season"].isin(season_sel) & moves_all["bookmaker"].isin(book_sel)]
if odds.empty:
    st.warning(tx("empty"))
    st.stop()

alerts = run_alerts(odds, threshold, method)
value = alerts[alerts["alert_type"] == "value"]
arbs = alerts[alerts["alert_type"] == "arbitrage"]

c1, c2, c3, c4 = st.columns(4)
c1.metric(tx("m_matches"), f"{odds['match_id'].nunique():,}")
c2.metric(tx("m_books"), odds["bookmaker"].nunique())
c3.metric(tx("m_value"), f"{len(value):,}")
c4.metric(tx("m_arbs"), f"{len(arbs):,}")

tab_m, tab_mv, tab_a, tab_p, tab_x, tab_c, tab_calc = st.tabs(
    [
        tx("tab_margins"),
        tx("tab_moves"),
        tx("tab_alerts"),
        tx("tab_perf"),
        tx("tab_exposure"),
        tx("tab_calib"),
        tx("tab_calc"),
    ]
)

with tab_m:
    st.subheader(tx("margins_h"))
    st.markdown(tx("margins_p"))
    snap = st.segmented_control(
        tx("odds"), ["close", "open"], default="close", required=True, key="margin_snap",
        format_func=lambda s: i18n.value(s, lang),
    )  # fmt: skip
    m = margins_table(odds, snap)
    st.altair_chart(
        bar_chart(m, "avg_margin_pct", "bookmaker", tx("avg_margin"),
                  ["bookmaker", "avg_margin_pct", "median_margin_pct", "n_matches"]),
        width="stretch",
    )  # fmt: skip
    st.dataframe(local(m), hide_index=True, width="stretch")

with tab_mv:
    st.subheader(tx("moves_h"))
    st.markdown(tx("moves_p"))
    n = st.slider(tx("how_many"), 5, 100, 20, key="n_moves")
    top = moves.reindex(moves["prob_move_pp"].abs().sort_values(ascending=False).index).head(n)
    st.dataframe(friendly_moves(top, lang), hide_index=True, width="stretch")

with tab_a:
    st.subheader(tx("alerts_h"))
    st.markdown(tx("alerts_p", thr=f"{threshold:.1%}"))
    st.markdown(tx("book_view"))
    if value.empty:
        st.write(tx("no_value"))
    else:
        counts = value["bookmaker"].value_counts().rename_axis("bookmaker").reset_index()
        st.altair_chart(
            bar_chart(counts, "count", "bookmaker", tx("n_alerts"),
                      ["bookmaker", "count"]).encode(y=alt.Y("bookmaker:N", sort="-x", title=None)),
            width="stretch",
        )  # fmt: skip
        st.dataframe(friendly_alerts(alerts, "value", lang), hide_index=True, width="stretch")
    st.markdown(f"**{tx('arbs')} ({len(arbs)})**")
    st.dataframe(friendly_alerts(alerts, "arbitrage", lang), hide_index=True, width="stretch")
    st.download_button(
        tx("download"), alerts.to_csv(index=False), "alerts.csv", "text/csv",
        icon=":material/download:",
    )  # fmt: skip

with tab_p:
    st.subheader(tx("perf_h"))
    st.markdown(tx("perf_what"))
    st.markdown(tx("perf_p"))
    perf, (checked, confirmed) = run_performance(odds, alerts, threshold, method)
    st.dataframe(friendly_performance(perf, lang), hide_index=True, width="stretch")
    st.markdown(tx("second", c=checked, k=confirmed))

with tab_x:
    st.subheader(tx("exp_h"))
    st.info(tx("exp_sim"), icon=":material/science:")
    st.markdown(tx("exp_p"))
    sportsbooks = [b for b in sorted(odds["bookmaker"].unique()) if b != "Betfair Exchange"]
    left, right = st.columns(2)
    default_book = liability.DEFAULTS["book"]
    our_book = left.selectbox(
        tx("our_book"), sportsbooks, key="our_book",
        index=sportsbooks.index(default_book) if default_book in sportsbooks else 0,
    )  # fmt: skip
    limit = right.number_input(
        tx("limit"), 1_000, 50_000, int(liability.DEFAULTS["limit"]), 1_000, key="limit"
    )
    sim = run_exposure(odds, our_book, float(limit), threshold, method)
    if sim.empty:
        st.write(tx("empty"))
    else:
        summary = liability.summarise(sim)
        st.dataframe(friendly_exposure_summary(summary, lang), hide_index=True, width="stretch")
        hist = (
            alt.Chart(sim)
            .mark_bar(color=BLUE)
            .encode(
                x=alt.X("worst_case:Q", bin=alt.Bin(maxbins=40), title=tx("worst_axis")),
                y=alt.Y("count():Q", title=tx("n_matches")),
                tooltip=[alt.Tooltip("count():Q", title=tx("n_matches"))],
            )
        )
        rule = alt.Chart(pd.DataFrame({"x": [-float(limit)]})).mark_rule(
            color=ORANGE, strokeWidth=2, strokeDash=[4, 4]
        ).encode(x="x:Q")  # fmt: skip
        st.altair_chart(hist + rule, width="stretch")
        st.markdown(f"**{tx('worst10')}**")
        st.dataframe(
            friendly_exposure(sim.nsmallest(10, "worst_case"), lang),
            hide_index=True,
            width="stretch",
        )

with tab_c:
    st.subheader(tx("calib_h"))
    st.markdown(tx("calib_p"))
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
            x=alt.X("predicted:Q", title=tx("predicted"), scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("observed:Q", title=tx("observed"), scale=alt.Scale(domain=[0, 1])),
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
        )
        .properties(height=420)
    )
    st.altair_chart(diagonal + lines, width="stretch")
    st.markdown(tx("scores"))
    st.dataframe(
        local(summary.round(5).rename(columns={"brier": "Brier score", "log_loss": "Log loss"})),
        hide_index=True, width="stretch",
    )  # fmt: skip

with tab_calc:
    st.subheader(tx("calc_h"))
    st.markdown(tx("calc_p"))
    raw = st.text_input(tx("calc_input"), RACE_EXAMPLE, key="calc_odds")
    try:
        prices = [float(x) for x in raw.replace(",", " ").split()]
        rows = fair_price_table(prices) if len(prices) >= 2 else []
    except ValueError:  # not a number, or odds <= 1
        rows = []
    if not rows:
        st.warning(tx("calc_bad"))
    else:
        k1, k2 = st.columns(2)
        k1.metric(tx("calc_n"), len(rows))
        k2.metric(tx("calc_over"), f"{overround(prices):.2%}")
        table = pd.DataFrame(rows)
        table.insert(0, "runner", range(1, len(rows) + 1))
        st.dataframe(
            table,
            hide_index=True,
            width="stretch",
            column_config={
                "runner": st.column_config.NumberColumn(tx("runner")),
                "odds": st.column_config.NumberColumn(tx("c_odds"), format="%.2f"),
                "implied": st.column_config.NumberColumn(tx("c_implied"), format="percent"),
                "proportional": st.column_config.NumberColumn(tx("c_prop"), format="percent"),
                "power": st.column_config.NumberColumn(tx("c_power"), format="percent"),
                "fair_odds": st.column_config.NumberColumn(tx("c_fair_odds"), format="%.2f"),
            },
        )
        st.caption(tx("calc_note"))

st.caption(", ".join(f"{k} = {i18n.value(k, lang)}" for k in ("H", "D", "A")) + ". " + tx("footer"))
