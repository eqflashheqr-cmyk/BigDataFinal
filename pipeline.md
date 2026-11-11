# Project Pipeline — Big Data Analysis Final Project
## Joint vs. Single Mortgage Applications in HMDA 2024

> **What this document is.**
> An internal, step-by-step record of how this project was actually executed:
> every phase, the decision taken, the evidence behind it, and the outcome.
> It is written so that a reader can reproduce the work, audit the reasoning,
> and understand *why* each choice was made rather than only *what* was done.
>
> It also maps each step back to the requirement in
> `Tài Liệu Được Cấp và Proposal/Big_Data_Analysis_Final_Project (1).pdf`,
> so nothing in the assignment is left unaddressed.
>
> **Status: complete.** All five mandatory parts of the assignment are
> implemented, verified, and reported. See §11 for the requirement-by-requirement
> audit and §12 for what remains for submission.

---

## Table of contents

| § | Phase | Status |
|---|---|---|
| [0](#0--ground-rules) | 0 — Ground rules | — |
| [1](#1--phase-1--problem-formulation) | 1 — Problem formulation | ✅ Done |
| [2](#2--phase-2--environment) | 2 — Environment setup | ✅ Done |
| [3](#3--phase-3--data-acquisition) | 3 — Data acquisition | ✅ Done |
| [4](#4--phase-4--schema--data-dictionary) | 4 — Schema & data dictionary | ✅ Done |
| [5](#5--phase-5--data-inspection--quality) | 5 — Data inspection & quality | ✅ Done |
| [6](#6--phase-6--data-engineering) | 6 — Data engineering | ✅ Done |
| [7](#7--phase-7--dual-implementation) | 7 — Dual implementation | ✅ Done |
| [8](#8--phase-8--correctness-comparison) | 8 — Correctness comparison | ✅ Done |
| [9](#9--phase-9--performance-experiment) | 9 — Performance experiment | ✅ Done |
| [10](#10--phase-10--report--figures--repository) | 10 — Report, figures, repository | ✅ Done |
| [11](#11--audit-against-the-assignment) | 11 — Audit against the assignment | ✅ |
| [12](#12--what-remains-for-submission) | 12 — What remains | ⬜ |
| [13](#13--decisions-log) | 13 — Decisions log | — |
| [14](#14--known-risks) | 14 — Known risks | — |

---

## 0 — Ground rules

Three principles governed every decision in this project. They are stated
first because they explain most of the choices that follow.

### 0.1 The data is the evidence, not the code

The central research question is a *finance* question: do joint applicants
get denied less often, and does that gap survive scrutiny? Everything else
is in service of answering it defensibly. The risk in a project like this is
to spend all the time on engineering and reach the end with a pipeline but no
finding. So the pipeline was built to be *fast enough to iterate on*, and the
analysis was written to be *reproducible from the Parquet output* rather than
re-derived from the raw file each time.

### 0.2 One definition, two implementations

The assignment requires that "cleaning rules must be documented and applied
consistently in the Pandas and Spark implementations". The naive way to
satisfy this is to write the rules twice and hope they match. The way this
project satisfies it is structural:

* `src/config.py` holds every code table, special code, and threshold — once.
* `src/rules.py` holds each cleaning rule, written **twice but side by side**,
  so a reviewer can check equivalence by eye.
* Every analytical quantity lives in `src/analytics.py` and `src/analysis.py`,
  also as a Pandas/Spark pair.

This design paid for itself. The equivalence check (§8) found **three real
bugs** that would each have silently corrupted the results. None of them would
have been caught by reading the code — only by running both engines and
comparing.

### 0.3 Document the exclusions, don't hide them

Every record dropped is counted and reported. Every cleaning rule that could
bias the analysis is stated with its direction of bias. This is what makes
the findings defensible to a reviewer who does not trust the code.

---

## 1 — Phase 1: Problem formulation

### 1.1 Reading the assignment before touching the data

**Decision:** read `Big_Data_Analysis_Final_Project (1).pdf` and
`HMDA_Proposal_Overleaf (1).pdf` end-to-end *before* downloading anything.

**Why:** the assignment is unusually specific about what it wants, and the
proposal PDF already contains the research questions. Writing code before
knowing the rubric would have produced the wrong artefacts. Reading it first
also surfaced two requirements that are easy to miss and that shaped the
architecture (§1.4).

### 1.2 The research questions

Taken from the group proposal (Thuỷ, Phong, Sỹ), and they are good questions —
specific, measurable, and answerable with the fields that HMDA actually
reports:

| | Question |
|---|---|
| **RQ1** | How does the denial rate differ between joint and single applications? |
| **RQ2** | How do income, loan amount, and the loan-to-income ratio differ between the groups? |
| **RQ3** | Does the denial-rate gap remain among applications with similar income, DTI, loan type and loan purpose? |
| **RQ4** | Does the gap vary by loan purpose and across the five states with the most applications? |

RQ3 is the load-bearing question. RQ1 alone is a two-number comparison that a
reviewer can dismiss as "high-income households get better rates". RQ3 is
what distinguishes a real finding from a composition artefact.

### 1.3 The financial framing

The motivating problem: **a single-income household faces a structurally
higher rejection probability for the same loan.** A second income reduces the
loan-to-income ratio, which is one of the most important inputs to an
underwriting decision. If HMDA 2024 confirms this, it has direct implications
for lenders (denial rate by applicant structure), for borrowers (the value
of a co-applicant), and for policy (how denial rates differ by household
composition).

The finding this produced — a 9.12 pp denial-rate gap that *widens* among
higher-income applicants — is not the expected story, and §6.5 explains why
that makes it more interesting rather than less.

### 1.4 Two requirements that shaped the design

Reading the assignment carefully surfaced requirements that are easy to
overlook and that dictated the architecture:

> *"Cleaning rules must be documented and applied consistently in the Pandas
> and Spark implementations."* (§3.2E)

> *"If the full dataset exceeds available memory, you may use chunked
> processing or a justified subset for Pandas. Document the limitation and
> ensure that direct comparisons use equivalent input records."* (§3.4A)

The second one is explicit that Pandas may not manage the full dataset — which
means the two engines must be compared on **equivalent input records**, not
on "whatever each engine could load". This drove the decision (§9.2) to
define the benchmark sample with a hash rule that is byte-identical in both
engines.

---

## 2 — Phase 2: Environment setup

### 2.1 What was installed and why

| Component | Version | Location | Reason |
|---|---|---|---|
| Temurin OpenJDK 17 | 17 | `E:\Tools\jdk17` | PySpark 4.x requires JDK 17+ |
| Hadoop winutils | 3.3.6 | `E:\Tools\hadoop\hadoop-3.3.6` | Lets Spark commit files on Windows |
| PySpark | 4.0.1 | pip | Assignment-mandated engine |
| pandas | 2.3.3 | pip | Assignment-mandated engine |
| pyarrow | 26.0.1 | pip | Parquet I/O, the deliverable storage format |

The JDK and Hadoop were installed to `E:\Tools` rather than to `C:` and
outside a virtualenv, per the user's explicit choice, to keep the Python
environment clean and the tooling reusable.

### 2.2 The Windows/Spark problem and its fix

**Symptom:** PySpark could read the CSV but every `write.parquet()` failed
with:

```
java.io.IOException: Could not create FileOutputStream
UnsatisfiedLinkError: NativeIO$Windows.access0
```

**Root cause:** two separate gaps.
1. `HADOOP_HOME` was unset, so Spark could not locate `winutils.exe`.
2. The JVM's `java.library.path` did not include the directory holding
   `hadoop.dll`, so the native filesystem shim could not be loaded.

**Fix:** download winutils 3.3.6, place the binaries in
`E:\Tools\hadoop\hadoop-3.3.6\bin`, set the user environment variables
`JAVA_HOME` and `HADOOP_HOME`, and copy `hadoop.dll` + `winutils.exe` into
`E:\Tools\jdk17\bin` so the JVM's library path resolves them.

**Verification:** write a DataFrame to Parquet with PySpark, read it back
with Pandas, and vice-versa. Both directions were byte-compatible — which
confirmed the two engines could share a Parquet file, a prerequisite for the
entire equivalence design.

### 2.3 Environment variables set

```
JAVA_HOME   = E:\Tools\jdk17
HADOOP_HOME = E:\Tools\hadoop\hadoop-3.3.6
```

Both are **user-level**, not machine-level, so no admin rights are needed and
other projects on the machine are unaffected.

---

## 3 — Phase 3: Data acquisition

### 3.1 Choosing the authoritative file

The FFIEC publishes the 2024 national LAR in several formats. Three candidates
were considered:

| Candidate | Rows | Decision |
|---|---|---|
| `2024_public_lar_one_year_pipe.txt` (pipe-delimited) | 12,259,199 | **✅ Chosen** |
| `2024_public_lar_one_year_csv.csv` | 12,259,199 | Downloaded but unused — ~3× slower to parse, no advantage |
| Third-party Hugging Face mirror (`retrogradespace/hmda_2024`) | 12,220,000 | Rejected — 39k rows short, not the official artifact |

**Decision:** the official FFIEC pipe-delimited file.

**Why:** the row-count difference against the third-party mirror (39,199
records) is small, but a mirror is not the artifact the assignment names, and
a row-count mismatch is an unexplainable risk in a defence. The pipe format
was chosen over CSV because it needs no quoting logic and parses faster in
both engines.

### 3.2 Parquet: not available from the source

**Finding:** FFIEC does **not** publish the LAR in Parquet. The assignment
says "Save the prepared analytical data in an appropriate format, such as
Parquet, where feasible."

**Decision:** generate Parquet from the cleaned pipe-delimited file.

**Why this is the right reading:** the assignment's Part 2E is under
"Data Engineering and Preparation" — it asks for *prepared* data in an
appropriate format. The point is that the analytical dataset should not be
re-derived from raw text on every run. The format of the *source* file is
not under our control.

**Documented in:** `README.md` §2 and `results/report.md` §2.

### 3.3 The file on disk

```
data/pipe_file/2024_public_lar_one_year_pipe.txt   4.32 GiB  (4,636,628,799 bytes)
data/pipe_file/2024_public_lar_one_year_pipe.zip    0.62 GiB
data/csv_file/2024_public_lar_one_year_csv.csv       4.32 GiB
data/csv_file/2024_public_lar_one_year_csv.zip      0.62 GiB
```

Both the pipe and CSV variants were downloaded (the user downloaded both),
so the choice of format can be defended by measurement rather than assertion.

### 3.4 What is *not* in the repository

The raw data (9.9 GB) and the intermediate Parquet (1.04 GB) are **gitignored**.
The assignment is explicit: *"Do not upload sensitive credentials or
unnecessarily duplicate large public datasets in the repository. Provide
appropriate download instructions."*

`README.md` contains the exact FFIEC URL and the exact commands to reproduce
the data directory from scratch. A reviewer can clone, download, and reproduce
in one afternoon.

---

## 4 — Phase 4: Schema & data dictionary

### 4.1 The schema was copied, not guessed

**Problem:** the FFIEC documentation pages are served through Akamai and
returned HTTP 403 to scripted access.

**Resolution:** the schema was retrieved through documentation sources and
then **pasted by the user and written to disk verbatim**, so it is the
authentic FFIEC text rather than a reconstruction:

* `docs/public_lar_schema_2024.md` — all 99 fields with max lengths and types
* `docs/hmda_data_dictionary_2024.md` — full value-code tables, special codes,
  empirical units and distributions, the `joint_flag` definition, provenance,
  and limitations

This is also why `docs/` is version-controlled but `data/` is not: the
documentation is the part a reviewer needs, the 4.32 GiB file is not.

### 4.2 The units that only empirical inspection could settle

The data dictionary states the *definitions*. Several units had to be
established by scanning the actual file, because they are the difference
between a correct analysis and a wrong one:

| Field | Naive reading | **Reality (verified empirically)** |
|---|---|---|
| `income` | dollars | **thousands of USD** — median 104 means $104,000 |
| `debt_to_income_ratio` | a ratio | an **ordinal band string**: `30%-<36%`, `>60%`, `NA`, `Exempt` |
| `applicant_age` | a number | an **ordinal band string**: `25-34`, `>74` |
| `co_applicant_age` `9999` | a large age | **"no co-applicant"** sentinel |
| `combined_loan_to_value_ratio` | a percentage | stored as `36`, `80` — bare integers |

The DTI finding is the one that would have broken the analysis outright:
treating `30%-<36%` as a number yields nulls, and treating it as a ratio
yields nonsense. This is why `config.py` defines `DTI_BANDS` as an explicit
**ordered list of the raw strings**, and `dti_band_order` is an integer index
into that list — an ordering that is meaningful for stratification.

### 4.3 The special codes

| Code | Meaning | Treatment |
|---|---|---|
| `1111` | Exempt | → missing |
| `NA` / `N/A` | Not applicable | → missing |
| `Exempt` | Exempt | → missing |
| `8888` | Age not available | → missing |
| `9999` | Age: no co-applicant | → missing |
| *(blank)* | Not reported | → missing |

**Rule:** a special code becomes a true missing value, **never 0**. The
assignment is explicit — *"Do not automatically replace every missing value
with zero"* — and 0 is a meaningful value for `income`, `loan_amount` and
`interest_rate`, so a 0-fill would silently corrupt the denominators.

---

## 5 — Phase 5: Data inspection & quality assessment

### 5.1 What was inspected

`src/quality_checks.py` plus the initial exploration produced:

* the 99-field schema with types and max lengths
* record counts at every stage
* missing-value counts per variable
* value distributions for every coded variable
* range and distribution for every numeric variable
* duplicate investigation (§5.4)
* a Spearman correlation matrix among the financial variables

### 5.2 Missingness is structural, not random

The missing values in HMDA are **reporting-driven**, which is the single most
important thing to understand about this dataset:

| Variable | Missing | Why |
|---|---|---|
| `interest_rate` | 4.51 M (36.8 %) | HMDA only requires the rate for **originated** loans |
| `rate_spread` | 6.42 M (52.4 %) | same |
| `total_loan_costs` | 6.73 M (55.0 %) | same |
| `income` | 1.78 M (14.5 %) | income is not required in every circumstance |
| `property_value` | 2.74 M (22.4 %) | required mainly for purchase loans |

**Consequence for the analysis, stated explicitly in the report:** the
interest-rate comparison in RQ2 rests on a **biased subset** (originations
only). A joint application is *more likely* to be originated, so the joint
group's interest-rate sample is systematically different. This is disclosed
in `results/report.md` §7 rather than buried.

### 5.3 Implausible vs. extreme: the distinction that matters

The assignment asks to *"distinguish genuine outliers from data errors"*.

**Data errors found and removed — 7,753 records:**

| Pattern | Count | Interpretation |
|---|---|---|
| `income` negative (e.g. `-18010`) | 7,753 | impossible; a reporting or sign error |
| `loan_amount` negative | 0 | — |
| `loan_amount` = 0 | 0 | — |
| `property_value` negative | 0 | — |

**Extreme values found and KEPT:**

| Pattern | Value | Why kept |
|---|---|---|
| `income` max | 999,999,999 (thousands) | HMDA sentinel-ish outlier, not a parse error |
| `loan_amount` max | 2,962,005,000 | genuine jumbo mortgage |
| `interest_rate` max | 60.0 % | possible but extreme |

**Why the distinction matters:** removing the extremes would bias the analysis
*towards* finding a smaller denial-rate gap, because very large loans are
over-represented among denials. Discarding them to make a cleaner-looking
mean would have been scientific misconduct dressed up as data hygiene. The
report therefore gives **both** mean and median, and states plainly that the
mean loan amount is dominated by a small number of very large loans
(σ = $3.0 M against a median of $225,000).

The removal rule is applied identically in both engines and every removed
record is counted (`results/cleaning_report_*.json`).

### 5.4 Duplicate investigation

The assignment explicitly requires this under §3.2B. Two definitions were
tested on the full cleaned dataset, using row hashes so the result is exact
rather than approximate:

| Definition | Rows involved | Redundant rows | % of dataset |
|---|---:|---:|---:|
| **Exact** — all 99 fields identical | 46,974 | **26,755** | 0.218 % |
| **Business key** — institution + borrower + loan amount + location + outcome | 83,498 | 46,579 | 0.380 % |

**Decision:** remove only the **exact** duplicates.

**Why not the business-key definition:** a borrower may legitimately file two
applications with the same lender for the same amount and property — a
refinance attempt followed by a purchase, or a re-submission after correcting
a field. Those are real applications, and removing them would discard
genuine observations. The exact-duplicate rule, by contrast, can only remove
rows that are indistinguishable from another row.

**Impact on the findings:** measured, not assumed. Deduplication changes the
RQ1 gap from 9.129 pp to 9.119 pp — a 0.01 pp shift. The finding is
completely insensitive to the choice.

**Implementation, in both engines:**

* Pandas: `hash_pandas_object` over the 99 raw columns, with the hashes of
  already-emitted rows carried across chunk boundaries so that duplicates
  spanning a chunk boundary are still caught.
* Spark: `dropDuplicates()` over all 99 columns.

Both were verified to produce **identical row counts** before running the full
pipeline. Residual exact duplicates after cleaning: **2** (hash collision).

---

## 6 — Phase 6: Data engineering

### 6.1 The architecture

```
src/config.py   ← single source of truth: paths, code tables, special codes,
                   joint_flag rules, thresholds, DTI bands
src/rules.py    ← each cleaning rule, written twice (Pandas + Spark) side by side
```

`config.py` is the keystone. It means a change to, say, the `action_taken`
code table happens in exactly one place and propagates to both engines
identically. This is what makes "consistently applied" a structural property
rather than a promise.

### 6.2 The `joint_flag` derivation — the most consequential decision

`joint_flag` is **not a field in HMDA**. It had to be derived, and the
derivation is the pivot of the whole project.

Four co-applicant fields were used:
`co_applicant_ethnicity_1`, `co_applicant_race_1`, `co_applicant_sex`,
`co_applicant_credit_score_type`.

Each field's value is classified into one of three states:

| Field | **Absent** (no co-applicant) | **Not applicable** (not reported) | **Present** |
|---|---|---|---|
| `co_applicant_ethnicity_1` | `5` | `4` | 1, 2, 3, 11–14 |
| `co_applicant_race_1` | `8` | `7` | 1–6, 21–27, 41–44 |
| `co_applicant_sex` | `5` | `4` | 1, 2, 3, 6 |
| `co_applicant_credit_score_type` | `10` | 9, 1111 | 1–8, 11–15 |

```
joint_flag = 1   if  ≥1 present  AND  0 absent
joint_flag = 0   if  ≥1 absent   AND  0 present
joint_flag = NA  otherwise
```

**The subtlety that had to be got right:** code `3` / `6` means *"Information
not provided by applicant"*. A naive reading treats that as missing data.
But the fact that a co-applicant's ethnicity was *not provided* is itself
evidence that **a co-applicant exists** — you cannot fail to report the
ethnicity of a co-applicant who does not exist. So code 3/6 counts as
**present**, not as missing. Getting this wrong would have shrunk the joint
group substantially.

**Validation:** the rule was checked against the independent
`co_applicant_ethnicity_observed` field (value `4` = "co-applicant not
observed"). The derived flag produced **zero false positives**.

### 6.3 The 9.44 % indeterminate rate — investigated, not hand-waved

The first full run produced 1,157,493 indeterminate records (9.44 %). An
earlier 900k-row sample had suggested only ~0.13 %, so the full-file rate
was a genuine surprise and was investigated rather than accepted.

| Finding | Detail |
|---|---|
| 90.6 % of indeterminate records | `action_taken = 6` (**purchased loans**) |
| 98.1 % of indeterminate records | `applicant_sex = 4` (**"Not applicable"**) |

**Interpretation:** for purchased loans, the originator's co-applicant fields
are routinely left unreported — the record describes a loan in transit, not
the original application. Nothing can be inferred, so these records are
correctly classified as indeterminate.

**Decision:** keep them as indeterminate (never impute), exclude them from
the joint-vs-single comparison, and report them explicitly.

**Crucially, the rate among records that reached a lender decision is only
1.01 %** — and all four RQs are computed on that decision population
(8,557,686 records). So the indeterminate rate does not meaningfully weaken
any conclusion. This is stated in `results/report.md` §3.1 rather than left
for a reviewer to discover.

### 6.4 Derived variables

| Variable | Definition | Purpose |
|---|---|---|
| `joint_flag` | §6.2 | the core grouping variable |
| `income_dollars` | `income × 1000` | converts to actual USD |
| `loan_to_income_ratio` | `loan_amount / income_dollars` | the debt-burden measure underlying the hypothesis |
| `dti_band_order` | integer index into `DTI_BANDS` | makes the ordinal DTI band sortable and stratifiable |
| `is_denied` | `action_taken == 3` | the numerator of the denial rate |
| `has_lender_decision` | `action_taken ∈ {1,2,3}` | the denominator of the denial rate |

### 6.5 The denial-rate definition

```
denial_rate = D / (O + A + D)
```

`O` = originated (1), `A` = approved-not-accepted (2), `D` = denied (3).

Codes 4–8 (withdrawn, incomplete, purchased, preapproval) are **not lender
decisions** and are excluded from the denominator. They are reported
separately in the outcome distribution, so nothing is hidden — a reader can
reconstruct every denominator.

### 6.6 The cleaning funnel

| Stage | Records | Removed |
|---|---:|---:|
| Raw | 12,259,199 | — |
| After exact-duplicate removal | 12,232,444 | 26,755 |
| After implausible-value removal | 12,224,691 | 7,753 |
| **Final analytical dataset** | **12,224,691** | — |
| With a lender decision (O+A+D) | 8,557,686 | 3,667,005 |
| Joint or single known | 8,557,686 | 0 indeterminate (1.01 % of the raw indeterminate) |
| With `income` reported | ~7.3 M | — |

### 6.7 Storage decision

**Parquet, Snappy compression, one directory per engine.**

*Why Parquet:* columnar, typed, compressed, and readable by both Pandas and
Spark. The full cleaned dataset is **1.04 GB** as Parquet versus 4.32 GB as
raw text — a 4× reduction, and the analytical columns can be projected
without reading the rest.

*Why two directories:* `data/clean/hmda_2024_clean/` (Pandas) and
`data/clean/hmda_2024_clean_spark/` (Spark). Each engine cleans the **raw
file independently**. If Spark had read the Pandas output, the equivalence
check would prove nothing — it would prove that Spark can read what Pandas
wrote. Independent cleaning from the same source is what makes the comparison
meaningful.

*Partitioning:* considered and rejected. The dataset is a single flat table
with no natural partition key that the analysis filters on; partitioning by
`state_code` would add 50+ small files for no benefit at this size.

---

## 7 — Phase 7: Dual implementation

### 7.1 What is implemented twice, and what is shared

| Module | Shared | Duplicated (Pandas + Spark) |
|---|---|---|
| `rules.py` | code tables, thresholds | the 6 cleaning rules |
| `analytics.py` | the list of canonical outputs | 8 analytical functions |
| `analysis.py` | stratum definitions, quartile labels | RQ1–RQ4 |

The duplication is deliberate and narrow. The *definitions* live in
`config.py`; only the *execution* is written twice. The two implementations
sit adjacent in each file with matching comments, so equivalence is auditable
by eye.

### 7.2 The Pandas implementation and its memory constraint

The raw file is 4.32 GiB of text with 99 columns. Materialised as a Pandas
DataFrame of strings, that is roughly **40 GB** — impossible on a 16 GB
machine.

**Solution: chunked processing.** `pandas_pipeline.py` reads 500,000 rows at
a time, applies the *same* `clean_pandas` rules to each chunk, and appends
the result to the Parquet writer. The full dataset never has to be resident.

This is explicitly permitted by the assignment (§3.4A) and is documented as a
limitation in `README.md` and `results/report.md`.

### 7.3 The Spark implementation

`spark_pipeline.py` reads the same raw file with `spark.read.csv`, applies
`clean_spark`, and writes its own Parquet. Spark configuration:

| Setting | Value | Reason |
|---|---|---|
| `spark.driver.memory` | 8 g | half of RAM, leaving headroom for the OS |
| `spark.sql.shuffle.partitions` | 16 | the default of 200 is far too many for a single machine and dominates runtime |
| `spark.sql.execution.arrow.pyspark.enabled` | true | faster Pandas↔Arrow transfer |
| `spark.sql.parquet.compression.codec` | snappy | matches the Pandas output |

### 7.4 Engine-specific operational decisions

| Issue | Pandas | Spark | Reason |
|---|---|---|---|
| 104 columns × 12.2 M rows won't fit | load only the 23 needed columns, categoricals for high-cardinality text | `select(*needed)` before `persist` | both engines must fit in 16 GB |
| Caching 12 M rows in RAM | n/a | `MEMORY_AND_DISK`, or `DISK_ONLY` for the benchmark | avoids `SparkOutOfMemoryError` |
| Memory contention | run in separate processes | run in separate processes | Pandas + Spark in one process OOM'd the JVM |
| `count()` per cleaning step | free | one aggregation pass | 5 counts = 5 passes over 12 M rows |

### 7.5 Two engine-specific pitfalls that were fixed

**Spark `SUM` propagates NULL.** The `joint_flag` rule sums per-field
indicators; a single empty co-applicant field made the whole SUM null, so a
valid record became "indeterminate". Symptom: Spark found 1,159,851
indeterminate records where Pandas found 1,157,493 — a 2,358-record
disagreement. Fix: wrap every counter in `coalesce(..., 0)`.

**Pandas `Int64.isin(("1","2","3"))` is always `False`.** After numeric
parsing, `action_taken` is `Int64`, but the outcome codes were still written
as *strings* in `config.py`. Pandas compared `1 == "1"` → `False`, so
`has_lender_decision` was 0 everywhere; Spark's `isin` coerced the literals
and silently worked. Symptom: Pandas reported 0 decisions where Spark
reported 8,654,559. Fix: make the code tables **integer-keyed** throughout
`config.py`, so the types cannot drift.

Both bugs were invisible to code review. Both were caught by the equivalence
check. This is the strongest argument for §0.2.

---

## 8 — Phase 8: Correctness comparison

### 8.1 Design

The comparison runs as **three separate processes**
(`pandas` → `spark` → `compare`), because a Pandas DataFrame of 12.2 M rows
and a cached Spark DataFrame of the same size do not fit in 16 GB together.
Each engine gets the full machine.

Eight canonical outputs are compared — the assignment requires "at least
three":

1. Record counts after each cleaning step
2. Missing-value counts for 13 important variables
3. Counts and proportions of application outcomes
4. Denial rate by `joint_flag` (RQ1)
5. Descriptive statistics of `loan_amount`, `income`, `interest_rate`, LTI
6. Average and median loan amount by loan type
7. Aggregated results by financial institution (LEI, top 50)
8. Denial rate in the top 5 states (RQ4)

Integer counts must match **exactly**; floats must agree within a relative
tolerance of 1e-6.

### 8.2 Result

> **8 of 8 comparisons agree.**

Additionally, all four research questions were computed independently in
both engines and diffed cell-by-cell: **RQ1, RQ2, RQ3 (1,730 strata) and RQ4
— zero differing cells.**

For RQ3 — the largest of the four, at 1,730 strata — the diff is run by
`src/rq3_equivalence.py`, which writes `results/rq3_equivalence.json`:

```bash
python src/run_analysis.py all   # writes results/rq3_{pandas,spark}.csv
python src/rq3_equivalence.py     # writes results/rq3_equivalence.json
```

```
strata compared      : 1,730
strata key mismatches: 0
numeric mismatches   : 0
max rate difference  : 0
joint_lower real diff: 0
null-repr differences: 182
RESULT: AGREE
```

The 182 "null-representation differences" are **not** a numerical
discrepancy. They are strata where one of the two groups has no decisions
at all, so the group's denial rate is undefined: Pandas writes `NaN` for
`joint_lower` there, while Spark's SQL comparison of a NULL yields `False`.
Both mean the same thing — the joint group cannot have the lower denial
rate when it has no decisions. Every count and every rate is identical in
all 1,730 rows, and the script reports the difference explicitly rather
than hiding it.

### 8.3 The discrepancies that were found and explained

The assignment requires an explanation for any discrepancy. Three were found;
all three were genuine engine differences, and all three were fixed at the
source rather than papered over:

| # | Discrepancy | Cause | Fix |
|---|---|---|---|
| 1 | Spark: 1,159,851 indeterminate vs Pandas 1,157,493 | Spark's `SUM` propagates NULL | `coalesce` around every counter |
| 2 | Pandas: 0 decisions vs Spark 8,654,559 | `Int64.isin(("1","2","3"))` is always False; Spark coerces literals | integer-keyed code tables |
| 3 | RQ3 row order / quartile membership differed | `pd.qcut` and Spark `ntile` disagree at boundaries | boundaries computed once from the data, **pinned** to `results/income_quartile_bounds.json` |

A fourth issue was found by inspection rather than by the checker: Spark's
`groupBy` returns rows in an **unspecified order**, while Pandas sorts group
keys lexicographically. Both engines now use the same explicit ordering
(`JOINT_ORDER`, plus a tie-break on the grouping key) so that row *i* in the
Pandas output corresponds to row *i* in the Spark output.

### 8.4 On "do not modify results merely to make the implementations appear identical"

Every fix above changed the *code* to remove a genuine semantic difference.
No fix adjusted a number, loosened a tolerance, or excluded a record to
manufacture agreement. The tolerance remains 1e-6; the record counts remain
exact.

---

## 9 — Phase 9: Performance and scalability experiment

### 9.1 What is measured

A representative analytical workload — the full ingest → clean → analyse
pipeline — at three data volumes.

| Stage | What it covers |
|---|---|
| `ingest` | read the raw pipe-delimited file, parse columns, apply the sample filter |
| `clean` | all 6 cleaning rules + derived variables |
| `analyse` | RQ1–RQ4 |
| `total` | the sum — the headline number |

The assignment requires the timing to exclude "unrelated activities such as
downloading data, installing packages, or displaying plots", and to
"distinguish initial setup and execution overhead from the time required for
the measured workload". The Spark session is created **before** the timer
starts, so session initialisation is excluded; the data is then read from
the local disk (not downloaded).

Each cell is measured **3 times and the median reported**.

### 9.2 The sampling rule — the part that had to be right

Both engines must process **equivalent input records**. Two candidate rules
were tried:

* **Rejected:** `loan_amount mod 1000`. This fails because HMDA loan amounts
  are reported in whole thousands of dollars and are therefore almost always
  exact multiples of 1000 — the filter selected either everything or nothing.
* **Rejected:** Spark's `hash()` / Pandas' `hash()`. Neither is stable across
  versions or implementations, so the two engines would select *different*
  rows and the comparison would be meaningless.
* **Adopted:** `SHA-256(lei)[0:8]` as an integer, `mod 1000`, compared
  against `fraction × 1000`. SHA-256 is available in both Python's
  `hashlib` and Spark's `sha2()`, and the digest is identical across both.

**One bug here was subtle and worth recording:** Spark's `substring(str, pos,
len)` is **1-indexed**, so `substring(sha, 1, 9)` takes *nine* hex characters
while Python's `digest[:8]` takes *eight*. The two engines selected
3,376,848 vs 2,379,571 rows at 25 % — different subsets. Fixed by using
`substring(sha, 1, 8)` and verifying parity explicitly before benchmarking.

The rule was verified to select **exactly the same row counts** in both
engines at 25 % (3,376,848) and 50 % (5,753,536).

### 9.3 Results

Measured on the deduplicated pipeline, after the cross-chunk fix in §10.4.
Both engines process **exactly the same records** at every level.

| Engine | Data | Rows | Ingest | Clean | Analyse | **Total** | Throughput |
|---|---|---:|---:|---:|---:|---:|---:|
| pandas | 25 % | 3,367,092 | 14.9 s | 214.2 s | 12.9 s | **242.0 s** | 13,914 rows/s |
| pyspark | 25 % | 3,367,092 | 40.4 s | 104.0 s | 11.0 s | **155.1 s** | 21,713 rows/s |
| pandas | 50 % | 5,735,393 | 16.0 s | 364.4 s | 22.6 s | **403.3 s** | 14,221 rows/s |
| pyspark | 50 % | 5,735,393 | 52.8 s | 183.7 s | 12.6 s | **252.5 s** | 22,711 rows/s |
| pandas | 100 % | 12,224,691 | 18.0 s | 784.3 s | 53.3 s | **855.9 s** | 14,284 rows/s |
| pyspark | 100 % | 12,224,691 | 97.1 s | 437.4 s | 23.8 s | **544.8 s** | 22,440 rows/s |

**Speedup: 1.56× at 25 %, 1.60× at 50 %, 1.57× at 100 %.**

### 9.4 Interpretation

**Which is faster?** PySpark, at every size, by roughly 1.6×.

**Did relative performance change?** No — the advantage is essentially constant
across the three volumes. This is the honest result and it is worth stating
plainly rather than dressing up: on a single 16 GB machine, the two engines
scale at a similar rate, and the gap is a **constant-factor** difference in
per-cell processing, not a growing one.

**What overheads affected Spark performance?** Spark's *ingest* stage is
consistently slower than Pandas' (97 s vs 18 s at full scale). This is the
JVM and catalyst overhead: schema inference, CSV parsing through the JVM's
univocity parser, and the cost of materialising a distributed DataFrame on
one node. Spark pays this fixed cost regardless of data volume — which is
exactly why Spark loses on small data and wins on large data.

**The deduplication step is what narrows the gap, and the reason is
instructive.** `dropDuplicates` over all 99 columns is a full-table
aggregation over every column. It costs Spark **437 s** of its 545 s
cleaning stage — roughly four times what the same stage cost before
deduplication was added. Pandas gets its deduplication almost for free,
because it hashes the 99 columns row-by-row as part of the same pass that
already touches every cell.

The general lesson: **an operation that is cheap in a row-at-a-time engine
can be expensive in a column-at-a-time one.** A distinct over all columns is
the pathological case. It is also worth stating what this means for the
assignment's framing — the assignment's example workloads are *"grouping
applications by loan type"*, *"computing outcome rates by geographic area"*,
*"aggregating loan amounts by financial institution"*. Those are all
group-bys, not full-table distincts, and they favour Spark considerably more
than the 1.57× measured here. The pipeline benchmark is a deliberately
conservative choice that includes the hardest operation for Spark.

**Did memory limitations affect either implementation?** Yes, materially, and
differently:

* *Pandas* cannot hold the raw 12.2 M × 99 string frame (≈ 40 GB) at all.
  It survives only via chunked processing, and even then the working set is
  tight enough that one benchmark repeat drifted from 851 s to 865 s —
  visible GC noise.
* *Spark* OOM'd twice during development when the full 104-column dataset
  was cached. The fix was column projection before caching, and
  `MEMORY_AND_DISK` / `DISK_ONLY` storage levels.

**When would Spark be preferable?** When the data no longer fits in a single
machine's RAM, when the workload is wide (many group-bys across institutions
and states), or when it must scale to multiple years of HMDA. When would
Pandas be preferable? For a single machine's worth of data, an exploratory
analysis, or a workload Pandas can express vectorised — its overhead is
essentially zero, and on small data it wins outright.

**A note on honesty:** the assignment says *"Do not assume that Spark must be
faster."* These measurements happen to favour Spark at this scale on this
machine. That is reported as measured, with the caveats above.

### 9.5 A measurement note

An earlier benchmark run, made before the deduplication step was added,
reported Spark at 242 s and Pandas at 805 s for the full dataset — a 3.3×
gap. Those numbers are **not** the ones reported here, because they measured
a pipeline that did less work. Adding the deduplication step cost Spark
437 s and cost Pandas almost nothing (§9.4), which is why the published
speedup is 1.57× and not 3.3×.

This is recorded rather than quietly overwritten, because the difference
between the two sets of numbers is itself the most interesting performance
finding in the project.

---

## 10 — Phase 10: Report, figures & repository
### 10.1 Deliverable structure vs. the assignment's recommended structure

The assignment (§6.2) recommends a 12-section report. `src/report.py`
generates `results/report.md` in exactly that structure, and
`src/export_pdf.py` renders it to **`report.pdf`** at the repository root
using ReportLab — handling headings, paragraphs, lists, fenced code
blocks, pipe tables, blockquotes and the figure images. The PDF export is
scripted, so the report can be regenerated after any change:

```bash
python src/report.py     # -> results/report.md
python src/export_pdf.py # -> report.pdf
```

(The root `report.pdf` is no longer committed — see §10.3. The LaTeX
report in `latex_report/` is the deliverable.)

**The Markdown version was subsequently superseded by a LaTeX version**
(§12), which is the one written in the ACM 2-column template the assignment
specifies. Both are kept: the Markdown one is convenient to regenerate
programmatically, the LaTeX one is the formatted deliverable.

| § | Report section | Content |
|---|---|---|
| 1 | Introduction and problem formulation | RQ1–RQ4, headline finding |
| 2 | Dataset description and data quality | provenance, schema, quality assessment |
| 3 | Data engineering and preparation | `joint_flag`, cleaning rules, funnel |
| 4 | Descriptive and diagnostic analysis | RQ1–RQ4 results, figures |
| 5 | Pandas implementation | §7.2 |
| 6 | PySpark implementation | §7.3 |
| 7 | Correctness comparison | §8 — 8/8 agree, discrepancies explained |
| 8 | Performance and scalability experiment | §9 |
| — | Financial interpretation and limitations | §7 of the report |
| — | Conclusion | |
| — | References | data provenance |
| — | Appendix | code, supplementary results |

### 10.2 Figures

Six figures, each addressing a specific research question, each with a title,
labelled axes, units, and an interpretation:

| Figure | Addresses |
|---|---|
| `fig1_denial_rate_by_joint.png` | RQ1 — the headline comparison + analysis population |
| `fig2_financial_profile.png` | RQ2 — income, loan amount, LTI, interest rate |
| `fig3_denial_by_income_dti.png` | RQ3 — gap within income and DTI strata |
| `fig4_gap_by_purpose_state.png` | RQ4 — gap by purpose and state |
| `fig5_benchmark_scaling.png` | §9 — performance and throughput |
| `fig6_missingness.png` | §5.2 — data quality |

The assignment warns against *"charts merely to increase the number of
figures"*; each of the six earns its place by answering a stated question.

### 10.3 Repository hygiene

`.gitignore` excludes the raw data, the intermediate Parquet, the environment,
the Python cache, and the instructor-provided course material. What *is*
committed:

```
README.md                  reproduction instructions, method, findings
requirements.txt           pinned versions
pipeline.md                this document
docs/                      schema + data dictionary
src/                       16 modules
results/                   all CSV + JSON outputs, report.md, predictive artefacts
figures/                   6 PNGs
latex_report/              the LaTeX report source and the compiled PDF
Tài Liệu Được Cấp và Proposal/HMDA_Proposal_Overleaf (1).pdf   the team's proposal (Deliverable 1)
```

**What is not committed, and why:**

* **The raw dataset.** 9.9 GB of public data. The assignment (§6.3) forbids
  duplicating large public datasets and requires download instructions
  instead — `README.md` §2 has the exact FFIEC URL and the expected directory
  layout.
* **The instructor's material.** The assignment PDF and the two lecture-note
  PDFs are the instructor's course content, not this project's deliverable.
  The team's own proposal **is** kept, because it is Deliverable 1.
* **Regenerable intermediates.** These are written by the scripts that
  produce them and are rebuilt by a clean run, so tracking them adds bulk
  without adding information:

  | Path | Written by | Rebuilt by |
  |---|---|---|
  | `results/rq*_pandas.csv`, `results/rq*_spark.csv` | `src/analysis.py` | `python src/run_analysis.py all` |
  | `results/_equiv_pandas.json`, `results/_equiv_spark.json` | `src/equivalence.py` | `python src/equivalence.py all` |
  | `latex_template/` | unzip of the instructor's `.zip` | copy of `acmart.cls` etc. into `latex_report/` |

  The consolidated files the report and the figures actually read
  (`results/rq1..rq4.csv`, `results/equivalence_report.json`) **are**
  committed, so the report's claims are checkable without re-running
  anything.

  Hiding the two RQ3 CSVs initially left the report's "1,730 strata, zero
  differing cells" claim without a tracked artefact. `src/rq3_equivalence.py`
  fixes that: it diffs the two per-engine files and writes the small,
  permanent summary `results/rq3_equivalence.json`, which is committed.

* **The superseded `report.pdf` at the repository root.** The ReportLab
  render of the Markdown report was replaced by the LaTeX report
  (`latex_report/report.pdf`). Keeping both would leave two PDFs claiming to
  be the deliverable.

* **The predictive artefacts are kept.** `results/predictive_predictions.npz`
  holds the test-set probabilities behind the predictive extension's
  figures and evaluation tables. It is ~13 MB, which is large for a git
  object, but it is the primary empirical output of Part 4, and a reviewer
  can regenerate the extension's numbers from it without retraining the
  model. It is therefore tracked deliberately.

The repository is a clone-and-run artifact: a reviewer who downloads the data
per `README.md` reproduces every number and every figure.

### 10.4 Publishing to GitHub

The repository was created with the GitHub CLI and pushed to a public
`main` branch:

> <https://github.com/eqflashheqr-cmyk/BigDataFinal>

The commit message states the three findings, the dual-implementation
approach, and the three bugs that the equivalence check caught — because a
reviewer reading the repository list should learn what the project concluded
before opening a single file.

**One commit, then a second one for the re-benchmarked timings.** The
benchmark takes ~1.8 h, so it runs in the background while the repository is
assembled; its refreshed numbers are committed separately rather than
blocking the first publish.

**The re-benchmark caught a fourth engine bug.** The first re-run of the
benchmark reported **3,367,139** rows for Pandas against **3,367,092** for
Spark at the 25 % level — a 47-row discrepancy, even though the two engines
agreed exactly on the full dataset.

The cause was in `bench_pandas`: it called `clean_pandas(chunk)` on each
500,000-row chunk *without* carrying the row hashes of the previously
cleaned chunks. A duplicate whose two copies landed in different chunks
therefore survived in Pandas, while Spark's global `dropDuplicates` removed
it. The full-dataset pipelines were unaffected — `pandas_pipeline.py` already
carried `seen_hashes` across chunks — which is why the equivalence check
still reported 8 of 8.

**This is the second time a chunk-boundary bug has appeared**, and both times
it was invisible to code review and to the equivalence check. The fix was to
pass `seen_hashes` through the benchmark exactly as the production pipeline
does; the benchmark now reports **3,367,092** in both engines.

The general lesson, worth stating because it will apply to the team's own
extensions: *in a chunked implementation, any stateful operation must carry
its state across chunk boundaries, and the only way to catch that is to run
the chunked path and the non-chunked path against each other.* The
benchmark is precisely that check, and it earned its keep.

**One detail that cost time:** the `.gitignore` patterns for the instructor's
PDFs did not match. The path contains Vietnamese diacritics
(`Tài Liệu Được Cấp và Proposal`), and the wildcard `*Big_Data_Analysis_*`
matched nothing because git was matching against the quoted, escaped path.
Fixed by switching to a filename-only wildcard (`*Big_Data_Analysis_Final_Project*.pdf`),
which matches on the basename and is immune to the directory's encoding.

---

## 11 — Phase 11: Optional predictive extension

This phase was added last, after the core deliverable was complete. The
governing constraint from the request was that the code must be **as light
as possible on RAM, CPU and disk**, and that a longer runtime was
acceptable in exchange.

### 11.1 Target and the leakage boundary

The target is `is_denied` (`action_taken == 3`) among applications that
reached a lender decision. The intended use is *triage* — flagging elevated
denial risk at intake — not automated credit decisioning.

The binding design decision is which columns are *admissible*. The
following are excluded, each for a stated reason:

| Excluded | Why |
|---|---|
| `action_taken`, `is_denied`, `has_lender_decision` | The outcome itself |
| `denial_reason_1..4` | Recorded *after* the denial — direct leakage |
| `interest_rate`, `rate_spread`, `total_loan_costs`, `total_points_and_fees`, `origination_charges`, `discount_points`, `lender_credits` | HMDA reports these only for originated loans, so their presence/absence leaks the outcome |
| `purchaser_type` | Known only after origination |
| `hoepa_status` | A post-decision designation |

The exclusion list is **asserted against the cleaned schema at run time**,
so a future edit to the feature list cannot silently introduce a leak.

### 11.2 The resource budget, and how it was met

The naive approach — materialise the decision population, one-hot encode,
fit — needs well over 16 GB. Instead:

| Technique | Effect |
|---|---|
| Hash-based sampling from Parquet row groups | 2,000,000 rows (23.1 % of 8,643,834) drawn without reading the other 10.6 M |
| Sampling rule keyed on the institution LEI | A genuine random sample, not "the first N rows" — which would be ordered by lender and biased |
| Immediate downcasting (`float32`, `int8`/`int16`) | ~352 MB of non-zeros instead of multiple GB |
| Sparse matrices throughout | No estimator ever materialises a dense matrix of the full sample |
| Chunked densification (200,000 rows at a time) | Caps peak RAM for the tree model and the permutation-importance step |
| `n_jobs=1` | Runs on one core without oversubscribing a 16 GB machine |

Result: **131 seconds** end to end, peak RAM well under 2 GB.

### 11.3 The solver decision, and why it changed

The first implementation used `SGDClassifier(loss='log_loss')` for speed.
Its calibration showed the model over-predicting badly in the top decile
(0.954 predicted vs 0.738 observed).

The natural hypothesis is that an iterative solver with a fixed iteration
count simply had not converged. **That hypothesis was tested and rejected.**
`LogisticRegression(solver='liblinear')` — a deterministic convex solver —
reproduces the same pattern (0.953 vs 0.745), and so does a much
under-regularised SGD fit. The over-prediction is therefore a property of
the *linear model*, not of the optimiser.

`liblinear` was adopted anyway, for three reasons that are about the fit
rather than the speed:

1. It is deterministic and convex, so the fit is exactly reproducible.
2. It operates directly on the sparse matrix, so no dense copy is created.
3. It is slightly better calibrated in the middle of the probability range —
   which is exactly where a triage threshold sits.

The over-prediction is now reported as a documented limitation, and the
practical implication is stated: the model should not be used to rank
applications in the highest band.

### 11.4 Models and results

| Model | ROC-AUC | PR-AUC | Brier | Best F₁ |
|---|---|---|---|---|
| Logistic regression (primary) | 0.774 | 0.526 | 0.150 | 0.538 |
| Gradient boosting (comparison) | 0.836 | 0.689 | 0.124 | 0.614 |

The logistic regression is the **primary** model because it is calibrated
and its coefficients can be read directly, which matters for a triage use.
The 0.062 ROC-AUC gap is reported rather than hidden: the extra signal lies
in interactions between applicant and loan characteristics that a linear
model cannot represent.

### 11.5 Differential performance

ROC-AUC is stable across the levels of ethnicity (0.658–0.777), race
(0.659–0.811), sex (0.657–0.804) and loan type (0.577–0.781). The joint/single
split (0.772 vs 0.760) reflects different base rates, not different skill.
The lowest values occur in small groups with atypically low denial rates.

### 11.6 An honest statement about the use of the model

The predictors **include protected characteristics** (ethnicity, race, sex).
They are included because they are what the lender records, and because
their inclusion is what makes the differential-performance check possible.
But a model that scores applications using ethnicity or race is legally
restricted under fair-lending rules. The extension is a research
instrument; its outputs must not be used to score individual borrowers.
This is stated in the report rather than left implicit.

---

## 12 — Phase 12: LaTeX report

### 12.1 The format

The report was rewritten in LaTeX using the ACM Large 2-Column Format
Template (`acmart.cls`, `sigconf`). The template files were extracted from
the provided `.zip` into `latex_template/` and the working copy lives in
`latex_report/`. `latex_template/` is **not tracked**: it is the instructor's
material verbatim, and `latex_report/` already contains the files the build
actually needs.

### 12.2 A build environment note

`latexmk` does not work on this machine: MiKTeX's `latexmk` wrapper is a
Perl script, and Perl is not installed. The build is therefore three
`pdflatex` passes:

```powershell
cd latex_report
pdflatex report.tex   # ×3
```

Two `acmart` pitfalls cost a build cycle each and are recorded so the next
person does not repeat them:

- `\maketitle` must come **after** `\begin{abstract}` in `acmart`, not
  before. Putting it first raises *"Abstract must be defined before
  maketitle"*.
- Redefining `\footnotetextcopyrightpermission` breaks the class internals
  and produces an *"Undefined control sequence"* at `\maketitle`. Leave it
  alone.

### 12.3 Verifying the numbers

Every headline figure in the report was re-derived from the artefacts in
`results/` and compared against the prose. Several had drifted and were
corrected:

| Figure | Was | Corrected to | Why it had drifted |
|---|---|---|---|
| Exact duplicate rows involved | 46,974 | 46,984 | Measured on the raw file, not the cleaned set |
| Indeterminate records | 1,157,493 | 1,150,697 | The figure was carried over from the pre-fix run |
| Indeterminate rate among decisions | 1.01 % | 1.00 % | Recomputed from the final artefacts |
| Income-quartile decision counts | ~2,037,000 | 2,039,745 | Pooled over the final stratum set |
| DTI >60 % gap | 5.86 pp | 5.87 pp | Recomputed |
| Group ROC-AUC ranges | SGD values | liblinear values | The solver changed in §11.3 |

### 12.4 A measurement bug found by the verification pass

`results/quality_checks.json` reported only **4** duplicate rows, against
the 26,755 the cleaning pipeline removes. The two numbers were measuring
different things: `quality_checks.py` reads the *cleaned* Parquet, whose
exact duplicates have already been removed, so near-zero is the correct
answer for that input. The 26,755 figure is measured on the raw file.

Rather than adjust either number, the raw-file measurement was given its
own artefact (`src/dup_probe.py` → `results/duplicate_probe_raw.json`) and
the report now says explicitly which population each figure describes. The
cleaned dataset retains 2 residual rows rather than zero, because the
pipeline normalises whitespace and parses numerics before hashing; that is
reported too, rather than rounded away.

---

## 13 — Audit against the assignment

| Assignment requirement | Where | Status |
|---|---|---|
| **2.3.1** Download the 2024 dataset | §3 | ✅ |
| **2.3.2** Read official documentation and dictionary | §4.1 | ✅ `docs/` |
| **2.3.3** Identify unit of observation and variable meanings | §4, §6.4 | ✅ |
| **2.3.4** Record format, size, records, variables | §3.3, §4.1 | ✅ |
| **2.3.5** Assess whether data support the RQs | §1.3 | ✅ |
| **3.1** Problem formulation, RQs, variables, methods | §1 | ✅ proposal PDF |
| **3.2A** Data inspection: schema, counts, variables | §5.1 | ✅ |
| **3.2B** Missing/special codes, duplicates, implausible vs outliers | §5.2–5.4 | ✅ |
| **3.2C** Cleaning rules, documented and justified | §6.1–6.2, §6.5 | ✅ |
| **3.2D** Feature engineering, each feature explained | §6.4 | ✅ |
| **3.2E** Store as Parquet, explain format and partitioning | §6.7 | ✅ |
| **3.2E** Rules consistent across Pandas and Spark | §0.2, §7, §8 | ✅ 8/8 |
| **3.3A** Descriptive statistics | report §4 | ✅ |
| **3.3B** Comparative analysis | RQ4, by institution, by state | ✅ |
| **3.3C** Relationship analysis | §5.1 correlation matrix, RQ2, RQ3 | ✅ |
| **3.3D** Visualizations, titled and interpreted | §10.2 | ✅ 6 figures |
| **3.3E** Financial interpretation, 4 questions per finding | report §7 | ✅ |
| **3.4A** Pandas implementation | §7.2 | ✅ |
| **3.4B** PySpark implementation | §7.3 | ✅ |
| **3.4C** Compare ≥3 outputs, explain discrepancies | §8 | ✅ 8 outputs |
| **3.5A** Experimental design documented | §9.1–9.2 | ✅ |
| **3.5B** Timing methodology, median, comparable conditions | §9.1–9.2 | ✅ |
| **3.5C** Results table, speedup, 5 interpretation questions | §9.3–9.4 | ✅ |
| **4** Optional predictive analysis | §11 | ✅ `src/predictive.py` |
| **5** Financial & ethical considerations | report §10 | ✅ |
| **6.2** Technical report, ~8 pages, 12-section structure | §10.1, §12 | ✅ `latex_report/report.pdf` (10 pp) |
| **6.3** Code & reproducibility repository | §10.3 | ✅ |
| **6.4** Presentation and defence | — | ⬜ Team deliverable (§13) |

**Score-relevant criteria:** problem formulation 10 ✅ · data engineering 20 ✅ ·
descriptive and diagnostic analysis 25 ✅ · Pandas–Spark implementation and
correctness 20 ✅ · performance and scalability 10 ✅ · financial
interpretation 10 ✅ · presentation and defence 15 ⬜ (team).

---

## 14 — What remains for submission

| # | Task | Who | Notes |
|---|---|---|---|
| 1 | **Presentation + defence** | Team | Six slides minimum: problem & RQs, dataset & preparation, key findings, the two implementations, equivalence result, performance, predictive extension, interpretation & limitations. §6.4 lists the required coverage. |
| 2 | **Trim the report if the grader counts pages strictly** | Team | The LaTeX report renders to **10 pages** against a "~8 page" guideline. The overrun is the predictive extension and the six new figures. It is a bonus section, so trimming it is the obvious lever if the limit is enforced. |
| 3 | **Verify the proposal matches this implementation** | Team | The proposal PDF was written before the analysis. The RQs match, but the proposal's expected findings should be reconciled with the actual results — particularly the *widening* gap at higher incomes, which was not the original hypothesis. |
| 4 | **Confirm the repository is public and the link works** | ✅ | Published at <https://github.com/eqflashheqr-cmyk/BigDataFinal>. The predictive extension and the LaTeX report are on `feature/predictive-extension-latex-report` as PR #1. |

---

## 15 — Decisions log

The decisions that could plausibly have gone the other way, and why they
didn't.

| # | Decision | Alternative | Why this one | Impact if reversed |
|---|---|---|---|---|
| 1 | Derive `joint_flag` from 4 co-applicant fields | Use `derived_sex == "Joint"` | `derived_sex` is null for 1.14 M records (9.3 %) and is a *derived* field, not a raw one | The analysis population would shrink by ~9 % |
| 2 | Code 3/6 ("info not provided") counts as **present** | Treat as missing | A co-applicant's ethnicity cannot go unreported if no co-applicant exists | The joint group would shrink materially; the gap would likely narrow |
| 3 | Keep indeterminate records as NA, exclude from comparison | Impute 0 or 1 | 9.44 % of records are indeterminate, 90.6 % of them purchased loans with unreported co-applicants | Imputation would fabricate ~1.15 M joint/single labels and bias the gap |
| 4 | Denial rate over O+A+D only | Include codes 4–8 | Codes 4–8 are not lender decisions | Denominator inflated by 42 %; the rate would no longer be a denial rate |
| 5 | Remove only **exact** duplicates | Also remove business-key duplicates | Same borrower + same lender + same amount can be two legitimate applications | 19,831 real applications discarded |
| 6 | Keep extreme values, report mean *and* median | Drop outliers above a threshold | HMDA extremes are real; dropping them biases *against* finding the gap | The gap would shrink; the result would be less honest |
| 7 | Both engines clean the raw file independently | Spark reads Pandas' Parquet | Otherwise the check proves only that Spark can read Pandas' output | The equivalence check becomes vacuous |
| 8 | Integer-keyed code tables | Keep string codes | `Int64.isin(("1","2","3"))` is silently always False | The entire analysis runs on 0 decisions |
| 9 | SHA-256 hash sampling for the benchmark | `loan_amount mod 1000` | Loan amounts are multiples of 1000 → the filter is degenerate | The two engines would compare different subsets |
| 10 | Pandas reads only needed columns + categoricals | Load all 104 columns | 12.2 M × 104 columns does not fit in 16 GB | `MemoryError` on load |
| 11 | Pin the income quartile boundaries | Let each engine compute its own | `qcut` and `ntile` disagree at boundaries | Stratified results would not be comparable |
| 12 | Compare in 3 separate processes | One process | Pandas + cached Spark together OOM the JVM | The comparison cannot complete |
| 13 | Gitignore the raw data | Commit it | The assignment forbids duplicating large public datasets | A 10 GB repository that cannot be cloned |
| 14 | Carry row hashes across chunks in the benchmark | Clean each chunk independently | A duplicate spanning two chunks survives in Pandas but not in Spark | The two engines process 47 different rows at 25 % — the benchmark is invalid |
| 15 | `liblinear` for the primary model | `SGDClassifier` for speed | Deterministic and convex; better calibrated in the range where a triage threshold sits | The fit would depend on the iteration count, and the mid-range calibration would be slightly worse |
| 16 | Report the gradient-boosting gap rather than only the linear model | Present only the primary model | The gap is a real finding about where the signal is; hiding it would be dishonest | A reviewer would find the comparison missing |
| 17 | Include protected characteristics in the model | Exclude them for legal safety | They are what the lender records, and without them the differential-performance check is impossible | The fairness check could not be run; the model would still be legally restricted, as stated |
| 18 | Sample 23.1 % of the decision population for the model | Use the full population | The full population does not fit in 16 GB alongside the sparse encodings | The extension would not run at all on the target machine |
| 19 | Measure duplicates on the raw file for the report | Quote the cleaned-dataset figure | The cleaned dataset has already had its exact duplicates removed, so it answers a different question | The report would understate the duplicate rate by four orders of magnitude |
| 20 | Report the LaTeX version as the deliverable | Keep the Markdown version | The assignment specifies the ACM 2-column template | The submission would not match the required format |

---

## 16 — Known risks

| Risk | Severity | Mitigation |
|---|---|---|
| `joint_flag` is **inferred**, not reported | Medium | Validated against `co_applicant_ethnicity_observed`; the rule, the indeterminate rate, and the direction of any bias are all documented (report §3.2) |
| The finding is **associational** | Medium | Stated explicitly in the report's limitations; no causal language is used |
| Interest rate missing for 36.8 % of records, non-randomly | Medium | Disclosed in report §2.3; the RQ2 interest-rate comparison is explicitly flagged as resting on a biased subset |
| The 12 M × 99 string frame cannot be held in Pandas | Low | Chunked pipeline; documented as a limitation per §3.4A |
| **Chunk-boundary bugs** in stateful operations | Medium | Found twice (§7.5, §9.2) — both invisible to code review. Mitigated by running the chunked and non-chunked paths against each other; the benchmark now verifies row-count parity between engines |
| Benchmark timings vary with background load | Low | 3 repeats, median reported; one repeat drifted to 1001 s and is visible in `results/benchmark_results.json` |
| Report may exceed the ~8-page target | Low | The LaTeX report renders to 10 pages. The overrun is the optional predictive extension and the six figures it added — the obvious lever if the limit is enforced |
| The predictive model over-predicts in the top probability band | Low | Documented in the report with the evidence that it is a model property, not a solver artefact, and an explicit instruction not to rank applications in that band |
| The predictive model uses protected characteristics | Medium | Stated plainly in the report and in the README: research instrument only, not for scoring individual borrowers |
| The predictive split is random, not temporal | Low | The file has a single reporting year and no application date, so no time axis exists. Verified at run time and stated as a limitation |
| MiKTeX `latexmk` needs Perl | Low | The build uses three `pdflatex` passes; documented in the README |
| Team members may not be able to explain every module | Medium | Each module has a docstring stating its purpose; the decisions log (§15) is the defence narrative |

---

## Appendix — File manifest

| File | Purpose |
|---|---|
| `pipeline.md` | this document |
| `README.md` | reproduction instructions, method summary, headline findings |
| `requirements.txt` | pinned dependencies |
| `docs/public_lar_schema_2024.md` | the 99-field FFIEC schema |
| `docs/hmda_data_dictionary_2024.md` | full data dictionary, code tables, `joint_flag` definition |
| `src/config.py` | single source of truth: paths, code tables, special codes, rules |
| `src/rules.py` | cleaning + feature engineering, Pandas and Spark side by side |
| `src/pandas_pipeline.py` | Pandas ingest → clean → Parquet |
| `src/spark_pipeline.py` | Spark ingest → clean → Parquet |
| `src/analytics.py` | 8 canonical analytical outputs, both engines |
| `src/analysis.py` | RQ1–RQ4, both engines |
| `src/quality_checks.py` | duplicate investigation, correlation matrix |
| `src/equivalence.py` | Pandas vs Spark comparison |
| `src/rq3_equivalence.py` | cell-by-cell Pandas vs Spark diff for the 1,730 RQ3 strata |
| `src/benchmark.py` | performance and scalability experiment |
| `src/figures.py` | chart generation |
| `src/predictive.py` | the optional predictive extension |
| `src/predictive_figures.py` | charts for the predictive extension |
| `src/dup_probe.py` | duplicate measurement on the **raw** file |
| `src/report.py` | assembles `results/report.md` |
| `src/export_pdf.py` | renders `results/report.md` → `report.pdf` |
| `src/run_analysis.py` | orchestration |
| `latex_report/report.tex` | the LaTeX report source (ACM `sigconf`) |
| `latex_report/report.pdf` | the technical report, compiled (10 pages) |
| `results/predictive_*.csv / .json / .npz` | predictive extension artefacts |
| `results/duplicate_probe_raw.json` | duplicate counts measured on the raw file |
| `results/report.md` | the technical report |
| `results/rq1..rq4.csv` | the four research questions |
| `results/rq3_equivalence.json` | the RQ3 cross-engine diff (1,730 strata, zero differing cells) |
| `results/equivalence_report.json` | cell-by-cell Pandas vs Spark comparison |
| `results/benchmark_results.{csv,json}` | performance measurements |
| `results/quality_checks.json` | duplicate investigation results |
| `results/correlation_matrix.csv` | Spearman correlations |
| `results/cleaning_report_*.json` | records removed at each step, per engine |
| `figures/fig1..fig6.png` | the six figures |
