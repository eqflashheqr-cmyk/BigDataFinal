"""
benchmark.py — Performance and scalability experiment.

The assignment asks for a comparison of Pandas and Spark at different data
sizes (25%, 50%, 100% of the dataset) with wall-clock timings and an
explanation of the results.

What is measured
----------------
For each fraction f in {25%, 50%, 100%} and each engine:

    * `ingest`    — read the raw pipe-delimited file and parse the columns
    * `clean`     — apply the shared cleaning rules
    * `analyze`   — the four research questions
    * `total`     — the sum of the three stages

Both engines apply the SAME sampling rule, so the comparison is
apples-to-apples. The rule is deterministic and order-independent:

    h = SHA-256(lei)
    keep the record if  int(h[0:8], 16) mod 1000 < fraction * 1000

`lei` (the Legal Entity Identifier) is a unique-ish string that is present
and non-missing on every record. SHA-256 is available both in Python's
`hashlib` and in Spark's `sha2()` function, so the two engines select exactly
the same records with no reliance on either engine's built-in hash function
(which is not stable across versions or implementations).

Note: a modulo rule on `loan_amount` does NOT work, because loan amounts are
reported in whole thousands of dollars and are therefore almost always exact
multiples of 1000.

Each measurement is repeated `config.BENCHMARK_REPEATS` times and the median
is reported, which is the standard way to reduce the effect of background
noise on a single machine.

Usage
-----
    python src/benchmark.py
"""

import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C
import analysis as A
from rules import clean_pandas


# --------------------------------------------------------------------------
# Sampling rule (identical in both engines)
# --------------------------------------------------------------------------

SAMPLE_MODULUS = 1000
#: Number of hex characters of the SHA-256 digest used for the hash.
#: NOTE: Spark's `substring(str, pos, len)` is 1-indexed, so the 8 leading
#: hex characters are `substring(sha, 1, 8)`.
SAMPLE_HASH_CHARS = 8


def sample_threshold(fraction: float) -> int:
    """The modulo threshold that keeps approximately `fraction` of the rows."""
    return int(round(fraction * SAMPLE_MODULUS))


def lei_hash_bucket(lei: str) -> int:
    """SHA-256 based bucket of an LEI. Mirrors Spark's `sha2(lei, 256)`."""
    digest = hashlib.sha256(lei.encode("utf-8")).hexdigest()
    return int(digest[:SAMPLE_HASH_CHARS], 16) % SAMPLE_MODULUS


# --------------------------------------------------------------------------
# Pandas benchmark
# --------------------------------------------------------------------------

#: Columns the analysis stage needs. Keeping only these after cleaning is
#: what makes the 100% Pandas benchmark fit in 16 GB of RAM: the raw frame
#: has 99 string columns, which is roughly 40 GB for 12.25 million rows.
ANALYSIS_COLUMNS = [
    "action_taken", "has_lender_decision", "is_denied", "joint_flag",
    "loan_amount", "income", "income_dollars", "interest_rate",
    "loan_to_income_ratio", "debt_to_income_ratio", "dti_band_order",
    "loan_type", "loan_purpose", "state_code", "lei",
]


def _read_pandas_raw(fraction: float):
    """Read the raw file and apply the sampling rule in Pandas.

    Returns the whole sample in memory. This is only used for small fractions;
    `bench_pandas` uses the streaming variant below for the full dataset.
    """
    threshold = sample_threshold(fraction)
    keep = []
    reader = pd.read_csv(
        C.RAW_FILE,
        sep=C.DELIMITER,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        header=None,
        skiprows=1,
        names=C.ALL_COLUMNS,
        chunksize=C.PANDAS_CHUNK_SIZE,
        encoding="utf-8",
        low_memory=False,
    )
    for chunk in reader:
        buckets = chunk["lei"].map(lei_hash_bucket)
        keep.append(chunk[buckets < threshold])
    return pd.concat(keep, ignore_index=True) if keep else pd.DataFrame(columns=C.ALL_COLUMNS)


def bench_pandas(fraction: float) -> dict:
    """Time the three stages of the Pandas pipeline on a sample.

    The file is streamed in chunks and each chunk is cleaned with the shared
    rules, exactly as `pandas_pipeline.py` does. Only the analysis columns
    are retained after cleaning, which keeps the 100% run inside the 16 GB
    of RAM available on this machine.
    """
    threshold = sample_threshold(fraction)
    t_ingest = 0.0
    t_clean = 0.0
    n_raw = 0
    parts = []
    # Row hashes of the records already cleaned, so that duplicates spanning
    # a chunk boundary are removed consistently with the Spark run.
    seen_hashes = None

    reader = pd.read_csv(
        C.RAW_FILE,
        sep=C.DELIMITER,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        header=None,
        skiprows=1,
        names=C.ALL_COLUMNS,
        chunksize=C.PANDAS_CHUNK_SIZE,
        encoding="utf-8",
        low_memory=False,
    )
    for chunk in reader:
        t0 = time.perf_counter()
        buckets = chunk["lei"].map(lei_hash_bucket)
        chunk = chunk[buckets < threshold]
        t_ingest += time.perf_counter() - t0
        n_raw += len(chunk)
        if len(chunk) == 0:
            continue

        t0 = time.perf_counter()
        chunk_report: dict = {}
        cleaned = clean_pandas(chunk, report=chunk_report, seen_hashes=seen_hashes)
        # Carry the hashes of the rows kept so far across chunk boundaries,
        # exactly as `pandas_pipeline.py` does. Without this, a duplicate
        # whose two copies fall in different chunks would survive, while
        # Spark's global `dropDuplicates` would remove it — and the two
        # engines would process different numbers of records.
        kept = chunk_report.pop("_kept_hashes", None)
        seen_hashes = kept if seen_hashes is None else np.concatenate([seen_hashes, kept])
        parts.append(cleaned[ANALYSIS_COLUMNS])
        t_clean += time.perf_counter() - t0

    t0 = time.perf_counter()
    cleaned = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=ANALYSIS_COLUMNS)
    t_clean += time.perf_counter() - t0
    n_cleaned = len(cleaned)

    t0 = time.perf_counter()
    for rq, (_, fp, _) in A.RQS.items():
        fp(cleaned)
    t_analyze = time.perf_counter() - t0

    return {
        "engine": "pandas",
        "fraction": fraction,
        "rows_raw": n_raw,
        "rows_cleaned": n_cleaned,
        "seconds_ingest": round(t_ingest, 3),
        "seconds_clean": round(t_clean, 3),
        "seconds_analyze": round(t_analyze, 3),
        "seconds_total": round(t_ingest + t_clean + t_analyze, 3),
    }


# --------------------------------------------------------------------------
# Spark benchmark
# --------------------------------------------------------------------------

def bench_spark(fraction: float) -> dict:
    """Time the three stages of the Spark pipeline on a sample."""
    from pyspark.sql import functions as F
    from pyspark import StorageLevel
    from spark_pipeline import build_session
    from rules import clean_spark

    spark = build_session("HMDA-Benchmark")
    try:
        t0 = time.perf_counter()
        raw = (spark.read
               .option("delimiter", C.DELIMITER)
               .option("header", "true")
               .option("inferSchema", "false")
               .option("mode", "PERMISSIVE")
               .option("encoding", "UTF-8")
               .csv(str(C.RAW_FILE)))
        threshold = sample_threshold(fraction)
        raw = raw.filter(
            F.pmod(
                F.conv(F.substring(F.sha2(F.col("lei"), 256), 1, SAMPLE_HASH_CHARS), 16, 10),
                F.lit(SAMPLE_MODULUS),
            ) < F.lit(threshold)
        )
        raw = raw.persist(StorageLevel.DISK_ONLY)
        n_raw = raw.count()
        t_ingest = time.perf_counter() - t0

        t0 = time.perf_counter()
        cleaned = clean_spark(raw).persist(StorageLevel.DISK_ONLY)
        n_cleaned = cleaned.count()
        t_clean = time.perf_counter() - t0

        t0 = time.perf_counter()
        needed = [
            "action_taken", "has_lender_decision", "is_denied", "joint_flag",
            "loan_amount", "income", "income_dollars", "interest_rate",
            "loan_to_income_ratio", "debt_to_income_ratio", "dti_band_order",
            "loan_type", "loan_purpose", "state_code",
        ]
        sdf = cleaned.select(*needed).persist(StorageLevel.DISK_ONLY)
        sdf.count()
        for rq, (_, _, fs) in A.RQS.items():
            fs(sdf)
        t_analyze = time.perf_counter() - t0

        sdf.unpersist()
        cleaned.unpersist()
        raw.unpersist()
    finally:
        spark.stop()

    return {
        "engine": "pyspark",
        "fraction": fraction,
        "rows_raw": n_raw,
        "rows_cleaned": n_cleaned,
        "seconds_ingest": round(t_ingest, 3),
        "seconds_clean": round(t_clean, 3),
        "seconds_analyze": round(t_analyze, 3),
        "seconds_total": round(t_ingest + t_clean + t_analyze, 3),
    }


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def _write_results(results: list) -> None:
    """Write the benchmark results to JSON and CSV (called after every cell)."""
    out_json = C.RESULTS_DIR / "benchmark_results.json"
    out_json.write_text(json.dumps({
        "config": {
            "repeats": C.BENCHMARK_REPEATS,
            "fractions": list(C.BENCHMARK_FRACTIONS),
            "sample_rule": (
                f"SHA-256(lei)[0:{SAMPLE_HASH_CHARS}] as int, mod {SAMPLE_MODULUS}, "
                f"< fraction * {SAMPLE_MODULUS}"
            ),
            "pandas_chunk_size": C.PANDAS_CHUNK_SIZE,
            "spark_driver_memory": C.SPARK_DRIVER_MEMORY,
            "spark_shuffle_partitions": C.SPARK_SHUFFLE_PARTITIONS,
            "pandas_version": pd.__version__,
        },
        "results": results,
    }, indent=2), encoding="utf-8")

    rows = []
    for r in results:
        rows.append({
            "engine": r["engine"],
            "fraction": f"{r['fraction']:.0%}",
            "rows_cleaned": r["rows_cleaned"],
            "ingest_s": r["seconds_ingest"],
            "clean_s": r["seconds_clean"],
            "analyze_s": r["seconds_analyze"],
            "total_s": r["seconds_total"],
            "rows_per_second": round(r["rows_cleaned"] / r["seconds_total"], 1),
        })
    pd.DataFrame(rows).to_csv(C.RESULTS_DIR / "benchmark_results.csv", index=False)


def main() -> None:
    if not C.RAW_FILE.exists():
        raise SystemExit(f"Raw file not found: {C.RAW_FILE}")

    # The income quartile bounds must be pinned before the analysis stage.
    from equivalence import load_clean_pandas
    print("Computing income quartile bounds from the full dataset...")
    full = load_clean_pandas()
    A.INCOME_QUARTILE_BOUNDS = A.compute_income_quartile_bounds(full)
    (C.RESULTS_DIR / "income_quartile_bounds.json").write_text(
        json.dumps(A.INCOME_QUARTILE_BOUNDS), encoding="utf-8"
    )
    print(f"  bounds: {A.INCOME_QUARTILE_BOUNDS}")
    del full

    results = []
    for fraction in C.BENCHMARK_FRACTIONS:
        for engine, fn in (("pandas", bench_pandas), ("pyspark", bench_spark)):
            runs = []
            for rep in range(C.BENCHMARK_REPEATS):
                print(f"\n>>> {engine} @ {fraction:.0%}  (repeat {rep + 1}/{C.BENCHMARK_REPEATS})",
                      flush=True)
                r = fn(fraction)
                runs.append(r)
                print(f"    rows={r['rows_cleaned']:,}  total={r['seconds_total']}s "
                      f"(ingest {r['seconds_ingest']}s / clean {r['seconds_clean']}s / "
                      f"analyze {r['seconds_analyze']}s)", flush=True)

            # median across repeats
            med = {"engine": engine, "fraction": fraction,
                   "rows_raw": runs[0]["rows_raw"],
                   "rows_cleaned": runs[0]["rows_cleaned"]}
            for stage in ["seconds_ingest", "seconds_clean", "seconds_analyze", "seconds_total"]:
                med[stage] = round(statistics.median(r[stage] for r in runs), 3)
            med["repeats"] = len(runs)
            med["all_runs"] = runs
            results.append(med)
            print(f"    -> median total {med['seconds_total']}s", flush=True)

            # Checkpoint after every cell, so a later failure does not lose
            # the measurements that already succeeded.
            _write_results(results)

    # ---- write results --------------------------------------------------
    _write_results(results)


if __name__ == "__main__":
    main()
