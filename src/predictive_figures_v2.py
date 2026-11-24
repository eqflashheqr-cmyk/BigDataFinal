"""
predictive_figures_v2.py — Charts for the reworked predictive extension.

Reads the artefacts written by `src/predictive_v2.py`:

* `predictive_v2_predictions.npz` — the test-set labels and probabilities
* `predictive_v2.json`          — the metrics, calibration table and the
                                  differential-performance rows
* `predictive_v2_coefficients.csv` — the signed logistic coefficients

and produces the three figures used in the report:

* `fig7_predictive_roc_pr.png`      — ROC and precision-recall curves
* `fig8_predictive_calibration.png` — reliability diagram
* `fig9_predictive_importance.png`  — the absolute standardised
                                       coefficients, since the v1 figure
                                       was a permutation-importance plot
                                       and the v2 model was refitted

Usage
-----
    python src/predictive_figures_v2.py
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C
from figures import COLORS, _save


def fig_roc_pr() -> None:
    """ROC and precision-recall curves for the v2 model."""
    from sklearn.metrics import precision_recall_curve, roc_curve

    d = np.load(C.RESULTS_DIR / "predictive_v2_predictions.npz")
    y = d["y_true"]
    p = d["p_lr"]

    meta = json.loads((C.RESULTS_DIR / "predictive_v2.json").read_text(encoding="utf-8"))
    thr = meta["threshold_selection"]["threshold"]

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.9))

    fpr, tpr, _ = roc_curve(y, p)
    axes[0].plot(fpr, tpr, color=COLORS["accent"], linewidth=2,
                 label=f"Logistic regression (AUC {meta['test_metrics']['roc_auc']:.3f})")
    axes[0].plot([0, 1], [0, 1], linestyle="--", color="#9AA5B1", linewidth=1)
    axes[0].set_xlabel("False positive rate")
    axes[0].set_ylabel("True positive rate")
    axes[0].set_title("ROC curve", loc="left", fontweight="bold")
    axes[0].legend(frameon=False, loc="lower right", fontsize=8.5)

    prec, rec, _ = precision_recall_curve(y, p)
    axes[1].plot(rec, prec, color=COLORS["accent"], linewidth=2,
                 label=f"Logistic regression (AP {meta['test_metrics']['pr_auc']:.3f})")
    axes[1].axhline(y.mean(), linestyle="--", color="#9AA5B1", linewidth=1,
                    label=f"No-skill ({y.mean():.3f})")
    axes[1].axvline(thr, color=COLORS["gap"], linestyle=":", linewidth=1.4,
                    label=f"Chosen threshold {thr}")
    axes[1].set_xlabel("Recall")
    axes[1].set_ylabel("Precision")
    axes[1].set_title("Precision-recall curve", loc="left", fontweight="bold")
    axes[1].legend(frameon=False, loc="lower left", fontsize=8.5)

    fig.suptitle(
        "Predicting denial without using ethnicity, race, sex or tract composition",
        fontweight="bold", x=0.01, ha="left", fontsize=11.5)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save(fig, "fig7_predictive_roc_pr.png")


def fig_calibration() -> None:
    """Reliability diagram for the v2 model."""
    cal = pd.read_csv(C.RESULTS_DIR / "predictive_v2_calibration.csv")

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.9))

    ax = axes[0]
    ax.plot([0, 1], [0, 1], linestyle="--", color="#9AA5B1", linewidth=1,
            label="Perfect calibration")
    ax.plot(cal["mean_predicted"], cal["observed_rate"], "o-",
            color=COLORS["accent"], linewidth=2, markersize=6,
            label="Logistic regression")

    p = cal["observed_rate"]
    n = cal["n"].replace(0, np.nan)
    se = np.sqrt(np.clip(p * (1 - p), 1e-9, None) / n)
    ax.errorbar(cal["mean_predicted"], cal["observed_rate"], yerr=1.96 * se,
                fmt="none", ecolor="#9AA5B1", elinewidth=1, capsize=3)

    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Observed denial rate")
    ax.set_title("Reliability diagram", loc="left", fontweight="bold")
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    ax.set_xlim(0, 0.55)
    ax.set_ylim(0, 0.55)

    ax = axes[1]
    gap = (cal["observed_rate"] - cal["mean_predicted"]) * 100
    ax.bar(range(len(gap)), gap, color=COLORS["accent"], width=0.7)
    ax.axhline(0, color="#52606D", linewidth=1)
    ax.set_xticks(range(len(gap)))
    ax.set_xticklabels([str(i + 1) for i in range(len(gap))], fontsize=8)
    ax.set_xlabel("Probability decile (low to high)")
    ax.set_ylabel("Observed $-$ predicted (percentage points)")
    ax.set_title("Calibration gap by decile", loc="left", fontweight="bold")
    ax.margins(y=0.28)

    fig.suptitle("The linear model under-predicts through the middle of the range",
                 fontweight="bold", x=0.01, ha="left", fontsize=11.5)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save(fig, "fig8_predictive_calibration.png")


def fig_importance() -> None:
    """The standardised logistic coefficients, largest first."""
    coef = pd.read_csv(C.RESULTS_DIR / "predictive_v2_coefficients.csv")
    coef = coef[coef["feature"] != "Intercept"].copy()

    def pretty(name: str) -> str:
        name = name.replace("num__", "").replace("cat__", "")
        for prefix, label in [
            ("missingindicator_", "income not reported: "),
            ("loan_purpose_", "loan purpose "),
            ("applicant_credit_score_type_", "credit score type "),
            ("joint_flag_", "joint application "),
            ("construction_method_", "construction "),
            ("lien_status_", "lien status "),
            ("occupancy_type_", "occupancy "),
            ("property_ownership_", "property ownership "),
            ("loan_type_", "loan type "),
        ]:
            if name.startswith(prefix):
                return label + name[len(prefix):].replace("_", " ")
        return name.replace("_", " ")

    top = coef.reindex(coef["coefficient"].abs().sort_values(ascending=False).index)
    top = top.head(14).iloc[::-1]

    fig, axes = plt.subplots(1, 2, figsize=(9.8, 4.2))

    ax = axes[0]
    y_pos = np.arange(len(top))
    colors = [COLORS["Single"] if c < 0 else COLORS["accent"] for c in top["coefficient"]]
    ax.barh(y_pos, top["coefficient"], color=colors, height=0.72)
    ax.set_yticks(y_pos)
    ax.set_yticklabels([pretty(n) for n in top["feature"]], fontsize=8)
    ax.axvline(0, color="#52606D", linewidth=0.8)
    ax.set_xlabel("Logistic coefficient (positive = higher denial odds)")
    ax.set_title("Largest coefficients", loc="left", fontweight="bold")
    ax.margins(x=0.04)

    # ---- the same thing, aggregated by source variable -------------------
    ax = axes[1]

    def group(name: str) -> str:
        name = name.replace("num__", "").replace("cat__", "")
        if name.startswith("missingindicator_"):
            return "missingness indicators"
        for prefix, label in [
            ("loan_purpose_", "loan purpose"),
            ("applicant_credit_score_type_", "credit score type"),
            ("joint_flag_", "joint application"),
            ("construction_method_", "construction method"),
            ("lien_status_", "lien status"),
            ("occupancy_type_", "occupancy type"),
            ("property_ownership_", "property ownership"),
            ("loan_type_", "loan type"),
        ]:
            if name.startswith(prefix):
                return label
        return name

    agg = (coef.assign(group=coef["feature"].map(group))
           .groupby("group")["coefficient"].sum().sort_values(ascending=True))
    ax.barh(np.arange(len(agg)), agg.values,
            color=COLORS["Single"], height=0.72)
    ax.set_yticks(np.arange(len(agg)))
    ax.set_yticklabels(agg.index, fontsize=8.5)
    ax.axvline(0, color="#52606D", linewidth=0.8)
    ax.set_xlabel("Summed logistic coefficient")
    ax.set_title("By source variable", loc="left", fontweight="bold")
    ax.margins(x=0.04)

    fig.suptitle(
        "What the model uses - no ethnicity, race, sex or tract composition",
        fontweight="bold", x=0.01, ha="left", fontsize=11.5)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save(fig, "fig9_predictive_importance.png")


def main() -> None:
    print("Generating predictive figures (v2)...")
    fig_roc_pr()
    fig_calibration()
    fig_importance()
    print("Done.")


if __name__ == "__main__":
    main()
