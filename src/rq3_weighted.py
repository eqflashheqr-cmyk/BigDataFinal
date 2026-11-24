"""Compute the 4-variable stratified weighted gap on the FULL data (RQ3), so
Table 8 can quote a gap that is on the same footing as the decomposition."""
import json
import numpy as np
import pandas as pd

d = pd.read_csv("results/rq3.csv")
print(f"strata: {len(d):,}  total decisions {d['n_decisions_total'].sum():,}")

big = d[d["n_decisions_total"] >= 100].copy()
print(f"strata with >=100 decisions: {len(big):,}")
print(f"  joint lower: {big['joint_lower'].sum()}  (True = joint rate is lower)")
print(f"  decisions covered: {big['n_decisions_total'].sum():,}")

w = big["n_decisions_total"].to_numpy(dtype=float)
gap = big["gap_pp"].to_numpy(dtype=float)

print()
print(f"unweighted mean gap            : {gap.mean():+.2f} pp")
print(f"cell-size-weighted mean gap     : {(gap*w).sum()/w.sum():+.2f} pp")
print(f"median gap                      : {np.median(gap):+.2f} pp")
print(f"decision-weighted gap           : {(gap*w).sum()/w.sum():+.2f} pp")

# joint and single decision-weighted pooled rates
nj = big["n_decisions_joint"].sum()
ns = big["n_decisions_single"].sum()
dj = (big["denial_rate_joint"] * big["n_decisions_joint"]).sum()
ds = (big["denial_rate_single"] * big["n_decisions_single"]).sum()
print()
print(f"pooled joint rate   : {dj/nj*100:.2f}%  (n={nj:,})")
print(f"pooled single rate  : {ds/ns*100:.2f}%  (n={ns:,})")
print(f"pooled gap          : {(dj/nj - ds/ns)*100:+.2f} pp")

# restrict to strata where both arms have data (no suppressed single cells)
both = big[(big["n_decisions_joint"] > 0) & (big["n_decisions_single"] > 0)]
w2 = both["n_decisions_total"].to_numpy(dtype=float)
print()
print(f"strata with BOTH arms populated: {len(both):,}")
print(f"  decision-weighted gap: {(both['gap_pp'].to_numpy()*w2).sum()/w2.sum():+.2f} pp")
print(f"  unweighted mean      : {both['gap_pp'].mean():+.2f} pp")
print(f"  decisions covered    : {both['n_decisions_total'].sum():,} of {d['n_decisions_total'].sum():,}")

# how many strata have joint rate HIGHER
print()
print(f"strata where joint rate is HIGHER: {(big['gap_pp'] > 0).sum()} of {len(big)}")
print(f"strata where joint rate is LOWER: {(big['gap_pp'] < 0).sum()}")

out = {
    "n_strata_total": int(len(d)),
    "n_strata_ge_100": int(len(big)),
    "decisions_covered": int(big["n_decisions_total"].sum()),
    "decisions_total": int(d["n_decisions_total"].sum()),
    "joint_lower_strata": int(big["joint_lower"].sum()),
    "unweighted_mean_gap_pp": float(gap.mean()),
    "cell_size_weighted_gap_pp": float((gap * w).sum() / w.sum()),
    "median_gap_pp": float(np.median(gap)),
    "pooled_joint_rate_pct": float(dj / nj * 100),
    "pooled_single_rate_pct": float(ds / ns * 100),
    "pooled_gap_pp": float((dj / nj - ds / ns) * 100),
    "n_strata_both_arms": int(len(both)),
    "both_arms_weighted_gap_pp": float((both["gap_pp"].to_numpy() * w2).sum() / w2.sum()),
    "n_strata_joint_higher": int((big["gap_pp"] > 0).sum()),
}
json.dump(out, open("results/rq3_weighted.json", "w", encoding="utf-8"), indent=1)
print("\nwritten results/rq3_weighted.json")
