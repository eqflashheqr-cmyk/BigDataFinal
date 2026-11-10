"""
pandas_pipeline.py — Build the prepared analytical dataset using Pandas.

Reads the raw FFIEC HMDA 2024 pipe-delimited file, applies the shared cleaning
rules from `rules.clean_pandas`, and writes the result to Parquet.

Memory note
------------
The raw file is 4.32 GiB of text with 99 columns; materialising it as a Pandas
DataFrame of strings would need far more than the 16 GB of RAM available on
this machine. The file is therefore processed in chunks, and each chunk is
cleaned with the exact same rules before being appended to the Parquet
dataset. This is the "justified subset / chunked processing" option the
assignment allows for Pandas.

Usage
-----
    python src/pandas_pipeline.py
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C
from rules import clean_pandas


def read_raw_chunks(chunksize: int = C.PANDAS_CHUNK_SIZE):
    """Yield raw chunks of the pipe-delimited file as strings.

    The file has a single header row whose names match `config.ALL_COLUMNS`
    exactly, so the header is skipped explicitly and the column names are
    supplied from the config. Reading with `dtype=str` keeps every value as
    text so that no silent numeric coercion happens at load time.
    """
    return pd.read_csv(
        C.RAW_FILE,
        sep=C.DELIMITER,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        header=None,
        skiprows=1,
        names=C.ALL_COLUMNS,
        chunksize=chunksize,
        encoding="utf-8",
        low_memory=False,
    )


def main() -> None:
    if not C.RAW_FILE.exists():
        raise SystemExit(f"Raw file not found: {C.RAW_FILE}")

    print(f"Raw file : {C.RAW_FILE}")
    print(f"Size     : {C.RAW_FILE.stat().st_size / (1024 ** 3):.2f} GiB")
    print(f"Output   : {C.CLEAN_PARQUET}")
    print()

    out_dir = Path(str(C.CLEAN_PARQUET))
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in sorted(out_dir.glob("*.parquet")):
        p.unlink()

    writer = None
    schema = None
    # Row hashes of the records already emitted, used to detect duplicates
    # that span chunk boundaries.
    seen_hashes = None
    totals = {
        "records_raw": 0,
        "removed_exact_duplicates": 0,
        "removed_negative_amounts": 0,
        "removed_zero_loan_amount": 0,
        "records_after_cleaning": 0,
        "records_indeterminate_joint": 0,
    }
    t0 = time.perf_counter()

    for i, chunk in enumerate(read_raw_chunks(), start=1):
        chunk_report: dict = {}
        cleaned = clean_pandas(chunk, report=chunk_report, seen_hashes=seen_hashes)
        kept = chunk_report.pop("_kept_hashes", None)
        seen_hashes = kept if seen_hashes is None else np.concatenate([seen_hashes, kept])

        for k in totals:
            totals[k] += chunk_report.get(k, 0)

        table = pa.Table.from_pandas(cleaned, preserve_index=False)
        if writer is None:
            schema = table.schema
            writer = pq.ParquetWriter(str(out_dir / "part-00000.parquet"), schema)
        elif table.schema != schema:
            table = table.cast(schema)
        writer.write_table(table)

        print(
            f"  chunk {i:>3}  raw={chunk_report['records_raw']:>9,}  "
            f"kept={chunk_report['records_after_cleaning']:>9,}  "
            f"dupes={chunk_report.get('removed_exact_duplicates', 0):>6,}  "
            f"removed_neg={chunk_report['removed_negative_amounts']:>6,}  "
            f"removed_zero_loan={chunk_report['removed_zero_loan_amount']:>5,}  "
            f"indet_joint={chunk_report['records_indeterminate_joint']:>6,}"
        )

    if writer is not None:
        writer.close()

    elapsed = time.perf_counter() - t0
    report = {
        "engine": "pandas",
        "pandas_version": pd.__version__,
        "raw_file": str(C.RAW_FILE),
        "raw_file_bytes": C.RAW_FILE.stat().st_size,
        "delimiter": C.DELIMITER,
        "n_columns_raw": len(C.ALL_COLUMNS),
        "chunk_size": C.PANDAS_CHUNK_SIZE,
        "elapsed_seconds": round(elapsed, 2),
        **totals,
    }

    out = C.RESULTS_DIR / "cleaning_report_pandas.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print()
    print("Cleaning report (Pandas)")
    print("-" * 46)
    for k, v in report.items():
        print(f"  {k:<34} {v}")
    print()
    print(f"Written: {out}")


if __name__ == "__main__":
    main()
