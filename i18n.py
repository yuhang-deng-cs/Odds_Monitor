"""English / Chinese labels shared by the HTML report and the Streamlit dashboard.

Only display text lives here; numbers and logic never depend on the language.
"""

LANGS = ("en", "zh")

VALUES = {
    "en": {
        "H": "Home win", "D": "Draw", "A": "Away win", "ALL": "All outcomes",
        "open": "Early", "close": "Closing",
    },
    "zh": {
        "H": "主胜", "D": "平局", "A": "客胜", "ALL": "全部结果",
        "open": "早盘", "close": "收盘",
    },
}  # fmt: skip

COLUMNS_ZH = {
    "Date": "日期", "Match": "比赛", "Bookmaker": "博彩公司", "Outcome": "结果",
    "Early odds": "早盘赔率", "Closing odds": "收盘赔率",
    "Change in chance (pts)": "概率变化（百分点）",
    "Final result": "实际赛果", "Odds taken": "赔率时点", "Odds offered": "提供赔率",
    "Fair chance": "公平概率", "Expected edge": "预期优势", "Compared with": "参考来源",
    "Best prices used": "所用最佳赔率", "Locked-in return": "锁定收益",
    "Group": "分组", "Bets": "注数", "Bets with CLV": "有 CLV 的注数",
    "Average CLV": "平均 CLV", "Beat the close": "跑赢收盘比例",
    "Return per unit": "每单位回报", "95% range": "95% 区间",
    "Metric": "指标", "Value": "数值", "Our price (H/D/A)": "我方赔率（主/平/客）",
    "Stakes H/D/A": "投注额 主/平/客", "Sharp bets on": "职业玩家下注", "Worst case": "最坏情况",
    "Actual P&L": "实际盈亏",
    "bookmaker": "博彩公司", "avg_margin_pct": "平均利润率 %", "median_margin_pct": "中位利润率 %",
    "n_matches": "比赛数", "count": "数量", "snapshot": "时点", "method": "方法",
    "Brier score": "Brier 分数", "Log loss": "对数损失",
}  # fmt: skip

GROUPS_ZH = {
    "early value alerts": "早盘价值提醒",
    "closing value alerts": "收盘价值提醒",
    "exchange-confirmed alerts": "交易所确认的提醒",
    "all early prices (baseline)": "全部早盘赔率（基准）",
}

METRICS_ZH = {
    "matches": "比赛数",
    "total stakes (simulated)": "总投注额（模拟）",
    "expected profit at fair prices": "按公平概率的预期利润",
    "actual profit on real results": "按真实赛果的实际利润",
    "  of which recreational bets": "  其中：普通玩家",
    "  of which sharp bets": "  其中：职业玩家",
    "matches with sharp bets": "有职业玩家下注的比赛",
    "expected profit on sharp bets": "职业玩家投注的预期利润",
    "exposure alerts (worst case below limit)": "敞口警报（最坏情况超过限额）",
    "largest worst-case loss": "单场最大潜在亏损",
}


def value(key: str, lang: str = "en") -> str:
    """Translate a categorical cell value such as 'H' or 'close'."""
    return VALUES[lang].get(key, key)


def columns(names: list[str], lang: str = "en") -> dict[str, str]:
    """Rename map for DataFrame columns (identity in English)."""
    return {n: COLUMNS_ZH.get(n, n) if lang == "zh" else n for n in names}
