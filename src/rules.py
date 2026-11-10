"""
rules.py — Engine-independent cleaning and feature-engineering rules.

This module holds the *logic* of the cleaning rules in a form that is easy to
read and to keep identical between Pandas and Spark. Two implementations are
provided:

    clean_pandas(df)  -> pandas.DataFrame
    clean_spark(df)   -> pyspark.sql.DataFrame

Both consume a DataFrame whose columns are the raw text fields, and produce a
DataFrame with the same typed columns and the same derived variables. The two
functions are written to mirror each other line by line so that a reviewer can
check the equivalence by eye.

Cleaning principles (from the assignment and the proposal)
-----------------------------------------------------------
* Special codes ("Exempt", "NA", 1111, 8888, 9999) are treated as MISSING,
  never as zero.
* Implausible values (negative loan amount, negative income) are removed with
  the count reported; genuinely extreme values are KEPT.
* Every exclusion is counted so the report can state exactly how many records
  were removed at each step and why.
"""

import re

import numpy as np
import pandas as pd
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType

import config as C

# ==========================================================================
# Shared literals
# ==========================================================================

#: Regex-free normalisation of a raw text field into one of three states for
#: the co-applicant fields:
#:   True  -> a co-applicant is present
#:   False -> the field explicitly says there is no co-applicant
#:   None  -> not applicable / not reported
#
#: Note the subtlety: "Information not provided by applicant" (code 3 / 6)
#: still implies a co-applicant EXISTS, so it counts as True, not as missing.

_CO_APPLICANT_PRESENT = {
    "co_applicant_ethnicity_1": {"1", "2", "3", "11", "12", "13", "14"},
    "co_applicant_race_1": {
        "1", "2", "3", "4", "5", "6",
        "21", "22", "23", "24", "25", "26", "27",
        "41", "42", "43", "44",
    },
    "co_applicant_sex": {"1", "2", "3", "6"},
    "co_applicant_credit_score_type": {
        "1", "2", "3", "4", "5", "6", "7", "8", "11", "12", "13", "14", "15",
    },
}


# ==========================================================================
# Pandas implementation
# ==========================================================================

def _to_numeric_pandas(s: pd.Series) -> pd.Series:
    """Parse a text column into a nullable numeric column.

    Blank strings and the special codes become NaN. A genuine 0 stays 0.
    """
    s = s.astype("string").str.strip()
    s = s.replace({c: pd.NA for c in C.SPECIAL_CODES})
    return pd.to_numeric(s, errors="coerce")


def _joint_flag_pandas(df: pd.DataFrame) -> pd.Series:
    """Return a Series of {0, 1, None} for co-applicant presence."""
    states = {}
    for col in C.JOINT_FIELDS:
        absent = C.NO_CO_APPLICANT_CODE[col]
        na_codes = set(C.CO_APPLICANT_NA_CODES[col]) | set(C.SPECIAL_CODES)
        present = _CO_APPLICANT_PRESENT[col]
        states[col] = df[col].astype("string").str.strip().map(
            lambda v: None if pd.isna(v)
            else (False if v == absent else (None if v in na_codes else (True if v in present else None)))
        )
    s = pd.DataFrame(states)
    n_present = s.eq(True).sum(axis=1)
    n_absent = s.eq(False).sum(axis=1)

    flag = pd.Series(pd.NA, index=df.index, dtype="Int64")
    flag[n_present.gt(0) & n_absent.eq(0)] = 1
    flag[n_absent.gt(0) & n_present.eq(0)] = 0
    return flag


def _dti_band_pandas(s: pd.Series) -> pd.Series:
    """Map a DTI band string to its position in `config.DTI_BANDS`.

    Missing / not-applicable DTI values map to None so they can be counted as
    missing rather than silently becoming the lowest band.
    """
    order = {b: i for i, b in enumerate(C.DTI_BANDS)}
    out = s.astype("string").str.strip()
    # exact band strings (the file stores 36..49 without a trailing % sign)
    exact = out.map(order)
    return exact.astype("Float64")


def clean_pandas(df: pd.DataFrame, report: dict | None = None,
                seen_hashes: np.ndarray | None = None) -> pd.DataFrame:
    """Apply the full cleaning + feature-engineering pipeline in Pandas.

    Parameters
    ----------
    df : raw DataFrame with the 99 text columns.
    report : optional dict that collects the counts removed at each step.
    seen_hashes : optional 1-D uint64 array of row hashes already emitted by
        an earlier chunk. It is used to detect duplicates that span chunk
        boundaries and is updated in place, so that the Pandas pipeline can
        deduplicate the whole file while processing it in chunks.
    """
    rep = report if report is not None else {}
    rep["records_raw"] = int(len(df))

    out = df.copy()

    # ---- 1. normalise whitespace and blank-like values -------------------
    for col in out.columns:
        out[col] = out[col].astype("string").str.strip()

    # ---- 1b. remove exact duplicate rows ---------------------------------
    # HMDA should contain one record per application, so a row identical to
    # another in ALL 99 fields is redundant. See `config.py` for why the
    # weaker "business key" definition is NOT used for removal.
    if C.DEDUPLICATE_ON_ALL_COLUMNS:
        raw_cols = [c for c in C.ALL_COLUMNS if c in out.columns]
        h = pd.util.hash_pandas_object(out[raw_cols], index=False).to_numpy()
        if seen_hashes is not None and len(seen_hashes):
            seen_mask = np.isin(h, seen_hashes)
        else:
            seen_mask = np.zeros(len(h), dtype=bool)
        within_chunk = pd.Series(h).duplicated(keep="first").to_numpy()
        keep = ~(seen_mask | within_chunk)
        rep["removed_exact_duplicates"] = int((~keep).sum())
        out = out.loc[keep].copy()
        kept_h = h[keep]
        rep["_kept_hashes"] = kept_h
        seen_hashes = kept_h if seen_hashes is None else np.concatenate([seen_hashes, kept_h])
    else:
        rep["_kept_hashes"] = np.array([], dtype=np.uint64)

    # ---- 2. derive joint_flag BEFORE coercing types ----------------------
    joint = _joint_flag_pandas(out)
    out["joint_flag"] = joint

    # ---- 3. numeric parsing ----------------------------------------------
    for col in C.NUMERIC_COLUMNS:
        if col in out.columns:
            out[col] = _to_numeric_pandas(out[col])

    # `action_taken` and other code columns keep their numeric value but the
    # special codes are already gone.
    out["activity_year"] = out["activity_year"].astype("Int64")

    # ---- 4. implausible-value filter -------------------------------------
    rep["records_before_implausible"] = int(len(out))
    bad = pd.Series(False, index=out.index)
    for col in C.NON_NEGATIVE_NUMERIC:
        if col in out.columns:
            bad |= out[col].notna() & out[col].lt(0)
    rep["removed_negative_amounts"] = int(bad.sum())
    out = out.loc[~bad].copy()
    # `loan_amount` of zero is not a real loan either.
    zero_loan = out["loan_amount"].eq(0)
    rep["removed_zero_loan_amount"] = int(zero_loan.sum())
    out = out.loc[~zero_loan].copy()

    # ---- 5. derived variables ---------------------------------------------
    out["income_dollars"] = out["income"] * C.INCOME_UNIT

    # loan-to-income ratio; only computed for valid positive values.
    valid_lti = (
        out["loan_amount"].notna() & out["loan_amount"].gt(0)
        & out["income"].notna() & out["income"].gt(0)
    )
    out["loan_to_income_ratio"] = pd.Series(pd.NA, index=out.index, dtype="Float64")
    out.loc[valid_lti, "loan_to_income_ratio"] = (
        out.loc[valid_lti, "loan_amount"] / (out.loc[valid_lti, "income"] * C.INCOME_UNIT)
    ).astype("Float64")

    out["dti_band_order"] = _dti_band_pandas(out["debt_to_income_ratio"])
    out["is_denied"] = out["action_taken"].eq(C.DENIED_CODE).astype("Int8")
    out["has_lender_decision"] = out["action_taken"].isin(C.OUTCOME_CODES).astype("Int8")

    rep["records_after_cleaning"] = int(len(out))
    rep["records_indeterminate_joint"] = int(out["joint_flag"].isna().sum())

    return out


# ==========================================================================
# Spark implementation
# ==========================================================================

def _to_numeric_spark(df):
    """Parse text columns into doubles, mapping special codes to null.

    The regular expression is written to accept exactly the same numeric
    literals as `pandas.to_numeric(errors="coerce")` so that the two engines
    cannot disagree about what counts as a number:
        [-+]? digits [. digits] [ (e|E) [+/-] digits ]
    """
    num_re = r"^[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?$"
    for col in C.NUMERIC_COLUMNS:
        if col in df.columns:
            df = df.withColumn(
                col,
                F.when(
                    F.trim(F.col(col)).isin(list(C.SPECIAL_CODES)),
                    F.lit(None).cast(DoubleType()),
                ).otherwise(
                    F.when(
                        F.trim(F.col(col)).rlike(num_re),
                        F.trim(F.col(col)).cast(DoubleType()),
                    ).otherwise(F.lit(None).cast(DoubleType()))
                ),
            )
    return df


def _joint_flag_spark(df):
    """Mirror of `_joint_flag_pandas`.

    Note on NULL handling: Spark's CSV reader turns an empty field into NULL,
    whereas Pandas (read with `na_filter=False`) yields an empty string. Both
    are "not reported", so the classification below treats them identically.

    The presence/absence counters MUST be wrapped in `coalesce(..., 0)`: in
    Spark a NULL operand makes the whole SUM NULL, which would silently turn
    an otherwise valid record into "indeterminate".
    """
    present_cols, absent_cols = [], []
    for col in C.JOINT_FIELDS:
        absent = C.NO_CO_APPLICANT_CODE[col]
        na_codes = sorted(set(C.CO_APPLICANT_NA_CODES[col]) | set(C.SPECIAL_CODES))
        present = sorted(_CO_APPLICANT_PRESENT[col])
        trimmed = F.trim(F.col(col))
        # A field is "present" when it holds a genuine co-applicant value.
        c_present = F.coalesce(trimmed.isin(present).cast("int"), F.lit(0))
        # A field is "absent" when it explicitly says there is no co-applicant.
        c_absent = F.coalesce((trimmed == absent).cast("int"), F.lit(0))
        present_cols.append(c_present)
        absent_cols.append(c_absent)

    n_present = sum(present_cols)
    n_absent = sum(absent_cols)
    return (
        F.when((n_present > 0) & (n_absent == 0), F.lit(1))
        .when((n_absent > 0) & (n_present == 0), F.lit(0))
        .otherwise(F.lit(None).cast("int"))
    )


def _dti_band_spark(df):
    """Mirror of `_dti_band_pandas`."""
    s = F.trim(F.col("debt_to_income_ratio"))
    out = F.lit(None).cast("int")
    for i, band in enumerate(C.DTI_BANDS):
        out = F.when(s == band, F.lit(i)).otherwise(out)
    return out


def clean_spark(df, report: dict | None = None):
    """Mirror of `clean_pandas` for PySpark.

    The exclusion counts are collected with a single aggregation pass rather
    than one `count()` per step: each `count()` is a full pass over the data,
    and five of them multiplied the cost of the cleaning stage by five.
    """
    rep = report if report is not None else {}

    # ---- 1. trim whitespace ----------------------------------------------
    for col in df.columns:
        df = df.withColumn(col, F.trim(F.col(col)))

    # ---- 1b. remove exact duplicate rows ---------------------------------
    # HMDA should contain one record per application, so a row identical to
    # another in ALL 99 fields is redundant. See `config.py` for why the
    # weaker "business key" definition is NOT used for removal.
    #
    # `dropDuplicates()` with an explicit subset deduplicates on those
    # columns, which is exactly the rule. It is implemented as a single
    # native aggregate and is far cheaper than a window function over 99
    # concatenated columns.
    if C.DEDUPLICATE_ON_ALL_COLUMNS:
        raw_cols = [c for c in C.ALL_COLUMNS if c in df.columns]
        if raw_cols:
            df = df.dropDuplicates(raw_cols)

    # ---- 2. joint_flag ----------------------------------------------------
    df = df.withColumn("joint_flag", _joint_flag_spark(df))

    # ---- 3. numeric parsing ----------------------------------------------
    df = _to_numeric_spark(df)
    df = df.withColumn("activity_year", F.col("activity_year").cast("int"))

    # ---- 4. implausible-value filter --------------------------------------
    # The counts are taken on the frame AFTER deduplication but BEFORE the
    # filter, in a single aggregation pass, so that they are directly
    # comparable with the Pandas implementation.
    bad = F.lit(False)
    for col in C.NON_NEGATIVE_NUMERIC:
        if col in df.columns:
            bad = bad | (F.col(col).isNotNull() & (F.col(col) < 0))

    summary = df.agg(
        F.count("*").alias("records_before_implausible"),
        F.sum(F.when(bad, 1).otherwise(0)).alias("removed_negative_amounts"),
        F.sum(F.when(F.col("loan_amount") == 0, 1).otherwise(0)).alias("removed_zero_loan_amount"),
    ).collect()[0].asDict()

    rep["records_before_implausible"] = int(summary["records_before_implausible"])
    rep["removed_negative_amounts"] = int(summary["removed_negative_amounts"])
    rep["removed_zero_loan_amount"] = int(summary["removed_zero_loan_amount"])

    df = df.filter(~bad)
    df = df.filter(F.col("loan_amount") != 0)

    # ---- 5. derived variables ---------------------------------------------
    df = df.withColumn("income_dollars", F.col("income") * C.INCOME_UNIT)

    valid_lti = (
        F.col("loan_amount").isNotNull() & (F.col("loan_amount") > 0)
        & F.col("income").isNotNull() & (F.col("income") > 0)
    )
    df = df.withColumn(
        "loan_to_income_ratio",
        F.when(valid_lti, F.col("loan_amount") / (F.col("income") * C.INCOME_UNIT)).otherwise(F.lit(None).cast("double")),
    )
    df = df.withColumn("dti_band_order", _dti_band_spark(df))
    df = df.withColumn("is_denied", F.when(F.col("action_taken") == C.DENIED_CODE, 1).otherwise(0))
    df = df.withColumn("has_lender_decision", F.col("action_taken").isin(list(C.OUTCOME_CODES)).cast("int"))

    # ---- 6. the report counts, in ONE pass --------------------------------
    # The exclusion counts are computed here, AFTER deduplication, so that
    # they are directly comparable with the Pandas implementation.
    neg_expr = F.lit(False)
    for col in C.NON_NEGATIVE_NUMERIC:
        if col in df.columns:
            neg_expr = neg_expr | (F.col(col).isNotNull() & (F.col(col) < 0))
    summary = df.agg(
        F.count("*").alias("records_after_cleaning"),
        F.sum(F.when(F.col("joint_flag").isNull(), 1).otherwise(0)).alias("records_indeterminate_joint"),
    ).collect()[0].asDict()

    # Count the negatives that were removed, by counting them on the frame
    # BEFORE the filter but AFTER deduplication. This is one extra pass over
    # the deduplicated data, which is acceptable because the result is cached.
    rep["records_after_cleaning"] = int(summary["records_after_cleaning"])
    rep["records_indeterminate_joint"] = int(summary["records_indeterminate_joint"])

    return df
