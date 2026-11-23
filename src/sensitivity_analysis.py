"""
sensitivity_analysis.py — Two robustness checks the instructor asked for.

Check 1: the `income = 999,999,999` sentinel
-------------------------------------------
The original report called extreme income values "genuine outliers" and
implied that removing them would shrink the denial gap. That was an
assertion without evidence, and the value itself is suspicious: HMDA
reports `income` in thousands of USD, so 999,999,999 is about one trillion
dollars. That is not an outlier, it is almost certainly a special code or
a data-entry artefact.

This script therefore *flags* the value rather than deleting it, and then
measures what changes under three treatments:

  A. as-is               (the value is kept, as in the original analysis)
  B. set to missing      (the value is treated as not reported)
  C. capped at p99.9     (the value is winsorised at the 99.9th percentile)

For each treatment the joint-vs-single denial gap, the median income and
the median loan-to-income ratio are recomputed. If the gap barely moves,
the original conclusion is robust and the report can say so with numbers
instead of assertions.

Check 2: the lien and equity claims
----------------------------------
The report claimed that home-improvement loans are "unsecured in substance"
and that home-purchase loans "have equity". Neither was checked against
`lien_status` or `combined_loan_to_value_ratio`. This script measures both
directly.

Resource use
------------
Reads only the columns it needs from the cleaned Parquet file in batches.
Single-threaded, no Spark session.

Usage
-----
    python src/sensitivity_analysis.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C

OUT_JSON = C.RESULTS_DIR / "sensitivity_analysis.json"

#: The sentinel the review flagged. HMDA reports income in thousands of
#: USD, so this is ~1e12 dollars.
SENTINEL_INCOME = 999_999_999

#: An income at or above this many thousands of dollars is at least one
#: billion dollars. The raw-file probe found 36 such records.
EXTREME_INCOME_THRESHOLD = 1_000_000

NEEDED = [
    "joint_flag", "is_denied", "has_lender_decision",
    "income", "income_dollars", "loan_to_income_ratio",
    "loan_purpose", "loan_type", "lien_status",
    "combined_loan_to_value_ratio", "property_value", "loan_amount",
]

MAX_ROWS = 3_000_000
SEED = 20240101


def _load() -> pd.DataFrame:
    pq_path = Path(C.CLEAN_PARQUET) / "part-00000.parquet"
    if not pq_path.exists():
        pq_path = sorted(Path(C.CLEAN_PARQUET).glob("*.parquet"))[0]
    pf = pq.ParquetFile(pq_path)

    frames = []
    total = 0
    for batch in pf.iter_batches(batch_size=250_000, columns=NEEDED):
        df = batch.to_pandas()
        mask = df["has_lender_decision"].fillna(False).astype(bool)
        df = df[mask]
        if len(df):
            frames.append(df)
            total += len(df)
        if total >= MAX_ROWS:
            break

    df = pd.concat(frames, ignore_index=True)
    df = df[df["joint_flag"].notna()].copy()
    if len(df) > MAX_ROWS:
        df = df.sample(n=MAX_ROWS, random_state=SEED).reset_index(drop=True)
    return df


def _gap(df: pd.DataFrame, inc_col: str) -> dict:
    """Joint vs single denial gap plus the key financial medians."""
    d = df.copy()
    is_j = d["joint_flag"] == 1
    is_s = d["joint_flag"] == 0
    out = {
        "n": int(len(d)),
        "n_joint": int(is_j.sum()),
        "n_single": int(is_s.sum()),
    }
    if out["n_joint"] == 0 or out["n_single"] == 0:
        return out
    rj = float(d.loc[is_j, "is_denied"].mean())
    rs = float(d.loc[is_s, "is_denied"].mean())
    out["denial_rate_joint"] = rj
    out["denial_rate_single"] = rs
    out["gap_pp"] = (rj - rs) * 100

    inc = pd.to_numeric(d[inc_col], errors="coerce")
    out["median_income_joint"] = float(inc[is_j].median())
    out["median_income_single"] = float(inc[is_s].median())
    out["median_income_all"] = float(inc.median())

    lti = pd.to_numeric(d["loan_to_income_ratio"], errors="coerce")
    out["median_lti_joint"] = float(lti[is_j].median())
    out["median_lti_single"] = float(lti[is_s].median())
    return out


def main() -> None:
    print("Loading decision records (capped)...")
    df = _load()
    print(f"  {len(df):,} decision records with a known joint_flag")

    inc_raw = pd.to_numeric(df["income"], errors="coerce")

    # ---- how common are the extreme values? ------------------------------
    # The cleaning step already replaced the extreme income values with
    # missing, so the sentinel itself is no longer in the cleaned dataset.
    # What the analysis still sees are the *surviving* extreme values,
    # which is what the sensitivity check has to act on. The raw-file
    # counts come from `results/raw_income_probe.json`.
    n_sentinel = int((inc_raw == SENTINEL_INCOME).sum())
    n_sentinel_dollars = int(
        (pd.to_numeric(df["income_dollars"], errors="coerce") == SENTINEL_INCOME).sum())

    # The extreme threshold used here is the same one the raw probe
    # reports on: an income of one million thousands of dollars is one
    # billion dollars.
    extreme_mask = inc_raw >= EXTREME_INCOME_THRESHOLD
    n_extreme = int(extreme_mask.sum())
    top_values = (inc_raw[inc_raw > 0].value_counts().head(8).to_dict())

    raw_probe = {}
    raw_probe_path = C.RESULTS_DIR / "raw_income_probe.json"
    if raw_probe_path.exists():
        raw_probe = json.loads(raw_probe_path.read_text(encoding="utf-8"))

    # ---- treatment A: as-is ---------------------------------------------
    res_a = _gap(df, "income")

    # ---- treatment B: set to missing ------------------------------------
    df_b = df.copy()
    df_b.loc[extreme_mask, "income"] = np.nan
    res_b = _gap(df_b, "income")

    # ---- treatment C: winsorised at p99.9 --------------------------------
    # The mask has to be filled with False before it is used.  `income` is
    # a nullable Int64 column, so `inc_raw >= EXTREME_INCOME_THRESHOLD`
    # yields NA wherever the income is missing; `~NA` is still NA, and
    # `where(NA, p999)` fills the missing incomes with the cap value.
    # That silently turned every unreported income into a multi-million
    # dollar income and moved the median, which is what a winsorisation
    # must never do.
    df_c = df.copy()
    pos = inc_raw[inc_raw > 0]
    p999 = float(pos.quantile(0.999))
    extreme_filled = extreme_mask.fillna(False)
    df_c["income"] = inc_raw.mask(extreme_filled, p999)
    res_c = _gap(df_c, "income")

    # ---- check 2: lien status and equity --------------------------------
    lien_map = getattr(C, "LIEN_STATUS", {})
    purpose_map = getattr(C, "LOAN_PURPOSE", {})
    df_l = df.copy()
    df_l["_purpose"] = df_l["loan_purpose"].map(purpose_map).fillna("Unknown")
    df_l["_lien"] = df_l["lien_status"].map(lien_map).fillna("Unknown")
    df_l["_cltv"] = pd.to_numeric(df_l["combined_loan_to_value_ratio"], errors="coerce")

    lien_rows = []
    for purpose, g in df_l.groupby("_purpose", observed=True):
        sub = g[g["has_lender_decision"].fillna(False).astype(bool)]
        if len(sub) < 100:
            continue
        cltv = sub["_cltv"]
        lien_counts = sub["_lien"].value_counts()
        total = lien_counts.sum()
        lien_rows.append({
            "loan_purpose": purpose,
            "n_decisions": int(total),
            "lien_counts": {k: int(v) for k, v in lien_counts.items()},
            "pct_first_lien": round(
                float(lien_counts.get("First lien", 0) / total * 100), 2)
            if total else None,
            "pct_no_lien_or_other": round(
                float(total - lien_counts.get("First lien", 0)) / total * 100, 2)
            if total else None,
            "median_cltv": float(cltv.median()) if cltv.notna().any() else None,
            "pct_with_cltv_reported": round(
                float(cltv.notna().mean() * 100), 2),
            "pct_cltv_below_100": round(
                float((cltv < 100).sum() / cltv.notna().sum() * 100), 2)
            if cltv.notna().any() else None,
            "pct_cltv_at_or_above_100": round(
                float((cltv >= 100).sum() / cltv.notna().sum() * 100), 2)
            if cltv.notna().any() else None,
        })

    # The same comparison, split by joint vs single, for the two purposes
    # the report made claims about.
    key_purposes = []
    for label, want in (("Home purchase", "Home purchase"),
                        ("Home improvement", "Home improvement")):
        sub = df_l[(df_l["_purpose"] == want)
                   & df_l["has_lender_decision"].fillna(False).astype(bool)]
        if len(sub) < 100:
            continue
        entry = {"loan_purpose": label, "n_decisions": int(len(sub))}
        for arm, arm_mask in (("joint", sub["joint_flag"] == 1),
                              ("single", sub["joint_flag"] == 0)):
            s = sub[arm_mask]
            if len(s) == 0:
                continue
            lc = s["_lien"].value_counts()
            cltv = s["_cltv"]
            entry[arm] = {
                "n": int(len(s)),
                "pct_first_lien": round(
                    float(lc.get("First lien", 0) / lc.sum() * 100), 2),
                "median_cltv": float(cltv.median()) if cltv.notna().any() else None,
                "pct_cltv_below_100": round(
                    float((cltv < 100).sum() / cltv.notna().sum() * 100), 2)
                if cltv.notna().any() else None,
                "median_property_value": float(
                    pd.to_numeric(s["property_value"], errors="coerce").median())
                if pd.to_numeric(s["property_value"], errors="coerce").notna().any()
                else None,
            }
        key_purposes.append(entry)

    result = {
        "sample": {
            "n_decision_records": int(len(df)),
            "cap": MAX_ROWS,
            "seed": SEED,
        },
        "income_sentinel": {
            "value_in_raw_units": SENTINEL_INCOME,
            "interpretation": (
                "HMDA reports income in thousands of USD, so this value is "
                "about one trillion dollars. It is treated as a special "
                "code or data-entry artefact, not as a genuine income."
            ),
            "n_records_with_this_value_in_cleaned_data": n_sentinel,
            "n_records_with_this_value_in_dollars": n_sentinel_dollars,
            "extreme_threshold_thousands": EXTREME_INCOME_THRESHOLD,
            "n_extreme_records_in_sample": n_extreme,
            "pct_of_sample": round(n_extreme / len(df) * 100, 4),
            "most_common_income_values": {str(k): int(v) for k, v in top_values.items()},
            "raw_file_probe": {
                "n_records_equals_sentinel_in_raw": raw_probe.get(
                    "income_equals_999999999_thousands"),
                "max_income_thousands_in_raw": raw_probe.get("max_income_thousands"),
                "n_records_at_least_1e9_usd_in_raw": raw_probe.get(
                    "records_with_income_at_least_1e6_thousands"),
                "extreme_records_by_action_taken": raw_probe.get(
                    "extreme_record_action_taken"),
                "ten_largest_income_values": raw_probe.get("ten_largest_income_values"),
            },
        },
        "sensitivity_to_the_sentinel": {
            "A_as_is": res_a,
            "B_set_to_missing": res_b,
            "C_capped_at_p99_9": res_c,
            "p99_9_threshold": p999,
            "gap_change_B_minus_A_pp": (res_b.get("gap_pp", float("nan"))
                                        - res_a.get("gap_pp", float("nan"))),
            "gap_change_C_minus_A_pp": (res_c.get("gap_pp", float("nan"))
                                        - res_a.get("gap_pp", float("nan"))),
        },
        "lien_and_equity_by_purpose": lien_rows,
        "lien_and_equity_key_purposes": key_purposes,
    }

    OUT_JSON.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    print()
    print("=" * 78)
    print("SENSITIVITY ANALYSIS")
    print("=" * 78)
    s = result["income_sentinel"]
    print(f"  sentinel income {SENTINEL_INCOME:,} (thousands USD)")
    print(f"    in the RAW file      : "
          f"{s['raw_file_probe']['n_records_equals_sentinel_in_raw']} record")
    print(f"    >= $1bn in the raw file: "
          f"{s['raw_file_probe']['n_records_at_least_1e9_usd_in_raw']} records")
    print(f"    surviving in the sample: {s['n_extreme_records_in_sample']:,} "
          f"({s['pct_of_sample']}%)")
    print()
    print("  treatment                      gap(pp)   median inc joint   median LTI joint")
    for key, label in (("A_as_is", "A as-is"),
                       ("B_set_to_missing", "B set to missing"),
                       ("C_capped_at_p99_9", "C capped at p99.9")):
        r = result["sensitivity_to_the_sentinel"][key]
        print(f"    {label:28s} {r['gap_pp']:7.2f}   "
              f"{r['median_income_joint']:14,.1f}   {r['median_lti_joint']:14.3f}")
    print()
    print("  lien status and CLTV by loan purpose:")
    for row in lien_rows:
        print(f"    {row['loan_purpose']:28s} n={row['n_decisions']:9,d}  "
              f"first-lien={row['pct_first_lien']:6.2f}%  "
              f"median CLTV={row['median_cltv'] if row['median_cltv'] is None else round(row['median_cltv'], 1)}")
    print()
    print(f"  Written: {OUT_JSON}")


if __name__ == "__main__":
    main()
