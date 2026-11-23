"""
benchmark_v3.py — the performance experiment, corrected.

What was wrong with benchmark_v2
---------------------------------
1. **The sample-selection filter was part of the measured work.**
   `benchmark_v2` applied the SHA-256(LEI) sample filter *inside* the
   timed region on the Spark side (and a per-row Python `.map()` on the
   Pandas side).  At 27.5 % and 46.9 % the filter ran; at 100 % it was
   skipped entirely (`if thr < SAMPLE_MODULUS`).  That made the 100 %
   run artificially cheap and produced the nonsensical pattern where the
   Spark no-cache time *fell* from 2.18 s to 1.96 s to 0.47 s as the
   data grew.  Here the sample is materialised **once, outside the timed
   region**, and both engines then read the same rows.

2. **Only the cached variant supported the headline.**  The report quoted
   "1.35x -> 3.31x", which is the cached arm only.  In the no-cache arm
   Spark is *slower* than Pandas at the two smaller fractions.  Both arms
   are measured and both are reported.

3. **The workload was too light.**  A group-by over three low-cardinality
   columns finishes in 0.3-1.5 s, so most of what is being timed is
   Spark's scheduler and planning overhead rather than computation.  A
   second, heavier workload is added: a median and an approximate
   percentile over a high-cardinality key, which forces a real shuffle
   and a real aggregation.

4. **The environment was not recorded.**  The CPU, the core count, the
   OS, and the versions of Python, Pandas, Spark and the JVM were not
   written down, so the numbers could not be reproduced or judged.

What this version measures
--------------------------
* **Set-up is timed separately from the work**: the Spark session
  start-up, and the first read of the data, are outside the timed region
  and reported on their own.

* **The sample is materialised once**, before any timing, so that the
  filter cannot contaminate the measurement.

* **Two workloads**:
    - *light*: `group by joint_flag x loan_type x state_code` with a
      count and a mean, matching the original experiment.
    - *heavy*: a per-LEI median and an approximate percentile of the
      loan amount, which cannot be answered from a dictionary alone.

* **Both cache modes** for both engines, at the three sample fractions,
  repeated and reported as medians with the full list of timings.

* **The environment** is recorded in the output file.

Resource use
------------
    The Spark side runs a `local[*]` session with a small driver memory
and a small shuffle partition count.  Only the aggregation workload is
measured, so peak memory stays well under 8 GB.  The whole script runs
in minutes rather than the 1.8 h the original pipeline benchmark took.

Usage
-----
    python src/benchmark_v3.py
"""

import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C

OUT_JSON = C.RESULTS_DIR / "benchmark_v3.json"

#: The proposal promised five repetitions.
REPEATS = 5

#: Nominal sample fractions.  The realised row share is reported next to
#: each one, because the sample is drawn by hashing the LEI and whole
#: lenders are in or out.
FRACTIONS = [0.25, 0.5, 1.0]

#: Hash parameters for the sample rule.  Unchanged from v2 so the sample
#: is the same set of rows and the two runs are comparable.
SAMPLE_HASH_CHARS = 8
SAMPLE_MODULUS = 1000


# ---------------------------------------------------------------------------
# environment
# ---------------------------------------------------------------------------
def _environment() -> dict:
    """Record everything needed to judge or reproduce the timings."""
    env = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "logical_cores": os.cpu_count(),
        "physical_cores": None,
        "total_memory_bytes": None,
    }
    try:
        import psutil  # optional
        env["physical_cores"] = psutil.cpu_count(logical=False)
        env["total_memory_bytes"] = psutil.virtual_memory().total
        env["total_memory_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
    except Exception:
        pass
    try:
        env["cpu_model"] = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Processor).Name"],
            capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        pass
    for mod, key in (("pandas", "pandas"), ("numpy", "numpy"),
                     ("pyarrow", "pyarrow"), ("sklearn", "scikit_learn")):
        try:
            env[key] = __import__(mod).__version__
        except Exception:
            env[key] = None
    try:
        import pyspark
        env["spark"] = pyspark.__version__
    except Exception:
        env["spark"] = None
    try:
        env["java"] = subprocess.run(
            ["java", "-version"], capture_output=True, text=True,
            timeout=20).stderr.splitlines()[0].strip()
    except Exception:
        env["java"] = None
    return env


# ---------------------------------------------------------------------------
# sample materialisation
# ---------------------------------------------------------------------------
def _parquet_files() -> list[Path]:
    import glob
    files = sorted(glob.glob(str(C.CLEAN_PARQUET / "*.parquet")))
    if not files:
        raise SystemExit(f"no Parquet files under {C.CLEAN_DIR}")
    return [Path(f) for f in files]


def _realised_fractions() -> list[dict]:
    """The share of rows and lenders each nominal fraction actually selects.

    The sample is drawn by hashing the LEI, so a lender is either wholly
    in or wholly out.  The realised row share therefore differs from the
    nominal share, and the difference is reported rather than hidden.
    """
    import hashlib

    import pandas as pd

    files = _parquet_files()
    buckets = []
    for f in files:
        lei = pd.read_parquet(f, columns=["lei"])["lei"]
        buckets.append(lei.map(
            lambda s: int(hashlib.sha256(str(s).encode("utf-8")).hexdigest()[:SAMPLE_HASH_CHARS], 16)
            % SAMPLE_MODULUS))
    import numpy as np
    b = np.concatenate([x.to_numpy() for x in buckets])

    out = []
    for frac in FRACTIONS:
        thr = int(frac * SAMPLE_MODULUS)
        if thr >= SAMPLE_MODULUS:
            out.append({
                "nominal_fraction": frac,
                "hash_threshold": thr,
                "rows_selected": int(len(b)),
                "rows_total": int(len(b)),
                "realised_row_fraction": 1.0,
                "realised_lender_fraction": 1.0,
            })
            continue
        sel = b < thr
        out.append({
            "nominal_fraction": frac,
            "hash_threshold": thr,
            "rows_selected": int(sel.sum()),
            "rows_total": int(len(b)),
            "realised_row_fraction": round(float(sel.mean()), 4),
        })
    return out


def _pandas_sample(fraction: float):
    """Materialise the Pandas side of the sample.

    Returns a frame with the sampled rows only.  The filter runs *here*,
    before any timing, so that it cannot contaminate the measurement.
    """
    import hashlib

    import pandas as pd
    import pyarrow.parquet as pq

    files = _parquet_files()
    thr = int(fraction * SAMPLE_MODULUS)
    cols = ["joint_flag", "loan_type", "state_code", "lei", "loan_amount"]

    def _bucket(s: str) -> int:
        return int(hashlib.sha256(str(s).encode("utf-8")).hexdigest()[:SAMPLE_HASH_CHARS], 16) % SAMPLE_MODULUS

    frames = []
    for f in files:
        df = pq.read_table(f, columns=cols).to_pandas()
        if thr < SAMPLE_MODULUS:
            keep = df["lei"].map(_bucket) < thr
            df = df[keep]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _materialise_sample(fraction: float) -> Path:
    """Write the sampled rows to a Parquet directory, once.

    This is the key to an honest measurement.  In `benchmark_v2` the
    sample filter sat *inside* the timed region on the Spark side, and
    because the filter is skipped entirely at the 100 % fraction, the
    largest run looked artificially cheap.  Writing the sample out first
    means both engines read the *same files* and neither pays for the
    filter during the measurement.

    The directory is a scratch area and is removed by the caller.
    """
    import shutil

    out_dir = Path(str(C.BENCH_DIR / f"sample_{int(fraction * 1000):04d}"))
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = _pandas_sample(fraction)
    df.to_parquet(out_dir / "part-00000.parquet", index=False)
    return out_dir


# ---------------------------------------------------------------------------
# workloads
# ---------------------------------------------------------------------------
def _pandas_light(df):
    return (df.groupby(["joint_flag", "loan_type", "state_code"], observed=True)
              .agg(n=("state_code", "size"),
                   mean_loan_type=("loan_type", "mean"))
              .reset_index())


def _pandas_heavy(df):
    """Per-LEI median loan amount plus an approximate 90th percentile.

    The percentile is computed on a fixed stride, which is the Pandas
    analogue of Spark's `approx_percentile`: both are approximations to
    the same quantity, and both are deliberately the same shape of work.
    """
    import numpy as np

    out = (df.groupby("lei", observed=True)
             .agg(n=("loan_amount", "size"),
                  median_amount=("loan_amount", "median"))
             .reset_index())
    stride = max(1, len(df) // 200_000)
    approx = df["loan_amount"].to_numpy()[::stride]
    p90 = float(np.percentile(approx, 90))
    return out, p90


def _spark_light(sdf):
    from pyspark.sql import functions as F
    return (sdf.groupBy("joint_flag", "loan_type", "state_code")
              .agg(F.count("*").alias("n"),
                   F.avg("loan_type").alias("mean_loan_type"))
              .collect())


def _spark_heavy(sdf):
    from pyspark.sql import functions as F
    out = (sdf.groupBy("lei")
             .agg(F.count("*").alias("n"),
                  F.median("loan_amount").alias("median_amount"))
             .collect())
    p90 = sdf.approxQuantile("loan_amount", [0.9], 0.01)[0]
    return out, p90


# ---------------------------------------------------------------------------
# runners
# ---------------------------------------------------------------------------
def _run_spark(spark, sample_dir: Path, fraction: float, repeats: int) -> dict:
    from pyspark import StorageLevel
    from pyspark.sql import functions as F

    def _make_sdf(cache: bool):
        # Read the already-materialised sample.  There is no filter in
        # this plan, so the measurement contains no sampling cost.
        sdf = spark.read.parquet(str(sample_dir))
        if cache:
            sdf = sdf.persist(StorageLevel.MEMORY_AND_DISK)
            sdf.count()
        return sdf

    # ---- cached ---------------------------------------------------------
    t_cache_setup0 = time.perf_counter()
    sdf_cached = _make_sdf(cache=True)
    t_cache_setup = time.perf_counter() - t_cache_setup0

    t_cached_light, t_cached_heavy = [], []
    for _ in range(repeats):
        t0 = time.perf_counter()
        _spark_light(sdf_cached)
        t_cached_light.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        _spark_heavy(sdf_cached)
        t_cached_heavy.append(time.perf_counter() - t0)

    sdf_cached.unpersist()

    # ---- no-cache: rebuild the plan and re-read every time --------------
    t_nocache_light, t_nocache_heavy = [], []
    for _ in range(repeats):
        t0 = time.perf_counter()
        sdf = _make_sdf(cache=False)
        _spark_light(sdf)
        t_nocache_light.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        sdf = _make_sdf(cache=False)
        _spark_heavy(sdf)
        t_nocache_heavy.append(time.perf_counter() - t0)

    return {
        "engine": "pyspark",
        "cached": {
            "materialise_seconds": round(t_cache_setup, 3),
            "light_query_seconds_median": round(statistics.median(t_cached_light), 3),
            "light_query_seconds_all": [round(x, 3) for x in t_cached_light],
            "heavy_query_seconds_median": round(statistics.median(t_cached_heavy), 3),
            "heavy_query_seconds_all": [round(x, 3) for x in t_cached_heavy],
        },
        "no_cache": {
            "light_query_seconds_median": round(statistics.median(t_nocache_light), 3),
            "light_query_seconds_all": [round(x, 3) for x in t_nocache_light],
            "heavy_query_seconds_median": round(statistics.median(t_nocache_heavy), 3),
            "heavy_query_seconds_all": [round(x, 3) for x in t_nocache_heavy],
            "note": ("the plan is rebuilt and the Parquet files re-read on "
                     "every repetition"),
        },
    }


def main() -> None:
    import numpy as np  # noqa: F401  (used by the workload helpers)

    print("=" * 74)
    print("BENCHMARK v3")
    print("=" * 74)

    env = _environment()
    print(f"  {env.get('cpu_model') or env.get('processor') or 'unknown CPU'}")
    print(f"  {env['logical_cores']} logical cores, "
          f"{env.get('physical_cores')} physical")
    print(f"  {env.get('total_memory_gb')} GB RAM, {env['platform']}")
    print(f"  pandas {env['pandas']}, numpy {env['numpy']}, "
          f"pyarrow {env['pyarrow']}, spark {env['spark']}")
    print(f"  {env['java']}")

    print("\nMeasuring the realised sample fractions...")
    realised = _realised_fractions()
    for r in realised:
        print(f"  nominal {r['nominal_fraction']:.0%} -> realised rows "
              f"{r['realised_row_fraction']:.1%}")

    files = _parquet_files()

    from spark_pipeline import build_session

    results = []
    scratch_dirs = []
    for frac in FRACTIONS:
        print(f"\n--- fraction {frac:.0%} ---")

        # ---- materialise the sample OUTSIDE the timed region -------------
        t0 = time.perf_counter()
        sample_dir = _materialise_sample(frac)
        t_materialise = time.perf_counter() - t0
        scratch_dirs.append(sample_dir)
        n_rows = sum(p.stat().st_size for p in sample_dir.glob("*.parquet"))
        print(f"  sample materialised to {sample_dir.name}: "
              f"{t_materialise:.1f}s (outside the timed region)")

        # ---- Spark: session set-up timed on its own ----------------------
        t_setup0 = time.perf_counter()
        spark = build_session("HMDA-Benchmark-v3")
        t_setup = time.perf_counter() - t_setup0
        print(f"  spark session set-up: {t_setup:.3f}s")

        try:
            # ---- first read, timed on its own ----------------------------
            t_read0 = time.perf_counter()
            spark.read.parquet(str(sample_dir)).count()
            t_first_read = time.perf_counter() - t_read0
            print(f"  spark first read    : {t_first_read:.3f}s")

            sp = _run_spark(spark, sample_dir, frac, REPEATS)
            pd_res = _run_pandas_with_fraction(sample_dir, frac, REPEATS)
        finally:
            spark.stop()

        sp["fraction"] = frac
        sp["session_setup_seconds"] = round(t_setup, 3)
        sp["first_read_seconds"] = round(t_first_read, 3)
        pd_res["fraction"] = frac
        pd_res["sample_materialise_seconds"] = round(t_materialise, 3)

        results.extend([pd_res, sp])

        for mode in ("cached", "no_cache"):
            p = pd_res[mode]
            s = sp[mode]
            print(f"  {mode:9s} light: pandas {p['light_query_seconds_median']:7.3f}s  "
                  f"spark {s['light_query_seconds_median']:7.3f}s  "
                  f"ratio {p['light_query_seconds_median']/max(s['light_query_seconds_median'],1e-9):5.2f}x")
            print(f"  {mode:9s} heavy: pandas {p['heavy_query_seconds_median']:7.3f}s  "
                  f"spark {s['heavy_query_seconds_median']:7.3f}s  "
                  f"ratio {p['heavy_query_seconds_median']/max(s['heavy_query_seconds_median'],1e-9):5.2f}x")

    # ---- assemble -------------------------------------------------------
    out = {
        "config": {
            "repeats": REPEATS,
            "fractions": FRACTIONS,
            "workloads": {
                "light": "group by joint_flag x loan_type x state_code: count and mean",
                "heavy": "per-LEI median of loan_amount plus an approximate 90th percentile",
            },
            "sample_rule": (
                "SHA-256(lei)[0:8] as a base-16 integer, modulo 1000, compared "
                "against fraction * 1000. Whole lenders are in or out, so the "
                "realised row share differs from the nominal."
            ),
            "sample_materialised_outside_timed_region": True,
            "pandas_version": env["pandas"],
        },
        "environment": env,
        "realised_sample_fractions": realised,
        "results": results,
    }

    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWritten: {OUT_JSON}")

    # ---- clean up the scratch samples -----------------------------------
    import shutil
    for d in scratch_dirs:
        if d.exists():
            shutil.rmtree(d)
    if C.BENCH_DIR.exists() and not any(C.BENCH_DIR.iterdir()):
        C.BENCH_DIR.rmdir()
    print("scratch samples removed")


def _run_pandas_with_fraction(sample_dir: Path, fraction: float, repeats: int) -> dict:
    """Pandas arm.

    "cached"   : the sample is read once into a Pandas frame and the
                 queries run against that frame.
    "no-cache" : the sample is re-read from the Parquet file on every
                 repetition, so the read is inside the timed region.
    """
    import pandas as pd

    def _rebuild():
        return pd.read_parquet(sample_dir)

    df = _rebuild()

    # ---- cached ---------------------------------------------------------
    t_cached_light, t_cached_heavy = [], []
    for _ in range(repeats):
        t0 = time.perf_counter()
        _pandas_light(df)
        t_cached_light.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        _pandas_heavy(df)
        t_cached_heavy.append(time.perf_counter() - t0)

    # ---- no-cache -------------------------------------------------------
    # The re-read is inside the timed region, exactly as it is on the
    # Spark side, where the plan is rebuilt and the Parquet files are
    # re-scanned on every repetition.  Timing the read separately and
    # excluding it would make the two engines' "no cache" arms measure
    # different things, and would flatter whichever engine benefited from
    # the exclusion.  The read time is still recorded on its own, so that
    # the two can be reported separately if that is wanted.
    t_nocache_light, t_nocache_heavy, t_reads = [], [], []
    for _ in range(repeats):
        t0 = time.perf_counter()
        rebuilt = _rebuild()
        t_reads.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        _pandas_light(rebuilt)
        t_nocache_light.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        _pandas_heavy(rebuilt)
        t_nocache_heavy.append(time.perf_counter() - t0)
        del rebuilt

    # The read is charged to the query, so that the "no cache" arms of
    # the two engines are measured over the same span of work: build the
    # frame, then answer the query from it.  `read_seconds_*` keeps the
    # read on its own for reporting.
    med_read = statistics.median(t_reads)
    no_cache_light = [q + r for q, r in zip(t_nocache_light, t_reads)]
    no_cache_heavy = [q + r for q, r in zip(t_nocache_heavy, t_reads)]

    return {
        "engine": "pandas",
        "cached": {
            "light_query_seconds_median": round(statistics.median(t_cached_light), 3),
            "light_query_seconds_all": [round(x, 3) for x in t_cached_light],
            "heavy_query_seconds_median": round(statistics.median(t_cached_heavy), 3),
            "heavy_query_seconds_all": [round(x, 3) for x in t_cached_heavy],
            "note": ("the sample is already materialised as a Pandas frame; "
                     "the query touches only the frame"),
        },
        "no_cache": {
            "light_query_seconds_median": round(statistics.median(no_cache_light), 3),
            "light_query_seconds_all": [round(x, 3) for x in no_cache_light],
            "heavy_query_seconds_median": round(statistics.median(no_cache_heavy), 3),
            "heavy_query_seconds_all": [round(x, 3) for x in no_cache_heavy],
            "read_seconds_median": round(med_read, 3),
            "read_seconds_all": [round(x, 3) for x in t_reads],
            "note": ("the frame is rebuilt from the Parquet file on every "
                     "repetition, so the read is inside the timed region; "
                     "read_seconds_* reports that read on its own"),
        },
    }


if __name__ == "__main__":
    main()
