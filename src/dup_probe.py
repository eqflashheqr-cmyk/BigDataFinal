"""
dup_probe.py — Measure duplicates on the RAW pipe file, not the cleaned
Parquet. This is the measurement the report quotes.

The cleaned dataset has already had its exact duplicates removed, so
`quality_checks.py` (which reads the cleaned Parquet) necessarily reports
almost nothing. This script reads the raw text file directly and computes
both duplicate definitions exactly, using the same hashing scheme as the
cleaning pipeline.

    python src/dup_probe.py
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C


def raw_files() -> list[Path]:
    """All raw pipe-delimited chunks, in file order."""
    out = sorted(C.RAW_DIR.glob("*.txt"))
    if not out:
        raise SystemExit(f"No raw .txt files under {C.RAW_DIR}")
    return out


def main() -> None:
    files = raw_files()
    print(f"raw files: {len(files)}")

    key_cols = [
        "lei", "state_code", "county_code", "census_tract", "action_taken",
        "loan_amount", "loan_type", "loan_purpose", "lien_status",
        "applicant_ethnicity_1", "applicant_race_1", "applicant_sex",
        "applicant_age", "income", "debt_to_income_ratio",
        "interest_rate", "property_value", "activity_year",
    ]
    hash_cols = list(C.ALL_COLUMNS)

    exact_parts: list[np.ndarray] = []
    key_parts: list[np.ndarray] = []
    n_total = 0
    t0 = time.perf_counter()

    for i, f in enumerate(files, 1):
        # Read as everything-is-text so the hash covers the raw field exactly
        # as written in the file.
        df = pd.read_csv(
            f,
            sep=C.DELIMITER,
            dtype=str,
            engine="c",
            na_filter=False,
            keep_default_na=False,
            on_bad_lines="skip",
        )
        df.columns = [c.strip() for c in df.columns]
        df = df[[c for c in hash_cols if c in df.columns]]
        for col in df.columns:
            df[col] = df[col].astype("string").str.strip()

        exact_parts.append(
            pd.util.hash_pandas_object(df, index=False).to_numpy()
        )

        kc = [c for c in key_cols if c in df.columns]
        key_parts.append(
            pd.util.hash_pandas_object(df[kc], index=False).to_numpy()
        )

        n_total += len(df)
        print(f"  [{i}/{len(files)}] {f.name}: {len(df):,} rows "
              f"({time.perf_counter() - t0:.0f}s)", flush=True)
        del df

    eh = np.concatenate(exact_parts)
    kh = np.concatenate(key_parts)

    out = {
        "records_raw": int(n_total),
        "exact_duplicates": {
            "definition": "all 99 raw fields identical",
            "rows_involved": int(pd.Series(eh).duplicated(keep=False).sum()),
            "redundant_rows": int(pd.Series(eh).duplicated(keep="first").sum()),
        },
        "business_key_duplicates": {
            "definition": (
                "identical on the application-identifying fields: "
                + ", ".join(key_cols)
            ),
            "rows_involved": int(pd.Series(kh).duplicated(keep=False).sum()),
            "redundant_rows": int(pd.Series(kh).duplicated(keep="first").sum()),
        },
    }
    out["exact_duplicates"]["pct_of_dataset"] = round(
        out["exact_duplicates"]["redundant_rows"] / n_total * 100, 4)
    out["business_key_duplicates"]["pct_of_dataset"] = round(
        out["business_key_duplicates"]["redundant_rows"] / n_total * 100, 4)

    path = C.RESULTS_DIR / "duplicate_probe_raw.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"\nWritten: {path}")


if __name__ == "__main__":
    main()
