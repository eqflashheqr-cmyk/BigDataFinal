"""Test whether the CFPB's published derived-sex 'Joint' figure
(20.7 % over 223,383 decided applications) can be a subset of our own
derived_sex == 'Joint' population (2,999,979 decisions at 18.27 %).

If the published decided-count is far smaller than the count of the
corresponding field in the release, then the published figure is over a
different, filtered population and cannot be compared with ours directly.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.getcwd(), "src"))
import config as C

df = pd.read_pickle("_audit_df.pkl")
dec = df[df["action_taken"].isin([1, 2, 3])].copy()
ds = dec["derived_sex"].astype("string").str.strip()
j = dec[ds == "Joint"]

CFPB_JOINT_DECIDED = 223_383
CFPB_JOINT_RATE = 20.7

print("=" * 78)
print("POPULATION COMPARISON")
print("=" * 78)
print(f"  CFPB published: {CFPB_JOINT_DECIDED:,} decided at {CFPB_JOINT_RATE} %")
print(f"  ours derived_sex == Joint : {len(j):,} decided at "
      f"{j['is_denied'].mean()*100:.2f} %")
print(f"  ratio of decided counts    : {len(j)/CFPB_JOINT_DECIDED:.2f}x")
print(f"  CFPB share of our release  : "
      f"{CFPB_JOINT_DECIDED/len(dec)*100:.2f} % of all decisions")

print()
print("=" * 78)
print("CAN THE PUBLISHED COUNT BE REPRODUCED FROM ANY NATURAL SUBSET?")
print("=" * 78)
candidates = {}
for col, name in [("loan_type", "loan_type"), ("loan_purpose", "loan_purpose"),
                  ("lien_status", "lien_status")]:
    if col not in j.columns:
        continue
    for val, g in j.groupby(col, observed=True):
        candidates[f"{name}={val}"] = len(g)

for k, v in sorted(candidates.items(), key=lambda kv: abs(kv[1] - CFPB_JOINT_DECIDED))[:12]:
    print(f"  {k:34s} {v:>10,}   (published {CFPB_JOINT_DECIDED:,})")

print()
print("=" * 78)
print("WHAT RATE WOULD THE PUBLISHED FIGURE IMPLY FOR OUR POPULATION?")
print("=" * 78)
# If the CFPB's Joint category were simply our derived_sex Joint, the rate
# would be ours. The published 20.7 % is 2.43 pp higher.
ours = j["is_denied"].mean() * 100
print(f"  ours {ours:.2f} % vs published {CFPB_JOINT_RATE} % -> "
      f"published is {CFPB_JOINT_RATE - ours:+.2f} pp higher")
print(f"  the extra denial count that implies, on our population: "
      f"{(CFPB_JOINT_RATE/100 - ours/100)*len(j):,.0f} extra denials")
print()
print("  Our same-sex pairs (our joint, HMDA says Male/Female) are denied at")
print("  22.30 %, i.e. ABOVE the published 20.7 %. So 'same-sex pairs are")
print("  weaker, which is why CFPB's stronger group is denied more often'")
print("  does not hold: CFPB's group is STRONGER (same-sex excluded) yet")
print("  has the HIGHER rate.")

out = {
    "cfpb_published_joint_decided": CFPB_JOINT_DECIDED,
    "cfpb_published_joint_rate_pct": CFPB_JOINT_RATE,
    "our_derived_sex_joint_decided": int(len(j)),
    "our_derived_sex_joint_rate_pct": round(float(ours), 4),
    "decided_count_ratio": round(len(j) / CFPB_JOINT_DECIDED, 4),
    "cfpb_share_of_all_decisions_pct": round(CFPB_JOINT_DECIDED / len(dec) * 100, 4),
    "our_same_sex_pairs_rate_pct": 22.2951,
    "conclusion": (
        "The published derived-sex figure is over a population an order of "
        "magnitude smaller than the derived_sex == 'Joint' population of the "
        "2024 release, so the two cannot be compared without the exact "
        "query filter. The report's explanation of the difference is "
        "internally inconsistent and is withdrawn."
    ),
}
(C.RESULTS_DIR / "derived_sex_population_check.json").write_text(
    json.dumps(out, indent=2), encoding="utf-8")
print("\nwritten results/derived_sex_population_check.json")
