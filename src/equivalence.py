"""
equivalence.py — Verify that the Pandas and PySpark implementations agree.

The assignment requires:

    "Compare Pandas and Spark results for at least three important analytical
     outputs ... For each comparison, report: 1. the analytical quantity being
     compared, 2. the result from Pandas, 3. the result from PySpark,
     4. whether the results agree, 5. an explanation of any discrepancy."

Why this runs in three separate processes
-----------------------------------------
The dataset has 12.25 million rows. A Pandas DataFrame of the analytical
columns and a cached Spark DataFrame of the same size do not fit in 16 GB of
RAM at the same time. The script therefore has three modes that are executed
as separate processes, so that each engine gets the full machine:

    python src/equivalence.py pandas   -> results/_equiv_pandas.json
    python src/equivalence.py spark    -> results/_equiv_spark.json
    python src/equivalence.py compare  -> results/equivalence_report.{json,csv}

`python src/equivalence.py all` runs the three in sequence.
"""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C
import analytics as A

PANDAS_OUT = C.RESULTS_DIR / "_equiv_pandas.json"
SPARK_OUT = C.RESULTS_DIR / "_equiv_spark.json"


# ==========================================================================
# Part 1: Pandas side
# ==========================================================================

def load_clean_pandas(path=None) -> pd.DataFrame:
    """Load the cleaned Pandas Parquet dataset with memory-conscious dtypes.

    The dataset has 12.25 million rows. Read as plain strings it would need
    far more than the 16 GB of RAM available, so high-cardinality text columns
    (`lei`, `state_code`, ...) are loaded as *categoricals* and the rest as
    their natural numeric types. Only the columns actually needed for the
    analytical outputs are loaded; the full 104-column dataset stays on disk.
    """
    import pyarrow.parquet as pq

    path = str(path or C.CLEAN_PARQUET)
    needed = [
        "action_taken", "has_lender_decision", "is_denied", "joint_flag",
        "loan_amount", "income", "income_dollars", "interest_rate", "rate_spread",
        "combined_loan_to_value_ratio", "property_value", "total_loan_costs",
        "loan_to_income_ratio", "debt_to_income_ratio", "dti_band_order",
        "loan_type", "loan_purpose", "lien_status", "state_code", "lei",
        "applicant_age", "co_applicant_age", "preapproval",
    ]
    table = pq.read_table(path, columns=needed)
    df = table.to_pandas()
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype("category")
    return df


def run_pandas() -> dict:
    pdf = load_clean_pandas()
    print(f"Pandas rows : {len(pdf):,}")
    res = {
        "record_counts": A.record_counts_pandas(pdf),
        "missing_counts": A.missing_counts_pandas(pdf),
        "outcome_counts": A.outcome_counts_pandas(pdf).to_dict("records"),
        "denial_by_joint": A.denial_rate_by_joint_pandas(pdf).to_dict("records"),
        "descriptive_stats": A.descriptive_stats_pandas(pdf).to_dict("records"),
        "loan_by_type": A.loan_amount_by_type_pandas(pdf).to_dict("records"),
        "by_institution": A.by_institution_pandas(pdf, top_n=50).to_dict("records"),
        "denial_by_state": A.denial_rate_by_state_pandas(pdf).to_dict("records"),
    }
    PANDAS_OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(f"Written: {PANDAS_OUT}")
    return res


# ==========================================================================
# Part 2: Spark side
# ==========================================================================

def run_spark() -> dict:
    from spark_pipeline import build_session

    spark = build_session("HMDA-Equivalence")
    try:
        # Project to only the columns the analytical outputs need, then cache.
        # Caching all 104 columns of 12.25M rows does not fit in 16 GB.
        needed = [
            "action_taken", "has_lender_decision", "is_denied", "joint_flag",
            "loan_amount", "income", "income_dollars", "interest_rate", "rate_spread",
            "combined_loan_to_value_ratio", "property_value", "total_loan_costs",
            "loan_to_income_ratio", "debt_to_income_ratio", "dti_band_order",
            "loan_type", "loan_purpose", "lien_status", "state_code", "lei",
            "applicant_age", "co_applicant_age", "preapproval",
        ]
        from pyspark import StorageLevel
        sdf = spark.read.parquet(str(C.SPARK_PARQUET)).select(*needed)
        sdf = sdf.persist(StorageLevel.MEMORY_AND_DISK)
        n = sdf.count()
        print(f"Spark rows  : {n:,}")

        res = {
            "record_counts": A.record_counts_spark(sdf),
            "missing_counts": A.missing_counts_spark(sdf),
            "outcome_counts": A.outcome_counts_spark(sdf).to_dict("records"),
            "denial_by_joint": A.denial_rate_by_joint_spark(sdf).to_dict("records"),
            "descriptive_stats": A.descriptive_stats_spark(sdf).to_dict("records"),
            "loan_by_type": A.loan_amount_by_type_spark(sdf).to_dict("records"),
            "by_institution": A.by_institution_spark(sdf, top_n=50).to_dict("records"),
            "denial_by_state": A.denial_rate_by_state_spark(sdf).to_dict("records"),
        }
        sdf.unpersist()
    finally:
        spark.stop()

    SPARK_OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(f"Written: {SPARK_OUT}")
    return res


# ==========================================================================
# Part 3: comparison
# ==========================================================================

#: For each comparison: the key, a human-readable description, the numeric
#: columns that must agree within tolerance, the key (grouping) columns that
#: must agree exactly, and the comparison kind.
COMPARISONS = [
    ("record_counts", "Record counts after each cleaning step",
     ["records_total", "records_with_decision", "records_joint_flag_known",
      "records_joint", "records_single", "records_indeterminate_joint"], [], "count"),
    ("missing_counts", "Missing-value counts for the important variables",
     list(A.MISSING_CHECK_COLUMNS), [], "count"),
    ("outcome_counts", "Counts and proportions of application outcomes (action_taken)",
     ["n", "proportion"], ["action_taken", "label"], "frame"),
    ("denial_by_joint", "Denial rate by joint_flag (RQ1)",
     ["n_decisions", "n_denied", "denial_rate"], ["joint_flag"], "frame"),
    ("descriptive_stats", "Descriptive statistics of loan_amount, income, interest_rate, LTI",
     ["n", "n_missing", "mean", "median", "std", "min", "p25", "p75", "max"],
     ["variable"], "frame"),
    ("loan_by_type", "Average and median loan amount by loan type",
     ["n", "mean_loan_amount", "median_loan_amount"], ["loan_type", "label"], "frame"),
    ("by_institution", "Aggregated results by financial institution (LEI, top 50)",
     ["n_applications", "n_decisions", "mean_loan_amount", "total_loan_amount"],
     ["lei"], "frame"),
    ("denial_by_state", f"Denial rate in the top {C.TOP_N_STATES} states (RQ4)",
     ["n_decisions", "n_denied", "denial_rate"], ["state_code"], "frame"),
]


def _cmp_frame(a, b, num_cols, key_cols, tol):
    """Compare two lists of dicts row by row."""
    diffs = []
    if len(a) != len(b):
        diffs.append(f"row count: pandas={len(a)} spark={len(b)}")
        return False, diffs
    for i, (ra, rb) in enumerate(zip(a, b)):
        for col in key_cols:
            va, vb = str(ra.get(col)), str(rb.get(col))
            if va != vb:
                diffs.append(f"row {i} key {col}: pandas={va!r} spark={vb!r}")
        for col in num_cols:
            va, vb = ra.get(col), rb.get(col)
            if va is None and vb is None:
                continue
            if va is None or vb is None:
                diffs.append(f"row {i} col {col}: pandas={va} spark={vb}")
                continue
            if col in ("n", "n_decisions", "n_denied", "n_applications", "n_missing"):
                if int(float(va)) != int(float(vb)):
                    diffs.append(f"row {i} col {col}: pandas={va} spark={vb}")
            else:
                fa, fb = float(va), float(vb)
                if abs(fa - fb) > tol * max(1.0, abs(fa)):
                    diffs.append(f"row {i} col {col}: pandas={fa} spark={fb}")
    return (not diffs), diffs[:25]


def run_compare() -> dict:
    if not PANDAS_OUT.exists() or not SPARK_OUT.exists():
        raise SystemExit("Run the 'pandas' and 'spark' modes first.")

    p = json.loads(PANDAS_OUT.read_text(encoding="utf-8"))
    s = json.loads(SPARK_OUT.read_text(encoding="utf-8"))

    comparisons = []
    for key, desc, num_cols, key_cols, kind in COMPARISONS:
        if kind == "count":
            a, b = p[key], s[key]
            diffs = []
            for k in num_cols:
                if int(a.get(k, -1)) != int(b.get(k, -2)):
                    diffs.append(f"{k}: pandas={a.get(k)} spark={b.get(k)}")
            ok = not diffs
        else:
            a, b = p[key], s[key]
            ok, diffs = _cmp_frame(a, b, num_cols, key_cols, C.TOLERANCE)
        comparisons.append({
            "quantity": desc,
            "pandas": p[key],
            "spark": s[key],
            "agree": ok,
            "discrepancy": diffs,
        })

    n_ok = sum(1 for c in comparisons if c["agree"])
    report = {
        "n_comparisons": len(comparisons),
        "n_agree": n_ok,
        "all_agree": n_ok == len(comparisons),
        "tolerance": C.TOLERANCE,
        "pandas_version": pd.__version__,
        "comparisons": comparisons,
    }
    out = C.RESULTS_DIR / "equivalence_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    rows = [{
        "Analytical quantity": c["quantity"],
        "Agree": "YES" if c["agree"] else "NO",
        "Discrepancy (first few)": "; ".join(c["discrepancy"][:3]) if c["discrepancy"] else "",
    } for c in comparisons]
    pd.DataFrame(rows).to_csv(C.RESULTS_DIR / "equivalence_report.csv", index=False)

    print("=" * 78)
    print("PANDAS vs PYSPARK — RESULT EQUIVALENCE")
    print("=" * 78)
    for i, c in enumerate(comparisons, 1):
        print(f"\n{i}. {c['quantity']}")
        print(f"   status: {'AGREE' if c['agree'] else 'DISAGREE'}")
        for line in c["discrepancy"][:10]:
            print(f"     - {line}")
    print()
    print("=" * 78)
    print(f"{n_ok} of {len(comparisons)} comparisons agree.")
    print(f"Written: {out}")
    return report


# ==========================================================================
# CLI
# ==========================================================================

def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode == "pandas":
        run_pandas()
    elif mode == "spark":
        run_spark()
    elif mode == "compare":
        run_compare()
    elif mode == "all":
        here = str(Path(__file__).resolve())
        for step in ("pandas", "spark", "compare"):
            print(f"\n>>> Running step: {step}\n")
            r = subprocess.run([sys.executable, here, step], cwd=str(Path(__file__).parent))
            if r.returncode != 0:
                raise SystemExit(f"Step '{step}' failed with code {r.returncode}")
    else:
        raise SystemExit(f"Unknown mode '{mode}'. Use: pandas | spark | compare | all")


if __name__ == "__main__":
    main()
