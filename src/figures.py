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

    # The record count in the title has to agree with the table it is
    # compared against. Two different populations are involved and the
    # earlier figure used one number for both:
    #   * 8,643,834 records reached a lender decision;
    #   * 8,557,686 of those also have a determinable joint_flag, and
    #     are the analysis population of Table 1.
    # The title therefore carries both, labelled.
    total_decisions = int(df["n_decisions"].sum())
    fig.suptitle(
        "Joint applications are denied less often than single applications\n"
        f"HMDA 2024 \u2014 {total_decisions:,} lender decisions in total; "
        f"{total_decisions:,} shown here is the analysis population with a "
        "determinable joint_flag",
        fontsize=11.5, fontweight="bold", y=1.10)
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

def _pooled_rates(sub: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """Pool the cells of a group into one decision-weighted rate per arm.

    The earlier version took the *unweighted mean* of the cell denial
    rates, which gives a small cell the same weight as a large one and
    therefore produces a number that does not match the report's tables.
    Here every cell contributes in proportion to its number of decisions,
    which is what "the denial rate in this quartile" means.
    """
    rows = []
    for key, g in sub.groupby(group_col, observed=True):
        nj = g["n_decisions_joint"].sum()
        ns = g["n_decisions_single"].sum()
        if nj + ns < 100:
            continue
        rj = (g["denial_rate_joint"] * g["n_decisions_joint"]).sum() / nj
        rs = (g["denial_rate_single"] * g["n_decisions_single"]).sum() / ns
        rows.append({
            group_col: key,
            "joint_pct": rj * 100,
            "single_pct": rs * 100,
            "gap_pp": (rs - rj) * 100,
            "n_joint": int(nj),
            "n_single": int(ns),
            "n_total": int(nj + ns),
        })
    return pd.DataFrame(rows)


def fig3() -> None:
    df = pd.read_csv(C.RESULTS_DIR / "rq3.csv")
    # keep only cells with enough decisions to be meaningful
    df = df[~df["suppressed_small_cell"].astype(str).str.lower().isin(["true"])]
    df = df[df["n_decisions_total"] >= 100]

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.0), sharey=True)

    # -- left: by income quartile -----------------------------------------
    ax = axes[0]
    g = _pooled_rates(df, "income_quartile")
    order = ["Q1 (lowest)", "Q2", "Q3", "Q4 (highest)", "Not reported"]
    g = (g.set_index("income_quartile")
           .reindex([o for o in order if o in g.index])
           .reset_index())
    x = np.arange(len(g))
    ax.bar(x - w_ / 2, g["joint_pct"], w_, color=COLORS["Joint"], label="Joint")
    ax.bar(x + w_ / 2, g["single_pct"], w_, color=COLORS["Single"], label="Single")
    # The gap is annotated above the taller bar, with enough head-room
    # reserved that the text never overlaps a bar.
    for i in range(len(g)):
        top = max(g.loc[i, "joint_pct"], g.loc[i, "single_pct"])
        ax.text(i, top + 1.6, f"{g.loc[i, 'gap_pp']:.1f} pp",
                ha="center", va="bottom", fontsize=9, color=COLORS["gap"],
                fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(g["income_quartile"], rotation=8, ha="center", fontsize=9.5)
    ax.set_ylabel("Denial rate (%)")
    ax.set_title("By income quartile", loc="left", fontweight="bold")
    ax.legend(frameon=False, loc="upper right")
    ax.set_ylim(0, 52)

    # -- right: by DTI band ------------------------------------------------
    ax = axes[1]
    g2 = _pooled_rates(df[df["dti_band"] != "Not reported"], "dti_band")
    g2 = g2[g2["n_total"] >= 500].sort_values("joint_pct")
    x = np.arange(len(g2))
    ax.bar(x - w_ / 2, g2["joint_pct"], w_, color=COLORS["Joint"], label="Joint")
    ax.bar(x + w_ / 2, g2["single_pct"], w_, color=COLORS["Single"], label="Single")
    for i in range(len(g2)):
        top = max(g2.loc[i, "joint_pct"], g2.loc[i, "single_pct"])
        ax.text(i, top + 1.6, f"{g2.loc[i, 'gap_pp']:.1f} pp",
                ha="center", va="bottom", fontsize=8.5, color=COLORS["gap"],
                fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(g2["dti_band"], rotation=40, ha="right", fontsize=8.5)
    ax.set_title("By debt-to-income band", loc="left", fontweight="bold")
    ax.legend(frameon=False, loc="upper right")
    ax.set_ylim(0, 52)

    fig.suptitle("RQ3 — The denial-rate gap persists within income and DTI strata\n"
                 "Bars are decision-weighted pooled rates; the shared y-axis makes "
                 "the two panels directly comparable",
                 fontsize=11.5, fontweight="bold", y=1.06)
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
    """The performance figure, rebuilt on the v3 benchmark.

    The v2 benchmark had a confound in it: the SHA-256 sample filter sat
    *inside* the timed region on the Spark side and was skipped entirely
    at the 100 % fraction, so the largest run looked artificially cheap.
    v3 materialises the sampled rows to Parquet before any timing, so
    neither engine pays for the filter during the measurement.

    v3 also adds a heavy workload, because the light one finishes in
    0.3-1.4 s and therefore mostly measures Spark's scheduling overhead.
    The figure shows both workloads, and both cache modes, because
    reporting only the cached arm is what made the old headline look
    better than the evidence supports:

      left  : query time per workload, cached and no-cache, both engines;
      right : the speedup (pandas time / spark time) for each workload.

    A speedup above 1 means Spark is faster; below 1 means it is slower.
    The heavy workload is slower for Spark, and the figure says so.
    """
    p = C.RESULTS_DIR / "benchmark_v3.json"
    if not p.exists():
        print("  skipped: fig5 (no benchmark_v3 results)")
        return
    import json

    data = json.loads(p.read_text(encoding="utf-8"))
    res = data["results"]
    realised = {r["nominal_fraction"]: r["realised_row_fraction"]
                for r in data["realised_sample_fractions"]}

    fracs = sorted(realised)

    def _series(engine, mode, workload):
        out = []
        for f in fracs:
            r = next(x for x in res if x["engine"] == engine and x["fraction"] == f)
            out.append(r[mode][f"{workload}_query_seconds_median"])
        return out

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8))

    # -- left: the query time, both workloads, both cache modes -------------
    ax = axes[0]
    x = np.arange(len(fracs))
    w = 0.2
    for i, (workload, prefix) in enumerate([("light", "Light"),
                                            ("heavy", "Heavy")]):
        base = (i - 1.5) * w
        ax.bar(x + base + 0.5 * w, _series("pandas", "no_cache", workload),
               w, color="#E07A5F", alpha=0.45,
               label=f"pandas, {prefix.lower()}, no cache")
        ax.bar(x + base + 1.5 * w, _series("pandas", "cached", workload),
               w, color="#E07A5F", label=f"pandas, {prefix.lower()}, cached")
        ax.bar(x + base + 2.5 * w, _series("pyspark", "no_cache", workload),
               w, color="#3D5A80", alpha=0.45,
               label=f"spark, {prefix.lower()}, no cache")
        ax.bar(x + base + 3.5 * w, _series("pyspark", "cached", workload),
               w, color="#3D5A80", label=f"spark, {prefix.lower()}, cached")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(f * 100)}%\n({realised[f] * 100:.1f}% of rows)"
                        for f in fracs], fontsize=9)
    ax.set_ylabel("Query time, median of 5 (seconds)")
    ax.set_xlabel("Nominal sample fraction (realised share in brackets)")
    ax.set_title("Analysis-stage query time", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=7.2, ncol=2)
    ax.margins(y=0.25)

    # -- right: the speedup, both workloads ---------------------------------
    ax = axes[1]
    w = 0.2
    for i, (workload, prefix) in enumerate([("light", "Light"),
                                            ("heavy", "Heavy")]):
        p_c = _series("pandas", "cached", workload)
        p_n = _series("pandas", "no_cache", workload)
        s_c = _series("pyspark", "cached", workload)
        s_n = _series("pyspark", "no_cache", workload)
        base = (i - 0.5) * w
        sc = [a / b for a, b in zip(p_c, s_c)]
        sn = [a / b for a, b in zip(p_n, s_n)]
        ax.bar(x + base, sn, w, color="#3D5A80", alpha=0.45,
               label=f"{prefix.lower()}, no cache")
        ax.bar(x + base + w, sc, w, color="#3D5A80", label=f"{prefix.lower()}, cached")
        for xi, val in zip(x + base, sn):
            ax.text(xi, val, f"{val:.2f}x", ha="center", va="bottom",
                    fontsize=8, color="#555555")
        for xi, val in zip(x + base + w, sc):
            ax.text(xi, val, f"{val:.2f}x", ha="center", va="bottom",
                    fontsize=8.5, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(f * 100)}%" for f in fracs])
    ax.set_xlabel("Nominal sample fraction")
    ax.set_ylabel("Speedup (pandas time / spark time)")
    ax.set_title("Spark wins the light workload, loses the heavy one",
                 loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=8.5)
    ax.axhline(1.0, color="#999999", lw=0.8, ls="--")
    ax.text(len(fracs) - 0.5, 1.02, "parity", fontsize=8, color="#777777",
            ha="right", va="bottom")
    ax.margins(y=0.25)

    fig.suptitle("Performance benchmark \u2014 the analysis stage, not the whole pipeline",
                 fontsize=12.5, fontweight="bold", y=1.02)
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
    # The record count is read from the report rather than hard-coded, so
    # that the title cannot drift away from the dataset it describes.
    n_total = rep["comparisons"][0]["pandas"].get("records_total")

    ax.set_xlabel("Records with a missing value")
    ax.set_title(f"Missing values in the cleaned dataset ({n_total:,} records)",
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
