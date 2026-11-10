"""
analytics.py — Paired analytical implementations (Pandas and PySpark).

Every function in this module exists twice: once for Pandas and once for
PySpark, and the two versions compute *exactly* the same quantity from the
same cleaned dataset. This is what makes the equivalence comparison in
`equivalence.py` meaningful: it compares the analytical results, not just the
raw record counts.

Each function returns a plain Python object (dict of scalars, or a Pandas
DataFrame) so that the two engines can be compared directly.

The canonical outputs defined here are the ones compared in the report:

    1. record counts after each cleaning step
    2. missing-value counts for the important variables
    3. counts and proportions of application outcomes
    4. denial rate by joint_flag
    5. descriptive statistics of the main financial variables
    6. average / median loan amount by loan type
    7. aggregated loan amounts by financial institution (LEI)
"""

import pandas as pd
from pyspark.sql import functions as F

import config as C

#: Variables whose missing-value counts are compared.
MISSING_CHECK_COLUMNS = [
    "loan_amount", "income", "interest_rate", "rate_spread",
    "combined_loan_to_value_ratio", "property_value", "debt_to_income_ratio",
    "total_loan_costs", "loan_to_income_ratio", "joint_flag",
    "state_code", "lei", "applicant_age",
]

#: Variables whose descriptive statistics are compared.
DESCRIPTIVE_COLUMNS = ["loan_amount", "income", "interest_rate", "loan_to_income_ratio"]


# ==========================================================================
# 1. Record counts
# ==========================================================================

def record_counts_pandas(df: pd.DataFrame) -> dict:
    return {
        "records_total": int(len(df)),
        "records_with_decision": int(df["has_lender_decision"].sum()),
        "records_joint_flag_known": int(df["joint_flag"].notna().sum()),
        "records_joint": int((df["joint_flag"] == 1).sum()),
        "records_single": int((df["joint_flag"] == 0).sum()),
        "records_indeterminate_joint": int(df["joint_flag"].isna().sum()),
    }


def record_counts_spark(df) -> dict:
    return {
        "records_total": df.count(),
        "records_with_decision": df.filter(F.col("has_lender_decision") == 1).count(),
        "records_joint_flag_known": df.filter(F.col("joint_flag").isNotNull()).count(),
        "records_joint": df.filter(F.col("joint_flag") == 1).count(),
        "records_single": df.filter(F.col("joint_flag") == 0).count(),
        "records_indeterminate_joint": df.filter(F.col("joint_flag").isNull()).count(),
    }


# ==========================================================================
# 2. Missing-value counts
# ==========================================================================

def missing_counts_pandas(df: pd.DataFrame) -> dict:
    return {c: int(df[c].isna().sum()) for c in MISSING_CHECK_COLUMNS}


def missing_counts_spark(df) -> dict:
    out = {}
    agg = df.agg(*[F.sum(F.when(F.col(c).isNull(), 1).otherwise(0)).alias(c)
                   for c in MISSING_CHECK_COLUMNS]).collect()[0].asDict()
    for c in MISSING_CHECK_COLUMNS:
        out[c] = int(agg[c])
    return out


# ==========================================================================
# 3. Application outcomes
# ==========================================================================

def outcome_counts_pandas(df: pd.DataFrame) -> pd.DataFrame:
    vc = df["action_taken"].value_counts(dropna=False)
    out = pd.DataFrame({
        "action_taken": vc.index,
        "n": vc.values,
    })
    out["action_taken"] = out["action_taken"].astype("Int64")
    total = int(out["n"].sum())
    out["label"] = out["action_taken"].map(C.ACTION_TAKEN)
    out["proportion"] = out["n"] / total
    return out.sort_values("action_taken").reset_index(drop=True)


def outcome_counts_spark(df) -> pd.DataFrame:
    out = (df.groupBy("action_taken").count()
             .withColumnRenamed("count", "n"))
    total = df.count()
    out = out.withColumn("proportion", F.col("n") / F.lit(total))
    out = out.toPandas().sort_values("action_taken").reset_index(drop=True)
    # Spark stores the parsed code as a double; present it as an integer so
    # that the Pandas and Spark outputs are directly comparable.
    out["action_taken"] = out["action_taken"].astype("Int64")
    out["label"] = out["action_taken"].map(C.ACTION_TAKEN)
    return out


# ==========================================================================
# 4. Denial rate by joint_flag  (RQ1)
# ==========================================================================

def denial_rate_by_joint_pandas(df: pd.DataFrame) -> pd.DataFrame:
    # Records whose joint_flag could not be determined are excluded from the
    # joint-vs-single comparison; they are reported separately by
    # `record_counts`. Spark and Pandas must apply the same rule.
    d = df[(df["has_lender_decision"] == 1) & df["joint_flag"].notna()]
    g = d.groupby("joint_flag", dropna=True)
    out = pd.DataFrame({
        "n_decisions": g.size(),
        "n_denied": g["is_denied"].sum(),
    }).reset_index()
    out["denial_rate"] = out["n_denied"] / out["n_decisions"]
    out["joint_flag"] = out["joint_flag"].astype("Int64")
    return out.sort_values("joint_flag").reset_index(drop=True)


def denial_rate_by_joint_spark(df) -> pd.DataFrame:
    out = (df.filter((F.col("has_lender_decision") == 1) & F.col("joint_flag").isNotNull())
             .groupBy("joint_flag")
             .agg(F.count("*").alias("n_decisions"),
                  F.sum("is_denied").alias("n_denied"))
             .withColumn("denial_rate", F.col("n_denied") / F.col("n_decisions"))
             .orderBy("joint_flag"))
    out = out.toPandas().reset_index(drop=True)
    out["joint_flag"] = out["joint_flag"].astype("Int64")
    return out


# ==========================================================================
# 5. Descriptive statistics
# ==========================================================================

def descriptive_stats_pandas(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in DESCRIPTIVE_COLUMNS:
        s = df[c].dropna()
        rows.append({
            "variable": c,
            "n": int(len(s)),
            "n_missing": int(df[c].isna().sum()),
            "mean": float(s.mean()) if len(s) else None,
            "median": float(s.median()) if len(s) else None,
            "std": float(s.std()) if len(s) > 1 else None,
            "min": float(s.min()) if len(s) else None,
            "p25": float(s.quantile(0.25)) if len(s) else None,
            "p75": float(s.quantile(0.75)) if len(s) else None,
            "max": float(s.max()) if len(s) else None,
        })
    return pd.DataFrame(rows)


def descriptive_stats_spark(df) -> pd.DataFrame:
    from pyspark.sql import functions as F
    exprs = []
    for c in DESCRIPTIVE_COLUMNS:
        exprs += [
            F.count(F.col(c)).alias(f"{c}__n"),
            F.avg(F.col(c)).alias(f"{c}__mean"),
            F.expr(f"percentile_approx({c}, 0.5)").alias(f"{c}__median"),
            F.stddev(F.col(c)).alias(f"{c}__std"),
            F.min(F.col(c)).alias(f"{c}__min"),
            F.expr(f"percentile_approx({c}, 0.25)").alias(f"{c}__p25"),
            F.expr(f"percentile_approx({c}, 0.75)").alias(f"{c}__p75"),
            F.max(F.col(c)).alias(f"{c}__max"),
        ]
    row = df.agg(*exprs).collect()[0].asDict()
    total = df.count()
    rows = []
    for c in DESCRIPTIVE_COLUMNS:
        rows.append({
            "variable": c,
            "n": int(row[f"{c}__n"]),
            "n_missing": int(total - row[f"{c}__n"]),
            "mean": float(row[f"{c}__mean"]) if row[f"{c}__mean"] is not None else None,
            "median": float(row[f"{c}__median"]) if row[f"{c}__median"] is not None else None,
            "std": float(row[f"{c}__std"]) if row[f"{c}__std"] is not None else None,
            "min": float(row[f"{c}__min"]) if row[f"{c}__min"] is not None else None,
            "p25": float(row[f"{c}__p25"]) if row[f"{c}__p25"] is not None else None,
            "p75": float(row[f"{c}__p75"]) if row[f"{c}__p75"] is not None else None,
            "max": float(row[f"{c}__max"]) if row[f"{c}__max"] is not None else None,
        })
    return pd.DataFrame(rows)


# ==========================================================================
# 6. Loan amount by loan type
# ==========================================================================

def loan_amount_by_type_pandas(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("loan_type", dropna=True)["loan_amount"]
    out = pd.DataFrame({
        "n": g.size(),
        "mean_loan_amount": g.mean(),
        "median_loan_amount": g.median(),
    }).reset_index()
    out["loan_type"] = out["loan_type"].astype("Int64")
    out["label"] = out["loan_type"].map(C.LOAN_TYPE)
    return out.sort_values("loan_type").reset_index(drop=True)


def loan_amount_by_type_spark(df) -> pd.DataFrame:
    out = (df.groupBy("loan_type")
             .agg(F.count("loan_amount").alias("n"),
                  F.avg("loan_amount").alias("mean_loan_amount"),
                  F.expr("percentile_approx(loan_amount, 0.5)").alias("median_loan_amount"))
             .orderBy("loan_type"))
    out = out.toPandas().reset_index(drop=True)
    out["loan_type"] = out["loan_type"].astype("Int64")
    out["label"] = out["loan_type"].map(C.LOAN_TYPE)
    return out


# ==========================================================================
# 7. Aggregation by financial institution (LEI)
# ==========================================================================

def by_institution_pandas(df: pd.DataFrame, top_n: int = 50) -> pd.DataFrame:
    g = df.groupby("lei", dropna=True)
    out = pd.DataFrame({
        "n_applications": g.size(),
        "n_decisions": g["has_lender_decision"].sum(),
        "mean_loan_amount": g["loan_amount"].mean(),
        "total_loan_amount": g["loan_amount"].sum(),
    }).reset_index()
    # Sort by LEI first so that ties are broken identically to the Spark
    # version, which sorts by (n_applications DESC, lei ASC).
    out = out.sort_values(["n_applications", "lei"], ascending=[False, True])
    return out.head(top_n).reset_index(drop=True)


def by_institution_spark(df, top_n: int = 50) -> pd.DataFrame:
    out = (df.groupBy("lei")
             .agg(F.count("*").alias("n_applications"),
                  F.sum("has_lender_decision").alias("n_decisions"),
                  F.avg("loan_amount").alias("mean_loan_amount"),
                  F.sum("loan_amount").alias("total_loan_amount"))
             .orderBy(F.desc("n_applications"), F.asc("lei"))
             .limit(top_n))
    return out.toPandas().reset_index(drop=True)


# ==========================================================================
# 8. Denial rate by state (RQ4)
# ==========================================================================

def denial_rate_by_state_pandas(df: pd.DataFrame, top_n: int = C.TOP_N_STATES) -> pd.DataFrame:
    d = df[df["has_lender_decision"] == 1]
    g = d.groupby("state_code", dropna=True)
    out = pd.DataFrame({
        "n_decisions": g.size(),
        "n_denied": g["is_denied"].sum(),
    }).reset_index()
    out["denial_rate"] = out["n_denied"] / out["n_decisions"]
    # Tie-break on state_code so the ordering matches the Spark version.
    out = out.sort_values(["n_decisions", "state_code"], ascending=[False, True])
    return out.head(top_n).reset_index(drop=True)


def denial_rate_by_state_spark(df, top_n: int = C.TOP_N_STATES) -> pd.DataFrame:
    out = (df.filter(F.col("has_lender_decision") == 1)
             .groupBy("state_code")
             .agg(F.count("*").alias("n_decisions"),
                  F.sum("is_denied").alias("n_denied"))
             .withColumn("denial_rate", F.col("n_denied") / F.col("n_decisions"))
             .orderBy(F.desc("n_decisions"), F.asc("state_code"))
             .limit(top_n))
    return out.toPandas().reset_index(drop=True)
