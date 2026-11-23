"""
purpose_cell_test.py — is the "Not applicable" loan-purpose cell really
noise?

The report calls the one cell in which joint applications are denied
\emph{more} often than single applications --- loan purpose "Not
applicable", 3,245 decisions, a gap of +9.35 pp --- "small enough to be
noise".  That is an assertion without a test, and the gap is large
enough that it may not be noise at all.

This script tests it.  For each loan purpose it computes the two-proportion
z-test of the difference between the joint and single denial rates, with
the standard error of the difference estimated from the pooled
proportion, and it reports a two-sided p-value and a 95% confidence
interval for the gap.

It also reports what the gap would look like if the same difference in
proportions had arisen by chance in a cell of the same size, and it
applies a multiple-comparison correction across the six purposes
(Holm), because testing six cells and quoting one unadjusted p-value
would overstate the evidence.

Output
------
    results/purpose_cell_test.json
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C

OUT_JSON = C.RESULTS_DIR / "purpose_cell_test.json"


def _two_proportion_z(n1: int, x1: int, n2: int, x2: int) -> dict:
    """Two-proportion z-test for p1 - p2."""
    p1 = x1 / n1 if n1 else float("nan")
    p2 = x2 / n2 if n2 else float("nan")
    gap = p1 - p2
    pooled = (x1 + x2) / (n1 + n2) if (n1 + n2) else float("nan")
    se_pooled = np.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2)) if n1 and n2 else float("nan")
    z = gap / se_pooled if se_pooled and se_pooled > 0 else float("nan")
    # unpooled standard error, used for the confidence interval
    se_unpooled = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2) if n1 and n2 else float("nan")
    from math import erf, sqrt
    pval = 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2)))) if np.isfinite(z) else float("nan")
    return {
        "rate_joint": p1,
        "rate_single": p2,
        "gap_pp": gap * 100,
        "z": z,
        "p_value": float(pval),
        "ci95_low_pp": (gap - 1.96 * se_unpooled) * 100,
        "ci95_high_pp": (gap + 1.96 * se_unpooled) * 100,
        "significant_at_5pct": bool(np.isfinite(z) and pval < 0.05),
    }


def _holm(pvals: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, order preserved."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        val = min(1.0, (m - rank) * pvals[i])
        running = max(running, val)
        adj[i] = running
    return adj


def main() -> None:
    import glob

    files = sorted(glob.glob(str(C.CLEAN_PARQUET / "*.parquet")))
    df = pd.read_parquet(files[0], columns=["loan_purpose", "joint_flag",
                                             "action_taken"])
    df = df[df["action_taken"].isin([1, 2, 3]) & df["joint_flag"].notna()]
    print(f"{len(df):,} decision records with a known joint flag")

    df["is_denied"] = (df["action_taken"] == 3).astype(int)
    df["is_joint"] = (df["joint_flag"] == 1).astype(int)

    rows = []
    for purpose, g in df.groupby("loan_purpose", observed=True):
        gj = g[g["is_joint"] == 1]
        gs = g[g["is_joint"] == 0]
        n1, x1 = len(gj), int(gj["is_denied"].sum())
        n2, x2 = len(gs), int(gs["is_denied"].sum())
        if n1 < 5 or n2 < 5:
            continue
        res = _two_proportion_z(n1, x1, n2, x2)
        res["loan_purpose"] = str(purpose)
        res["n_joint"] = n1
        res["n_single"] = n2
        res["n_denied_joint"] = x1
        res["n_denied_single"] = x2
        rows.append(res)

    rows.sort(key=lambda r: r["loan_purpose"])
    adj = _holm([r["p_value"] for r in rows])
    for r, a in zip(rows, adj):
        r["p_value_holm_adjusted"] = a
        r["significant_at_5pct_after_holm"] = bool(a < 0.05)

    # ---- what would "noise" look like? -----------------------------------
    # For the smallest cell, how many standard errors would a +9.35 pp gap
    # have to be to be surprising?
    na = next((r for r in rows if r["loan_purpose"] == "Not applicable"), None)
    context = {}
    if na:
        # a cell of the same size drawn from the overall rates
        overall_j = df[df["is_joint"] == 1]["is_denied"].mean()
        overall_s = df[df["is_joint"] == 0]["is_denied"].mean()
        context = {
            "smallest_cell_n_joint": na["n_joint"],
            "smallest_cell_n_single": na["n_single"],
            "overall_joint_rate": overall_j,
            "overall_single_rate": overall_s,
            "expected_gap_if_pure_noise_pp": (overall_j - overall_s) * 100,
            "observed_gap_pp": na["gap_pp"],
            "note": ("The 'Not applicable' cell is the one loan purpose "
                     "that does not correspond to a real transaction: the "
                     "purpose is not reported.  Its composition is "
                     "therefore not comparable with the other five cells, "
                     "and the gap cannot be read as a behavioural "
                     "difference at all."),
        }

    out = {
        "population": {
            "n_decision_records": int(len(df)),
            "n_purposes_tested": len(rows),
        },
        "purpose_cells": rows,
        "not_applicable_context": context,
        "note": (
            "Holm correction across the six purposes, because testing six "
            "cells and quoting one unadjusted p-value would overstate the "
            "evidence."
        ),
    }

    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    print()
    print("=" * 78)
    print("LOAN PURPOSE CELLS: two-proportion z-test")
    print("=" * 78)
    print(f"{'purpose':<26s}{'n_joint':>9s}{'n_single':>9s}"
          f"{'gap pp':>9s}{'z':>8s}{'p':>10s}{'p(Holm)':>10s}")
    for r in rows:
        print(f"{r['loan_purpose']:<26s}{r['n_joint']:>9,d}{r['n_single']:>9,d}"
              f"{r['gap_pp']:>9.2f}{r['z']:>8.2f}{r['p_value']:>10.2e}"
              f"{r['p_value_holm_adjusted']:>10.2e}")
    print("=" * 78)
    print(f"Written: {OUT_JSON}")


if __name__ == "__main__":
    main()
