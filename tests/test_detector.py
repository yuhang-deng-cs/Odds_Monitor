import pandas as pd
import pytest

from detector import arbitrage_alert, detect, reference_probs, value_alerts


def test_synthetic_arbitrage_is_flagged():
    # best prices: H 2.30 (X), D 3.90 (Y), A 3.60 (Y) -> 0.4348 + 0.2564 + 0.2778 = 0.969 < 1
    prices = {"X": (2.30, 3.30, 3.00), "Y": (2.00, 3.90, 3.60)}
    arb = arbitrage_alert(prices)
    assert arb is not None
    assert arb["bookmaker"] == "H:X@2.3|D:Y@3.9|A:Y@3.6"
    assert arb["edge"] == pytest.approx(1 / (1 / 2.30 + 1 / 3.90 + 1 / 3.60) - 1)


def test_normal_market_is_not_arbitrage():
    # best prices 2.10 / 3.40 / 3.50 -> sum of implied probs 1.056 > 1
    assert arbitrage_alert({"X": (2.10, 3.30, 3.40), "Y": (2.05, 3.40, 3.50)}) is None


def test_exchange_is_ignored_for_arbitrage():
    # The exchange's pre-commission price would create a fake arb with X
    prices = {"X": (2.30, 3.30, 3.00), "Betfair Exchange": (2.00, 3.90, 3.60)}
    assert arbitrage_alert(prices) is None


def test_mispriced_bookmaker_is_flagged():
    prices = {
        "Pinnacle": (2.00, 3.50, 4.00),
        "Bet365": (1.95, 3.40, 3.80),  # normal margin vs Pinnacle: no alert
        "BadBook": (1.95, 3.40, 5.00),  # away price far too generous
    }
    alerts = value_alerts(prices, threshold=0.03)
    assert [(a["bookmaker"], a["outcome"]) for a in alerts] == [("BadBook", "A")]
    assert alerts[0]["reference"] == "Pinnacle"
    assert alerts[0]["edge"] > 0.15


def test_threshold_is_configurable():
    prices = {"Pinnacle": (2.00, 3.50, 4.00), "BadBook": (1.95, 3.40, 5.00)}
    assert value_alerts(prices, threshold=0.50) == []


def test_reference_fallback_order():
    _, ref = reference_probs({"Betfair Exchange": (2.0, 3.6, 4.2), "Bet365": (1.9, 3.4, 4.0)})
    assert ref == "Betfair Exchange"
    probs, ref = reference_probs({"A": (2.0, 3.4, 3.8), "B": (1.9, 3.5, 4.0)})
    assert ref == "market_average"
    assert sum(probs) == pytest.approx(1.0)


def _frame(rows):
    cols = ["bookmaker", "odds_h", "odds_d", "odds_a"]
    df = pd.DataFrame(rows, columns=cols)
    return df.assign(match_id="m1", match_date="2025-01-01", home="X", away="Y", snapshot="close")


def test_detect_end_to_end_with_dedupe():
    rows = [
        ("Pinnacle", 2.00, 3.50, 4.00),
        ("BadBook", 1.95, 3.40, 5.00),
        ("BadBook", 1.95, 3.40, 5.00),  # duplicated feed row
    ]
    alerts = detect(_frame(rows))
    # The duplicated row yields ONE value alert. BadBook's 5.00 combined with Pinnacle's H and D
    # prices is also a genuine arb: 1/2.00 + 1/3.50 + 1/5.00 = 0.986 < 1.
    got = sorted(alerts[["alert_type", "bookmaker", "outcome"]].itertuples(index=False, name=None))
    assert got == [
        ("arbitrage", "H:Pinnacle@2.0|D:Pinnacle@3.5|A:BadBook@5.0", "ALL"),
        ("value", "BadBook", "A"),
    ]
