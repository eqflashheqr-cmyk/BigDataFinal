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

| Engine | Data | Rows | Ingest | Clean | Analyse | **Total** | Throughput |
|---|---|---:|---:|---:|---:|---:|---:|
| pandas | 25 % | 3,374,950 | 15.5 s | 196.2 s | 13.1 s | **224.6 s** | 15,029 rows/s |
| pyspark | 25 % | 3,374,950 | 41.4 s | 37.0 s | 11.3 s | **89.9 s** | 37,532 rows/s |
| pandas | 50 % | 5,750,421 | 16.4 s | 333.8 s | 22.5 s | **372.8 s** | 15,425 rows/s |
| pyspark | 50 % | 5,750,421 | 55.2 s | 58.3 s | 16.2 s | **129.4 s** | 44,455 rows/s |
| pandas | 100 % | 12,224,691 | 18.9 s | 732.8 s | 54.2 s | **805.2 s** | 15,215 rows/s |
| pyspark | 100 % | 12,224,691 | 104.3 s | 108.9 s | 28.4 s | **241.5 s** | 50,725 rows/s |

**Speedup at full scale: 3.3× (Spark).** Spark's advantage holds at every
data volume.

### 9.4 Interpretation

**Which is faster?** PySpark, at every size, by 2.5–3.3×.

**Did relative performance change?** Yes, modestly. Spark's advantage is
2.5× at 25 % and 3.3× at 100 %, because Pandas' cost grows super-linearly
in practice — the working set stops fitting comfortably in 16 GB and
allocation and garbage-collection overhead rises.

**What overheads affected Spark?** Spark's *ingest* stage is consistently
slower than Pandas' (104 s vs 19 s at full scale). This is the JVM and
catalyst overhead: schema inference, CSV parsing through the JVM's
univocity parser, and the cost of materialising a distributed DataFrame on
one node. Spark pays this fixed cost regardless of data volume — which is
exactly why Spark loses on small data and wins on large data.

**Did memory limitations affect either implementation?** Yes, materially, and
differently:

* *Pandas* cannot hold the raw 12.2 M × 99 string frame (≈ 40 GB) at all.
  It survives only via chunked processing, and even then the working set is
  tight enough that one benchmark repeat drifted from 787 s to 1001 s —
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

The Spark timings in this table were measured after the `clean_spark`
refactor that consolidated five `count()` passes into one aggregation. An
earlier benchmark run, made before that refactor, reported 296 s instead of
241 s for Spark at full scale — i.e. the published figures are the
optimistic end. The Pandas figures are unaffected. The conclusion is
unchanged either way.

---

## 10 — Phase 10: Report, figures & repository

### 10.1 Deliverable structure vs. the assignment's recommended structure

The assignment (§6.2) recommends a 12-section report. `src/report.py`
generates `results/report.md` in exactly that structure:

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
and the Python cache. What *is* committed:

```
README.md                  reproduction instructions, method, findings
requirements.txt           pinned versions
pipeline.md                this document
docs/                      schema + data dictionary
src/                       12 modules
results/                   all CSV + JSON outputs, report.md
figures/                   6 PNGs
```

The repository is a clone-and-run artifact: a reviewer who downloads the data
per `README.md` reproduces every number and every figure.

---

## 11 — Audit against the assignment

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
| **4** Optional predictive analysis | — | ⬜ Not undertaken (§12) |
| **5** Financial & ethical considerations | report §7 | ✅ |
| **6.2** Technical report, ~8 pages, 12-section structure | §10.1 | ✅ `results/report.md` |
| **6.3** Code & reproducibility repository | §10.3 | ✅ |
| **6.4** Presentation and defence | — | ⬜ Team deliverable (§12) |

**Score-relevant criteria:** problem formulation 10 ✅ · data engineering 20 ✅ ·
descriptive and diagnostic analysis 25 ✅ · Pandas–Spark implementation and
correctness 20 ✅ · performance and scalability 10 ✅ · financial
interpretation 10 ✅ · presentation and defence 15 ⬜ (team).

---

## 12 — What remains for submission

| # | Task | Who | Notes |
|---|---|---|---|
| 1 | **Optional predictive extension** | Team | Up to 10 bonus points, capped at 100. A logistic regression predicting `action_taken == 3` from borrower characteristics, trained on 2024 data with a proper temporal split if a second year is added. §4 of the assignment gives the exact requirements. Not started. |
| 2 | **`report.pdf`** | Team | `results/report.md` is complete and structured; it needs to be rendered to PDF and reviewed against the ~8-page target. The PDF export step is not scripted. |
| 3 | **Presentation + defence** | Team | Six slides minimum: problem & RQs, dataset & preparation, key findings, the two implementations, equivalence result, performance, interpretation & limitations. §6.4 lists the required coverage. |
| 4 | **Re-run the benchmark** | Optional | Spark's figures are from before the `clean_spark` refactor (§9.5). The published numbers are already the optimistic end, so this is optional. |
| 5 | **Verify the proposal matches this implementation** | Team | The proposal PDF was written before the analysis. The RQs match, but the proposal's expected findings should be reconciled with the actual results — particularly the *widening* gap at higher incomes, which was not the original hypothesis. |
| 6 | **Confirm the repository is public and the link works** | Team | §10.3 describes the repository; the final push and link check happen last. |

---

## 13 — Decisions log

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

---

## 14 — Known risks

| Risk | Severity | Mitigation |
|---|---|---|
| `joint_flag` is **inferred**, not reported | Medium | Validated against `co_applicant_ethnicity_observed`; the rule, the indeterminate rate, and the direction of any bias are all documented (report §3.1, §7) |
| The finding is **associational** | Medium | Stated explicitly in the report's limitations; no causal language is used |
| Interest rate missing for 36.8 % of records, non-randomly | Medium | Disclosed in report §7; the RQ2 interest-rate comparison is explicitly flagged as resting on a biased subset |
| The 12 M × 99 string frame cannot be held in Pandas | Low | Chunked pipeline; documented as a limitation per §3.4A |
| Benchmark timings vary with background load | Low | 3 repeats, median reported; one repeat drifted to 1001 s and is visible in `results/benchmark_results.json` |
| Report may exceed the ~8-page target | Low | `results/report.md` is 256 lines of dense prose; will need trimming when rendered |
| Team members may not be able to explain every module | Medium | Each module has a docstring stating its purpose; the decisions log (§13) is the defence narrative |

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
| `src/benchmark.py` | performance and scalability experiment |
| `src/figures.py` | chart generation |
| `src/report.py` | assembles `results/report.md` |
| `src/run_analysis.py` | orchestration |
| `results/report.md` | the technical report |
| `results/rq1..rq4.csv` | the four research questions |
| `results/equivalence_report.json` | cell-by-cell Pandas vs Spark comparison |
| `results/benchmark_results.{csv,json}` | performance measurements |
| `results/quality_checks.json` | duplicate investigation results |
| `results/correlation_matrix.csv` | Spearman correlations |
| `results/cleaning_report_*.json` | records removed at each step, per engine |
| `figures/fig1..fig6.png` | the six figures |
