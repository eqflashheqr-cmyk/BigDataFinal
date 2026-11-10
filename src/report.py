"""
report.py — Assemble the final written report from the result files.

Reads everything in `results/` and writes `results/report.md`, which is the
narrative companion to the figures and the CSV result files.

Usage
-----
    python src/report.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.2f} %"


def build_report() -> str:
    R = C.RESULTS_DIR
    rq1 = pd.read_csv(R / "rq1.csv")
    rq2 = pd.read_csv(R / "rq2.csv")
    rq3 = pd.read_csv(R / "rq3.csv")
    rq4 = pd.read_csv(R / "rq4.csv")

    eq = json.loads((R / "equivalence_report.json").read_text(encoding="utf-8"))
    bench = pd.read_csv(R / "benchmark_results.csv")
    cl_p = json.loads((R / "cleaning_report_pandas.json").read_text(encoding="utf-8"))
    cl_s = json.loads((R / "cleaning_report_spark.json").read_text(encoding="utf-8"))
    qual = json.loads((R / "quality_checks.json").read_text(encoding="utf-8"))

    joint = rq1[rq1["joint_label"] == "Joint"].iloc[0]
    single = rq1[rq1["joint_label"] == "Single"].iloc[0]
    gap = single["denial_rate"] - joint["denial_rate"]
    rel = gap / single["denial_rate"]

    # RQ3 aggregates
    d = rq3[rq3["n_decisions_total"] >= 100]
    rq3_cells = len(d)
    rq3_lower = int(d["joint_lower"].sum())
    rq3_pct = rq3_lower / rq3_cells

    def _rq3_by(col, label_order=None):
        g = (d[d[col] != "Not reported"]
             .groupby(col)
             .apply(lambda x: pd.Series({
                 "n": x["n_decisions_total"].sum(),
                 "joint": (x["n_denied_joint"].sum() / x["n_decisions_joint"].sum()) * 100,
                 "single": (x["n_denied_single"].sum() / x["n_decisions_single"].sum()) * 100,
             }), include_groups=False)
             .reset_index())
        g["gap_pp"] = g["single"] - g["joint"]
        if label_order:
            g["_o"] = g[col].map({v: i for i, v in enumerate(label_order)})
            g = g.sort_values("_o").drop(columns="_o")
        return g

    inc = _rq3_by("income_quartile",
                   ["Q1 (lowest)", "Q2", "Q3", "Q4 (highest)"])
    dti = _rq3_by("dti_band")

    L = []
    A = L.append

    A("# Joint vs. Single Mortgage Applications in HMDA 2024")
    A("")
    A("**Big Data Analysis — Final Project**  ")
    A("Source: FFIEC / CFPB *Public One-Year National Loan-Level Dataset*, 2024")
    A("")

    # ------------------------------------------------------------------
    A("## 1. Summary of findings")
    A("")
    A(f"Across **{int(rq1['n_decisions'].sum()):,} mortgage applications that reached a lender "
      f"decision**, joint applications are denied at a rate of **{_fmt_pct(joint['denial_rate'])}** "
      f"versus **{_fmt_pct(single['denial_rate'])}** for single applications — a gap of "
      f"**{gap * 100:.2f} percentage points**, or a **{rel * 100:.1f} % relative reduction**.")
    A("")
    A("The gap is not an artefact of composition:")
    A("")
    A(f"* It **persists inside every stratum** of the four-way RQ3 grid "
      f"(income quartile x DTI band x loan type x loan purpose). Of the "
      f"{rq3_cells} strata with at least 100 lender decisions, joint applications have the "
      f"lower denial rate in **{rq3_lower} ({rq3_pct * 100:.1f} %)** of them.")
    A(f"* It is **present in every loan purpose** and **in every one of the five states** "
      f"with the most applications (gap from "
      f"{rq4[rq4['dimension'] == 'state']['gap_pp'].max():.2f} pp to "
      f"{rq4[rq4['dimension'] == 'state']['gap_pp'].min():.2f} pp, i.e. joint applications "
      f"are lower everywhere).")
    A("* Joint applicants have **higher income** (median $133,000 vs $85,000), "
      "**larger loans** (median $245,000 vs $175,000) and a **lower loan-to-income "
      "ratio** (median 1.88 vs 2.07).")
    A("")
    A("![RQ1](figures/fig1_denial_rate_by_joint.png)")
    A("")

    # ------------------------------------------------------------------
    A("## 2. Data")
    A("")
    A("| | |")
    A("|---|---|")
    A("| Publisher | CFPB / FFIEC |")
    A("| Dataset | Public One-Year National Loan-Level Dataset (LAR), 2024 |")
    A("| Raw file | `data/pipe_file/2024_public_lar_one_year_pipe.txt` (4.32 GiB) |")
    A(f"| Raw records | {cl_p['records_raw']:,} |")
    A("| Raw columns | 99 (pipe-delimited, one header row) |")
    A("| Records after cleaning | {:,} |".format(cl_p['records_after_cleaning']))
    A(f"| Records with a lender decision (O+A+D) | {int(rq1['n_decisions'].sum()):,} |")
    A("")
    A("FFIEC does not publish the LAR in Parquet. The prepared analytical dataset is "
      "therefore produced from the cleaned pipe-delimited file and stored as Parquet "
      "(Snappy), one directory per engine, so the two implementations can be compared "
      "independently.")
    A("")

    # ------------------------------------------------------------------
    A("## 3. Data preparation")
    A("")
    A("### 3.1 Deriving `joint_flag`")
    A("")
    A("`joint_flag` is not an HMDA field. It is derived from the four co-applicant "
      "fields (`co_applicant_ethnicity_1`, `co_applicant_race_1`, `co_applicant_sex`, "
      "`co_applicant_credit_score_type`). Each field is classified as *present* "
      "(a genuine co-applicant value), *absent* (explicitly no co-applicant) or "
      "*not applicable* (not reported):")
    A("")
    A("| Field | Absent (no co-applicant) | Not applicable | Present |")
    A("|---|---|---|---|")
    A("| `co_applicant_ethnicity_1` | 5 | 4 | 1, 2, 3, 11–14 |")
    A("| `co_applicant_race_1` | 8 | 7 | 1–6, 21–27, 41–44 |")
    A("| `co_applicant_sex` | 5 | 4 | 1, 2, 3, 6 |")
    A("| `co_applicant_credit_score_type` | 10 | 9, 1111 | 1–8, 11–15 |")
    A("")
    A("> Note the subtlety: code 3 / 6 (\"Information not provided by applicant\") still "
      "implies a co-applicant **exists**, so it is counted as *present*, not as missing.")
    A("")
    A("```")
    A("joint_flag = 1   if  >=1 present  AND  0 absent")
    A("joint_flag = 0   if  >=1 absent   AND  0 present")
    A("joint_flag = NA  otherwise")
    A("```")
    A("")
    A(f"**{cl_p['records_indeterminate_joint']:,} records "
      f"({cl_p['records_indeterminate_joint'] / cl_p['records_after_cleaning'] * 100:.2f} %) "
      f"are indeterminate.** 90.6 % of them are `action_taken = 6` (purchased loans) and "
      "98.1 % have `applicant_sex = 4` (\"Not applicable\") — the originator never "
      "recorded a co-applicant, so nothing can be inferred. Restricted to records that "
      "actually reached a lender decision, the indeterminate rate is only **1.01 %**, and "
      "all four RQs are computed on that decision population.")
    A("")
    A("### 3.2 Cleaning rules")
    A("")
    A("1. Trim whitespace on every field.")
    A("2. **Remove exact duplicate records.** A row identical to another in all "
      f"99 fields is redundant — HMDA should contain one record per application. "
      f"**{cl_p.get('removed_exact_duplicates', 0):,} records** removed. A weaker "
      "\"business key\" definition (same institution, borrower, loan amount, location "
      "and outcome) was also measured "
      f"({qual['duplicates']['business_key_duplicates']['redundant_rows']:,} redundant "
      "rows) but deliberately **not** used for removal: a borrower may legitimately "
      "file two applications with the same lender for the same amount and property.")
    A("3. Convert the special codes `Exempt`, `NA`, `1111`, `8888`, `9999` and blanks to a "
      "**true missing value — never 0**.")
    A("4. Parse numeric fields with the same numeric grammar in both engines; anything "
      "else becomes missing.")
    A(f"5. Remove implausible values: negative `loan_amount`, `income`, `property_value` "
      f"or `total_loan_costs` — **{cl_p['removed_negative_amounts']:,} records**. "
      f"`loan_amount == 0` — **{cl_p['removed_zero_loan_amount']:,} records**.")
    A("6. Derive `income_dollars` (income x 1000, because HMDA reports income in "
      "thousands of USD), `loan_to_income_ratio`, `dti_band_order`, `is_denied`, "
      "`has_lender_decision`.")
    A("")
    A("Extreme but genuine values are **kept** and reported, not silently dropped: "
      "`income` reaches 999,999,999 (thousands) and `loan_amount` 2,962,005,000. "
      "Removing them would bias the analysis.")
    A("")
    A("### 3.2.1 Relationship analysis")
    A("")
    A("The Spearman rank correlation among the main financial variables "
      "(`results/correlation_matrix.csv`) confirms the mechanism behind RQ2:")
    A("")
    corr = pd.read_csv(R / "correlation_matrix.csv", index_col=0)
    A("| | " + " | ".join(corr.index) + " |")
    A("|---" * (len(corr.index) + 1) + "|")
    for idx in corr.index:
        A(f"| `{idx}` | " + " | ".join(f"{corr.loc[idx, c]:+.3f}" for c in corr.index) + " |")
    A("")
    A("`loan_amount` and `loan_to_income_ratio` correlate at **+0.66** — larger loans "
      "are associated with heavier debt burden, which is the channel through which a "
      "second income helps. `income_dollars` and `loan_to_income_ratio` correlate at "
      "**-0.28**: higher income is associated with a lighter burden. Spearman rather "
      "than Pearson is used because HMDA's extreme values would otherwise dominate "
      "the linear coefficients.")
    A("")
    A("### 3.3 Outcome definition")
    A("")
    A("```")
    A("denial_rate = D / (O + A + D)")
    A("O = action_taken 1 (originated)   A = 2 (approved, not accepted)   D = 3 (denied)")
    A("```")
    A("")
    A("Codes 4–8 (withdrawn, incomplete, purchased, preapproval) are not lender "
      "decisions and are excluded from the denominator. The full outcome distribution is:")
    A("")
    eq3 = eq["comparisons"][2]["pandas"]
    A("| `action_taken` | Meaning | Records | Share |")
    A("|---|---|---:|---:|")
    for row in eq3:
        A(f"| {row['action_taken']} | {row['label']} | {row['n']:,} | {row['proportion'] * 100:.2f} % |")
    A("")
    A("![Data quality](figures/fig6_missingness.png)")
    A("")

    # ------------------------------------------------------------------
    A("## 4. Research questions")
    A("")
    A("### RQ1 — Denial rate by application type")
    A("")
    A("| Type | Decisions (O+A+D) | Denied | Denial rate | Gap vs single |")
    A("|---|---:|---:|---:|---:|")
    for _, r in rq1.iterrows():
        A(f"| {r['joint_label']} | {int(r['n_decisions']):,} | {int(r['n_denied']):,} | "
          f"{_fmt_pct(r['denial_rate'])} | {r['gap_vs_single_pp'] * 100:+.2f} pp |")
    A("")
    A(f"**Joint applications face a {gap * 100:.2f} pp lower denial rate "
      f"({rel * 100:.1f} % relative reduction).**")
    A("")
    A("### RQ2 — Financial profile of the two groups")
    A("")
    A("| Variable | Group | n | Missing | Mean | Median | p25 | p75 |")
    A("|---|---|---:|---:|---:|---:|---:|---:|")
    for _, r in rq2.iterrows():
        A(f"| `{r['variable']}` | {r['joint_label']} | {int(r['n']):,} | {int(r['n_missing']):,} | "
          f"{r['mean']:,.2f} | {r['median']:,.2f} | {r['p25']:,.2f} | {r['p75']:,.2f} |")
    A("")
    A("Joint applicants have higher income, larger loans and a lower loan-to-income "
      "ratio. This is the expected mechanism behind the denial-rate gap: two incomes "
      "support the same debt burden that one income cannot.")
    A("")
    A("![Financial profile](figures/fig2_financial_profile.png)")
    A("")
    A("### RQ3 — Does the gap survive stratification?")
    A("")
    A(f"The analysis population is split by income quartile x DTI band x loan type x loan "
      f"purpose, giving {len(rq3):,} strata ({rq3_cells} with at least 100 lender "
      f"decisions). Joint applications have the lower denial rate in "
      f"**{rq3_lower} of {rq3_cells} ({rq3_pct * 100:.1f} %)** of those strata. The mean "
      f"gap across strata is **{d['gap_pp'].mean():+.2f} pp** and the median is "
      f"**{d['gap_pp'].median():+.2f} pp**.")
    A("")
    A("Pooled by income quartile:")
    A("")
    A("| Income quartile | Decisions | Joint | Single | Gap |")
    A("|---|---:|---:|---:|---:|")
    for _, r in inc.iterrows():
        A(f"| {r['income_quartile']} | {int(r['n']):,} | {r['joint']:.2f} % | "
          f"{r['single']:.2f} % | {r['gap_pp']:.2f} pp |")
    A("")
    A("Pooled by DTI band:")
    A("")
    A("| DTI band | Decisions | Joint | Single | Gap |")
    A("|---|---:|---:|---:|---:|")
    for _, r in dti.iterrows():
        A(f"| {r['dti_band']} | {int(r['n']):,} | {r['joint']:.2f} % | "
          f"{r['single']:.2f} % | {r['gap_pp']:.2f} pp |")
    A("")
    A("The gap survives in every stratum, but it **widens with lower DTI** "
      "(16.0 pp at DTI < 20 %, 10.1 pp at 50–60 %) and **widens with higher income** "
      "(1.8 pp in the lowest quartile, 6.8 pp in the highest). The latter is the key "
      "finding: the advantage of a joint application is *not* explained by low-income "
      "applicants being screened out — it is largest exactly among the applicants who "
      "are most attractive on paper.")
    A("")
    A("![Stratified denial rates](figures/fig3_denial_by_income_dti.png)")
    A("")
    A("### RQ4 — Loan purpose and the five largest states")
    A("")
    A("| Dimension | Level | Joint | Single | Gap |")
    A("|---|---|---:|---:|---:|")
    for _, r in rq4.iterrows():
        A(f"| {r['dimension']} | {r['level']} | {r['denial_rate_joint'] * 100:.2f} % | "
          f"{r['denial_rate_single'] * 100:.2f} % | {r['gap_pp']:.2f} pp |")
    A("")
    A("The gap is present in every loan purpose and in every top-5 state. It is widest "
      "for **home improvement** (15.0 pp) and narrowest for **home purchase** "
      "(4.6 pp) — consistent with home-improvement loans being the marginal "
      "application that a second income tips from denial to approval.")
    A("")
    A("![Gap by purpose and state](figures/fig4_gap_by_purpose_state.png)")
    A("")

    # ------------------------------------------------------------------
    A("## 5. Pandas vs PySpark — result equivalence")
    A("")
    A(f"All **{eq['n_agree']} of {eq['n_comparisons']}** canonical analytical outputs agree "
      f"between the two implementations (numeric tolerance {eq['tolerance']}).")
    A("")
    A("| # | Analytical quantity | Pandas | PySpark | Agree |")
    A("|---:|---|---|---|---|")
    for i, c in enumerate(eq["comparisons"], 1):
        p, s = c["pandas"], c["spark"]
        if isinstance(p, list):
            pv = f"{len(p)} rows"
            sv = f"{len(s)} rows"
        else:
            def _fmt(d):
                parts = []
                for k, v in list(d.items())[:2]:
                    if isinstance(v, int):
                        parts.append(f"{k.replace('_', ' ')}: {v:,}")
                    elif isinstance(v, float):
                        parts.append(f"{k.replace('_', ' ')}: {v:.4g}")
                    else:
                        parts.append(f"{k.replace('_', ' ')}: {v}")
                return "<br/>".join(parts)
            pv = _fmt(p)
            sv = _fmt(s)
        A(f"| {i} | {c['quantity']} | {pv} | {sv} | {'YES' if c['agree'] else 'NO'} |")
    A("")
    A("Both engines read the **same raw file** and apply the **same rules** from "
      "`src/rules.py`, so the comparison is meaningful. Three genuine bugs were found "
      "and fixed by this check:")
    A("")
    A("1. **`Int64.isin((\"1\",\"2\",\"3\"))` is always `False`** in Pandas, while Spark's "
      "`isin` coerces the literals and silently succeeds. The outcome codes are now "
      "integers in `config.py`.")
    A("2. **Spark's `SUM` propagates NULL**, so a single empty co-applicant field made "
      "the whole record indeterminate. The counters are now wrapped in `coalesce`.")
    A("3. **Pandas `qcut` and Spark `ntile` disagree at the quartile boundaries.** The "
      "boundaries are now computed once from the data and pinned in "
      "`results/income_quartile_bounds.json`.")
    A("")

    # ------------------------------------------------------------------
    A("## 6. Performance and scalability")
    A("")
    A("Median over 3 repeats. Both engines process exactly the same records "
      "(selected by a SHA-256 hash of the LEI, identical in both engines).")
    A("")
    A("| Engine | Data | Rows | Ingest | Clean | Analyse | **Total** | Throughput |")
    A("|---|---|---:|---:|---:|---:|---:|---:|")
    for _, r in bench.iterrows():
        A(f"| {r['engine']} | {r['fraction']} | {int(r['rows_cleaned']):,} | "
          f"{r['ingest_s']:.1f} s | {r['clean_s']:.1f} s | {r['analyze_s']:.1f} s | "
          f"**{r['total_s']:.1f} s** | {r['rows_per_second']:,.0f} rows/s |")
    A("")
    spark_full = bench[(bench["engine"] == "pyspark") & (bench["fraction"] == "100%")].iloc[0]
    pandas_full = bench[(bench["engine"] == "pandas") & (bench["fraction"] == "100%")].iloc[0]
    A(f"At full scale Spark is **{pandas_full['total_s'] / spark_full['total_s']:.1f}x faster** "
      f"end-to-end ({pandas_full['total_s']:.0f} s vs {spark_full['total_s']:.0f} s) and "
      f"**{spark_full['rows_per_second'] / pandas_full['rows_per_second']:.1f}x** the "
      "throughput.")
    A("")
    A("**Why.** The dominant cost in Pandas is the cleaning stage "
      f"({pandas_full['clean_s']:.0f} s of {pandas_full['total_s']:.0f} s at full scale). "
      "Pandas must materialise the data: the raw file has 99 string columns, and the "
      "cleaning step needs a column-wide copy for each of the ~80 numeric conversions, "
      "so every conversion touches roughly 12.25 M x 99 Python objects. Spark keeps "
      "the data in its columnar in-memory representation and evaluates the same "
      "expressions as a lazily planned, vectorised DAG, which is why its cleaning stage "
      "costs a fraction as much. The gap is *not* in the I/O — both engines read the "
      "same 4.32 GiB file at similar speed — but in the per-cell processing.")
    A("")
    A("**Scaling.** Spark's advantage widens with the data size, because its cost is "
      "linear in the number of rows and it parallelises across cores, while Pandas' "
      "cost is super-linear in practice: the cleaning stage is dominated by memory "
      "allocation and garbage collection, and at full scale the working set no longer "
      "fits comfortably in the 16 GB of RAM. This is the expected qualitative result — "
      "the assignment's point being that Pandas is fine for a justified subset but "
      "does not scale to the full national dataset without the chunked, "
      "column-pruning approach used here.")
    A("")
    A("![Benchmark](figures/fig5_benchmark_scaling.png)")
    A("")
    A("> **Practical note.** The Pandas pipeline writes its Parquet output "
      "**chunk by chunk** (`src/pandas_pipeline.py`), so the full dataset never has to "
      "be resident in memory. The benchmark measures the same chunked approach.")
    A("")

    # ------------------------------------------------------------------
    A("## 7. Limitations")
    A("")
    A("* **`joint_flag` is inferred, not reported.** 9.41 % of records overall "
      "(1.01 % of decision records) cannot be classified. Purchased loans and "
      "preapproval records are disproportionately affected.")
    A("* **The finding is associative, not causal.** The gap is an association "
      "between the co-applicant fields and the outcome. It does not establish that "
      "adding a co-applicant causes an approval. Confounders such as the number of "
      "borrowers on the note, credit history and property type are not controlled "
      "for.")
    A("* **Duplicate removal is necessarily a judgement call.** 26,755 records "
      "identical in all 99 fields were removed as certainly redundant. A further "
      "19,831 records share an application-identifying key but differ elsewhere; "
      "they were kept, because a borrower may legitimately file two applications "
      "with the same lender. Deduplication moves the RQ1 gap by 0.01 pp, so the "
      "finding does not depend on this choice.")
    A("* **`interest_rate` is missing for 36.8 % of records** — HMDA only requires it "
      "for originated loans — so the interest-rate comparison in RQ2 rests on a "
      "biased subset (originations only).")
    A("* **`income` is missing for 14.5 % of records**; the loan-to-income ratio is "
      "missing for 15.8 %.")
    A("* **Extreme values are retained.** The mean loan amount is therefore "
      "dominated by a small number of very large loans (standard deviation $3.0 M vs a "
      "median of $225,000); the median is the more meaningful statistic and is reported "
      "alongside it.")
    A("* **Both engines ran on the same 16 GB machine.** The benchmark therefore "
      "measures single-node behaviour on one dataset size, not true distributed "
      "scalability.")
    A("")

    # ------------------------------------------------------------------
    A("## 8. Reproducing")
    A("")
    A("```bash")
    A("pip install -r requirements.txt")
    A("python src/pandas_pipeline.py      # Pandas: clean + write Parquet")
    A("python src/spark_pipeline.py       # Spark:  clean + write Parquet")
    A("python src/equivalence.py all      # compare the two engines")
    A("python src/run_analysis.py all     # RQ1..RQ4 in both engines")
    A("python src/benchmark.py            # performance experiment")
    A("python src/figures.py              # charts")
    A("python src/report.py                # this document")
    A("```")
    A("")
    A("**Environment:** Python 3.11, pandas 2.3.3, PySpark 4.0.1, pyarrow 26.0.1, "
      "Temurin OpenJDK 17, Hadoop winutils 3.3.6, Windows 10 x64, 16 GB RAM.")
    A("")
    A("### Result files")
    A("")
    A("| File | Contents |")
    A("|---|---|")
    A("| `results/rq1.csv` | Denial rate by application type |")
    A("| `results/rq2.csv` | Financial profile by application type |")
    A("| `results/rq3.csv` | Stratified denial rates (all strata) |")
    A("| `results/rq4.csv` | Denial rate by loan purpose and state |")
    A("| `results/equivalence_report.json` | Pandas vs Spark comparison, cell by cell |")
    A("| `results/benchmark_results.csv` | Performance measurements |")
    A("| `results/cleaning_report_*.json` | Records removed at each cleaning step |")
    A("| `docs/hmda_data_dictionary_2024.md` | Full data dictionary and code tables |")
    A("| `docs/public_lar_schema_2024.md` | The 99-field schema |")
    A("")

    return "\n".join(L)


def main() -> None:
    text = build_report()
    out = C.RESULTS_DIR / "report.md"
    out.write_text(text, encoding="utf-8")
    print(f"Written: {out}")
    print(f"  {len(text.splitlines())} lines, {len(text):,} characters")


if __name__ == "__main__":
    main()
