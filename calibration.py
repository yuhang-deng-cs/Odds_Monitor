"""Calibration of de-vigged sharp probabilities against actual results.

Compares proportional vs power de-vig and open vs close snapshots with Brier score and
log loss (lower is better for both), plus a reliability table and one plot.
"""

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # write files only, no GUI window
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from detector import DEVIG, OUTCOMES, reference_probs  # noqa: E402

PROB_COLS = ["p_h", "p_d", "p_a"]


def brier_score(probs: list[list[float]], results: list[str]) -> float:
    """Multi-class Brier: mean over matches of sum_k (p_k - y_k)^2. 0 = perfect, 2 = worst."""
    total = 0.0
    for p, r in zip(probs, results, strict=True):
        total += sum(
            (pk - (1.0 if o == r else 0.0)) ** 2 for pk, o in zip(p, OUTCOMES, strict=True)
        )
    return total / len(results)


def log_loss(probs: list[list[float]], results: list[str]) -> float:
    """Mean of -ln(probability given to the outcome that happened). Punishes confident misses."""
    eps = 1e-15
    total = 0.0
    for p, r in zip(probs, results, strict=True):
        total += -math.log(max(p[OUTCOMES.index(r)], eps))
    return total / len(results)


def sharp_probs(odds: pd.DataFrame, method: str, snapshot: str) -> pd.DataFrame:
    """One row per match: fair H/D/A probabilities from the reference (Pinnacle -> BFE -> avg)."""
    rows = []
    sub = odds[odds["snapshot"] == snapshot]
    for match_id, group in sub.groupby("match_id", sort=True):
        prices = {r.bookmaker: (r.odds_h, r.odds_d, r.odds_a) for r in group.itertuples()}
        probs, ref = reference_probs(prices, method)
        rows.append([match_id, group["result"].iloc[0], ref, *probs])
    return pd.DataFrame(rows, columns=["match_id", "result", "reference", *PROB_COLS])


def evaluate(odds: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Score every (snapshot, method) on the SAME set of matches, plus a base-rate baseline.

    Returns (summary table, {"<snapshot>/<method>": per-match probabilities}).
    """
    preds = {
        f"{snap}/{method}": sharp_probs(odds, method, snap)
        for snap in ("open", "close")
        for method in DEVIG
    }
    # Like-for-like: keep only matches that have a reference price in every combination.
    common = set.intersection(*(set(p["match_id"]) for p in preds.values()))
    preds = {k: p[p["match_id"].isin(common)].reset_index(drop=True) for k, p in preds.items()}

    rows = []
    for key, p in preds.items():
        snap, method = key.split("/")
        probs, results = p[PROB_COLS].values.tolist(), p["result"].tolist()
        refs = p["reference"].value_counts().to_dict()
        rows.append({
            "snapshot": snap, "method": method, "n_matches": len(p),
            "brier": brier_score(probs, results), "log_loss": log_loss(probs, results),
            "references": ", ".join(f"{k}={v}" for k, v in sorted(refs.items())),
        })  # fmt: skip

    # Baseline: always predict the overall H/D/A frequencies (in-sample, so slightly flattering).
    results = next(iter(preds.values()))["result"].tolist()
    base = [results.count(o) / len(results) for o in OUTCOMES]
    rows.append({
        "snapshot": "-", "method": "base rates", "n_matches": len(results),
        "brier": brier_score([base] * len(results), results),
        "log_loss": log_loss([base] * len(results), results), "references": "none",
    })  # fmt: skip
    return pd.DataFrame(rows), preds


def reliability_table(p: pd.DataFrame, n_bins: int = 10) -> pd.DataFrame:
    """Pool all three outcomes, bin predicted probability, compare with observed frequency.

    Well calibrated means mean_predicted ~= observed_freq in every bin.
    """
    long = pd.DataFrame({
        "pred": pd.concat([p[c] for c in PROB_COLS], ignore_index=True),
        "hit": pd.concat([(p["result"] == o).astype(float) for o in OUTCOMES], ignore_index=True),
    })  # fmt: skip
    edges = [i / n_bins for i in range(n_bins + 1)]
    long["bin"] = pd.cut(long["pred"], bins=edges, include_lowest=True)
    table = long.groupby("bin", observed=True).agg(
        n=("hit", "size"), mean_predicted=("pred", "mean"), observed_freq=("hit", "mean")
    )
    return table.reset_index().assign(bin=lambda t: t["bin"].astype(str))


def plot_reliability(tables: dict[str, pd.DataFrame], path: Path) -> None:
    """Save the reliability diagram to a PNG file."""
    fig = reliability_figure(tables)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def reliability_figure(tables: dict[str, pd.DataFrame]) -> plt.Figure:
    """Reliability diagram: one line per series against the perfect-calibration diagonal."""
    colors = ["#2a78d6", "#eb6834"]  # categorical slots 1-2 of the default palette
    fig, ax = plt.subplots(figsize=(6, 6), facecolor="#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    ax.plot(
        [0, 1], [0, 1], linestyle="--", linewidth=1, color="#9a9994", label="perfect calibration"
    )
    for (label, t), color in zip(tables.items(), colors, strict=False):
        ax.plot(t["mean_predicted"], t["observed_freq"], marker="o", markersize=6,
                linewidth=2, color=color, label=label)  # fmt: skip
    ax.set(xlim=(0, 1), ylim=(0, 1), xlabel="Predicted probability (de-vigged reference)",
           ylabel="Observed frequency")  # fmt: skip
    ax.set_title("Reliability of sharp de-vigged probabilities", color="#0b0b0b", loc="left")
    ax.grid(color="#e4e3df", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors="#52514e")
    ax.legend(frameon=False, labelcolor="#52514e", loc="upper left")
    fig.tight_layout()
    return fig


def run(odds: pd.DataFrame, out_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute the summary and reliability tables, write CSVs and the plot to out_dir."""
    summary, preds = evaluate(odds)
    rel = {k: reliability_table(preds[k]) for k in ("open/power", "close/power")}
    reliability = pd.concat([t.assign(series=k) for k, t in rel.items()], ignore_index=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_dir / "calibration_summary.csv", index=False)
    reliability.to_csv(out_dir / "reliability.csv", index=False)
    plot_reliability(rel, out_dir / "calibration.png")
    return summary, reliability
