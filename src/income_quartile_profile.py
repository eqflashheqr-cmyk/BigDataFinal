"""The income-quartile profile of the analysis population.

Two quantities are reported, and they are different:
  * the denial *rate* within each quartile, for each arm;
  * each quartile's *share of all denials*, which is what the financial
    interpretation turns on.

The second is the one that was mis-stated in an earlier version of the
report, which claimed that the largest group of denials is not the lowest
income.  It is: Q1 accounts for about 40.5 % of all denials.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.getcwd(), "src"))
import config as C

OUT = C.RESULTS_DIR / "income_quartile_profile.json"

df = pd.read_pickle("_audit_df.pkl")
dec = df[df["action_taken"].isin([1, 2, 3])].copy()
known = dec[dec["joint_flag"].notna()].copy()

bounds = [-np.inf, 67.0, 104.0, 164.0, np.inf]
known["q"] = pd.cut(known["income"], bins=bounds, labels=[1, 2, 3, 4])

total_denied = int(known["is_denied"].sum())
rows = []
for q, g in known.groupby("q", observed=True):
    j = g[g["joint_flag"] == 1]
    s = g[g["joint_flag"] == 0]
    n_d = int(g["is_denied"].sum())
    rows.append({
        "quartile": int(q),
        "label": {1: "Q1 (lowest)", 2: "Q2", 3: "Q3", 4: "Q4 (highest)"}[int(q)],
        "n_decisions": int(len(g)),
        "n_denied": n_d,
        "denial_rate_pct": round(float(g["is_denied"].mean()) * 100, 4),
        "share_of_all_denials_pct": round(n_d / total_denied * 100, 4),
        "joint_n": int(len(j)),
        "joint_rate_pct": round(float(j["is_denied"].mean()) * 100, 4),
        "single_n": int(len(s)),
        "single_rate_pct": round(float(s["is_denied"].mean()) * 100, 4),
        "raw_gap_pp": round(
            float(j["is_denied"].mean() - s["is_denied"].mean()) * 100, 4),
    })

# 468,164 decision records report no income, so they fall into no quartile.
# The two shares are therefore different and both are reported:
#   * share_of_all_denials_pct          -- of every denial in the analysis
#                                          population, no-income records
#                                          included in the denominator;
#   * share_of_quartiled_denials_pct    -- of the denials among the records
#                                          that do report an income.
n_no_income = int(known["income"].isna().sum())
denied_no_income = int(known.loc[known["income"].isna(), "is_denied"].sum())
quartiled_denied = sum(r["n_denied"] for r in rows)
for r in rows:
    r["share_of_quartiled_denials_pct"] = round(
        r["n_denied"] / quartiled_denied * 100, 4)

out = {
    "population": ("applications with a lender decision and a known "
                   "application type"),
    "n_decisions": int(len(known)),
    "n_denied": total_denied,
    "overall_denial_rate_pct": round(float(known["is_denied"].mean()) * 100, 4),
    "quartile_bounds_income_thousands": [67.0, 104.0, 164.0],
    "n_decisions_without_income": n_no_income,
    "n_denied_without_income": denied_no_income,
    "n_denials_in_quartiles": quartiled_denied,
    "quartiles": rows,
    "largest_share_of_denials": max(rows, key=lambda r: r["share_of_all_denials_pct"])["label"],
    "largest_share_pct": max(r["share_of_all_denials_pct"] for r in rows),
    "smallest_share_pct": min(r["share_of_all_denials_pct"] for r in rows),
    "overall_denial_rate_one_in_n": round(len(known) / total_denied, 2),
}

OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=2))
print(f"\nwritten {OUT}")
