import pandas as pd
import pytest

from report import _formatted, friendly_performance, number_formats


def _perf() -> pd.DataFrame:
    return pd.DataFrame({
        "group": ["early value alerts", "closing value alerts", "exchange-confirmed alerts"],
        "n": [40, 113, 21],
        "n_clv": [40, 0, 3],
        "avg_clv": [-0.006, float("nan"), 0.049],
        "beat_close_pct": [0.6, float("nan"), 1.0],
        "roi": [0.154, -0.43, -0.447],
        "roi_ci_low": [-0.54, -0.70, -0.89],
        "roi_ci_high": [0.99, -0.06, 0.13],
    })  # fmt: skip


def test_table_columns_stay_numeric_so_sorting_is_by_value():
    table = friendly_performance(_perf())
    assert pd.api.types.is_numeric_dtype(table["Average CLV"])
    order = table.sort_values("Average CLV", ascending=False)["Average CLV"].tolist()
    assert order[:2] == pytest.approx([4.9, -0.6])  # sorted by value; missing goes last
    assert pd.isna(order[2])


def test_html_report_formats_numbers_and_missing_values():
    text = _formatted(friendly_performance(_perf()))
    assert text["Average CLV"].tolist() == ["-0.6%", "–", "+4.9%"]
    assert text["Bets with CLV"].tolist() == ["40", "0", "3"]


def test_chinese_column_names_get_the_same_formats():
    zh = friendly_performance(_perf(), lang="zh")
    assert set(number_formats("zh")) & set(zh.columns) >= {"平均 CLV", "有 CLV 的注数"}
    assert _formatted(zh)["平均 CLV"].tolist() == ["-0.6%", "–", "+4.9%"]
