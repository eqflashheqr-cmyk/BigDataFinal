"""
config.py — Single source of truth for the HMDA 2024 project.

Every data dictionary, code table, cleaning rule and derived-variable definition
lives here so that the Pandas and PySpark implementations are guaranteed to use
*identical* definitions, as required by the assignment:

    "Cleaning rules must be documented and applied consistently in the Pandas and
     Spark implementations."

This module contains no engine-specific logic: it is plain Python data that both
`pandas_pipeline.py` and `spark_pipeline.py` import.

Sources
-------
Schema:  docs/public_lar_schema_2024.md   (FFIEC Public LAR Schema, 2024)
Codes:   docs/hmda_data_dictionary_2024.md (FFIEC Public HMDA Data Fields, 2024)
"""

from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = ROOT / "data" / "pipe_file"
CLEAN_DIR = ROOT / "data" / "clean"
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = ROOT / "figures"
DOCS_DIR = ROOT / "docs"

#: Source file. The official FFIEC "One Year" national LAR, pipe-delimited text.
RAW_FILE = RAW_DIR / "2024_public_lar_one_year_pipe.txt"
RAW_ZIP = RAW_DIR / "2024_public_lar_one_year_pipe.zip"

#: Prepared analytical dataset (Parquet), written by the Pandas cleaning step.
CLEAN_PARQUET = CLEAN_DIR / "hmda_2024_clean"

#: Prepared analytical dataset (Parquet), written by the Spark cleaning step.
#: Kept separate so the two implementations can be compared independently.
SPARK_PARQUET = CLEAN_DIR / "hmda_2024_clean_spark"

for _d in (CLEAN_DIR, RESULTS_DIR, FIGURES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

#: Delimiter of the raw pipe-delimited file.
DELIMITER = "|"

#: Column names, in file order (99 fields).
ALL_COLUMNS = [
    "activity_year", "lei", "derived_msa_md", "state_code", "county_code",
    "census_tract", "conforming_loan_limit", "derived_loan_product_type",
    "derived_dwelling_category", "derived_ethnicity", "derived_race",
    "derived_sex", "action_taken", "purchaser_type", "preapproval", "loan_type",
    "loan_purpose", "lien_status", "reverse_mortgage", "open_end_line_of_credit",
    "business_or_commercial_purpose", "loan_amount",
    "combined_loan_to_value_ratio", "interest_rate", "rate_spread", "hoepa_status",
    "total_loan_costs", "total_points_and_fees", "origination_charges",
    "discount_points", "lender_credits", "loan_term", "prepayment_penalty_term",
    "intro_rate_period", "negative_amortization", "interest_only_payment",
    "balloon_payment", "other_nonamortizing_features", "property_value",
    "construction_method", "occupancy_type",
    "manufactured_home_secured_property_type",
    "manufactured_home_land_property_interest", "total_units",
    "multifamily_affordable_units", "income", "debt_to_income_ratio",
    "applicant_credit_score_type", "co_applicant_credit_score_type",
    "applicant_ethnicity_1", "applicant_ethnicity_2", "applicant_ethnicity_3",
    "applicant_ethnicity_4", "applicant_ethnicity_5", "co_applicant_ethnicity_1",
    "co_applicant_ethnicity_2", "co_applicant_ethnicity_3",
    "co_applicant_ethnicity_4", "co_applicant_ethnicity_5",
    "applicant_ethnicity_observed", "co_applicant_ethnicity_observed",
    "applicant_race_1", "applicant_race_2", "applicant_race_3",
    "applicant_race_4", "applicant_race_5", "co_applicant_race_1",
    "co_applicant_race_2", "co_applicant_race_3", "co_applicant_race_4",
    "co_applicant_race_5", "applicant_race_observed", "co_applicant_race_observed",
    "applicant_sex", "co_applicant_sex", "applicant_sex_observed",
    "co_applicant_sex_observed", "applicant_age", "co_applicant_age",
    "applicant_age_above_62", "co_applicant_age_above_62",
    "submission_of_application", "initially_payable_to_institution",
    "aus_1", "aus_2", "aus_3", "aus_4", "aus_5", "denial_reason_1",
    "denial_reason_2", "denial_reason_3", "denial_reason_4", "tract_population",
    "tract_minority_population_percent", "ffiec_msa_md_median_family_income",
    "tract_to_msa_income_percentage", "tract_owner_occupied_units",
    "tract_one_to_four_family_homes", "tract_median_age_of_housing_units",
]

# --------------------------------------------------------------------------
# Code tables (FFIEC Public HMDA Data Fields, 2024)
#
# The code tables are keyed by INTEGER. The raw file stores the codes as
# text, but the analytical code compares them as numbers after the numeric
# parsing step. Keeping the keys numeric everywhere removes any chance of a
# silent string/number mismatch (a real bug caught during development:
# `Int64.isin(("1","2","3"))` is always False, while Spark's `isin` coerces
# the literals and silently succeeds).
# --------------------------------------------------------------------------

ACTION_TAKEN = {
    1: "Loan originated",
    2: "Application approved but not accepted",
    3: "Application denied",
    4: "Application withdrawn by applicant",
    5: "File closed for incompleteness",
    6: "Purchased loan",
    7: "Preapproval request denied",
    8: "Preapproval request approved but not accepted",
}

LOAN_TYPE = {
    1: "Conventional",
    2: "FHA",
    3: "VA",
    4: "RHS/FSA",
}

LOAN_PURPOSE = {
    1: "Home purchase",
    2: "Home improvement",
    31: "Refinancing",
    32: "Cash-out refinancing",
    4: "Other purpose",
    5: "Not applicable",
}

LIEN_STATUS = {
    1: "First lien",
    2: "Subordinate lien",
}

# --------------------------------------------------------------------------
# Outcome definition
# --------------------------------------------------------------------------

#: Outcome codes that constitute a lender decision.
#:   O = originated, A = approved but not accepted, D = denied.
#: Every other `action_taken` value is excluded from the denial-rate denominator
#: and reported separately (withdrawn, incomplete, purchased, preapproval).
OUTCOME_CODES = (1, 2, 3)

DENIED_CODE = 3
ORIGINATED_CODE = 1
APPROVED_NOT_ACCEPTED_CODE = 2

#: Outcome codes excluded from the denial-rate denominator.
NON_DECISION_CODES = (4, 5, 6, 7, 8)

#: `action_taken` value meaning "a lender decision was made".
HAS_DECISION_CODES = OUTCOME_CODES

# --------------------------------------------------------------------------
# Special / missing value codes
# --------------------------------------------------------------------------

#: Codes that mean "not applicable / not reported / exempt". They are converted
#: to a true missing value and NEVER to 0.
#:   1111 -> Exempt (HMDA sentinel)
#:   NA   -> Not applicable / not available
#:   Exempt
#:   8888 -> age not available
#:   9999 -> age: no co-applicant
SPECIAL_CODES = ("1111", "NA", "N/A", "Exempt", "8888", "9999", "")

#: Sentinel meaning "no co-applicant", per field.
NO_CO_APPLICANT_CODE = {
    "co_applicant_ethnicity_1": "5",
    "co_applicant_race_1": "8",
    "co_applicant_sex": "5",
    "co_applicant_credit_score_type": "10",
}

#: Codes meaning "not applicable" for the co-applicant fields. These are
#: distinct from the no-co-applicant sentinel and must not be conflated.
CO_APPLICANT_NA_CODES = {
    "co_applicant_ethnicity_1": ("4",),
    "co_applicant_race_1": ("7",),
    "co_applicant_sex": ("4",),
    "co_applicant_credit_score_type": ("9", "1111"),
}

#: Fields used to decide whether a co-applicant exists.
JOINT_FIELDS = tuple(NO_CO_APPLICANT_CODE.keys())

# --------------------------------------------------------------------------
# Numeric vs categorical columns
# --------------------------------------------------------------------------

#: Columns read as numeric. The raw file stores them as text; they are parsed
#: with the rule "non-numeric -> missing" (never 0).
NUMERIC_COLUMNS = [
    "activity_year", "action_taken", "purchaser_type", "preapproval", "loan_type",
    "loan_purpose", "lien_status", "reverse_mortgage", "open_end_line_of_credit",
    "business_or_commercial_purpose", "loan_amount",
    "combined_loan_to_value_ratio", "interest_rate", "rate_spread", "hoepa_status",
    "total_loan_costs", "total_points_and_fees", "origination_charges",
    "discount_points", "lender_credits", "loan_term", "prepayment_penalty_term",
    "intro_rate_period", "negative_amortization", "interest_only_payment",
    "balloon_payment", "other_nonamortizing_features", "property_value",
    "construction_method", "occupancy_type",
    "manufactured_home_secured_property_type",
    "manufactured_home_land_property_interest", "multifamily_affordable_units",
    "income", "applicant_credit_score_type", "co_applicant_credit_score_type",
    "applicant_ethnicity_1", "applicant_ethnicity_2", "applicant_ethnicity_3",
    "applicant_ethnicity_4", "applicant_ethnicity_5", "co_applicant_ethnicity_1",
    "co_applicant_ethnicity_2", "co_applicant_ethnicity_3",
    "co_applicant_ethnicity_4", "co_applicant_ethnicity_5",
    "applicant_ethnicity_observed", "co_applicant_ethnicity_observed",
    "applicant_race_1", "applicant_race_2", "applicant_race_3", "applicant_race_4",
    "applicant_race_5", "co_applicant_race_1", "co_applicant_race_2",
    "co_applicant_race_3", "co_applicant_race_4", "co_applicant_race_5",
    "applicant_race_observed", "co_applicant_race_observed", "applicant_sex",
    "co_applicant_sex", "applicant_sex_observed", "co_applicant_sex_observed",
    "aus_1", "aus_2", "aus_3", "aus_4", "aus_5", "denial_reason_1",
    "denial_reason_2", "denial_reason_3", "denial_reason_4", "tract_population",
    "tract_minority_population_percent", "ffiec_msa_md_median_family_income",
    "tract_to_msa_income_percentage", "tract_owner_occupied_units",
    "tract_one_to_four_family_homes", "tract_median_age_of_housing_units",
]

#: Columns that stay categorical (ordinal bands or codes).
CATEGORICAL_COLUMNS = [
    "lei", "derived_msa_md", "state_code", "county_code", "census_tract",
    "conforming_loan_limit", "derived_loan_product_type",
    "derived_dwelling_category", "derived_ethnicity", "derived_race",
    "derived_sex", "total_units", "debt_to_income_ratio", "applicant_age",
    "co_applicant_age", "applicant_age_above_62", "co_applicant_age_above_62",
    "submission_of_application", "initially_payable_to_institution",
]

#: Ordered band for `debt_to_income_ratio`. Used for the RQ3 stratification.
#: These are the *raw* strings as they appear in the file, in ascending order.
#: `None` marks a band that carries no information (missing / not applicable).
DTI_BANDS = [
    "<20%", "20%-<30%", "30%-<36%",
    "36", "37", "38", "39", "40", "41", "42", "43", "44", "45", "46", "47",
    "48", "49",
    "50%-60%", ">60%",
]

#: Ordered bands for `applicant_age`.
AGE_BANDS = ["<25", "25-34", "35-44", "45-54", "55-64", "65-74", ">74"]

# --------------------------------------------------------------------------
# Cleaning rules
# --------------------------------------------------------------------------

#: `income` is reported in thousands of US dollars.
INCOME_UNIT = 1000

#: Values that are impossible for a positive monetary amount. Rows violating
#: this are flagged and reported; the cleaning step excludes them from the
#: analysis set because a negative loan amount or income is not a real
#: observation.
NON_NEGATIVE_NUMERIC = ["loan_amount", "income", "property_value", "total_loan_costs"]

#: Denominator of the loan-to-income ratio.
LTI_NUMERATOR = "loan_amount"
LTI_DENOMINATOR = "income"

#: RQ4 asks about the five states with the most applications. The number of
#: states is derived from the data by default, but is pinned here so that both
#: engines agree on the same list.
TOP_N_STATES = 5

# --------------------------------------------------------------------------
# Duplicate handling
# --------------------------------------------------------------------------
# HMDA is meant to contain one record per application, so a record that is
# identical to another in ALL 99 fields is redundant and is removed.
#
# A weaker "business key" definition (identical institution + borrower +
# loan amount + location + outcome) is deliberately NOT used for removal:
# a borrower may legitimately file two applications with the same lender for
# the same amount and property (for example a refinance attempt followed by a
# purchase, or a re-submission after a correction). Removing those would
# discard real applications. Both definitions are measured and reported by
# `src/quality_checks.py`.

#: Duplicate removal is based on all of the raw columns.
DEDUPLICATE_ON_ALL_COLUMNS = True

# --------------------------------------------------------------------------
# Engine configuration
# --------------------------------------------------------------------------

#: Spark driver memory. The machine has 16 GB RAM; 8 GB leaves headroom for the
#: OS and for a simultaneous Pandas process.
SPARK_DRIVER_MEMORY = "8g"

#: Spark shuffle partitions. The Spark default of 200 is far too many for a
#: single-machine dataset of this size and dominates the runtime.
SPARK_SHUFFLE_PARTITIONS = 16

#: Rows per Pandas chunk when streaming the raw file.
PANDAS_CHUNK_SIZE = 500_000

#: Number of repeats for the performance experiment; the median is reported.
#: Five repeats of the full six-cell grid would take many hours, so three is
#: the compromise between statistical stability and total run time.
BENCHMARK_REPEATS = 3

#: Fractions of the dataset used for the performance/scalability experiment.
BENCHMARK_FRACTIONS = (0.25, 0.50, 1.00)

#: Numerical tolerance for comparing Pandas and Spark results.
TOLERANCE = 1e-6
