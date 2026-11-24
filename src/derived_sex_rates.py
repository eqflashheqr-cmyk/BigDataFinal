"""A3: measure the derived_sex == 'Joint' denial rate in our own file, and the
rate of the remainder, so the report can state what the data actually shows
instead of asserting that same-sex pairs have 'the weakest credit profile'.

Also computes the rate within our own joint_flag == 1 arm, split by
derived_sex, which is the comparison the report's argument rests on.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.getcwd(), "src"))
import config as C

OUT = C.RESULTS_DIR / "derived_sex_rates.json"

df = pd.read_pickle("_audit_df.pkl")
dec = df[df["action_taken"].isin([1, 2, 3])].copy()
ds = dec["derived_sex"].astype("string").str.strip()

out = {
    "population": "applications with a lender decision (action_taken 1, 2 or 3)",
    "n_decisions": int(len(dec)),
    "n_denied": int(dec["is_denied"].sum()),
    "overall_denial_rate_pct": round(float(dec["is_denied"].mean()) * 100, 4),
    "by_derived_sex": {},
    "derived_sex_joint_vs_rest": {},
    "within_our_joint_flag": {},
}

for lab in ["Joint", "Male", "Female", "Sex Not Available"]:
    sub = dec[ds == lab]
    if len(sub) == 0:
        continue
    out["by_derived_sex"][lab] = {
        "n_decisions": int(len(sub)),
        "n_denied": int(sub["is_denied"].sum()),
        "denial_rate_pct": round(float(sub["is_denied"].mean()) * 100, 4),
    }

j = dec[ds == "Joint"]
r = dec[ds != "Joint"]
out["derived_sex_joint_vs_rest"] = {
    "joint_n": int(len(j)),
    "joint_rate_pct": round(float(j["is_denied"].mean()) * 100, 4),
    "rest_n": int(len(r)),
    "rest_rate_pct": round(float(r["is_denied"].mean()) * 100, 4),
    "gap_pp": round(float(j["is_denied"].mean() - r["is_denied"].mean()) * 100, 4),
}

# Within our own joint arm: derived_sex == 'Joint' is what HMDA's own field
# calls a joint application; the others are the same-sex pairs and the
# records HMDA could not classify.
jf1 = dec[dec["joint_flag"] == 1].copy()
jf1["ds"] = jf1["derived_sex"].astype("string").str.strip()
for lab, g in jf1.groupby("ds", observed=True):
    out["within_our_joint_flag"][lab] = {
        "n_decisions": int(len(g)),
        "n_denied": int(g["is_denied"].sum()),
        "denial_rate_pct": round(float(g["is_denied"].mean()) * 100, 4),
    }

# The comparison the report actually needs: same-sex pairs (the records our
# flag calls joint but HMDA calls Male or Female) against the rest of our
# joint arm.
same_sex = jf1[jf1["ds"].isin(["Male", "Female"])]
not_same_sex = jf1[jf1["ds"] != "Sex Not Available"]
out["same_sex_pairs"] = {
    "definition": ("records this report calls joint that HMDA's own "
                   "derived_sex field calls Male or Female"),
    "n_decisions": int(len(same_sex)),
    "n_denied": int(same_sex["is_denied"].sum()),
    "denial_rate_pct": round(float(same_sex["is_denied"].mean()) * 100, 4),
    "rest_of_joint_arm_n": int(len(not_same_sex)),
    "rest_of_joint_arm_rate_pct": round(float(not_same_sex["is_denied"].mean()) * 100, 4),
}

OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=2))
print(f"\nwritten {OUT}")
