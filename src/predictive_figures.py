"""
predictive_figures.py — Charts for the optional predictive extension.

Reads the artefacts written by `src/predictive.py` and produces the three
figures used in the report:

* `fig7_predictive_roc_pr.png`   — ROC and precision-recall curves
* `fig8_predictive_calibration.png` — reliability diagram
* `fig9_predictive_importance.png`  — permutation importance

Usage
-----
    python src/predictive_figures.py
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


def _save_fig(fig, name: str) -> None:
    """Save a figure to the figures directory."""
    _save(fig, name)


def fig_roc_pr() -> None:
    """ROC and precision-recall curves for both models."""
    from sklearn.metrics import precision_recall_curve, roc_curve

    d = np.load(C.RESULTS_DIR / "predictive_predictions.npz")
    y = d["y_true"]
    models = [("Logistic regression", d["p_lr"], COLORS["accent"]),
              ("Gradient boosting", d["p_gb"], COLORS["Single"])]

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.9))

    for label, p, color in models:
        fpr, tpr, _ = roc_curve(y, p)
        axes[0].plot(fpr, tpr, color=color, linewidth=2, label=label)

        prec, rec, _ = precision_recall_curve(y, p)
        axes[1].plot(rec, prec, color=color, linewidth=2, label=label)

    axes[0].plot([0, 1], [0, 1], linestyle="--", color="#9AA5B1", linewidth=1)
    axes[0].set_xlabel("False positive rate")
    axes[0].set_ylabel("True positive rate")
    axes[0].set_title("ROC curve", loc="left", fontweight="bold")
    axes[0].legend(frameon=False, loc="lower right", fontsize=9)

    axes[1].axhline(y.mean(), linestyle="--", color="#9AA5B1", linewidth=1,
                    label=f"No-skill ({y.mean():.3f})")
    axes[1].set_xlabel("Recall")
    axes[1].set_ylabel("Precision")
    axes[1].set_title("Precision-recall curve", loc="left", fontweight="bold")
    axes[1].legend(frameon=False, loc="lower left", fontsize=9)

    fig.suptitle("Predicting denial from application characteristics",
                 fontweight="bold", x=0.01, ha="left", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    _save_fig(fig, "fig7_predictive_roc_pr.png")


def fig_calibration() -> None:
    """Reliability diagram: predicted probability vs observed rate."""
    cal = pd.read_csv(C.RESULTS_DIR / "predictive_calibration.csv")

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.9))

    # ---- reliability diagram --------------------------------------------
    ax = axes[0]
    ax.plot([0, 1], [0, 1], linestyle="--", color="#9AA5B1", linewidth=1,
            label="Perfect calibration")
    ax.plot(cal["mean_predicted"], cal["observed_rate"], "o-",
            color=COLORS["accent"], linewidth=2, markersize=6,
            label="Logistic regression")

    # Standard error of the observed rate in each bin, as error bars.
    p = cal["observed_rate"]
    n = cal["n"]
    se = np.sqrt(np.clip(p * (1 - p), 1e-9, None) / n)
    ax.errorbar(cal["mean_predicted"], cal["observed_rate"], yerr=1.96 * se,
                fmt="none", ecolor="#9AA5B1", elinewidth=1, capsize=3)

    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Observed denial rate")
    ax.set_title("Reliability diagram", loc="left", fontweight="bold")
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    # ---- the calibration gap, bin by bin ---------------------------------
    ax = axes[1]
    gap = (cal["observed_rate"] - cal["mean_predicted"]) * 100
    colors = [COLORS["accent"] if g <= 0 else COLORS["accent"] for g in gap]
    ax.bar(range(len(gap)), gap, color=colors, width=0.7)
    ax.axhline(0, color="#52606D", linewidth=1)
    ax.set_xticks(range(len(gap)))
    ax.set_xticklabels([b.replace("[", "").replace(")", "").replace(", ", "\n")
                         for b in cal["bin"]], fontsize=7.5)
    ax.set_ylabel("Observed $-$ predicted (percentage points)")
    ax.set_title("Calibration gap by probability bin", loc="left", fontweight="bold")
    ax.margins(y=0.25)

    fig.suptitle("The linear model over-predicts at the top of the range",
                 fontweight="bold", x=0.01, ha="left", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    _save_fig(fig, "fig8_predictive_calibration.png")


def fig_importance() -> None:
    """Permutation importance of the primary model."""
    imp = pd.read_csv(C.RESULTS_DIR / "predictive_permutation_importance.csv")
    top = imp.head(14).iloc[::-1]

    def pretty(name: str) -> str:
        name = name.replace("num__", "").replace("cat__", "")
        for prefix, label in [
            ("missingindicator_", "reported: "),
            ("loan_purpose_", "loan purpose "),
            ("applicant_credit_score_type_", "credit score type "),
            ("applicant_ethnicity_1_", "ethnicity "),
            ("applicant_race_1_", "race "),
            ("applicant_sex_", "sex "),
            ("joint_flag_", "joint flag "),
            ("construction_method_", "construction "),
            ("lien_status_", "lien status "),
            ("occupancy_type_", "occupancy "),
        ]:
            if name.startswith(prefix):
                return label + name[len(prefix):].replace("_", " ")
        return name.replace("_", " ")

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.0))

    ax = axes[0]
    y_pos = np.arange(len(top))
    colors = [COLORS["accent"] if not n.startswith("missingindicator")
              else COLORS["accent"] for n in top["feature"]]
    ax.barh(y_pos, top["importance"], color=colors, height=0.72)
    ax.set_yticks(y_pos)
    ax.set_yticklabels([pretty(n) for n in top["feature"]], fontsize=8.5)
    ax.set_xlabel("Increase in ROC-AUC when the feature is permuted")
    ax.set_title("Permutation importance", loc="left", fontweight="bold")
    ax.margins(x=0.02)

    # ---- the same thing, aggregated by source variable --------------------
    ax = axes[1]
    def group(name: str) -> str:
        name = name.replace("num__", "").replace("cat__", "")
        if name.startswith("missingindicator_"):
            return "missingness indicators"
        for prefix, label in [
            ("loan_purpose_", "loan purpose"),
            ("applicant_credit_score_type_", "credit score"),
            ("applicant_ethnicity_1_", "ethnicity"),
            ("applicant_race_1_", "race"),
            ("applicant_sex_", "sex"),
            ("joint_flag_", "joint application"),
            ("construction_method_", "construction method"),
            ("lien_status_", "lien status"),
            ("occupancy_type_", "occupancy"),
        ]:
            if name.startswith(prefix):
                return label
        return name

    agg = (imp.assign(group=imp["feature"].map(group))
           .groupby("group")["importance"].sum().sort_values(ascending=True))
    ax.barh(np.arange(len(agg)), agg.values,
            color=COLORS["Single"], height=0.72)
    ax.set_yticks(np.arange(len(agg)))
    ax.set_yticklabels(agg.index, fontsize=8.5)
    ax.set_xlabel("Total increase in ROC-AUC")
    ax.set_title("Importance by source variable", loc="left", fontweight="bold")
    ax.margins(x=0.02)

    fig.suptitle("What the model actually uses",
                 fontweight="bold", x=0.01, ha="left", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    _save_fig(fig, "fig9_predictive_importance.png")


def main() -> None:
    print("Generating predictive figures...")
    fig_roc_pr()
    fig_calibration()
    fig_importance()
    print("Done.")


if __name__ == "__main__":
    main()


