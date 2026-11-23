"""Empirical evidence for the debt-to-income (DTI) discussion.

The earlier version of the report asserted that lenders refuse to lend above
a 43% DTI and that this is a legal ceiling.  Both parts were wrong:

  * 43% is not a legal threshold.  No US federal law caps DTI at 43%.  The
    figure is the back-end DTI limit in the *general qualified-mortgage*
    definition, Reg Z 1026.43(e)(2)(vi), which determined whether a loan
    carried the QM liability protection and was therefore saleable into the
    securitisation market.  The general ability-to-repay rule,
    1026.43(c), requires a creditor to *consider* DTI or residual income
    but sets no numerical threshold.  The 2021 pricing rule removed the
    43% limit for general QMs entirely and replaced it with price-based
    (APR relative to APOR) thresholds.
  * In HMDA 2024 a large share of originations sit *above* 43% DTI, so
    "no loan is made above 43%" is empirically false.

This script measures the share of applications and of originations in each
DTI band, so the report can state the fact rather than assert it.

Reads the cleaned Parquet dataset in chunks (bounded RAM), writes
results/dti_bands.json.
"""
import json
import os
import sys

import pandas as pd
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import config as C  # noqa: E402

PANDAS_DIR = os.path.join(ROOT, "data", "clean", "hmda_2024_clean")
OUT = os.path.join(ROOT, "results", "dti_bands.json")

CHUNK = 250_000
THRESHOLD = 43


def band_bounds(band):
    """Return (lo, hi) for a raw DTI band string, or None if it carries no
    numeric information.

    Handles "<20%", "20%-<30%", "30%-<36%", the single values "36".."49",
    "50%-60%" and ">60%".
    """
    band = band.strip()
    if band.startswith("<"):
        return (0.0, float(band[1:].rstrip("%")))
    if band.startswith(">"):
        return (float(band[1:].rstrip("%")), float("inf"))
    if "-" in band:
        lo, _, hi = band.partition("-")
        lo = float(lo.rstrip("%"))
        hi = float(hi.lstrip("<").rstrip("%"))
        return (lo, hi)
    try:
        v = float(band)
    except ValueError:
        return None
    return (v, v)


def band_above(band, threshold):
    """True if the whole band lies strictly above the threshold."""
    b = band_bounds(band)
    if b is None:
        return False
    return b[0] > threshold


def band_at_or_below(band, threshold):
    """True if the whole band lies at or below the threshold."""
    b = band_bounds(band)
    if b is None:
        return False
    return b[1] <= threshold


def iter_chunks(columns):
    """Stream the cleaned dataset in row-group chunks (bounded RAM)."""
    import glob
    files = sorted(glob.glob(os.path.join(PANDAS_DIR, "*.parquet")))
    if not files:
        raise FileNotFoundError("no parquet files under " + PANDAS_DIR)
    for path in files:
        pf = pq.ParquetFile(path)
        for batch in pf.iter_batches(batch_size=CHUNK, columns=columns):
            yield batch.to_pandas()


def tally(frame, key="dti_band_order"):
    out = {}
    for order, n in frame[key].value_counts(dropna=False).items():
        order = -1 if pd.isna(order) else int(order)
        out[order] = out.get(order, 0) + int(n)
    return out


def main():
    if not os.path.isdir(PANDAS_DIR):
        print("cleaned dataset not found:", PANDAS_DIR)
        return 1

    bands = list(C.DTI_BANDS)
    band_of = {i: b for i, b in enumerate(bands)}

    counts = {}
    joint_counts = {}
    orig = {}
    total = 0
    joint_total = 0
    orig_total = 0

    for chunk in iter_chunks(["dti_band_order", "action_taken", "joint_flag"]):
        total += len(chunk)
        for order, n in tally(chunk).items():
            counts[order] = counts.get(order, 0) + n

        joint = chunk[chunk["joint_flag"] == 1]
        joint_total += len(joint)
        for order, n in tally(joint).items():
            joint_counts[order] = joint_counts.get(order, 0) + n

        made = chunk[chunk["action_taken"] == 1]
        orig_total += len(made)
        for order, n in tally(made).items():
            orig[order] = orig.get(order, 0) + n

    def split(tbl):
        above = below = unknown = 0
        for order, n in tbl.items():
            band = band_of.get(order)
            if band is None:                      # missing / not applicable
                unknown += n
            elif band_above(band, THRESHOLD):
                above += n
            elif band_at_or_below(band, THRESHOLD):
                below += n
            else:                                  # band straddles the threshold
                unknown += n
        return above, below, unknown

    app_above, app_below, app_unknown = split(counts)
    jnt_above, jnt_below, jnt_unknown = split(joint_counts)
    org_above, org_below, org_unknown = split(orig)

    rows = []
    for order, band in enumerate(bands):
        n = counts.get(order, 0)
        jn = joint_counts.get(order, 0)
        on = orig.get(order, 0)
        rows.append({
            "band": band,
            "records": n,
            "share_pct": round(100.0 * n / total, 4) if total else None,
            "joint_records": jn,
            "originations": on,
            "origination_share_pct": round(100.0 * on / orig_total, 4) if orig_total else None,
            "above_43": band_above(band, THRESHOLD),
        })

    result = {
        "source": "HMDA 2024 national loan-level dataset (cleaned Parquet)",
        "threshold_pct": THRESHOLD,
        "total_records": total,
        "total_joint": joint_total,
        "total_originations": orig_total,
        "bands": rows,
        "summary": {
            "applications_above_43": app_above,
            "applications_at_or_below_43": app_below,
            "applications_unclassified": app_unknown,
            "share_applications_above_43_pct": round(100.0 * app_above / total, 4) if total else None,
            "joint_applications_above_43": jnt_above,
            "originations_above_43": org_above,
            "originations_at_or_below_43": org_below,
            "originations_unclassified": org_unknown,
            "share_originations_above_43_pct": round(100.0 * org_above / orig_total, 4) if orig_total else None,
        },
        "note": (
            "HMDA reports debt_to_income_ratio as an ordinal band string. A "
            "band is counted as 'above 43%' only when its whole range lies "
            "strictly above 43% and as 'at or below 43%' only when its whole "
            "range lies at or below 43%; the 50%-60% band therefore straddles "
            "the threshold and is excluded from both counts. Missing, 'Exempt' "
            "and 'Not applicable' records are unclassified."
        ),
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    print(json.dumps(result["summary"], indent=2))
    print("\nband table (records / share):")
    for r in rows:
        print("  %-12s %10s  %7s%%  orig %9s  above43=%s"
              % (r["band"], f'{r["records"]:,}', r["share_pct"],
                 f'{r["originations"]:,}', r["above_43"]))
    print("\nwrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
