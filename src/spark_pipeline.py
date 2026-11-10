"""
spark_pipeline.py — Build the prepared analytical dataset using PySpark.

Reads the same raw FFIEC HMDA 2024 pipe-delimited file as `pandas_pipeline.py`,
applies the identical cleaning rules from `rules.clean_spark`, and writes its own
Parquet output. The two outputs are then compared by `equivalence.py`.

Why the raw text file and not the Pandas Parquet?
-------------------------------------------------
Both engines must start from the *same* input records and apply the *same*
rules independently, otherwise the equivalence check proves nothing. Reading
the raw file in both engines makes the comparison meaningful.

Usage
-----
    python src/spark_pipeline.py
"""

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

import config as C
from rules import clean_spark


def build_session(app_name: str = "HMDA-Spark-Pipeline") -> SparkSession:
    spark = (
        SparkSession.builder
        .master("local[*]")
        .appName(app_name)
        .config("spark.driver.memory", C.SPARK_DRIVER_MEMORY)
        .config("spark.sql.shuffle.partitions", str(C.SPARK_SHUFFLE_PARTITIONS))
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def main() -> None:
    if not C.RAW_FILE.exists():
        raise SystemExit(f"Raw file not found: {C.RAW_FILE}")

    print(f"Raw file : {C.RAW_FILE}")
    print(f"Size     : {C.RAW_FILE.stat().st_size / (1024 ** 3):.2f} GiB")
    print(f"Output   : {C.SPARK_PARQUET}")
    print()

    out_dir = Path(str(C.SPARK_PARQUET))
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    spark = build_session()
    try:
        t0 = time.perf_counter()

        raw = (
            spark.read
            .option("delimiter", C.DELIMITER)
            .option("header", "true")
            .option("inferSchema", "false")
            .option("mode", "PERMISSIVE")
            .option("encoding", "UTF-8")
            .csv(str(C.RAW_FILE))
        )

        # ---- exclusion counts, computed on the raw frame in ONE pass -------
        # These are counted on the RAW frame, before deduplication, so they
        # include negatives that were also exact duplicates. The
        # authoritative comparable figures are computed by `clean_spark`
        # after deduplication.
        bad_expr = F.lit(False)
        for col in C.NON_NEGATIVE_NUMERIC:
            if col in raw.columns:
                num = F.when(
                    F.trim(F.col(col)).isin(list(C.SPECIAL_CODES)), F.lit(None).cast("double")
                ).otherwise(
                    F.when(
                        F.trim(F.col(col)).rlike(r"^[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?$"),
                        F.trim(F.col(col)).cast("double"),
                    ).otherwise(F.lit(None).cast("double"))
                )
                bad_expr = bad_expr | (num.isNotNull() & (num < 0))

        summary = raw.agg(
            F.count("*").alias("records_raw"),
            F.sum(F.when(bad_expr, 1).otherwise(0)).alias("removed_negative_amounts"),
        ).collect()[0].asDict()

        report: dict = {
            "records_raw": int(summary["records_raw"]),
            "removed_negative_amounts_raw_frame": int(summary["removed_negative_amounts"]),
        }

        print(f"Raw rows (Spark count)      : {report['records_raw']:,}")
        print(f"Raw columns (Spark schema)  : {len(raw.columns)}")
        print()

        cleaned = clean_spark(raw, report=report)

        # Materialise once so the counting actions are not repeated.
        cleaned = cleaned.cache()
        cleaned.count()

        elapsed = time.perf_counter() - t0

        cleaned.write.mode("overwrite").parquet(str(out_dir))

        report_out = {
            "engine": "pyspark",
            "spark_version": spark.version,
            "raw_file": str(C.RAW_FILE),
            "raw_file_bytes": C.RAW_FILE.stat().st_size,
            "delimiter": C.DELIMITER,
            "n_columns_raw": len(raw.columns),
            "spark_driver_memory": C.SPARK_DRIVER_MEMORY,
            "spark_shuffle_partitions": C.SPARK_SHUFFLE_PARTITIONS,
            "elapsed_seconds": round(elapsed, 2),
            **report,
        }
        out_json = C.RESULTS_DIR / "cleaning_report_spark.json"
        out_json.write_text(json.dumps(report_out, indent=2), encoding="utf-8")

        print()
        print("Cleaning report (PySpark)")
        print("-" * 46)
        for k, v in report_out.items():
            print(f"  {k:<34} {v}")
        print()
        print(f"Written: {out_json}")
        print(f"Written: {out_dir}")

        cleaned.unpersist()
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
