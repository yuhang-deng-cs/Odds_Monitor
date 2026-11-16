"""Build one self-contained HTML report for non-technical readers (English / Chinese).

Everything (charts as embedded PNGs, tables, CSS, a tiny language-switch script) lives in a
single file that opens in any browser with no server and no internet. The numbers come from
the same functions the CLI uses. Every piece of text is written in both languages; the
button at the top right shows one or the other (English by default).
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
import clv
import i18n
import liability
import queries
from detector import detect

OUTCOME_NAMES = {k: v for k, v in i18n.VALUES["en"].items() if k in ("H", "D", "A", "ALL")}
INK, INK_2, GRID, SURFACE, BLUE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#2a78d6"


def gather(
    con: duckdb.DuckDBPyConnection, threshold: float = 0.03, method: str = "power"
) -> dict[str, object]:
    """Collect every table the report shows."""
    odds = queries.odds_with_matches(con)
    alerts = detect(odds, threshold=threshold, method=method)
    summary, preds = calibration.evaluate(odds)
    params = {**liability.DEFAULTS, "threshold": threshold, "method": method}
    exposure = liability.simulate(odds, **params)
    return {
        "odds": odds,
        "margins": queries.margins(con),
        "moves": queries.moves(con, limit=10),
        "alerts": alerts,
        "calibration": summary,
        "reliability": {k: calibration.reliability_table(preds[k]) for k in ("open/power", "close/power")},
        "performance": clv.performance(odds, alerts, method)[0],
        "exchange_check": clv.exchange_check(alerts),
        "exposure": exposure,
        "exposure_summary": liability.summarise(exposure),
        "exposure_params": params,
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


# ---------- friendly tables (column names and categories follow `lang`) ----------


# Numeric columns stay numbers so the dashboard sorts them correctly; only the display is
# formatted. Each entry: (str.format pattern for the HTML report, printf pattern for
# st.column_config). Percent columns hold percentage points (4.9 means 4.9%).
_ODDS = ("{:.2f}", "%.2f")
_COUNT = ("{:,.0f}", "localized")
NUMBER_FORMATS = {
    "Early odds": _ODDS,
    "Closing odds": _ODDS,
    "Odds offered": _ODDS,
    "Change in chance (pts)": ("{:+.1f}", "%+.1f"),
    "Fair chance": ("{:.1f}%", "%.1f%%"),
    "Expected edge": ("{:.1f}%", "%.1f%%"),
    "Locked-in return": ("{:.2f}%", "%.2f%%"),
    "Bets": _COUNT,
    "Bets with CLV": _COUNT,
    "Average CLV": ("{:+.1f}%", "%+.1f%%"),
    "Beat the close": ("{:.0f}%", "%.0f%%"),
    "Return per unit": ("{:+.1f}%", "%+.1f%%"),
    "Worst case": _COUNT,
    "Actual P&L": ("{:+,.0f}", "localized"),
}


def number_formats(lang: str = "en") -> dict[str, str]:
    """Displayed column name -> printf pattern, for st.column_config.NumberColumn."""
    return {i18n.columns([c], lang)[c]: f for c, (_, f) in NUMBER_FORMATS.items()}


def _localise(df: pd.DataFrame, lang: str) -> pd.DataFrame:
    return df.rename(columns=i18n.columns(list(df.columns), lang))


def _formatted(df: pd.DataFrame) -> pd.DataFrame:
    """Render numeric columns as text for the static HTML report (missing values show a dash)."""
    out = df.copy()
    for col, (pattern, _) in NUMBER_FORMATS.items():
        for name in {col, i18n.COLUMNS_ZH.get(col, col)} & set(out.columns):
            out[name] = out[name].map(lambda x, p=pattern: "–" if pd.isna(x) else p.format(x))
    return out


def _date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.strftime("%d %b %Y")


def friendly_moves(moves: pd.DataFrame, lang: str = "en") -> pd.DataFrame:
    return _localise(pd.DataFrame({
        "Date": _date(moves["match_date"]),
        "Match": moves["home"] + " v " + moves["away"],
        "Bookmaker": moves["bookmaker"],
        "Outcome": moves["outcome"].map(lambda o: i18n.value(o, lang)),
        "Early odds": moves["open_odds"],
        "Closing odds": moves["close_odds"],
        "Change in chance (pts)": moves["prob_move_pp"],
        "Final result": moves["result"].map(lambda o: i18n.value(o, lang)),
    }), lang)  # fmt: skip


def friendly_alerts(alerts: pd.DataFrame, alert_type: str, lang: str = "en") -> pd.DataFrame:
    a = alerts[alerts["alert_type"] == alert_type]
    out = pd.DataFrame({
        "Date": _date(a["match_date"]),
        "Match": a["home"] + " v " + a["away"],
        "Odds taken": a["snapshot"].map(lambda s: i18n.value(s, lang)),
    })  # fmt: skip
    if alert_type == "value":
        out["Bookmaker"] = a["bookmaker"]
        out["Outcome"] = a["outcome"].map(lambda o: i18n.value(o, lang))
        out["Odds offered"] = a["odds"]
        out["Fair chance"] = a["fair_prob"] * 100
        out["Expected edge"] = a["edge"] * 100
        out["Compared with"] = a["reference"].str.replace("_", " ")
    else:
        out["Best prices used"] = a["bookmaker"].str.replace("|", ", ").str.replace(":", " ")
        out["Locked-in return"] = a["edge"] * 100
    return _localise(out, lang)


def _pct(x: float, fmt: str = "{:+.1%}") -> str:
    return "–" if pd.isna(x) else fmt.format(x)


def _group_label(row, lang: str) -> str:
    """Group name; a group mixing early and closing bets says how many of each."""
    name = i18n.GROUPS_ZH[row.group] if lang == "zh" else row.group
    early, close = row.n_early, row.n - row.n_early
    if early and close:
        name += (
            f"（{early} 早盘 + {close} 收盘）"
            if lang == "zh"
            else f" ({early} early + {close} closing)"
        )
    return name


def friendly_performance(perf: pd.DataFrame, lang: str = "en") -> pd.DataFrame:
    return _localise(pd.DataFrame({
        "Group": [_group_label(r, lang) for r in perf.itertuples()],
        "Bets": perf["n"],
        "Return per unit": perf["roi"] * 100,
        "95% range": [f"{_pct(lo, '{:+.0%}')} … {_pct(hi, '{:+.0%}')}"
                      for lo, hi in zip(perf["roi_ci_low"], perf["roi_ci_high"], strict=True)],
        # CLV needs a later price to beat, so only early bets have it: show how many did.
        "Bets with CLV": perf["n_clv"],
        "Average CLV": perf["avg_clv"] * 100,
        "Beat the close": perf["beat_close_pct"] * 100,
    }), lang)  # fmt: skip


def friendly_exposure_summary(summary: pd.DataFrame, lang: str = "en") -> pd.DataFrame:
    def fmt(metric: str, v: float) -> str:
        counts = "matches" in metric or "alerts" in metric
        return f"{v:,.0f}" if counts else f"{v:,.0f} u"

    return _localise(pd.DataFrame({
        "Metric": summary["metric"].map(lambda m: i18n.METRICS_ZH[m] if lang == "zh" else m),
        "Value": [fmt(m, v) for m, v in zip(summary["metric"], summary["value"], strict=True)],
    }), lang)  # fmt: skip


def friendly_exposure(sim: pd.DataFrame, lang: str = "en") -> pd.DataFrame:
    def outcomes(codes: str) -> str:
        return ", ".join(i18n.value(c, lang) for c in codes) or "–"

    stakes = zip(sim["stake_h"], sim["stake_d"], sim["stake_a"], strict=True)
    return _localise(pd.DataFrame({
        "Date": _date(sim["match_date"]),
        "Match": sim["home"] + " v " + sim["away"],
        "Stakes H/D/A": [f"{h:,.0f} / {d:,.0f} / {a:,.0f}" for h, d, a in stakes],
        "Sharp bets on": sim["sharp_on"].map(outcomes),
        "Worst case": sim["worst_case"].round(),
        "Final result": sim["result"].map(lambda o: i18n.value(o, lang)),
        "Actual P&L": sim["actual_pnl"].round(),
    }), lang)  # fmt: skip


def _table(df: pd.DataFrame) -> str:
    html = _formatted(df).to_html(index=False, border=0, escape=True)
    return '<div class="scroll">' + html + "</div>"


def _tables(make, *args) -> str:
    """The same table twice, one per language; CSS shows the active one."""
    en, zh = _table(make(*args, lang="en")), _table(make(*args, lang="zh"))
    return f'<div class="en">{en}</div><div class="zh">{zh}</div>'


def t(en: str, zh: str) -> str:
    """Inline bilingual text: both spans are in the page, CSS hides the inactive one."""
    return f'<span class="en">{en}</span><span class="zh">{zh}</span>'


# ---------- page ----------


def build_html(data: dict[str, object]) -> str:
    """Render the report as one HTML string."""
    odds: pd.DataFrame = data["odds"]
    margins: pd.DataFrame = data["margins"]
    moves: pd.DataFrame = data["moves"]
    alerts: pd.DataFrame = data["alerts"]
    calib: pd.DataFrame = data["calibration"]
    rel: dict[str, pd.DataFrame] = data["reliability"]
    perf = data["performance"].set_index("group")
    checked, confirmed = data["exchange_check"]
    sim: pd.DataFrame = data["exposure"]
    es = dict(
        zip(data["exposure_summary"]["metric"], data["exposure_summary"]["value"], strict=True)
    )
    xp = data["exposure_params"]
    threshold = data["threshold"]

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
    e = html.escape

    # Wording is derived from the numbers, never assumed.
    gap = abs(quarter.observed_freq - quarter.mean_predicted)
    verdict = t("They do", "基本准确") if gap < 0.03 else t("Not exactly", "并不完全准确")
    ll = calib.set_index(["snapshot", "method"])["log_loss"]
    close_better = ll[("close", "power")] < ll[("open", "power")]
    timing = (
        t("Closing odds were more accurate than early odds, as expected", "收盘赔率比早盘赔率更准，符合预期")
        if close_better
        else t("Surprisingly, early odds were at least as accurate as closing odds", "意外的是，早盘赔率不比收盘赔率差")
    )  # fmt: skip

    early = perf.loc["early value alerts"]
    closing = perf.loc["closing value alerts"]
    both = perf.loc["exchange-confirmed alerts"]
    both_note = (
        t(": too few bets to judge", "：样本太少，无法下结论")
        if pd.isna(both.roi_ci_low) or both.roi_ci_low < 0 < both.roi_ci_high
        else ""
    )
    baseline = perf.loc["all early prices (baseline)"]
    clv_verdict = (
        t("better than a typical early price", "比一般早盘赔率好")
        if early.avg_clv > baseline.avg_clv
        else t("no better than a typical early price", "并不比一般早盘赔率好")
    ) + (
        t(", and on average still generous at the close.", "，而且到收盘时平均仍然偏高。")
        if early.avg_clv > 0
        else t(", but on average not enough to beat the closing price.", "，但平均来说还不足以跑赢收盘价。")
    )  # fmt: skip
    if closing.roi_ci_high < 0:
        close_note = t(
            f"Closing alerts lost money even allowing for luck ({closing.roi:+.0%}, 95% range "
            f"{closing.roi_ci_low:+.0%} to {closing.roi_ci_high:+.0%}).",
            f"收盘提醒即使考虑运气因素也是亏损的（{closing.roi:+.0%}，95% 区间 "
            f"{closing.roi_ci_low:+.0%} 至 {closing.roi_ci_high:+.0%}）。",
        )
    else:
        close_note = t(
            f"Closing alerts returned {closing.roi:+.0%} (95% range {closing.roi_ci_low:+.0%} to "
            f"{closing.roi_ci_high:+.0%}), not clearly different from zero.",
            f"收盘提醒回报 {closing.roi:+.0%}（95% 区间 {closing.roi_ci_low:+.0%} 至 "
            f"{closing.roi_ci_high:+.0%}），与零没有明显差别。",
        )

    handle_total = es["total stakes (simulated)"]
    expected = es["expected profit at fair prices"]
    breaches = int(es["exposure alerts (worst case below limit)"])
    n_matches = int(es["matches"])
    n_sharp = int(es["matches with sharp bets"])
    sharp_cost = -es["expected profit on sharp bets"]
    sharp_real = es["  of which sharp bets"]
    sharp_word = t("won" if sharp_real >= 0 else "lost", "赚了" if sharp_real >= 0 else "亏了")
    book = e(xp["book"])

    tiles = [
        (f"{odds['match_id'].nunique():,}", t("matches analysed", "场比赛")),
        (str(odds["bookmaker"].nunique()), t("bookmakers compared", "家博彩公司")),
        (f"{len(value):,}", t("value alerts", "条价值提醒")),
        (f"{len(arbs):,}", t("arbitrage alerts", "条套利提醒")),
        (f"{breaches:,}", t("exposure alerts (simulated)", "条敞口警报（模拟）")),
    ]
    tiles_html = "".join(
        f'<div class="tile"><div class="num">{n}</div><div class="lbl">{lbl}</div></div>'
        for n, lbl in tiles
    )
    worst = sim.nsmallest(10, "worst_case")

    # fmt: off
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Odds Monitor Report</title>
<style>
:root {{ --bg:{SURFACE}; --ink:{INK}; --ink2:{INK_2}; --line:{GRID}; --accent:{BLUE};
        --note:#fff6e0; --sim:#eef4fc; color-scheme: light; }}
* {{ box-sizing: border-box; }}
html[lang="en"] .zh, html[lang="zh-CN"] .en {{ display:none; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
       font:16px/1.55 system-ui,-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC",Roboto,sans-serif; }}
main {{ max-width:980px; margin:0 auto; padding:24px 16px 64px; }}
h1 {{ font-size:1.8rem; margin:0 0 4px; }} h2 {{ font-size:1.3rem; margin:40px 0 6px; }}
.top {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }}
#lang {{ font:inherit; font-size:.9rem; padding:6px 14px; border:1px solid var(--line);
        border-radius:999px; background:#fff; color:var(--ink); cursor:pointer; white-space:nowrap; }}
#lang:hover {{ border-color:var(--accent); }}
.sub {{ color:var(--ink2); margin:0 0 20px; }}
.banner {{ background:var(--note); border-radius:8px; padding:10px 14px; font-size:.95rem; }}
.banner.sim {{ background:var(--sim); }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:20px 0; }}
.tile {{ border:1px solid var(--line); border-radius:10px; padding:14px 16px; background:#fff; }}
.num {{ font-size:1.9rem; font-weight:650; }} .lbl {{ color:var(--ink2); font-size:.9rem; }}
.explain {{ color:var(--ink2); max-width:72ch; }}
.caption {{ color:var(--ink2); font-size:.85rem; margin-top:-6px; }}
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
<div class="top"><h1>Odds Monitor</h1>
<button id="lang" type="button" aria-label="Switch language / 切换语言">中文</button></div>
<p class="sub">{t("Premier League", "英超")} {e(season_txt)} &middot; {t("built", "生成于")} {date.today():%d %b %Y}</p>
<p class="banner">{t(
"<strong>Historical replay.</strong> This looks back at past odds published by football-data.co.uk. It is a prototype: nothing here is live and no bets were placed.",
"<strong>历史回放。</strong>本报告分析 football-data.co.uk 发布的历史赔率，是一个原型：没有接入实时数据，也没有真实下注。")}</p>
<div class="tiles">{tiles_html}</div>

<h2>{t("Which bookmakers charge the most?", "哪家博彩公司抽水最多？")}</h2>
<p class="explain">{t(
f"Every bookmaker builds a profit margin into its odds. A lower margin means better prices for customers. At closing time, <span class='key'>{e(cheapest.bookmaker)}</span> had the lowest average margin ({cheapest.avg_margin_pct:.2f}%) and <span class='key'>{e(dearest.bookmaker)}</span> the highest ({dearest.avg_margin_pct:.2f}%). Betfair Exchange is shown for comparison: it is a betting exchange, not a bookmaker, and its prices are before commission.",
f"每家博彩公司都会在赔率里加入利润率（抽水）。利润率越低，对玩家越有利。收盘时，<span class='key'>{e(cheapest.bookmaker)}</span> 的平均利润率最低（{cheapest.avg_margin_pct:.2f}%），<span class='key'>{e(dearest.bookmaker)}</span> 最高（{dearest.avg_margin_pct:.2f}%）。Betfair Exchange 仅作对比：它是投注交易所而不是博彩公司，其赔率尚未扣除佣金。")}</p>
<img alt="Bar chart of average closing margin per bookmaker" src="data:image/png;base64,{_png(margin_figure(margins))}">
<p class="caption zh">横轴：收盘平均利润率（%）</p>

<h2>{t("Where did the odds move most before kick-off?", "开赛前哪些赔率变动最大？")}</h2>
<p class="explain">{t(
f"Odds change as news and money arrive. This compares the early odds with the closing odds, measured as the change in the outcome's chance after the margin is removed. The biggest move was <span class='key'>{e(top_move.home)} v {e(top_move.away)}</span>: the {OUTCOME_NAMES[top_move.outcome].lower()} at {e(top_move.bookmaker)} went from {top_move.open_odds:.2f} to {top_move.close_odds:.2f} ({top_move.prob_move_pp:+.1f} percentage points). With only two snapshots per match, this is a rough view, not minute-by-minute data.",
f"赔率会随着消息和资金流入而变化。这里比较早盘与收盘赔率，用去水后概率的变化来衡量。变动最大的是 <span class='key'>{e(top_move.home)} v {e(top_move.away)}</span>：{e(top_move.bookmaker)} 的{i18n.value(top_move.outcome, 'zh')}赔率从 {top_move.open_odds:.2f} 变为 {top_move.close_odds:.2f}（{top_move.prob_move_pp:+.1f} 个百分点）。每场比赛只有两个时间点，所以这只是粗略的视角，不是逐分钟数据。")}</p>
{_tables(friendly_moves, moves)}

<h2>{t("Which prices looked out of line?", "哪些赔率明显偏离市场？")}</h2>
<p class="explain">{t(
f"A <span class='key'>value alert</span> means a bookmaker offered noticeably better odds than the sharpest available price suggested was fair (more than {threshold:.0%} expected edge). Fair prices come from Pinnacle, or Betfair Exchange when Pinnacle is missing. An alert is a flag for a person to check, not guaranteed profit: some come from stale or wrong prices, including the reference price itself.",
f"<span class='key'>价值提醒</span>表示某家博彩公司给出的赔率明显高于最专业的参考价所对应的公平赔率（预期优势超过 {threshold:.0%}）。公平概率取自 Pinnacle；缺少 Pinnacle 时用 Betfair Exchange。提醒只是需要人工核查的信号，不代表一定盈利：有些来自过时或错误的报价，参考价本身也可能出错。")}</p>
<p class="explain">{t(
"<span class='key'>Seen from the sportsbook's side</span>, the same alert is a warning: it is one of <em>our</em> prices that professional (sharp) customers would target, and an arbitrage is a price that arbitrage bettors would take off us. A trading team would use these alerts to review or move the price before kick-off.",
"<span class='key'>站在博彩公司（庄家）的角度</span>，同一条提醒就是一个风险警告：这是<em>我们自己</em>的一个赔率，会被职业玩家盯上；套利提醒则说明我们的某个价格会被套利玩家利用。交易团队可以用这些提醒在开赛前复核或调整价格。")}</p>
<img alt="Bar chart of value alerts per bookmaker" src="data:image/png;base64,{_png(alerts_by_book_figure(alerts))}">
<p class="caption zh">横轴：价值提醒数量</p>
<p class="explain">{t("The 15 biggest value alerts:", "预期优势最大的 15 条价值提醒：")}</p>
{_tables(lambda a, lang: friendly_alerts(a, "value", lang).head(15), alerts)}

<p class="explain">{t(
f"An <span class='key'>arbitrage</span> is when the best prices at different bookmakers are so far apart that backing every outcome locks in a profit whatever the result. {len(arbs)} were found; the typical locked-in return was only {arbs['edge'].median():.2%}, and most would vanish once timing gaps and stake limits are considered.",
f"<span class='key'>套利</span>是指不同博彩公司的最佳赔率差距大到同时买入所有结果，无论赛果如何都能锁定利润。共发现 {len(arbs)} 次；锁定收益的中位数只有 {arbs['edge'].median():.2%}，考虑到报价时间差和投注限额，大多数会消失。")}</p>
{_tables(lambda a, lang: friendly_alerts(a, "arbitrage", lang).head(10), alerts)}

<h2>{t("Did the alerts hold up?", "这些提醒经得起检验吗？")}</h2>
<p class="explain">{t(
f"<span class='key'>Closing line value (CLV)</span> is the standard trading check: was an early price still generous once the market closed, when it had the most information? Across all {baseline.n:,} early sportsbook prices the average CLV was {baseline.avg_clv:+.1%} (about the bookmakers' margin) and only {baseline.beat_close_pct:.0%} beat the closing price. The {early.n} early value alerts averaged {early.avg_clv:+.1%} and {early.beat_close_pct:.0%} beat the close: ",
f"<span class='key'>收盘价值（CLV）</span>是交易中最常用的检验：一个早盘赔率到收盘时（市场信息最充分时）是否仍然偏高？全部 {baseline.n:,} 个早盘赔率的平均 CLV 为 {baseline.avg_clv:+.1%}（约等于博彩公司的利润率），只有 {baseline.beat_close_pct:.0%} 跑赢了收盘价。{early.n} 条早盘价值提醒的平均 CLV 为 {early.avg_clv:+.1%}，{early.beat_close_pct:.0%} 跑赢收盘价：")}{clv_verdict}</p>
<p class="explain">{t(
f"Staking 1 unit on every alert, using the real results: early alerts returned {early.roi:+.0%} per unit, but the 95% range ({early.roi_ci_low:+.0%} to {early.roi_ci_high:+.0%}) is far too wide to tell skill from luck. ",
f"如果每条提醒都下注 1 个单位并按真实赛果结算：早盘提醒每单位回报 {early.roi:+.0%}，但 95% 区间（{early.roi_ci_low:+.0%} 至 {early.roi_ci_high:+.0%}）太宽，无法区分是能力还是运气。")}{close_note}
{t(
f"A second opinion explains much of this: of {checked} alerts graded against Pinnacle that also had a Betfair Exchange price, only {confirmed} still cleared the {threshold:.0%} threshold against the exchange. Most alerts come from Pinnacle alone disagreeing with the market, so a production version should require two sharp sources to agree. The <i>exchange-confirmed alerts</i> row tests that rule: {int(both.n)} bets, average CLV {_pct(both.avg_clv)} on the early ones, but a return of {_pct(both.roi)} per unit with a 95% range of {_pct(both.roi_ci_low, '{:+.0%}')} to {_pct(both.roi_ci_high, '{:+.0%}')}{both_note}. (Ranges come from resampling whole matches, because one odd price can trigger several alerts at once.)",
f"用第二个参考源复核可以解释其中大部分原因：在以 Pinnacle 为参考、且同时有 Betfair Exchange 报价的 {checked} 条提醒中，只有 {confirmed} 条相对交易所仍超过 {threshold:.0%} 的阈值。大多数提醒只是 Pinnacle 单独与市场不一致，所以生产版本应要求两个专业参考源一致才发出提醒。表中“交易所确认的提醒”一行检验了这条规则：共 {int(both.n)} 注，其中早盘部分的平均 CLV 为 {_pct(both.avg_clv)}，但每单位回报 {_pct(both.roi)}，95% 区间 {_pct(both.roi_ci_low, '{:+.0%}')} 至 {_pct(both.roi_ci_high, '{:+.0%}')}{both_note}。（区间按整场比赛重抽样计算，因为一个异常报价可能同时触发多条提醒。）")}</p>
{_tables(friendly_performance, data["performance"])}

<h2>{t("Simulated: our exposure as a sportsbook", "模拟：作为博彩公司的风险敞口")}</h2>
<p class="banner sim">{t(
"<strong>Simulated bets.</strong> Prices and results are real; the bets are made up, because the data has no stake information.",
"<strong>模拟投注。</strong>赔率和赛果是真实的，但投注是模拟的，因为数据中没有投注金额信息。")}</p>
<p class="explain">{t(
f"Here we play the bookmaker: {book}'s real closing prices stand in for our prices. Per match, recreational customers stake {xp['handle']:,.0f} units, split roughly in line with the fair chances plus random noise, and a sharp customer adds {xp['sharp_stake']:,.0f} on any outcome where our price beats fair by more than {threshold:.0%}, exactly where the value alerts fire. For each match we compute the book's profit or loss if each outcome wins; the worst of the three is the match's liability.",
f"这里我们扮演博彩公司：用 {book} 的真实收盘赔率作为“我们的”赔率。每场比赛，普通玩家共投注 {xp['handle']:,.0f} 个单位，大致按公平概率分配并加入随机波动；当我们的某个赔率比公平赔率高出 {threshold:.0%} 以上时（也就是价值提醒触发的地方），职业玩家会在该结果上额外投注 {xp['sharp_stake']:,.0f}。每场比赛分别计算每个结果发生时庄家的盈亏，三者中最差的就是该场的负债（liability）。")}</p>
<p class="explain">{t(
f"Expected profit at fair prices: {expected:,.0f} on {handle_total:,.0f} staked ({expected / handle_total:.1%}, close to {book}'s margin); on the real results the book made {es['actual profit on real results']:,.0f}. <span class='key'>{breaches} of {n_matches:,} matches</span> had a worst case beyond the {xp['limit']:,.0f}-unit limit: these are the matches a trader would act on, by shortening the risky price or capping stakes. Sharp bets came in on {n_sharp} matches with an expected cost to the book of {sharp_cost:,.0f}; on the real results the book ",
f"按公平概率计算，预期利润为 {expected:,.0f}，总投注额 {handle_total:,.0f}（{expected / handle_total:.1%}，接近 {book} 的利润率）；按真实赛果，庄家实际盈利 {es['actual profit on real results']:,.0f}。<span class='key'>{n_matches:,} 场比赛中有 {breaches} 场</span>的最坏情况超过了 {xp['limit']:,.0f} 单位的限额：这些就是交易员需要处理的比赛，例如降低风险结果的赔率或限制投注额。职业玩家在 {n_sharp} 场比赛中下注，对庄家的预期成本为 {sharp_cost:,.0f}；按真实赛果，庄家")}{sharp_word} {abs(sharp_real):,.0f}{t(
" on them, which with so few bets is luck, not evidence.", "，但投注数量太少，这只是运气，不能说明问题。")}</p>
{_tables(friendly_exposure_summary, data["exposure_summary"])}
<p class="explain">{t("The 10 matches with the largest worst-case loss:", "最坏情况亏损最大的 10 场比赛：")}</p>
{_tables(friendly_exposure, worst)}

<h2>{t("Are the odds a good forecast?", "赔率是好的预测吗？")}</h2>
<p class="explain">{t(
"If odds are accurate, outcomes given a 25% chance should happen about 25% of the time. ",
"如果赔率准确，被赋予 25% 概率的结果应该大约有 25% 的时候发生。")}{verdict}{t(
f": when the closing fair price put an outcome between 20% and 30% (average {quarter.mean_predicted:.1%}), it happened {quarter.observed_freq:.1%} of the time across {int(quarter.n):,} cases. Points close to the dashed line mean accurate odds. The most accurate version was the <span class='key'>{e(best.snapshot)}</span> odds with the {e(best.method)} method (log loss {best.log_loss:.4f}; lower is better), against {base.log_loss:.4f} for simply guessing the usual home/draw/away rates. ",
f"：当收盘公平概率在 20% 到 30% 之间（平均 {quarter.mean_predicted:.1%}）时，实际发生率为 {quarter.observed_freq:.1%}，共 {int(quarter.n):,} 个样本。点越接近虚线说明赔率越准确。最准确的是<span class='key'>{i18n.value(best.snapshot, 'zh')}</span>赔率加 {e(best.method)} 去水法（对数损失 {best.log_loss:.4f}，越低越好），而简单按主/平/客历史比例猜测的对数损失为 {base.log_loss:.4f}。")}{timing}{t(
", but the differences between versions are small.", "，但各版本之间差别很小。")}</p>
<img alt="Calibration chart: predicted chance against how often it happened" class="narrow"
 src="data:image/png;base64,{_png(calibration.reliability_figure(rel))}">
<p class="caption zh">横轴：预测概率；纵轴：实际发生频率；虚线 = 完全准确</p>

<footer>{t("Data: football-data.co.uk. Method details and limitations are in the project README.",
"数据来源：football-data.co.uk。方法细节和局限性见项目 README。")}
{t("Alert settings", "提醒设置")}: {threshold:.0%}, {e(data["method"])}.</footer>
</main>
<script>
(function () {{
  var root = document.documentElement, btn = document.getElementById("lang");
  btn.addEventListener("click", function () {{
    var zh = root.lang === "en";
    root.lang = zh ? "zh-CN" : "en";
    btn.textContent = zh ? "English" : "中文";
  }});
}})();
</script>
</body></html>
"""
    # fmt: on


def write_report(con: duckdb.DuckDBPyConnection, out: Path, **kwargs: object) -> Path:
    """Gather data, render HTML and write it to out."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(gather(con, **kwargs)), encoding="utf-8")
    return out
