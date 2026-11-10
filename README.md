# Big Data Analysis — Final Project
## Joint vs. Single Mortgage Applications in HMDA 2024

**Course:** Big Data Analysis — Large-Scale Analysis of Mortgage Lending Data
**Dataset:** FFIEC/CFPB *Public One-Year National Loan-Level Dataset* (HMDA 2024)

> **Full execution record:** [`pipeline.md`](pipeline.md) documents every phase of
> this project — the decisions taken, the evidence behind them, and the
> mistakes that were found and fixed along the way.

---

## 1. Research questions

| | Question |
|---|---|
| **RQ1** | How does the denial rate differ between joint and single applications? |
| **RQ2** | How do income, loan amount, and the loan-to-income ratio differ between the groups? |
| **RQ3** | Does the denial-rate gap remain among applications with similar income, debt-to-income ratio, loan type and loan purpose? |
| **RQ4** | Does the gap vary by loan purpose and across the five states with the most applications? |

### Headline result

> **Joint applications are denied less often than single applications: 18.96 % vs 28.08 %,
> a gap of 9.12 percentage points (a 32.5 % relative reduction).**
> The gap survives stratification by income quartile, DTI band, loan type and loan
> purpose — joint applications have the lower denial rate in **84 % of the 1,011
> strata** with at least 100 lender decisions — and it is present in every one of
> the five states with the most applications.
>
> The gap is **widest** among higher-income applicants (6.8 pp in the top income
> quartile vs 1.8 pp in the bottom), which rules out the explanation that
> low-income applicants are being screened out.

---

## 2. Data acquisition

The raw dataset is **not** in this repository (the assignment forbids
duplicating large public datasets). Download it from the official source:

> **Source:** <https://ffiec.cfpb.gov/data-publication/> →
> *2024 → One-Year National Loan-Level Dataset → Pipe-delimited*

```bash
# Expected layout after downloading and extracting:
data/
├── pipe_file/
│   └── 2024_public_lar_one_year_pipe.txt   # 4.32 GiB, 99 cols, 12,259,199 records
└── clean/                                    # created by the pipelines
```

The zip archives must be extracted — the pipelines read the plain text file.

### Environment (Windows)

```bash
pip install -r requirements.txt
```

PySpark needs, as user environment variables:

```
JAVA_HOME   = E:\Tools\jdk17                  # Temurin OpenJDK 17
HADOOP_HOME = E:\Tools\hadoop\hadoop-3.3.6     # Hadoop winutils
```

and `hadoop.dll` + `winutils.exe` must be reachable from the JVM's
`java.library.path` (copying them into `%JAVA_HOME%\bin` works).

---

## 3. How to reproduce

```bash
pip install -r requirements.txt

python src/pandas_pipeline.py      # Pandas: clean + write Parquet
python src/spark_pipeline.py       # Spark:  clean + write Parquet
python src/equivalence.py all      # compare the two engines  -> 8/8 agree
python src/run_analysis.py all     # RQ1..RQ4 in both engines
python src/quality_checks.py       # duplicate investigation + correlations
python src/benchmark.py            # performance experiment   (~1.8 h)
python src/figures.py              # charts
python src/report.py               # regenerate results/report.md
```

Total wall-clock on a 16 GB machine: roughly **40 minutes** for everything
except the benchmark, which takes about 1.8 hours.

---

## 4. Repository layout

```
BigDataFinal/
├── pipeline.md                  # full execution record (read this first)
├── README.md                    # this file
├── requirements.txt
├── .gitignore
├── docs/
│   ├── public_lar_schema_2024.md     # 99-field schema from FFIEC
│   └── hmda_data_dictionary_2024.md   # full data dictionary + code tables
├── src/
│   ├── config.py             # single source of truth: paths, code tables, rules
│   ├── rules.py              # cleaning + feature engineering, once per engine
│   ├── pandas_pipeline.py    # Pandas ingest -> clean -> Parquet
│   ├── spark_pipeline.py     # Spark  ingest -> clean -> Parquet
│   ├── analytics.py          # canonical analytical outputs, once per engine
│   ├── analysis.py           # RQ1..RQ4, once per engine
│   ├── quality_checks.py     # duplicate investigation, correlation matrix
│   ├── equivalence.py        # Pandas vs Spark comparison
│   ├── benchmark.py          # performance & scalability experiment
│   ├── figures.py            # chart generation
│   ├── report.py             # assembles results/report.md
│   └── run_analysis.py       # orchestration
├── results/
│   ├── report.md             # the technical report
│   ├── rq1..rq4.csv          # the four research questions
│   ├── equivalence_report.json
│   ├── benchmark_results.csv / .json
│   ├── quality_checks.json
│   ├── correlation_matrix.csv
│   └── cleaning_report_{pandas,spark}.json
└── figures/
    └── fig1..fig6.png
```

---

## 5. Method

### 5.1 Data

| | |
|---|---|
| Publisher | CFPB / FFIEC |
| File | `2024_public_lar_one_year_pipe.txt` (4.32 GiB, pipe-delimited, 1 header row) |
| Raw records | 12,259,199 |
| Columns | 99 |
| After cleaning | 12,224,691 |
| With a lender decision (O+A+D) | 8,557,686 |
| Output format | Parquet (Snappy) — FFIEC does not publish Parquet; it is generated from the cleaned pipe-delimited file |

### 5.2 The `joint_flag` variable

`joint_flag` is **not** a field in HMDA. It is derived from the four
co-applicant fields:

`co_applicant_ethnicity_1`, `co_applicant_race_1`, `co_applicant_sex`,
`co_applicant_credit_score_type`

Each field is classified as:

* **present** — holds a genuine co-applicant value
  (ethnicity `1,2,3,11..14`; race `1..6,21..27,41..44`; sex `1,2,3,6`;
  credit score `1..8,11..15`).
  Note that *code 3 / 6 ("Information not provided by applicant") still implies
  a co-applicant exists*, so it counts as present, not as missing.
* **absent** — explicitly says there is no co-applicant
  (ethnicity `5`; race `8`; sex `5`; credit score `10`).
* **not applicable** — not reported
  (ethnicity `4`; race `7`; sex `4`; credit score `9`, `1111`).

Then:

```
joint_flag = 1   if  at least one present  AND  zero absent
joint_flag = 0   if  at least one absent   AND  zero present
joint_flag = NA  otherwise  (indeterminate)
```

The rule was validated against the independent `co_applicant_ethnicity_observed`
field with **zero false positives**.

### 5.3 Outcome and denial rate

```
denial_rate = D / (O + A + D)
```

with `O` = `action_taken` 1 (originated), `A` = 2 (approved but not accepted),
`D` = 3 (denied). Codes 4–8 (withdrawn, incomplete, purchased, preapproval)
are **not** lender decisions and are excluded from the denominator.

### 5.4 Cleaning rules

1. **Whitespace** is trimmed on every field.
2. **Duplicates** — 26,755 records identical in all 99 fields are removed.
   A weaker "business key" definition (same institution + borrower + amount +
   location + outcome) was measured too but deliberately **not** used for
   removal, because a borrower may legitimately file two applications with the
   same lender for the same amount and property.
3. **Special codes** (`Exempt`, `NA`, `1111`, `8888`, `9999`, blank) become a
   true missing value — never `0`.
4. **Numeric parsing** accepts the same numeric literal grammar in both
   engines; anything else becomes missing.
5. **Implausible values** — negative `loan_amount`, `income`, `property_value`
   or `total_loan_costs` — are removed and counted. 7,753 records removed.
   `loan_amount == 0` is removed as well (0 records).
6. **Derived variables** — `income_dollars` (income × 1000, because HMDA
   reports income in thousands of USD), `loan_to_income_ratio`,
   `dti_band_order`, `is_denied`, `has_lender_decision`.

Every rule lives in `src/rules.py`, written **twice side by side** (Pandas and
Spark), with all code tables in `src/config.py`. This is what makes "applied
consistently in both implementations" a structural property rather than a
promise — and it is how three real bugs were caught (§6).

### 5.5 Known limitations

* **Indeterminate `joint_flag`: 1,150,697 records (9.41 %).** 90.6 % of these
  are `action_taken = 6` (purchased loans) and 98.1 % have
  `applicant_sex = 4` ("Not applicable"), i.e. the originator never recorded a
  co-applicant. Restricted to records that actually reached a lender
  decision, the indeterminate rate is only **1.01 %**, and all four RQs are
  computed on that decision population.
* **The finding is associative, not causal.** It does not establish that
  adding a co-applicant causes an approval.
* **Extreme values are kept.** `income` has a maximum of 999,999,999 and
  `loan_amount` a maximum of 2,962,005,000. These are genuine HMDA outliers,
  not data errors, and removing them would bias the analysis. They are
  reported in the descriptive statistics instead.
* **`interest_rate` is missing for 4.51 M records (36.8 %)** — HMDA only
  requires the rate for originated loans. `rate_spread` is missing for 6.42 M.
  The RQ2 interest-rate comparison therefore rests on a biased subset.
* **Income is missing for 1.78 M records (14.5 %).**
* **Pandas cannot hold the raw frame.** 12.2 M × 99 string columns is ≈ 40 GB;
  the Pandas pipeline reads in 500,000-row chunks and writes Parquet
  incrementally.

---

## 6. Correctness and performance

### 6.1 Pandas vs PySpark — 8 of 8 comparisons agree

| # | Analytical quantity | Result |
|---:|---|---|
| 1 | Record counts after each cleaning step | ✅ agree |
| 2 | Missing-value counts for 13 important variables | ✅ agree |
| 3 | Counts and proportions of application outcomes | ✅ agree |
| 4 | Denial rate by `joint_flag` (RQ1) | ✅ agree |
| 5 | Descriptive statistics of loan amount, income, rate, LTI | ✅ agree |
| 6 | Average and median loan amount by loan type | ✅ agree |
| 7 | Aggregated results by financial institution (LEI, top 50) | ✅ agree |
| 8 | Denial rate in the top 5 states (RQ4) | ✅ agree |

All four RQs were additionally computed independently in both engines and
diffed cell by cell (RQ3 = 1,730 strata): **zero differing cells**.

The comparison found three genuine engine differences, all fixed at the
source rather than papered over:

1. Spark's `SUM` propagates NULL → a single empty co-applicant field made
   whole records indeterminate. Fixed with `coalesce`.
2. Pandas `Int64.isin(("1","2","3"))` is always `False` while Spark coerces
   the literals → `has_lender_decision` was 0 everywhere in Pandas. Fixed by
   making the code tables integer-keyed.
3. Pandas `qcut` and Spark `ntile` disagree at quartile boundaries → the
   boundaries are now computed once and pinned in
   `results/income_quartile_bounds.json`.

### 6.2 Performance — Spark is 3.3× faster at full scale

Median of 3 repeats; both engines process identical records (selected by a
SHA-256 hash rule that is byte-identical in both).

| Engine | Data | Rows | Total | Throughput |
|---|---|---:|---:|---:|
| pandas | 25 % | 3,374,950 | 224.6 s | 15,029 rows/s |
| pyspark | 25 % | 3,374,950 | **89.9 s** | 37,532 rows/s |
| pandas | 50 % | 5,750,421 | 372.8 s | 15,425 rows/s |
| pyspark | 50 % | 5,750,421 | **129.4 s** | 44,455 rows/s |
| pandas | 100 % | 12,224,691 | 805.2 s | 15,215 rows/s |
| pyspark | 100 % | 12,224,691 | **241.5 s** | 50,725 rows/s |

The dominant cost in Pandas is the cleaning stage (733 s of 805 s at full
scale): the raw file has 99 string columns, so each numeric conversion
touches ~12.2 M × 99 Python objects. Spark keeps the data columnar and
evaluates the same expressions as a vectorised DAG.

Spark's *ingest* stage is slower than Pandas' (104 s vs 19 s) — that is the
JVM and CSV-parser overhead, which is a fixed cost and is exactly why Spark
loses on small data and wins on large data. Full interpretation, including
the honest note that both engines ran on the same 16 GB machine, is in
`results/report.md` §6.

---

## 7. Figures

| Figure | Addresses |
|---|---|
| `fig1_denial_rate_by_joint.png` | RQ1 — the headline comparison |
| `fig2_financial_profile.png` | RQ2 — income, loan amount, LTI, interest rate |
| `fig3_denial_by_income_dti.png` | RQ3 — the gap within income and DTI strata |
| `fig4_gap_by_purpose_state.png` | RQ4 — the gap by purpose and state |
| `fig5_benchmark_scaling.png` | Performance and throughput |
| `fig6_missingness.png` | Data quality |

---

## 8. Environment

Python 3.11 · pandas 2.3.3 · numpy 2.2.6 · pyarrow 26.0.1 · PySpark 4.0.1 ·
matplotlib 3.10.9 · seaborn 0.13.2 · Temurin OpenJDK 17 · Hadoop winutils 3.3.6 ·
Windows 10 x64, 16 GB RAM.
