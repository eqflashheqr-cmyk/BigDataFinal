"""
figures.py — Generate the charts used in the report.

All figures are produced from the result files in `results/`, so they are
reproducible without re-running the analysis.

    fig1_denial_rate_by_joint.png     RQ1 — the headline comparison
    fig2_financial_profile.png        RQ2 — income / loan amount / LTI
    fig3_denial_by_income_dti.png      RQ3 — stratified denial rates
    fig4_gap_by_purpose_state.png     RQ4 — where the gap is widest
    fig5_benchmark_scaling.png        performance comparison
    fig6_missingness.png              data-quality overview

Usage
-----
    python src/figures.py
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C

# --------------------------------------------------------------------------
# Style
# --------------------------------------------------------------------------

COLORS = {
    "Joint": "#2E86AB",
    "Single": "#E4572E",
    "gap": "#8D99AE",
    "accent": "#1B998B",
    "neutral": "#6C757D",
}

plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 150,
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "-",
    "axes.axisbelow": True,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})

DPI = 160


def _save(fig, name: str) -> None:
    path = C.FIGURES_DIR / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  written: figures/{name}")


# --------------------------------------------------------------------------
# Figure 1 — RQ1: denial rate by joint_flag
# --------------------------------------------------------------------------

def fig1() -> None:
    df = pd.read_csv(C.RESULTS_DIR / "rq1.csv")
    df = df.sort_values("denial_rate")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))

    # -- left: bar chart of the denial rates
    ax = axes[0]
    bars = ax.bar(df["joint_label"], df["denial_rate"] * 100,
                  color=[COLORS[l] for l in df["joint_label"]], width=0.55)
    for b, v, n in zip(bars, df["denial_rate"] * 100, df["n_denied"]):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.6,
                f"{v:.2f}%", ha="center", va="bottom", fontweight="bold", fontsize=11)
    ax.set_ylabel("Denial rate (%)")
    ax.set_xlabel("Application type")
    ax.set_title("RQ1 — Denial rate by application type", loc="left", fontweight="bold")
    ax.set_ylim(0, max(df["denial_rate"] * 100) * 1.22)

    # -- right: the decision funnel
    ax = axes[1]
    counts = pd.read_csv(C.RESULTS_DIR / "equivalence_report.json") if False else None
    labels = ["Joint", "Single"]
    for i, label in enumerate(labels):
        row = df[df["joint_label"] == label].iloc[0]
        ax.barh(i, row["n_decisions"], color=COLORS[label], height=0.5, label=label)
        ax.text(row["n_decisions"] + 40000, i,
                f"{row['n_decisions']:,} decisions\n{row['n_denied']:,} denied",
                va="center", fontsize=9)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_xlabel("Records with a lender decision (O + A + D)")
    ax.set_title("Analysis population", loc="left", fontweight="bold")
    ax.set_xlim(0, df["n_decisions"].max() * 1.55)

    fig.suptitle("Joint applications are denied less often than single applications "
                 "(HMDA 2024, 8.65M lender decisions)",
                 fontsize=12, fontweight="bold", y=1.04)
    _save(fig, "fig1_denial_rate_by_joint.png")


# --------------------------------------------------------------------------
# Figure 2 — RQ2: financial profile
# --------------------------------------------------------------------------

def fig2() -> None:
    df = pd.read_csv(C.RESULTS_DIR / "rq2.csv")
    variables = [
        ("income_dollars", "Income (USD)", 1000),
        ("loan_amount", "Loan amount (USD)", 1000),
        ("loan_to_income_ratio", "Loan-to-income ratio", 1),
        ("interest_rate", "Interest rate (%)", 1),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for ax, (var, title, scale) in zip(axes.flat, variables):
        sub = df[df["variable"] == var].set_index("joint_label")
        labels = ["Joint", "Single"]
        means = [sub.loc[l, "mean"] / scale for l in labels]
        medians = [sub.loc[l, "median"] / scale for l in labels]
        x = np.arange(len(labels))
        w = 0.34

        b1 = ax.bar(x - w / 2, means, w, color=[COLORS[l] for l in labels],
                    alpha=0.55, label="Mean")
        b2 = ax.bar(x + w / 2, medians, w, color=[COLORS[l] for l in labels],
                    label="Median")
        for b in list(b1) + list(b2):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                    f"{b.get_height():,.2f}", ha="center", va="bottom", fontsize=8.5)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_title(title, loc="left", fontweight="bold")
        ax.legend(frameon=False, fontsize=9)
        ax.margins(y=0.18)

    fig.suptitle("RQ2 — Financial profile of joint vs single applications",
                 fontsize=13, fontweight="bold", y=1.01)
    fig.tight_layout()
    _save(fig, "fig2_financial_profile.png")


# --------------------------------------------------------------------------
# Figure 3 — RQ3: stratified denial rates
# --------------------------------------------------------------------------

def fig3() -> None:
    df = pd.read_csv(C.RESULTS_DIR / "rq3.csv")
    # keep only cells with enough decisions to be meaningful
    df = df[~df["suppressed_small_cell"].astype(str).str.lower().isin(["true"])]
    df = df[df["n_decisions_total"] >= 100]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.4))

    # -- left: by income quartile
    ax = axes[0]
    g = df.groupby("income_quartile").agg(
        j=("denial_rate_joint", "mean"), s=("denial_rate_single", "mean"),
        n=("n_decisions_total", "sum")).reset_index()
    order = ["Q1 (lowest)", "Q2", "Q3", "Q4 (highest)", "Not reported"]
    g = g.set_index("income_quartile").reindex([o for o in order if o in g.index]).reset_index()
    x = np.arange(len(g))
    ax.bar(x - w_ / 2, g["j"] * 100, w_, color=COLORS["Joint"], label="Joint")
    ax.bar(x + w_ / 2, g["s"] * 100, w_, color=COLORS["Single"], label="Single")
    for i in range(len(g)):
        gap = (g.loc[i, "s"] - g.loc[i, "j"]) * 100
        ax.plot([i - w_ / 2, i + w_ / 2], [g.loc[i, "s"] * 100, g.loc[i, "s"] * 100],
                color=COLORS["gap"], lw=1.2, zorder=0)
        ax.text(i, max(g.loc[i, "j"], g.loc[i, "s"]) * 100 + 1.2,
                f"gap {gap:.1f} pp", ha="center", fontsize=8.5, color=COLORS["gap"],
                fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(g["income_quartile"], rotation=12)
    ax.set_ylabel("Denial rate (%)")
    ax.set_title("By income quartile", loc="left", fontweight="bold")
    ax.legend(frameon=False)
    ax.margins(y=0.20)

    # -- right: by DTI band
    ax = axes[1]
    g2 = df[df["dti_band"] != "Not reported"].groupby("dti_band").agg(
        j=("denial_rate_joint", "mean"), s=("denial_rate_single", "mean"),
        n=("n_decisions_total", "sum")).reset_index()
    g2 = g2[g2["n"] >= 500].sort_values("j")
    x = np.arange(len(g2))
    ax.bar(x - w_ / 2, g2["j"] * 100, w_, color=COLORS["Joint"], label="Joint")
    ax.bar(x + w_ / 2, g2["s"] * 100, w_, color=COLORS["Single"], label="Single")
    for i in range(len(g2)):
        gap = (g2.loc[i, "s"] - g2.loc[i, "j"]) * 100
        ax.text(i, max(g2.loc[i, "j"], g2.loc[i, "s"]) * 100 + 1.0,
                f"{gap:.1f}", ha="center", fontsize=8, color=COLORS["gap"],
                fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(g2["dti_band"], rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Denial rate (%)")
    ax.set_title("By debt-to-income band", loc="left", fontweight="bold")
    ax.legend(frameon=False)
    ax.margins(y=0.20)

    fig.suptitle("RQ3 — The denial-rate gap persists within income and DTI strata",
                 fontsize=13, fontweight="bold", y=1.02)
    fig.tight_layout()
    _save(fig, "fig3_denial_by_income_dti.png")


w_ = 0.36


# --------------------------------------------------------------------------
# Figure 4 — RQ4: gap by loan purpose and state
# --------------------------------------------------------------------------

def fig4() -> None:
    df = pd.read_csv(C.RESULTS_DIR / "rq4.csv")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    for ax, dim, title in [(axes[0], "loan_purpose", "By loan purpose"),
                           (axes[1], "state", "By state (top 5 by applications)")]:
        sub = df[df["dimension"] == dim].copy()
        sub = sub.sort_values("gap_pp")
        y = np.arange(len(sub))
        h = 0.34
        ax.barh(y + h / 2, sub["denial_rate_joint"] * 100, h,
                color=COLORS["Joint"], label="Joint")
        ax.barh(y - h / 2, sub["denial_rate_single"] * 100, h,
                color=COLORS["Single"], label="Single")
        for i in range(len(sub)):
            gap = sub.iloc[i]["gap_pp"]
            ax.text(max(sub.iloc[i]["denial_rate_joint"], sub.iloc[i]["denial_rate_single"]) * 100 + 1.5,
                    i, f"{gap:.1f} pp", va="center", fontsize=9,
                    color=COLORS["gap"], fontweight="bold")
        ax.set_yticks(y)
        ax.set_yticklabels(sub["level"], fontsize=9)
        ax.set_xlabel("Denial rate (%)")
        ax.set_title(title, loc="left", fontweight="bold")
        ax.legend(frameon=False, loc="lower right")
        ax.set_xlim(0, max(sub[["denial_rate_joint", "denial_rate_single"]].max()) * 118)

    fig.suptitle("RQ4 — The joint-application advantage appears in every loan purpose "
                 "and every top-5 state",
                 fontsize=13, fontweight="bold", y=1.02)
    fig.tight_layout()
    _save(fig, "fig4_gap_by_purpose_state.png")


# --------------------------------------------------------------------------
# Figure 5 — benchmark
# --------------------------------------------------------------------------

def fig5() -> None:
    p = C.RESULTS_DIR / "benchmark_results.csv"
    if not p.exists():
        print("  skipped: fig5 (no benchmark results)")
        return
    df = pd.read_csv(p)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))

    ax = axes[0]
    df["frac_num"] = df["fraction"].str.rstrip("%").astype(float)
    for engine, marker in [("pandas", "o"), ("pyspark", "s")]:
        sub = df[df["engine"] == engine].sort_values("frac_num")
        ax.plot(sub["rows_cleaned"] / 1e6, sub["total_s"], marker=marker,
                linewidth=2, label=engine, color=COLORS.get(engine, COLORS["accent"]))
        for _, r in sub.iterrows():
            ax.annotate(f"{r['total_s']:.0f}s", (r["rows_cleaned"] / 1e6, r["total_s"]),
                        textcoords="offset points", xytext=(6, 6), fontsize=8.5)
    ax.set_xlabel("Rows processed (millions)")
    ax.set_ylabel("Total pipeline time (seconds)")
    ax.set_title("End-to-end pipeline time", loc="left", fontweight="bold")
    ax.legend(frameon=False)
    ax.margins(x=0.15, y=0.2)

    ax = axes[1]
    # `fraction` is stored as a percentage string; convert it back to a number
    # so that the pivot table sorts correctly.
    df["frac_num"] = df["fraction"].str.rstrip("%").astype(float)
    piv = df.pivot(index="frac_num", columns="engine", values="rows_per_second")
    piv = piv.sort_index()
    x = np.arange(len(piv))
    w = 0.36
    ax.bar(x - w / 2, piv["pandas"], w, color="#E07A5F", label="pandas")
    ax.bar(x + w / 2, piv["pyspark"], w, color="#3D5A80", label="pyspark")
    for i, fr in enumerate(piv.index):
        ax.text(i - w / 2, piv["pandas"].iloc[i], f"{piv['pandas'].iloc[i]:,.0f}",
                ha="center", va="bottom", fontsize=8.5)
        ax.text(i + w / 2, piv["pyspark"].iloc[i], f"{piv['pyspark'].iloc[i]:,.0f}",
                ha="center", va="bottom", fontsize=8.5)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(f)}%" for f in piv.index])
    ax.set_ylabel("Throughput (rows / second)")
    ax.set_title("Throughput", loc="left", fontweight="bold")
    ax.legend(frameon=False)
    ax.margins(y=0.22)

    fig.suptitle("Performance benchmark — Spark scales better than Pandas",
                 fontsize=13, fontweight="bold", y=1.02)
    fig.tight_layout()
    _save(fig, "fig5_benchmark_scaling.png")


# --------------------------------------------------------------------------
# Figure 6 — data quality
# --------------------------------------------------------------------------

def fig6() -> None:
    p = C.RESULTS_DIR / "equivalence_report.json"
    if not p.exists():
        print("  skipped: fig6 (no equivalence report)")
        return
    import json
    rep = json.loads(p.read_text(encoding="utf-8"))
    miss = rep["comparisons"][1]["pandas"]

    order = sorted(miss.items(), key=lambda kv: -kv[1])
    labels = [k for k, _ in order]
    values = [v for _, v in order]
    colors = [COLORS["accent"] if v == 0 else "#C1666B" for v in values]

    fig, ax = plt.subplots(figsize=(11, 5.4))
    y = np.arange(len(labels))
    ax.barh(y, values, color=colors, height=0.6)
    for i, v in enumerate(values):
        ax.text(v + max(values) * 0.01, i, f"{v:,}", va="center", fontsize=8.5)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Records with a missing value")
    ax.set_title("Missing values in the cleaned dataset (12,251,439 records)",
                 loc="left", fontweight="bold")
    ax.invert_yaxis()
    ax.margins(x=0.12)
    _save(fig, "fig6_missingness.png")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

FIGURES = [fig1, fig2, fig3, fig4, fig5, fig6]


def main() -> None:
    print("Generating figures...")
    for fn in FIGURES:
        try:
            fn()
        except Exception as exc:  # keep going if one figure fails
            print(f"  !! {fn.__name__} failed: {exc}")
    print("Done.")


if __name__ == "__main__":
    main()
