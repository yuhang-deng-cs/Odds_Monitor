import math

import pandas as pd
import pytest

from calibration import brier_score, log_loss, reliability_table, run


def test_perfect_forecast_scores_zero():
    assert brier_score([[1.0, 0.0, 0.0]], ["H"]) == 0.0
    assert log_loss([[1.0, 0.0, 0.0]], ["H"]) == pytest.approx(0.0)


def test_known_values():
    probs = [[0.5, 0.3, 0.2]]
    # result D: (0.5-0)^2 + (0.3-1)^2 + (0.2-0)^2 = 0.25 + 0.49 + 0.04 = 0.78
    assert brier_score(probs, ["D"]) == pytest.approx(0.78)
    assert log_loss(probs, ["D"]) == pytest.approx(-math.log(0.3))


def test_reliability_table_bins():
    p = pd.DataFrame({"p_h": [0.65, 0.62], "p_d": [0.2, 0.22], "p_a": [0.15, 0.16],
                      "result": ["H", "D"]})  # fmt: skip
    t = reliability_table(p)
    row = t[t["bin"] == "(0.6, 0.7]"].iloc[0]
    assert row["n"] == 2 and row["observed_freq"] == 0.5
    assert t["n"].sum() == 6  # 2 matches x 3 outcomes


def test_run_writes_outputs(raw_dir, tmp_path):
    from load import load_dir

    odds = load_dir(raw_dir)
    summary, _ = run(odds, tmp_path / "reports")
    assert set(summary["method"]) == {"proportional", "power", "base rates"}
    assert (summary["n_matches"] == 3).all()  # every match has Pinnacle in both snapshots
    for name in ("calibration.png", "calibration_summary.csv", "reliability.csv"):
        assert (tmp_path / "reports" / name).exists()
