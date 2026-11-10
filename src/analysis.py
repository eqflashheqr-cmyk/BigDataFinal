"""
analysis.py — Answer the four research questions of the group proposal.

    RQ1. How does the denial rate differ between joint and single applications?
    RQ2. How do income, loan amount, and loan-to-income ratio differ between
         the groups?
    RQ3. Does the denial-rate gap remain among applications with similar
         income, debt-to-income ratio, loan type, and loan purpose?
    RQ4. Does the gap vary by loan purpose and across the five states with
         the most applications?

The analysis is written once in "logical" form and executed by BOTH engines.
Each metric is a `Metric` object: a name, a Pandas implementation and a Spark
implementation that must return the same result.

Denial-rate definition (consistent with the proposal)
------------------------------------------------------
    denial_rate = D / (O + A + D)

where
    O = action_taken 1  (loan originated)
    A = action_taken 2  (approved but not accepted)
    D = action_taken 3  (application denied)

Codes 4-8 (withdrawn, incomplete, purchased, preapproval) are NOT lender
decisions and are excluded from the denominator. Records whose joint_flag is
indeterminate are excluded from the joint-vs-single comparison and reported
separately.

Outputs
-------
    results/rq1_denial_by_joint.csv
    results/rq2_financial_profile.csv
    results/rq3_stratified_denial.csv
    results/rq4_loan_purpose_and_states.csv
    results/analysis_report.json
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C

# --------------------------------------------------------------------------
# Shared derived variables used by the stratification in RQ3
# --------------------------------------------------------------------------

#: Income quartiles are computed on the *analysis population* (records with a
#: lender decision and a known joint_flag). The boundaries are computed once
#: from the data and then pinned, so that the Pandas and Spark implementations
#: place every record in exactly the same quartile. `pd.qcut` and Spark's
#: `ntile` would otherwise disagree at the boundaries.
INCOME_QUARTILE_LABELS = ["Q1 (lowest)", "Q2", "Q3", "Q4 (highest)"]

#: Filled in by `compute_income_quartile_bounds`; used by both engines.
INCOME_QUARTILE_BOUNDS: list[float] = [0.0, 75.0, 110.0, 165.0, float("inf")]


def compute_income_quartile_bounds(df: pd.DataFrame) -> list[float]:
    """Compute the income quartile cut points on the analysis population.

    The cut points are the 25th, 50th and 75th percentiles of `income`
    (reported in thousands of USD) over records that have a lender decision,
    a known joint_flag, and a reported income.
    """
    d = df[(df["has_lender_decision"] == 1) & df["joint_flag"].notna()]
    s = d["income"].dropna()
    q = s.quantile([0.25, 0.50, 0.75]).tolist()
    return [-float("inf")] + [float(x) for x in q] + [float("inf")]


def _income_quartile_from_bounds(income: float) -> str:
    """Assign an income value to a quartile label using the pinned bounds."""
    if income is None or (isinstance(income, float) and np.isnan(income)):
        return "Not reported"
    b = INCOME_QUARTILE_BOUNDS
    if income < b[1]:
        return INCOME_QUARTILE_LABELS[0]
    if income < b[2]:
        return INCOME_QUARTILE_LABELS[1]
    if income < b[3]:
        return INCOME_QUARTILE_LABELS[2]
    return INCOME_QUARTILE_LABELS[3]


def add_analysis_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add the derived columns the stratification needs (Pandas only)."""
    out = df.copy()
    out = out[out["has_lender_decision"] == 1].copy()

    # analysis population for the joint-vs-single comparison
    out = out[out["joint_flag"].notna()].copy()

    # income quartile, using the pinned bounds
    out["income_quartile"] = out["income"].map(_income_quartile_from_bounds)

    # DTI band label
    band_map = {i: b for i, b in enumerate(C.DTI_BANDS)}
    out["dti_band"] = out["dti_band_order"].map(band_map).fillna("Not reported")

    # readable labels
    out["loan_type_label"] = out["loan_type"].map(C.LOAN_TYPE).fillna("Unknown")
    out["loan_purpose_label"] = out["loan_purpose"].map(C.LOAN_PURPOSE).fillna("Unknown")
    out["joint_label"] = out["joint_flag"].map({0: "Single", 1: "Joint"}).astype("object")
    return out


def add_analysis_columns_spark(df):
    """Mirror of `add_analysis_columns` for PySpark."""
    from pyspark.sql import functions as F

    out = df.filter((F.col("has_lender_decision") == 1) & F.col("joint_flag").isNotNull())

    # income quartile, using the SAME pinned bounds as the Pandas version
    b = INCOME_QUARTILE_BOUNDS
    out = out.withColumn(
        "income_quartile",
        F.when(F.col("income").isNull(), F.lit("Not reported"))
         .when(F.col("income") < F.lit(b[1]), F.lit(INCOME_QUARTILE_LABELS[0]))
         .when(F.col("income") < F.lit(b[2]), F.lit(INCOME_QUARTILE_LABELS[1]))
         .when(F.col("income") < F.lit(b[3]), F.lit(INCOME_QUARTILE_LABELS[2]))
         .otherwise(F.lit(INCOME_QUARTILE_LABELS[3])),
    )

    band_map = {i: b for i, b in enumerate(C.DTI_BANDS)}
    band_expr = F.lit("Not reported")
    for i, b in reversed(list(band_map.items())):
        band_expr = F.when(F.col("dti_band_order") == F.lit(i), F.lit(b)).otherwise(band_expr)
    out = out.withColumn("dti_band", band_expr)

    out = out.withColumn(
        "loan_type_label",
        F.when(F.col("loan_type") == 1, F.lit(C.LOAN_TYPE[1]))
         .when(F.col("loan_type") == 2, F.lit(C.LOAN_TYPE[2]))
         .when(F.col("loan_type") == 3, F.lit(C.LOAN_TYPE[3]))
         .when(F.col("loan_type") == 4, F.lit(C.LOAN_TYPE[4]))
         .otherwise(F.lit("Unknown")),
    )
    out = out.withColumn(
        "loan_purpose_label",
        F.when(F.col("loan_purpose") == 1, F.lit(C.LOAN_PURPOSE[1]))
         .when(F.col("loan_purpose") == 2, F.lit(C.LOAN_PURPOSE[2]))
         .when(F.col("loan_purpose") == 31, F.lit(C.LOAN_PURPOSE[31]))
         .when(F.col("loan_purpose") == 32, F.lit(C.LOAN_PURPOSE[32]))
         .when(F.col("loan_purpose") == 4, F.lit(C.LOAN_PURPOSE[4]))
         .when(F.col("loan_purpose") == 5, F.lit(C.LOAN_PURPOSE[5]))
         .otherwise(F.lit("Unknown")),
    )
    out = out.withColumn(
        "joint_label",
        F.when(F.col("joint_flag") == 1, F.lit("Joint")).otherwise(F.lit("Single")),
    )
    return out


# ==========================================================================
# RQ1 — Denial rate by joint_flag
# ==========================================================================

#: Fixed display order for the two groups. Both engines must use it, because
#: Spark's `groupBy` returns rows in an unspecified order while Pandas sorts
#: group keys lexicographically ("Joint" < "Single").
JOINT_ORDER = ["Joint", "Single"]


def rq1_pandas(df: pd.DataFrame) -> pd.DataFrame:
    d = add_analysis_columns(df)
    g = d.groupby("joint_label")
    out = pd.DataFrame({
        "n_decisions": g.size(),
        "n_denied": g["is_denied"].sum(),
    }).reset_index()
    out["denial_rate"] = out["n_denied"] / out["n_decisions"]
    out["gap_vs_single_pp"] = out["denial_rate"] - out.loc[out["joint_label"] == "Single", "denial_rate"].iloc[0]
    out["joint_label"] = pd.Categorical(out["joint_label"], categories=JOINT_ORDER, ordered=True)
    return out.sort_values("joint_label").reset_index(drop=True)


def rq1_spark(df) -> pd.DataFrame:
    from pyspark.sql import functions as F
    d = add_analysis_columns_spark(df)
    out = (d.groupBy("joint_label")
             .agg(F.count("*").alias("n_decisions"),
                  F.sum("is_denied").alias("n_denied"))
             .withColumn("denial_rate", F.col("n_denied") / F.col("n_decisions")))
    out = out.toPandas()
    single = out.loc[out["joint_label"] == "Single", "denial_rate"].iloc[0]
    out["gap_vs_single_pp"] = out["denial_rate"] - single
    out["joint_label"] = pd.Categorical(out["joint_label"], categories=JOINT_ORDER, ordered=True)
    return out.sort_values("joint_label").reset_index(drop=True)


# ==========================================================================
# RQ2 — Financial profile of the two groups
# ==========================================================================

RQ2_VARS = ["income_dollars", "loan_amount", "loan_to_income_ratio", "interest_rate"]


def rq2_pandas(df: pd.DataFrame) -> pd.DataFrame:
    d = add_analysis_columns(df)
    rows = []
    for var in RQ2_VARS:
        for label in JOINT_ORDER:
            grp = d[d["joint_label"] == label]
            s = grp[var].dropna()
            rows.append({
                "variable": var,
                "joint_label": label,
                "n": int(len(s)),
                "n_missing": int(grp[var].isna().sum()),
                "mean": float(s.mean()) if len(s) else np.nan,
                "median": float(s.median()) if len(s) else np.nan,
                "std": float(s.std()) if len(s) > 1 else np.nan,
                "p25": float(s.quantile(0.25)) if len(s) else np.nan,
                "p75": float(s.quantile(0.75)) if len(s) else np.nan,
            })
    return pd.DataFrame(rows)


def rq2_spark(df) -> pd.DataFrame:
    from pyspark.sql import functions as F
    d = add_analysis_columns_spark(df)
    exprs = []
    for v in RQ2_VARS:
        exprs += [
            F.count(F.col(v)).alias(f"{v}__n"),
            F.avg(F.col(v)).alias(f"{v}__mean"),
            F.expr(f"percentile_approx({v}, 0.5)").alias(f"{v}__median"),
            F.stddev(F.col(v)).alias(f"{v}__std"),
            F.expr(f"percentile_approx({v}, 0.25)").alias(f"{v}__p25"),
            F.expr(f"percentile_approx({v}, 0.75)").alias(f"{v}__p75"),
        ]
    agg = d.groupBy("joint_label").agg(*exprs).toPandas()
    total = d.groupBy("joint_label").count().toPandas().set_index("joint_label")["count"]

    rows = []
    for _, r in agg.iterrows():
        label = r["joint_label"]
        for v in RQ2_VARS:
            rows.append({
                "variable": v,
                "joint_label": label,
                "n": int(r[f"{v}__n"]),
                "n_missing": int(total[label] - r[f"{v}__n"]),
                "mean": float(r[f"{v}__mean"]) if pd.notna(r[f"{v}__mean"]) else np.nan,
                "median": float(r[f"{v}__median"]) if pd.notna(r[f"{v}__median"]) else np.nan,
                "std": float(r[f"{v}__std"]) if pd.notna(r[f"{v}__std"]) else np.nan,
                "p25": float(r[f"{v}__p25"]) if pd.notna(r[f"{v}__p25"]) else np.nan,
                "p75": float(r[f"{v}__p75"]) if pd.notna(r[f"{v}__p75"]) else np.nan,
            })
    out = pd.DataFrame(rows)
    # Fixed row order: variable order from RQ2_VARS, then Joint before Single.
    out["_v"] = out["variable"].map({v: i for i, v in enumerate(RQ2_VARS)})
    out["_j"] = out["joint_label"].map({v: i for i, v in enumerate(JOINT_ORDER)})
    out = out.sort_values(["_v", "_j"]).drop(columns=["_v", "_j"])
    return out.reset_index(drop=True)


# ==========================================================================
# RQ3 — Stratified denial rates
# ==========================================================================

RQ3_STRATA = ["income_quartile", "dti_band", "loan_type_label", "loan_purpose_label"]
RQ3_MIN_CELL = 30  # suppress cells with fewer decisions


def _rq3_frame(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(RQ3_STRATA + ["joint_label"])
    out = pd.DataFrame({
        "n_decisions": g.size(),
        "n_denied": g["is_denied"].sum(),
    }).reset_index()
    out["denial_rate"] = out["n_denied"] / out["n_decisions"]
    return out


def _pivot_denial(out: pd.DataFrame) -> pd.DataFrame:
    """Pivot the joint/single denial rates side by side and add the gap.

    `out` must be a Pandas DataFrame with the columns
    [strata..., joint_label, n_decisions, n_denied, denial_rate].
    """
    piv = out.pivot_table(index=RQ3_STRATA, columns="joint_label",
                          values=["n_decisions", "n_denied", "denial_rate"],
                          aggfunc="first").reset_index()
    piv.columns = [
        "_".join([str(x) for x in c if str(x) != ""]) if isinstance(c, tuple) else c
        for c in piv.columns
    ]
    piv = piv.rename(columns={
        "n_decisions_Joint": "n_decisions_joint",
        "n_decisions_Single": "n_decisions_single",
        "n_denied_Joint": "n_denied_joint",
        "n_denied_Single": "n_denied_single",
        "denial_rate_Joint": "denial_rate_joint",
        "denial_rate_Single": "denial_rate_single",
    })
    for c in ["n_decisions_joint", "n_decisions_single", "n_denied_joint", "n_denied_single"]:
        if c in piv.columns:
            piv[c] = piv[c].fillna(0).astype("int64")
    if "denial_rate_joint" in piv.columns and "denial_rate_single" in piv.columns:
        piv["gap_pp"] = (piv["denial_rate_joint"] - piv["denial_rate_single"]) * 100
        piv["joint_lower"] = piv["denial_rate_joint"] < piv["denial_rate_single"]
    piv["n_decisions_total"] = piv.get("n_decisions_joint", 0) + piv.get("n_decisions_single", 0)
    piv["suppressed_small_cell"] = piv["n_decisions_total"] < RQ3_MIN_CELL
    return piv


def rq3_pandas(df: pd.DataFrame) -> pd.DataFrame:
    d = add_analysis_columns(df)
    out = _rq3_frame(d)
    return _pivot_denial(out)


def rq3_spark(df) -> pd.DataFrame:
    from pyspark.sql import functions as F
    d = add_analysis_columns_spark(df)
    out = (d.groupBy(*RQ3_STRATA, "joint_label")
             .agg(F.count("*").alias("n_decisions"),
                  F.sum("is_denied").alias("n_denied"))
             .withColumn("denial_rate", F.col("n_denied") / F.col("n_decisions")))
    # The aggregated result is small enough to collect; the pivot is then
    # performed in Pandas so that both engines use identical pivot logic.
    return _pivot_denial(out.toPandas())


# ==========================================================================
# RQ4 — Loan purpose and the top-5 states
# ==========================================================================

def _pivot_rq4(out: pd.DataFrame) -> pd.DataFrame:
    """Pivot the RQ4 joint/single results side by side and add the gap."""
    piv = out.pivot_table(index=["dimension", "level"], columns="joint_label",
                          values=["n_decisions", "n_denied", "denial_rate"],
                          aggfunc="first").reset_index()
    piv.columns = [
        "_".join([str(x) for x in c if str(x) != ""]) if isinstance(c, tuple) else c
        for c in piv.columns
    ]
    piv = piv.rename(columns={
        "n_decisions_Joint": "n_decisions_joint",
        "n_decisions_Single": "n_decisions_single",
        "n_denied_Joint": "n_denied_joint",
        "n_denied_Single": "n_denied_single",
        "denial_rate_Joint": "denial_rate_joint",
        "denial_rate_Single": "denial_rate_single",
    })
    for c in ["n_decisions_joint", "n_decisions_single", "n_denied_joint", "n_denied_single"]:
        if c in piv.columns:
            piv[c] = piv[c].fillna(0).astype("int64")
    if "denial_rate_joint" in piv.columns and "denial_rate_single" in piv.columns:
        piv["gap_pp"] = (piv["denial_rate_joint"] - piv["denial_rate_single"]) * 100
        piv["joint_lower"] = piv["denial_rate_joint"] < piv["denial_rate_single"]
    return piv.sort_values(["dimension", "level"]).reset_index(drop=True)


def rq4_pandas(df: pd.DataFrame) -> pd.DataFrame:
    d = add_analysis_columns(df)

    top_states = (
        d.groupby("state_code", dropna=True).size()
        .sort_values(ascending=False).head(C.TOP_N_STATES).index.tolist()
    )

    parts = []
    for dim, col in [("loan_purpose", "loan_purpose_label"), ("state", "state_code")]:
        sub = d if dim == "loan_purpose" else d[d["state_code"].isin(top_states)]
        g = sub.groupby([col, "joint_label"])
        t = pd.DataFrame({
            "n_decisions": g.size(),
            "n_denied": g["is_denied"].sum(),
        }).reset_index().rename(columns={col: "level"})
        t.insert(0, "dimension", dim)
        parts.append(t)

    out = pd.concat(parts, ignore_index=True)
    out["denial_rate"] = out["n_denied"] / out["n_decisions"]
    return _pivot_rq4(out)


def rq4_spark(df) -> pd.DataFrame:
    from pyspark.sql import functions as F
    d = add_analysis_columns_spark(df)

    top_states = [
        r["state_code"] for r in
        d.groupBy("state_code").count()
         .orderBy(F.desc("count"), F.asc("state_code"))
         .limit(C.TOP_N_STATES).collect()
    ]

    parts = []
    for dim, col in [("loan_purpose", "loan_purpose_label"), ("state", "state_code")]:
        sub = d if dim == "loan_purpose" else d.filter(F.col("state_code").isin(top_states))
        t = (sub.groupBy(col, "joint_label")
               .agg(F.count("*").alias("n_decisions"),
                    F.sum("is_denied").alias("n_denied"))
               .withColumn("denial_rate", F.col("n_denied") / F.col("n_decisions"))
               .withColumn("dimension", F.lit(dim))
               .withColumnRenamed(col, "level"))
        parts.append(t)

    from functools import reduce
    out = reduce(lambda a, b: a.unionByName(b), parts)
    return _pivot_rq4(out.toPandas())


# ==========================================================================
# Orchestration
# ==========================================================================

RQS = {
    "RQ1": ("Denial rate by joint_flag", rq1_pandas, rq1_spark),
    "RQ2": ("Financial profile: income, loan amount, loan-to-income ratio", rq2_pandas, rq2_spark),
    "RQ3": ("Stratified denial rates (income quartile x DTI x loan type x purpose)", rq3_pandas, rq3_spark),
    "RQ4": ("Denial rate by loan purpose and by top-5 state", rq4_pandas, rq4_spark),
}


def run(engine: str) -> dict:
    """Run all four RQs in the requested engine ('pandas' or 'spark')."""
    global INCOME_QUARTILE_BOUNDS
    results = {}
    if engine == "pandas":
        from equivalence import load_clean_pandas
        df = load_clean_pandas()
        # Pin the income quartile boundaries from the data once, so that the
        # Spark run places every record in exactly the same quartile.
        INCOME_QUARTILE_BOUNDS = compute_income_quartile_bounds(df)
        print(f"Income quartile bounds (thousands USD): {INCOME_QUARTILE_BOUNDS}")
        (C.RESULTS_DIR / "income_quartile_bounds.json").write_text(
            json.dumps(INCOME_QUARTILE_BOUNDS), encoding="utf-8"
        )
        for rq, (_, fp, _) in RQS.items():
            results[rq] = fp(df)
            results[rq].to_csv(C.RESULTS_DIR / f"{rq.lower()}_pandas.csv", index=False)
    else:
        from spark_pipeline import build_session
        from pyspark import StorageLevel
        # Use the SAME bounds as the Pandas run.
        INCOME_QUARTILE_BOUNDS = load_bounds_from_json()
        print(f"Income quartile bounds (thousands USD): {INCOME_QUARTILE_BOUNDS}")
        spark = build_session("HMDA-Analysis")
        try:
            needed = [
                "action_taken", "has_lender_decision", "is_denied", "joint_flag",
                "loan_amount", "income", "income_dollars", "interest_rate",
                "loan_to_income_ratio", "debt_to_income_ratio", "dti_band_order",
                "loan_type", "loan_purpose", "state_code",
            ]
            sdf = spark.read.parquet(str(C.SPARK_PARQUET)).select(*needed)
            sdf = sdf.persist(StorageLevel.MEMORY_AND_DISK)
            sdf.count()
            for rq, (_, _, fs) in RQS.items():
                results[rq] = fs(sdf)
                results[rq].to_csv(C.RESULTS_DIR / f"{rq.lower()}_spark.csv", index=False)
            sdf.unpersist()
        finally:
            spark.stop()
    return results


def load_bounds_from_json() -> list[float]:
    """Load the pinned income quartile bounds written by the Pandas run."""
    p = C.RESULTS_DIR / "income_quartile_bounds.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return INCOME_QUARTILE_BOUNDS
