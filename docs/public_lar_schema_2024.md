# Public LAR Schema — HMDA 2024

Source: FFIEC/CFPB — *Public LAR Schema*, "2024 File Specifications"
(https://ffiec.cfpb.gov/data-publication/one-year-national-loan-level-dataset/2024)

Verified against the actual file `data/pipe_file/2024_public_lar_one_year_pipe.txt`:
the header row contains **exactly 99 fields** with names and order matching this schema.

| # | Field | Max Length | Type |
|---:|---|---:|---|
| 1 | `activity_year` | 4 | Numeric |
| 2 | `lei` | 20 | Alphanumeric |
| 3 | `derived_msa_md` | 5 | Alphanumeric |
| 4 | `state_code` | 2 | Alphanumeric |
| 5 | `county_code` | 5 | Alphanumeric |
| 6 | `census_tract` | 11 | Alphanumeric |
| 7 | `conforming_loan_limit` | 2 | Alphanumeric |
| 8 | `derived_loan_product_type` | 29 | Alphanumeric |
| 9 | `derived_dwelling_category` | 38 | Alphanumeric |
| 10 | `derived_ethnicity` | 23 | Alphanumeric |
| 11 | `derived_race` | 41 | Alphanumeric |
| 12 | `derived_sex` | 17 | Alphanumeric |
| 13 | `action_taken` | 1 | Numeric |
| 14 | `purchaser_type` | 1 | Numeric |
| 15 | `preapproval` | 1 | Numeric |
| 16 | `loan_type` | 1 | Numeric |
| 17 | `loan_purpose` | 2 | Numeric |
| 18 | `lien_status` | 1 | Numeric |
| 19 | `reverse_mortgage` | 4 | Numeric |
| 20 | `open_end_line_of_credit` | 4 | Numeric |
| 21 | `business_or_commercial_purpose` | 4 | Numeric |
| 22 | `loan_amount` | | Integer |
| 23 | `combined_loan_to_value_ratio` | | Alphanumeric |
| 24 | `interest_rate` | | Alphanumeric |
| 25 | `rate_spread` | | Alphanumeric |
| 26 | `hoepa_status` | 1 | Numeric |
| 27 | `total_loan_costs` | | Alphanumeric |
| 28 | `total_points_and_fees` | | Alphanumeric |
| 29 | `origination_charges` | | Alphanumeric |
| 30 | `discount_points` | | Alphanumeric |
| 31 | `lender_credits` | | Alphanumeric |
| 32 | `loan_term` | | Alphanumeric |
| 33 | `prepayment_penalty_term` | | Alphanumeric |
| 34 | `intro_rate_period` | | Alphanumeric |
| 35 | `negative_amortization` | 4 | Numeric |
| 36 | `interest_only_payment` | 4 | Numeric |
| 37 | `balloon_payment` | 4 | Numeric |
| 38 | `other_nonamortizing_features` | 4 | Numeric |
| 39 | `property_value` | | Alphanumeric |
| 40 | `construction_method` | 1 | Numeric |
| 41 | `occupancy_type` | 1 | Numeric |
| 42 | `manufactured_home_secured_property_type` | 4 | Numeric |
| 43 | `manufactured_home_land_property_interest` | 4 | Numeric |
| 44 | `total_units` | 7 | Alphanumeric |
| 45 | `multifamily_affordable_units` | 6 | Alphanumeric |
| 46 | `income` | | Alphanumeric |
| 47 | `debt_to_income_ratio` | | Alphanumeric |
| 48 | `applicant_credit_score_type` | 4 | Numeric |
| 49 | `co_applicant_credit_score_type` | 4 | Numeric |
| 50 | `applicant_ethnicity_1` | 2 | Alphanumeric |
| 51 | `applicant_ethnicity_2` | 2 | Alphanumeric |
| 52 | `applicant_ethnicity_3` | 2 | Alphanumeric |
| 53 | `applicant_ethnicity_4` | 2 | Alphanumeric |
| 54 | `applicant_ethnicity_5` | 2 | Alphanumeric |
| 55 | `co_applicant_ethnicity_1` | 2 | Alphanumeric |
| 56 | `co_applicant_ethnicity_2` | 2 | Alphanumeric |
| 57 | `co_applicant_ethnicity_3` | 2 | Alphanumeric |
| 58 | `co_applicant_ethnicity_4` | 2 | Alphanumeric |
| 59 | `co_applicant_ethnicity_5` | 2 | Alphanumeric |
| 60 | `applicant_ethnicity_observed` | 1 | Alphanumeric |
| 61 | `co_applicant_ethnicity_observed` | 1 | Alphanumeric |
| 62 | `applicant_race_1` | 2 | Alphanumeric |
| 63 | `applicant_race_2` | 2 | Alphanumeric |
| 64 | `applicant_race_3` | 2 | Alphanumeric |
| 65 | `applicant_race_4` | 2 | Alphanumeric |
| 66 | `applicant_race_5` | 2 | Alphanumeric |
| 67 | `co_applicant_race_1` | 2 | Alphanumeric |
| 68 | `co_applicant_race_2` | 2 | Alphanumeric |
| 69 | `co_applicant_race_3` | 2 | Alphanumeric |
| 70 | `co_applicant_race_4` | 2 | Alphanumeric |
| 71 | `co_applicant_race_5` | 2 | Alphanumeric |
| 72 | `applicant_race_observed` | 1 | Numeric |
| 73 | `co_applicant_race_observed` | 1 | Numeric |
| 74 | `applicant_sex` | 1 | Numeric |
| 75 | `co_applicant_sex` | 1 | Numeric |
| 76 | `applicant_sex_observed` | 1 | Numeric |
| 77 | `co_applicant_sex_observed` | 1 | Numeric |
| 78 | `applicant_age` | | Alphanumeric |
| 79 | `co_applicant_age` | | Alphanumeric |
| 80 | `applicant_age_above_62` | | Alphanumeric |
| 81 | `co_applicant_age_above_62` | | Alphanumeric |
| 82 | `submission_of_application` | 4 | Alphanumeric |
| 83 | `initially_payable_to_institution` | 4 | Alphanumeric |
| 84 | `aus_1` | 4 | Numeric |
| 85 | `aus_2` | 1 | Alphanumeric |
| 86 | `aus_3` | 1 | Alphanumeric |
| 87 | `aus_4` | 1 | Alphanumeric |
| 88 | `aus_5` | 1 | Alphanumeric |
| 89 | `denial_reason_1` | 4 | Alphanumeric |
| 90 | `denial_reason_2` | 1 | Alphanumeric |
| 91 | `denial_reason_3` | 1 | Alphanumeric |
| 92 | `denial_reason_4` | 1 | Alphanumeric |
| 93 | `tract_population` | | Numeric |
| 94 | `tract_minority_population_percent` | | Numeric |
| 95 | `ffiec_msa_md_median_family_income` | | Numeric |
| 96 | `tract_to_msa_income_percentage` | | Numeric |
| 97 | `tract_owner_occupied_units` | | Numeric |
| 98 | `tract_one_to_four_family_homes` | | Numeric |
| 99 | `tract_median_age_of_housing_units` | | Numeric |

---

## Notes on the actual file

- The pipe-delimited file has a **single header row** (no multi-row header). Delimiter is `|`, encoding UTF-8, no trailing delimiter on the last field.
- Columns marked `Alphanumeric` with no max length are free-format numeric fields stored as text — they contain values such as `NA`, `Exempt`, `NotApplicable`, or banded values (e.g. `30%-<36%`). They must be parsed explicitly and must **not** be silently coerced to 0.
- `combined_loan_to_value_ratio` (field 23) is the CLTV field, not a raw numeric LTV.
- `debt_to_income_ratio` (field 47) is reported as ranges/bands, not a continuous number.
- `income` (field 46) is reported as bands in the public file (in thousands of dollars), not a raw amount.

## Still needed

The data dictionary — *Public HMDA Data Fields with Values and Definitions* — is required to
document the value codes for `action_taken`, `loan_type`, `loan_purpose`, `lien_status`,
`co_applicant_*` and the derived fields. Save it alongside this file when available.
