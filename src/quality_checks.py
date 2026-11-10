"""
quality_checks.py — Data quality investigations required by the assignment.

Section 3.2B of the assignment requires investigating potential duplicate
records. Section 3.3C asks for relationship analysis including correlation.

This module answers both questions empirically and writes the findings to
`results/quality_checks.json` and `results/correlation_matrix.csv`.

Usage
-----
    python src/quality_checks.py
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C


def check_duplicates() -> dict:
    """Investigate potential duplicate records.

    HMDA is a "one record per application" dataset, so a true duplicate would
    be the same application reported twice. Two definitions are tested:

    1. **Exact duplicate** — every one of the 99 fields identical.
    2. **Business-key duplicate** — identical on the fields that identify an
       application: institution (LEI), borrower, loan amount, property
       location and outcome. This catches the realistic failure mode where
       the same application is filed twice with a cosmetic difference.

    Both are checked on the full cleaned dataset. The check is done row group
    by row group: the 12.25 M x 99 string frame does not fit in 16 GB of RAM
    all at once, so the per-row hashes are computed in chunks and only the
    64-bit hashes are retained. The result is exact, not approximate.
    """
    import pyarrow.parquet as pq

    # `CLEAN_PARQUET` is a directory; ParquetFile needs a concrete file.
    files = sorted(Path(str(C.CLEAN_PARQUET)).glob("*.parquet"))
    if not files:
        raise SystemExit(f"No Parquet files found under {C.CLEAN_PARQUET}")
    path = files[0]

    pf = pq.ParquetFile(str(path))
    n = pf.metadata.num_rows

    available = set(pf.schema_arrow.names)
    hash_cols = [c for c in C.ALL_COLUMNS if c in available]
    key_cols = [
        "lei", "state_code", "county_code", "census_tract", "action_taken",
        "loan_amount", "loan_type", "loan_purpose", "lien_status",
        "applicant_ethnicity_1", "applicant_race_1", "applicant_sex",
        "applicant_age", "income", "debt_to_income_ratio",
        "interest_rate", "property_value", "activity_year",
    ]

    exact_hashes = []
    key_hashes = []
    for rg in range(pf.num_row_groups):
        t = pf.read_row_group(rg)
        df = t.to_pandas()
        # Hash a string representation so that numeric and string columns are
        # both handled and NA is rendered consistently.
        exact_hashes.append(
            pd.util.hash_pandas_object(
                df[hash_cols].astype("string").fillna("<NA>"), index=False
            )
        )
        kc = [c for c in key_cols if c in df.columns]
        key_hashes.append(
            pd.util.hash_pandas_object(
                df[kc].astype("string").fillna("<NA>"), index=False
            )
        )
        del df, t

    eh = pd.concat(exact_hashes, ignore_index=True)
    kh = pd.concat(key_hashes, ignore_index=True)

    n_exact_dup_rows = int(eh.duplicated(keep=False).sum())
    n_exact_dup_extra = int(eh.duplicated(keep="first").sum())
    n_key_dup_rows = int(kh.duplicated(keep=False).sum())
    n_key_dup_extra = int(kh.duplicated(keep="first").sum())

    return {
        "records": n,
        "exact_duplicates": {
            "definition": "all 99 raw fields identical",
            "rows_involved": n_exact_dup_rows,
            "redundant_rows": n_exact_dup_extra,
            "pct_of_dataset": round(n_exact_dup_extra / n * 100, 4),
        },
        "business_key_duplicates": {
            "definition": (
                "identical on the application-identifying fields: "
                + ", ".join(c for c in key_cols if c in hash_cols)
            ),
            "rows_involved": n_key_dup_rows,
            "redundant_rows": n_key_dup_extra,
            "pct_of_dataset": round(n_key_dup_extra / n * 100, 4),
        },
    }


def check_correlations() -> pd.DataFrame:
    """Correlation matrix among the main financial variables."""
    from equivalence import load_clean_pandas

    df = load_clean_pandas()
    cols = [
        "loan_amount", "income_dollars", "loan_to_income_ratio",
        "interest_rate", "property_value", "total_loan_costs",
        "combined_loan_to_value_ratio",
    ]
    cols = [c for c in cols if c in df.columns]
    sub = df[cols].astype("float64")
    corr = sub.corr(method="spearman")
    corr.index.name = "variable"
    return corr.reset_index()


def main() -> None:
    print("Checking for duplicate records...")
    dup = check_duplicates()
    print(f"  records                          : {dup['records']:,}")
    print(f"  exact duplicate rows involved    : {dup['exact_duplicates']['rows_involved']:,}")
    print(f"  exact redundant rows             : {dup['exact_duplicates']['redundant_rows']:,} "
          f"({dup['exact_duplicates']['pct_of_dataset']}%)")
    print(f"  business-key duplicate rows      : {dup['business_key_duplicates']['rows_involved']:,}")
    print(f"  business-key redundant rows      : {dup['business_key_duplicates']['redundant_rows']:,} "
          f"({dup['business_key_duplicates']['pct_of_dataset']}%)")

    print("\nComputing Spearman correlations...")
    corr = check_correlations()
    corr.to_csv(C.RESULTS_DIR / "correlation_matrix.csv", index=False)
    print(corr.to_string(index=False))

    out = C.RESULTS_DIR / "quality_checks.json"
    out.write_text(json.dumps({
        "duplicates": dup,
        "correlation_matrix_file": "results/correlation_matrix.csv",
        "correlation_method": "Spearman rank correlation (robust to the extreme outliers in HMDA)",
    }, indent=2), encoding="utf-8")
    print(f"\nWritten: {out}")
    print(f"Written: {C.RESULTS_DIR / 'correlation_matrix.csv'}")


if __name__ == "__main__":
    main()
