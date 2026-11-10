# Public HMDA — LAR Data Fields with Values and Definitions (2024)

Source: FFIEC/CFPB — *Public HMDA Data Fields with Values and Definitions*, "2024 File Specifications"
(https://ffiec.cfpb.gov/data-publication/one-year-national-loan-level-dataset/2024)

Companion file: `docs/public_lar_schema_2024.md` (field order and declared types).

> Field names in this document are transcribed from the official publication. Where the official
> documentation renders a field name with a hyphen (e.g. `co-applicant_ethnicity-1`), the actual
> column in the data file uses an underscore (`co_applicant_ethnicity_1`). The underscore form is
> what appears in the data and is used throughout the project.

---

## 1. Core identification and geography

### `activity_year`
The calendar year the data submission covers.
Values: `2017` `2018` `2019` `2020` `2021` `2022` `2023` `2024` `2025`

### `lei`
A financial institution's Legal Entity Identifier. Values: varying.
> This is the institution identifier used for the "financial institution" comparison dimension.

### `derived_msa_md`
The 5 digit derived MSA (metropolitan statistical area) or MD (metropolitan division) code.

### `state_code`
Two-letter state code.

### `county_code`
State-county FIPS code.

### `census_tract`
11 digit census tract number.

### `conforming_loan_limit`
Indicates whether the reported loan amount exceeds the GSE (government sponsored enterprise)
conforming loan limit.
Values: `C` (Conforming) · `NC` (Nonconforming) · `U` (Undetermined) · `NA` (Not Applicable)

---

## 2. Derived categorisation fields

### `derived_loan_product_type`
Derived loan product type from Loan Type and Lien Status fields.
Values: `Conventional:First Lien` · `FHA:First Lien` · `VA:First Lien` · `FSA/RHS:First Lien` ·
`Conventional:Subordinate Lien` · `FHA:Subordinate Lien` · `VA:Subordinate Lien` ·
`FSA/RHS:Subordinate Lien`

### `derived_dwelling_category`
Derived dwelling type from Construction Method and Total Units fields.
Values: `Single Family (1-4 Units):Site-Built` · `Multifamily:Site-Built (5+ Units)` ·
`Single Family (1-4 Units):Manufactured` · `Multifamily:Manufactured (5+ Units)`

### `derived_ethnicity`
Single aggregated ethnicity derived from applicant and co-applicant ethnicity fields.
Values: `Hispanic or Latino` · `Not Hispanic or Latino` · `Joint` · `Ethnicity Not Available` ·
`Free Form Text Only`

### `derived_race`
Single aggregated race derived from applicant and co-applicant race fields.
Values: `American Indian or Alaska Native` · `Asian` · `Black or African American` ·
`Native Hawaiian or Other Pacific Islander` · `White` · `2 or more minority races` · `Joint` ·
`Free Form Text Only` · `Race Not Available`

### `derived_sex`
Single aggregated sex derived from applicant and co-applicant sex fields.
Values: `Male` · `Female` · `Joint` · `Sex Not Available`

> **Important:** the `derived_*` fields already encode co-applicant presence through the value
> `Joint`. They are convenient for description, but the project defines its own `joint_flag`
> from the raw co-applicant fields so the rule is explicit and reproducible in both Pandas and
> Spark. See Section 12.

---

## 3. `action_taken` — the outcome variable

The action taken on the covered loan or application.

| Code | Meaning | In denial-rate denominator? |
|---|---|---|
| `1` | Loan originated (**O**) | ✅ yes |
| `2` | Application approved but not accepted (**A**) | ✅ yes |
| `3` | Application denied (**D**) | ✅ yes |
| `4` | Application withdrawn by applicant | ❌ excluded (reported separately) |
| `5` | File closed for incompleteness | ❌ excluded (reported separately) |
| `6` | Purchased loan | ❌ excluded (reported separately) |
| `7` | Preapproval request denied | ❌ excluded (not a mortgage application decision) |
| `8` | Preapproval request approved but not accepted | ❌ excluded (not a mortgage application decision) |

**Denial rate** = `D / (O + A + D)` = `count(action_taken = 3) / count(action_taken ∈ {1,2,3})`

> **Scope decision to document in the report.** The project treats `action_taken ∈ {7, 8}` as
> preapproval records rather than application decisions, so they are excluded from the
> denominator and reported separately alongside `4`, `5`, `6`. This must be stated explicitly
> in the data-cleaning section, because an alternative treatment (folding `7` into denials)
> would produce a materially different denial rate.

---

## 4. Purchaser, preapproval, loan characteristics

### `purchaser_type`
Type of entity purchasing a covered loan from the institution.
Values: `0` Not applicable · `1` Fannie Mae · `2` Ginnie Mae · `3` Freddie Mac ·
`4` Farmer Mac · `5` Private securitizer ·
`6` Commercial bank, savings bank, or savings association ·
`71` Credit union, mortgage company, or finance company ·
`72` Life insurance company · `8` Affiliate institution · `9` Other type of purchaser

### `preapproval`
Whether the covered loan or application involved a request for a preapproval of a home purchase
loan under a preapproval program.
Values: `1` Preapproval requested · `2` Preapproval not requested

### `loan_type`
The type of covered loan or application.
Values: `1` Conventional (not insured or guaranteed by FHA, VA, RHS, or FSA) ·
`2` Federal Housing Administration insured (FHA) ·
`3` Veterans Affairs guaranteed (VA) ·
`4` USDA Rural Housing Service or Farm Service Agency guaranteed (RHS or FSA)

### `loan_purpose`
The purpose of covered loan or application.
Values: `1` Home purchase · `2` Home improvement · `31` Refinancing ·
`32` Cash-out refinancing · `4` Other purpose · `5` Not applicable

### `lien_status`
Lien status of the property securing the covered loan or application.
Values: `1` Secured by a first lien · `2` Secured by a subordinate lien

### `reverse_mortgage`
Values: `1` Reverse mortgage · `2` Not a reverse mortgage · `1111` Exempt

### `open_end_line_of_credit`
Values: `1` Open-end line of credit · `2` Not an open-end line of credit · `1111` Exempt

### `business_or_commercial_purpose`
Values: `1` Primarily for a business or commercial purpose ·
`2` Not primarily for a business or commercial purpose · `1111` Exempt

### `loan_amount`
The amount of the covered loan, or the amount applied for. Values: varying (integer).

---

## 5. Financial indicators

### `combined_loan_to_value_ratio` (CLTV)
The ratio of the total amount of debt secured by the property to the value of the property
relied on in making the credit decision. Values: varying.

> **Note.** There is **no** `loan_to_value_ratio` field in the 2024 public LAR — only the
> *combined* CLTV. Any "LTV" in the report must be identified as CLTV.

### `interest_rate`
The interest rate for the covered loan or application. Values: varying.

### `rate_spread`
The difference between the covered loan's APR and the average prime offer rate (APOR) for a
comparable transaction as of the date the interest rate is set. Values: varying.

### `hoepa_status`
Whether the covered loan is a high-cost mortgage.
Values: `1` High-cost mortgage · `2` Not a high-cost mortgage · `3` Not applicable

### `total_loan_costs`
The amount, in dollars, of total loan costs. Values: varying.

### `total_points_and_fees`
The total points and fees, in dollars, charged in connection with the covered loan.

### `origination_charges`
The total of all itemized amounts, in dollars, designated borrower-paid at or before closing.

### `discount_points`
The points paid, in dollars, to the creditor to reduce the interest rate.

### `lender_credits`
The amount, in dollars, of lender credits.

### `loan_term`
The number of months after which the legal obligation will mature or terminate. Values: varying.

### `prepayment_penalty_term`
The term, in months, of any prepayment penalty. Values: varying.

### `intro_rate_period`
The number of months until the first date the interest rate may change after closing. Varying.

---

## 6. Contract terms and property

### `negative_amortization` · `interest_only_payment` · `balloon_payment` · `other_nonamortizing_features`
Values: `1` (Yes) · `2` (No) · `1111` Exempt

### `property_value`
The value of the property securing the covered loan. Values: varying; rounded to the midpoint of
the nearest $10,000 interval.

### `construction_method`
Values: `1` Site-built · `2` Manufactured home

### `occupancy_type`
Values: `1` Principal residence · `2` Second residence · `3` Investment property

### `manufactured_home_secured_property_type`
Values: `1` Manufactured home and land · `2` Manufactured home and not land ·
`3` Not applicable · `1111` Exempt

### `manufactured_home_land_property_interest`
Values: `1` Direct ownership · `2` Indirect ownership · `3` Paid leasehold ·
`4` Unpaid leasehold · `5` Not applicable · `1111` Exempt

### `total_units`
Values: `1` `2` `3` `4` `5-24` `25-49` `50-99` `100-149` `>149`

---

## 7. Income and debt-to-income

### `income`
The gross annual income, **in thousands of dollars**, relied on in making the credit decision, or
if a credit decision was not made, the gross annual income relied on in processing the
application. Values: varying.

> **Critical for the analysis.** `income` is expressed in thousands of dollars, so the value `179`
> means approximately $179,000 — not $179. Because the value is a rounded band rather than an
> exact amount, any derived ratio such as LTI = `loan_amount / income` carries band-width error
> and must be described as approximate.

### `debt_to_income_ratio`
The ratio, as a percentage, of the applicant's or borrower's total monthly debt to the total
monthly income relied on in making the credit decision.

Binned values: `<20%` · `20%-<30%` · `30%-<36%` · `36%` · `37%` · `38%` · `39%` · `40%` ·
`41%` · `42%` · `43%` · `44%` · `45%` · `46%` · `47%` · `48%` · `49%` · `50%-60%` · `>60%` ·
`NA` · `Exempt`

> **Critical for the analysis.** DTI is reported as an **ordered band string**, not a number.
> It is used as a categorical ordinal variable throughout. `NA` and `Exempt` are **missing /
> not applicable**, not zero and not a band.

---

## 8. Credit score

### `applicant_credit_score_type`
The name and version of the credit scoring model used to generate the credit score relied on in
making the credit decision.
Values: `1` Equifax Beacon 5.0 · `2` Experian Fair Isaac · `3` FICO Risk Score Classic 04 ·
`4` FICO Risk Score Classic 98 · `5` VantageScore 2.0 · `6` VantageScore 3.0 ·
`7` More than one credit scoring model · `8` Other credit scoring model ·
`9` Not applicable · `1111` Exempt

### `co_applicant_credit_score_type`
Values: `1`–`9` (same meanings as above) · **`10` No co-applicant** ·
`11` FICO Score 9 · `12` FICO Score 8 · `13` FICO Score 10 · `14` FICO Score 10T ·
`15` VantageScore 4.0 · `1111` Exempt

---

## 9. Applicant characteristics

### `applicant_ethnicity_1` … `applicant_ethnicity_5`
Values: `1` Hispanic or Latino · `11` Mexican · `12` Puerto Rican · `13` Cuban ·
`14` Other Hispanic or Latino · `2` Not Hispanic or Latino ·
`3` Information not provided by applicant in mail, internet, or telephone application ·
`4` Not applicable

### `applicant_race_1` … `applicant_race_5`
Values: `1` American Indian or Alaska Native · `2` Asian · `21` Asian Indian · `22` Chinese ·
`23` Filipino · `24` Japanese · `25` Korean · `26` Vietnamese · `27` Other Asian ·
`3` Black or African American · `4` Native Hawaiian or Other Pacific Islander ·
`41` Native Hawaiian · `42` Guamanian or Chamorro · `43` Samoan ·
`44` Other Pacific Islander · `5` White ·
`6` Information not provided by applicant · `7` Not applicable

### `applicant_sex`
Values: `1` Male · `2` Female ·
`3` Information not provided by applicant in mail, internet, or telephone application ·
`4` Not applicable · `6` Applicant selected both male and female

### `applicant_age`
The age of the applicant. Binned values: `<25` · `25-34` · `35-44` · `45-54` · `55-64` ·
`65-74` · `>74` · `8888`

### `applicant_age_above_62`
Values: `Yes` · `No` · `NA`

### `applicant_ethnicity_observed` · `applicant_race_observed` · `applicant_sex_observed`
Values: `1` Collected on the basis of visual observation or surname ·
`2` Not collected on the basis of visual observation or surname · `3` Not applicable

---

## 10. Co-applicant characteristics — the basis for `joint_flag`

### `co_applicant_ethnicity_1` … `co_applicant_ethnicity_5`
Values: `1` Hispanic or Latino · `11` Mexican · `12` Puerto Rican · `13` Cuban ·
`14` Other Hispanic or Latino · `2` Not Hispanic or Latino ·
`3` Information not provided by applicant · `4` Not applicable · **`5` No co-applicant**

### `co_applicant_race_1` … `co_applicant_race_5`
Values: `1`–`5` and `21`–`27` (same meanings as applicant race) ·
`6` Information not provided by applicant · `7` Not applicable · **`8` No co-applicant**

### `co_applicant_sex`
Values: `1` Male · `2` Female ·
`3` Information not provided by applicant · `4` Not applicable ·
**`5` No co-applicant** · `6` Co-applicant selected both male and female

### `co_applicant_age`
The age, in years, of the first co-applicant. Binned: `< 25` · `25-34` · `35-44` · `45-54` ·
`55-64` · `65-74` · `> 74` · `8888` · `9999`

### `co_applicant_age_above_62`
Values: `Yes` · `No` · `NA`

### `co_applicant_ethnicity_observed` · `co_applicant_race_observed` · `co_applicant_sex_observed`
Values: `1` Collected on the basis of visual observation or surname ·
`2` Not collected on the basis of visual observation or surname · `3` Not applicable ·
**`4` No co-applicant**

---

## 11. Submission, AUS and denial reasons

### `submission_of_application`
Values: `1` Submitted directly to your institution · `2` Not submitted directly to your
institution · `3` Not applicable · `1111` Exempt

### `initially_payable_to_institution`
Values: `1` Initially payable to your institution · `2` Not initially payable to your institution ·
`3` Not applicable · `1111` Exempt

### `aus_1` … `aus_5`
The automated underwriting system(s) used to evaluate the application.
Values: `1` Desktop Underwriter (DU) · `2` Loan Prospector (LP) or Loan Product Advisor ·
`3` Technology Open to Approved Lenders (TOTAL) Scorecard ·
`4` Guaranteed Underwriting System (GUS) · `5` Other · `6` Not applicable ·
`7` Internal Proprietary System · `1111` Exempt

### `denial_reason_1` … `denial_reason_4`
Values: `1` Debt-to-income ratio · `2` Employment history · `3` Credit history · `4` Collateral ·
`5` Insufficient cash (downpayment, closing costs) · `6` Unverifiable information ·
`7` Credit application incomplete · `8` Mortgage insurance denied · `9` Other ·
`10` Not applicable

> These fields are populated only when `action_taken = 3`. They are **excluded from the
> predictive extension** because they reveal the outcome and would cause data leakage.

---

## 12. Census fields appended by the U.S. Census Bureau

`tract_population` · `tract_minority_population_percent` (rounded to two decimals) ·
`ffiec_msa_md_median_family_income` (dollars, adjusted annually by FFIEC) ·
`tract_to_msa_income_percentage` · `tract_owner_occupied_units` ·
`tract_one_to_four_family_homes` · `tract_median_age_of_housing_units`

---

## 13. Special / missing value codes

These are **not numeric zero** and must be treated as missing or not-applicable:

| Code | Meaning | Appears in |
|---|---|---|
| `1111` | Exempt | `reverse_mortgage`, `open_end_line_of_credit`, `business_or_commercial_purpose`, `negative_amortization`, `interest_only_payment`, `balloon_payment`, `other_nonamortizing_features`, `manufactured_home_secured_property_type`, `manufactured_home_land_property_interest`, `applicant_credit_score_type`, `co_applicant_credit_score_type`, `submission_of_application`, `initially_payable_to_institution`, `aus_*` |
| `NA` | Not applicable / not available | `conforming_loan_limit`, `debt_to_income_ratio`, `applicant_age_above_62`, `co_applicant_age_above_62`, and many numeric fields |
| `Exempt` | Exempt | `debt_to_income_ratio` |
| `9999` | No co-applicant (age sentinel) | `co_applicant_age` |
| `8888` | Age not available | `applicant_age`, `co_applicant_age` |

> **Cleaning rule.** Every one of these codes is converted to a true missing value (`null`) and
> never to `0`, in both the Pandas and the Spark implementation. The rule set is identical in
> both engines and is applied before any aggregation.

---

## 14. `joint_flag` — project definition

The main research question compares **joint** applications (with a co-applicant) against
**single** applications (without one).

**Definition used in this project**

> `joint_flag = 1` if the record indicates the presence of a co-applicant; `joint_flag = 0` if the
> record explicitly indicates that there is no co-applicant.

### 14.1 Which values mean what

Each co-applicant field carries its **own** no-co-applicant code, and — critically — its own
"not applicable" code. Both must be distinguished from a genuine co-applicant value.

| Field | Absent (no co-applicant) | Not applicable / not reported | Present (co-applicant exists) |
|---|---|---|---|
| `co_applicant_ethnicity_1` | `5` | `4` | `1` `2` `3` `11`–`14` |
| `co_applicant_race_1` | `8` | `7` | `1`–`6` `21`–`27` `41`–`44` |
| `co_applicant_sex` | `5` | `4` | `1` `2` `3` `6` |
| `co_applicant_credit_score_type` | `10` | `9` `1111` | `1`–`8` `11`–`15` |

> **The key subtlety.** Code `3` ("Information not provided by applicant") and code `6`
> ("Information not provided") still **imply that a co-applicant exists** — the form was filed
> with a co-applicant who did not provide that particular attribute. Treating `3`/`6` as missing
> (rather than as evidence of a co-applicant) misclassifies a large group of records as
> indeterminate.

### 14.2 Implementation rule (identical in Pandas and Spark)

1. Classify each of the four co-applicant fields independently into one of three states:
   `present` (True), `absent` (False), or `not applicable / missing` (null).
2. `joint_flag = 1` when at least one field is `present` and **no** field is `absent`.
3. `joint_flag = 0` when at least one field is `absent` and **no** field is `present`.
4. If fields conflict (some present, some absent) or all four are not-applicable, the record is
   **indeterminate** and is excluded from the joint/single comparison, with the excluded count
   reported explicitly.

### 14.3 Empirical validation

The rule was validated on the first 900,000 rows of the national file and cross-checked against
the independent FFIEC field `co_applicant_ethnicity_observed` (code `4` = "No co-applicant"):

| Rule result | Rows (of 900,000) | Share |
|---|---:|---:|
| `joint_flag = 1` (joint) | 328,858 | 36.54 % |
| `joint_flag = 0` (single) | 569,979 | 63.33 % |
| Indeterminate (excluded) | 1,163 | 0.13 % |

Cross-tabulation against `co_applicant_ethnicity_observed`:

| | `observed = 4` (no co-applicant) | `observed ≠ 4` |
|---|---:|---:|
| rule = joint | **0** | 328,858 |
| rule = single | 530,657 | 39,322 |
| indeterminate | 27 | 1,136 |

The rule never labels a record "joint" when FFIEC explicitly says there is no co-applicant
(0 false positives on that axis). The 39,322 "single but not observed-no-co-applicant" rows are
records where the ethnicity/race/sex of the applicant were *not* collected by observation — these
are consistent with a single applicant, and the rule's "single" label remains valid.

The independent FFIEC derived fields `derived_sex`/`derived_ethnicity`/`derived_race` also carry a
`Joint` value, but they are **not** used to define the flag: they aggregate applicant *and*
co-applicant attributes into one label, so they cannot separate "no co-applicant" from
"co-applicant present but attribute not reported". They are used only as a descriptive cross-check
and their partial agreement (65–92 %) is reported as a data-quality observation.

> **Reporting requirement.** The count of records excluded as indeterminate must be stated in the
> report. A co-applicant is not the same as a spouse, and the presence of a co-applicant does
> not imply the incomes were combined — this limitation is stated in the proposal and must be
> repeated in the interpretation section.

---

## 15. Field profiles observed in the actual 2024 file

Measured on the first 900,000 rows of
`data/pipe_file/2024_public_lar_one_year_pipe.txt` (national file, pipe-delimited).

### `action_taken` distribution

| Code | Meaning | Rows | Share |
|---|---|---:|---:|
| `1` | Loan originated | 525,149 | 58.35 % |
| `2` | Approved but not accepted | 23,889 | 2.65 % |
| `3` | Denied | 158,443 | 17.60 % |
| `4` | Withdrawn by applicant | 71,285 | 7.92 % |
| `5` | File closed for incompleteness | 11,501 | 1.28 % |
| `6` | Purchased loan | 39,884 | 4.43 % |
| `7` | Preapproval request denied | 7,121 | 0.79 % |
| `8` | Preapproval approved but not accepted | 62,728 | 6.97 % |

> **Scale note.** `action_taken = 6` (purchased loan) is a large category — these are loans the
> institution originated and later sold. Because the denial-rate denominator is
> `O + A + D`, purchased loans are excluded, which matches the proposal. Records with
> `action_taken = 6` must still be reported separately so the reader can see the full
> disposition of applications.

### `state_code`

Top states in the first 900,000 rows: `FL` 92,060 · `CA` 74,404 · `TX` 62,865 ·
`MI` 43,692. Additionally **61,623 rows have a missing `state_code`** — this is a genuine data
quality finding to report, not a parse error (the field is blank for a subset of records).

### `loan_amount`

Numeric for every row in the sample (no text values). Min 5,000 · median 205,000 ·
max **164,065,000**. The maximum is a real reported value, not an error — the assignment
explicitly warns that loan amount and income have no upper limit. Extreme values must be
retained and discussed, not silently dropped.

### `income`

Stored in thousands of dollars. Median 103 (i.e. ~$103,000). Min is **−31,553**, which is
**negative and therefore impossible** — a clear invalid-value case to document and handle.
Max 357,000 (i.e. $357M) is extreme but not impossible.

### `interest_rate`

Numeric for 642,696 of 900,000 rows; the remaining **10,905 rows contain the literal string
`Exempt`** (plus blanks). `Exempt` must become missing, never `0`.

### `debt_to_income_ratio`

Reported as an ordered band string. In the sample: `30%-<36%` 114,520 · `20%-<30%` 110,012 ·
`50%-60%` 61,155 · `<20%` 39,819 · `49` 39,541 · `>60%` 37,426 · `44` 34,953 · `42` 30,874 ·
`43` 29,087 · `40` 28,168 · `41` 27,261, plus **147,382 blank/NA** and `Exempt`. Values are used
as an ordinal categorical variable throughout; no numeric coercion is applied.

---

## 16. Units of the "Varying values" fields

The official documentation lists several fields only as "Varying values". Their units and formats
were confirmed empirically against the actual file (first 400,000 rows of the national pipe file).

| Field | Unit / format | Observed min | Observed median | Observed max | Missing (blank) |
|---|---|---:|---:|---:|---:|
| `loan_amount` | US dollars, integer | 5,000 | 215,000 | 12,565,000 | 0 |
| `income` | **thousands of US dollars** | −18,010 | 100 | 21,675 | 10,518 |
| `interest_rate` | percent, numeric (may be `Exempt`) | 0.000 | 6.625 | 14.375 | 49,263 |
| `rate_spread` | percentage points vs APOR (can be negative) | −2.460 | 0.447 | 8.881 | 51,896 |
| `combined_loan_to_value_ratio` | percent (CLTV) | 2.00 | 75.00 | 1,360.19 | 9,331 |
| `property_value` | US dollars, rounded to $10,000 midpoint | 15,000 | 375,000 | 15,705,000 | 229 |
| `total_loan_costs` | US dollars, fractional | 0.00 | 6,427.09 | 99,456.26 | 57,788 |
| `loan_term` | months | 36 | 360 | 360 | 26 |
| `total_units` | count, or band string above 4 units | 1 | 1 | 4 | 0 |
| `applicant_age` | band string, or `8888` (not available) | — | `45-54` | — | 0 |

**Notes that affect the analysis**

- `income` is in thousands, so the median value `100` means **$100,000**. Multiplying by 1,000
  gives dollars; the LTI denominator must be scaled accordingly.
- `interest_rate` of exactly `0.000` is not a parse artefact — zero-rate loans exist in the file
  and must be kept, with a note that they are unusual.
- `rate_spread` is legitimately negative (a rate below APOR). Negative values are **not** errors.
- `combined_loan_to_value_ratio` above 100 means the debt exceeds the property value; the observed
  maximum of 1,360 % is extreme but is a reported value, not a data error.
- `property_value` is always a multiple of 5,000 because of the $10,000 midpoint rounding.
- `loan_term` is dominated by 360 months (73 %) and 240 months (19 %) — the standard US terms.
- `total_units` is banded (`5-24`, `25-49`, `50-99`, `100-149`, `>149`) above four units, so it
  must be treated as a categorical ordinal variable, not a count.

---

## 17. Known limitations of the public file

- The public file is **privacy-protected**, not the raw institution register. Ages are bucketed,
  DTI is a range string, property value is rounded to the nearest $10,000 midpoint, and small
  cells are masked.
- Credit history, FICO score values, and employment history are **not available** in the public
  file; only the *name and version* of the credit scoring model is reported.
- `loan_amount` and `income` have **no upper limit** and legitimately contain very large values.
  These are genuine observations, not errors, and must not be removed merely for being extreme.
- One reporting year cannot show trends.

---

## 18. Dataset provenance and record counts (national file)

| Property | Value |
|---|---|
| Dataset | HMDA 2024 One Year National Loan-Level Dataset (LAR) |
| Publisher | CFPB / FFIEC |
| File | `2024_public_lar_one_year_pipe.zip` → `2024_public_lar_one_year_pipe.txt` |
| Format | Pipe-delimited text, UTF-8, single header row, 99 columns |
| Compressed size | 635.57 MB |
| Uncompressed size | 4,636,628,799 bytes (4.32 GiB) |
| Data records | **12,259,199** (12,259,200 lines including the header) |
| Last updated | 2 June 2026 |

> The "One Year" release incorporates all LAR and TS adjustments made in the 12 months after the
> 1 March 2025 reporting deadline, so it is a **stable** snapshot — unlike the "Dynamic" release,
> which is updated weekly. For a reproducible assignment this is the correct file to use and to
> document.

