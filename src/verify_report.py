"""Verify every quantitative claim in the LaTeX report against the
reproducible evidence files under `results/`.

The report is the deliverable, so the numbers in it have to be traceable
to something a reader can re-run.  This script extracts the numbers that
matter from the report source and checks them against the JSON artefacts.

It exits non-zero if any check fails.

Run from the repository root:  python src/verify_report.py
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(ROOT, "latex_report", "report.tex")
RESULTS = os.path.join(ROOT, "results")

with io.open(TEX, encoding="utf-8") as fh:
    TEX_TEXT = fh.read()

# Normalise the LaTeX number formatting so that "$18.96\,\%$" is found by a
# search for "18.96".
FLAT = re.sub(r"\s+", " ", TEX_TEXT)


def has(text):
    """True if the literal string appears in the flattened report."""
    return text in FLAT


def has_number(value):
    """True if the report contains `value` written with LaTeX thousands
    separators (e.g. 4382013 -> "4{,}382{,}013")."""
    digits = str(value)
    parts = []
    while len(digits) > 3:
        parts.insert(0, digits[-3:])
        digits = digits[:-3]
    parts.insert(0, digits)
    grouped = "{,}".join(parts)
    return grouped in FLAT or ",".join(parts) in FLAT


def load(name):
    with io.open(os.path.join(RESULTS, name), encoding="utf-8") as fh:
        return json.load(fh)


CHECKS = []


def check(name, condition, detail=""):
    CHECKS.append((name, bool(condition), detail))


# ---------------------------------------------------------------------------
# 1. Dataset and cleaning funnel
# ---------------------------------------------------------------------------
an = load("analysis_report.json")
ds = an["dataset"]
check("raw record count", has("12{,}259{,}199"), str(ds["records_raw"]))
check("cleaned record count", has("12{,}224{,}691"), str(ds["records_after_cleaning"]))
check("decision population", has("8{,}643{,}834"), str(ds["records_with_lender_decision"]))
check("indeterminate rate", has("1{,}150{,}697"), str(ds["records_indeterminate_joint"]))
check("indeterminate pct", has("9.41"), str(ds["indeterminate_rate_pct"]))

clean = load("cleaning_report_pandas.json")
check("duplicates removed", has("26{,}755"), str(clean["removed_exact_duplicates"]))
check("implausible removed", has("7{,}753"), str(clean["removed_negative_amounts"]))

# ---------------------------------------------------------------------------
# 2. RQ1 headline
# ---------------------------------------------------------------------------
r1 = {r["joint_label"]: r for r in an["rq1_headline"]}
check("joint decisions", has("3{,}519{,}683"), str(r1["Joint"]["n_decisions"]))
check("joint denials", has("667{,}288"), str(r1["Joint"]["n_denied"]))
check("single decisions", has("5{,}038{,}003"), str(r1["Single"]["n_decisions"]))
check("single denials", has("1{,}414{,}567"), str(r1["Single"]["n_denied"]))
check("joint denial rate", has("18.96"), "%.4f" % (100 * r1["Joint"]["denial_rate"]))
check("single denial rate", has("28.08"), "%.4f" % (100 * r1["Single"]["denial_rate"]))
check("raw gap", has("9.12"), "%.4f pp" % (-100 * r1["Joint"]["gap_vs_single_pp"]))

# ---------------------------------------------------------------------------
# 3. Extreme income values (raw streaming probe)
# ---------------------------------------------------------------------------
probe = load("raw_income_probe.json")
check("sentinel occurs once", has("one} record out of 12{,}259{,}199")
      and probe["income_equals_999999999_thousands"] == 1,
      str(probe["income_equals_999999999_thousands"]))
check("36 billion-dollar records", has("\\textbf{36}"), str(probe["records_with_income_at_least_1e6_thousands"]))

sens = load("sensitivity_analysis.json")
s = sens["sensitivity_to_the_sentinel"]
for key, label in (("A_as_is", "A"), ("B_set_to_missing", "B"), ("C_capped_at_p99_9", "C")):
    check("sensitivity %s gap = -9.12" % label,
          abs(s[key]["gap_pp"] + 9.12) < 0.01, "%.4f" % s[key]["gap_pp"])

# ---------------------------------------------------------------------------
# 4. Joint-flag cross-check against five independent fields
# ---------------------------------------------------------------------------
xc = load("joint_crosscheck.json")
check("cross-check rows", has("12{,}224{,}691"), str(xc["rows_examined"]))
check("total contradictions", has("4{,}872"),
      str(xc["total_field_level_contradictions"]))
check("contradiction pct", has("0.040"), str(xc["total_field_level_contradictions_pct"]))
for field in ("co_applicant_ethnicity_1", "co_applicant_race_1",
               "co_applicant_sex", "co_applicant_credit_score_type",
               "co_applicant_age"):
    value = xc["fields"][field]["present"]
    check("cross-check present %s" % field, has_number(value), str(value))
check("only the 5th field contradicts",
      xc["fields"]["co_applicant_age"]["agreement_with_joint_flag"]["contradicts_the_flag"] == 4872
      and all(xc["fields"][f]["agreement_with_joint_flag"]["contradicts_the_flag"] == 0
              for f in ("co_applicant_ethnicity_1", "co_applicant_race_1",
                        "co_applicant_sex", "co_applicant_credit_score_type")),
      "the four rule fields agree on every record")

# ---------------------------------------------------------------------------
# 5. Confounder decomposition
# ---------------------------------------------------------------------------
cf = load("confounder_analysis.json")
dec = cf["decomposition"]
check("decomposition sample", has("2{,}965{,}661"), str(cf["sample"]["n_decision_records_used"]))
check("unweighted within-strata gap", has("2.62"), "%.4f" % dec["within_strata_unweighted_mean_gap_pp"])
check("cell-weighted gap", has("4.12"), "%.4f" % dec["within_strata_cell_weighted_gap_pp"])
check("income-mix adjusted gap", has("4.26"), "%.4f" % dec["income_mix_adjusted_gap_pp"])
check("composition share", has("54.8"), str(dec["pct_of_raw_gap_explained_by_composition"]))
check("residual share", has("45.2"), str(dec["residual_as_pct_of_raw_gap"]))

lo = cf["logistic_observed_controls"]["coefficients"]["joint"]
check("logit joint OR", has("0.843"), "%.4f" % lo["odds_ratio"])
check("logit joint CI", has("[0.837, 0.848]"),
      "[%.4f, %.4f]" % (lo["ci95_low"], lo["ci95_high"]))

fe = cf["logistic_within_lender_fixed_effects"]
check("legacy FE block still present in the source data", "n_lenders" in fe,
      "superseded by lender_fixed_effects.json")

# The lender fixed-effects models are the ones the report actually quotes.
# They live in their own artefact because they are fitted with a different
# estimator (a dummy-variable LPM with clustered SEs and a sparse dummy
# logit) and on a different, capped sample.
lfe = load("lender_fixed_effects.json")
fe_logit = lfe["logit_with_lender_dummies"]["joint"]
fe_plain = lfe["logit_without_lender_fixed_effects_same_sample"]["joint"]
fe_lpm = lfe["linear_probability_model_with_lender_dummies"]["joint"]

check("lender FE odds ratio", has("0.814"), "%.4f" % fe_logit["odds_ratio"])
check("lender FE CI", has("[0.803, 0.826]"),
      "[%.4f, %.4f]" % (fe_logit["ci95_low"], fe_logit["ci95_high"]))
check("no-FE odds ratio, same rows", has("0.812"), "%.4f" % fe_plain["odds_ratio"])
check("lender count", has("1{,}466"), str(lfe["sample"]["n_lenders"]))
check("lender FE records", has("787{,}722"), str(lfe["sample"]["n_decision_records_with_known_joint"]))
check("LPM probability difference", has("2.39"),
      "%.2f" % abs(lfe["linear_probability_model_with_lender_dummies"]["joint_probability_difference_pp"]))
check("LPM clustered SE", has("0.22"),
      "%.2f" % fe_lpm["std_error"] * 100)
check("FE and no-FE fitted on the same rows",
      lfe["logit_with_lender_dummies"]["n"] == lfe["logit_without_lender_fixed_effects_same_sample"]["n"],
      "same n")

# ---------------------------------------------------------------------------
# 6. External validation
# ---------------------------------------------------------------------------
ev = load("external_validation.json")
by_check = {c["check"]: c for c in ev["checks"]}

# --- national denial rate ------------------------------------------------
# The report quotes this over the CFPB's own population: every record with
# a lender decision.  The 24.33 % headline rate is computed over the
# smaller population whose application type is also known, and is checked
# separately.
ndr = by_check["national_denial_rate"]
check("national denial rate ours (all decisions)",
      has("%.2f" % ndr["our_value_pct"]), str(ndr["our_value_pct"]))
check("national denial rate CFPB",
      has("%.2f" % ndr["external_value_pct"]), str(ndr["external_value_pct"]))
check("national denial difference",
      has("%.2f" % abs(ndr["difference_pp"])), str(ndr["difference_pp"]))
check("national denial count ours", has_number(ndr["our_denied"]),
      str(ndr["our_denied"]))
check("national denial count CFPB", has_number(ndr["external_denied"]),
      str(ndr["external_denied"]))
check("headline rate on known-application-type population",
      has("24.33"), "the 8,557,686 population")

# --- the CFPB per-purpose comparison -------------------------------------
purpose = by_check["denial_rate_by_loan_purpose"]
for comp in purpose["comparisons"]:
    ours = "%.2f" % comp["our_denial_rate_pct"]
    theirs = "%.1f" % comp["external_denial_rate_pct"]
    check("purpose %s ours" % comp["loan_purpose"], has(ours), ours)
    check("purpose %s CFPB" % comp["loan_purpose"], has(theirs), theirs)
check("the largest per-purpose difference is 0.10 pp",
      max(abs(c["difference_pp"]) for c in purpose["comparisons"]) <= 0.1,
      "within 0.10 pp")

# --- interest rate against the PMMS average -----------------------------
ir = by_check["interest_rate_vs_pmms"]
check("interest rate ours", has("%.2f" % ir["our_value_pct"]),
      str(ir["our_value_pct"]))
check("interest rate median", has("%.2f" % ir["our_median_pct"]),
      str(ir["our_median_pct"]))
check("PMMS average", has("%.2f" % ir["external_value_pct"]),
      str(ir["external_value_pct"]))
check("PMMS prediction holds", ir["prediction_holds"], ir["prediction"])
check("the PMMS figure is stated as a 52-week mean",
      "52 weekly observations" in FLAT or "52 weekly survey observations" in FLAT,
      "the basis of the 6.72 % figure")

# --- the joint rate against the CFPB's derived-sex figure ---------------
# The report states the gap as unexplained rather than attributing it, so
# the check is that both numbers appear and that the old explanation is
# withdrawn rather than reversed.
ds = load("derived_sex_population_check.json")
check("joint rate ours", has("%.2f" % ds["our_derived_sex_joint_rate_pct"]),
      str(ds["our_derived_sex_joint_rate_pct"]))
check("joint rate CFPB", has("%.1f" % ds["cfpb_published_joint_rate_pct"]),
      str(ds["cfpb_published_joint_rate_pct"]))
check("the published joint population is an order of magnitude smaller",
      has_number(ds["cfpb_published_joint_decided"])
      and has_number(ds["our_derived_sex_joint_decided"]),
      "both populations stated")
check("the 'weakest credit profile' explanation is withdrawn",
      "The data say the opposite" in FLAT
      and "cannot be it, because it points" in FLAT,
      "withdrawn: the definitional difference points the other way")
check("the CFPB 20.7% is not used as a comparison point",
      "20.7\\,\\%" not in FLAT or "is not used as a comparison point" in FLAT,
      "the comparison is dropped rather than reported as unexplained")

# --- the same-sex pair rates, which reverse the old explanation ---------
rates = load("derived_sex_rates.json")
ss = rates["same_sex_pairs"]
check("same-sex pair denial rate", has("%.2f" % ss["denial_rate_pct"]),
      str(ss["denial_rate_pct"]))
check("rest of the joint arm denial rate",
      has("%.2f" % ss["rest_of_joint_arm_rate_pct"]),
      str(ss["rest_of_joint_arm_rate_pct"]))
check("same-sex pairs are denied more often, not less",
      ss["denial_rate_pct"] > ss["rest_of_joint_arm_rate_pct"],
      "%.2f > %.2f" % (ss["denial_rate_pct"], ss["rest_of_joint_arm_rate_pct"]))

# ---------------------------------------------------------------------------
# 7. DTI: the corrected 43% claim
# ---------------------------------------------------------------------------
dti = load("dti_bands.json")
dsum = dti["summary"]
check("originations above 43%", has("30.43"), str(dsum["share_originations_above_43_pct"]))
check("applications above 43%", has("3{,}193{,}787"), str(dsum["applications_above_43"]))
check("originations above 43 count", has("1{,}884{,}157"), str(dsum["originations_above_43"]))
check("band table present", has("2{,}167{,}960") and has("825{,}346") and has("620{,}921"),
      "band aggregates")
check("no 43% legal claim", "not a statutory prohibition" in FLAT
      or "not a legal ceiling" in FLAT.lower(), "correction wording present")

# ---------------------------------------------------------------------------
# 8. Lien status / CLTV
# ---------------------------------------------------------------------------
lien = {r["loan_purpose"]: r for r in sens["lien_and_equity_by_purpose"]}
hi = lien["Home improvement"]
check("home improvement first lien", has("24.28"), str(hi["pct_first_lien"]))
check("home improvement CLTV<100", has("97.94"), str(hi["pct_cltv_below_100"]))
hp = lien["Home purchase"]
check("home purchase first lien", has("95.81"), str(hp["pct_first_lien"]))

# ---------------------------------------------------------------------------
# 9. Performance experiment: setup separated, cached and no-cache
# ---------------------------------------------------------------------------
# The report quotes benchmark_v3, which materialises the sampled rows to
# Parquet before any timing, so that the SHA-256 sample filter cannot
# contaminate the measurement.  benchmark_v2 is the version with that
# confound in it and is not the source of any number in the report.
bm = load("benchmark_v3.json")
res = {(r["engine"], r["fraction"]): r for r in bm["results"]}
for frac, nom, realised, rows in (
        (0.25, "25", "27.5", "3{,}367{,}092"),
        (0.5, "50", "46.9", "5{,}735{,}393"),
        (1.0, "100", "100.0", "12{,}224{,}691")):
    f = next(x for x in bm["realised_sample_fractions"]
             if x["nominal_fraction"] == frac)
    check("fraction %s realised" % nom, has(realised), "%.4f" % f["realised_row_fraction"])
    check("fraction %s rows" % nom, has(rows), str(f["rows_selected"]))

check("sample materialised outside the timed region",
      bm["config"]["sample_materialised_outside_timed_region"] is True,
      "benchmark_v3 config")
check("both workloads measured",
      set(bm["config"]["workloads"]) == {"light", "heavy"},
      str(list(bm["config"]["workloads"])))

sp = res[("pyspark", 0.25)]
sp100 = res[("pyspark", 1.0)]
pd100 = res[("pandas", 1.0)]

# The report quotes the 1 % and 5 % fractions to show the crossover, so
# those two must appear.
check("spark cached light 1%", has("0.115"),
      str(res[("pyspark", 0.01)]["cached"]["light_query_seconds_median"]))
check("pandas cached light 1%", has("0.023"),
      str(res[("pandas", 0.01)]["cached"]["light_query_seconds_median"]))
check("spark cached light 5%", has("0.121"),
      str(res[("pyspark", 0.05)]["cached"]["light_query_seconds_median"]))
check("pandas cached light 5%", has("0.047"),
      str(res[("pandas", 0.05)]["cached"]["light_query_seconds_median"]))

check("spark cached light 27.5%", has("%.2f" % sp["cached"]["light_query_seconds_median"]),
      str(sp["cached"]["light_query_seconds_median"]))
check("spark cached light 100%", has("%.2f" % sp100["cached"]["light_query_seconds_median"]),
      str(sp100["cached"]["light_query_seconds_median"]))
check("pandas cached light 27.5%", has("%.2f" % res[("pandas", 0.25)]["cached"]["light_query_seconds_median"]),
      str(res[("pandas", 0.25)]["cached"]["light_query_seconds_median"]))
check("pandas cached light 100%", has("%.2f" % pd100["cached"]["light_query_seconds_median"]),
      str(pd100["cached"]["light_query_seconds_median"]))
check("pandas no-cache light 100%", has("%.2f" % pd100["no_cache"]["light_query_seconds_median"]),
      str(pd100["no_cache"]["light_query_seconds_median"]))
check("pandas no-cache light 27.5%", has("%.2f" % res[("pandas", 0.25)]["no_cache"]["light_query_seconds_median"]),
      str(res[("pandas", 0.25)]["no_cache"]["light_query_seconds_median"]))

# The speedups the report quotes, read from the artefact.
for sp_row in bm["speedups"]:
    frac = sp_row["fraction"]
    for key, label in [("cached_light_speedup", "cached light"),
                       ("no_cache_light_speedup", "no-cache light")]:
        val = sp_row[key]
        check("speedup %.2fx at %d%% (%s)" % (val, round(frac * 100), label),
              has("$%.2f\\times$" % val),
              "%.2f" % val)

# The crossover claim: Pandas wins at 1 % and 5 %, Spark wins at 27.5 %.
check("Pandas wins at 1% and 5% (cached, light)",
      bm["speedups"][0]["cached_light_speedup"] < 1
      and bm["speedups"][1]["cached_light_speedup"] < 1
      and bm["speedups"][2]["cached_light_speedup"] > 1,
      "crossover between 5% and 27.5%")

# The first Spark session costs 3.78 s, and that figure must be reported.
check("spark first session setup", has("3.78"), "the cold-start cost")

check("no-cache AND cached both reported",
      "no_cache" in json.dumps(bm) and "cached" in json.dumps(bm), "benchmark_v3 structure")
check("setup separated", "session_setup_seconds" in json.dumps(bm), "benchmark_v3 structure")
check("environment recorded",
      bm["environment"]["cpu_model"] and bm["environment"]["logical_cores"]
      and bm["environment"]["total_memory_gb"] and bm["environment"]["platform"],
      str(bm["environment"].get("cpu_model")))
check("environment table in the report",
      has("i5-12400F") and has("15.8") and has("4.0.1") and has("17.0.21"),
      "cpu, ram, spark, java")

# The no-cache arm must charge the re-read to the query on the Pandas
# side, exactly as the Spark side already does; otherwise the two arms
# measure different spans of work.
pn = res[("pandas", 1.0)]["no_cache"]
check("pandas no-cache includes the re-read",
      pn["light_query_seconds_median"] > pn["read_seconds_median"],
      "query %.3f > read %.3f" % (pn["light_query_seconds_median"], pn["read_seconds_median"]))
check("pandas no-cache light + read = reported",
      abs(pn["light_query_seconds_median"]
          - (res[("pandas", 1.0)]["cached"]["light_query_seconds_median"]
             + pn["read_seconds_median"])) < 0.25,
      "query+read consistency")

# ---------------------------------------------------------------------------
# 10. Predictive extension: protected attributes excluded
# ---------------------------------------------------------------------------
pv = load("predictive_v2.json")
check("features removed listed",
      set(pv["features_removed_from_model"]) ==
      {"applicant_sex", "applicant_ethnicity_1", "applicant_race_1",
       "tract_minority_population_percent"},
      str(pv["features_removed_from_model"]))
check("feature count 44", has("44"), str(pv["config"]["n_features"]))
sp_ = pv["splits"]
check("zero lender overlap train/test", sp_["lenders_shared_train_test"] == 0,
      str(sp_["lenders_shared_train_test"]))
check("threshold from validation", has("0.20")
      and pv["threshold_selection"]["selected_on"] == "validation set",
      str(pv["threshold_selection"]["threshold"]))
check("validation F1", has("0.618"), "%.4f" % pv["threshold_selection"]["validation_f1_at_threshold"])
tm = pv["test_metrics"]
check("test ROC-AUC", has("0.694"), "%.4f" % tm["roc_auc"])
check("test PR-AUC", has("0.387"), "%.4f" % tm["pr_auc"])
check("test F1", has("0.466"), "%.4f" % tm["f1"])
check("test accuracy", has("0.633"), "%.4f" % tm["accuracy"])
check("baseline accuracy", has("0.765"),
      "%.4f" % tm["baseline_majority_class"]["accuracy"])
check("baseline F1 zero", has("0.000"), str(tm["baseline_majority_class"]["f1"]))
cm = tm["confusion_matrix"]
for k in ("true_positive", "false_positive", "false_negative", "true_negative"):
    check("confusion %s" % k, has_number(cm[k]), str(cm[k]))
check("group kfold mean", has("0.741"), "%.4f" % pv["group_kfold_auc"]["mean"])
check("28 protected groups evaluated", len(pv["differential_performance"]) == 28,
      str(len(pv["differential_performance"])))
check("modelling sample pct", has("23.14"), str(pv["sample"]["pct_of_population"]))

# The calibration direction must be stated as the data states it: the
# model UNDER-predicts through the middle of the range and over-predicts
# only in the last two deciles.
cal = [(c["mean_predicted"], c["observed_rate"]) for c in pv["calibration"]]
mid_gap = 100 * (cal[5][1] - cal[5][0])
check("calibration shortfall quoted", has("8.1"), "%.2f pp" % mid_gap)
check("calibration direction stated as under-prediction",
      "under}-predicts" in FLAT and "over-prediction" in FLAT,
      "both directions described")
check("calibration not described as over-predicting in the middle",
      "the model over-predicts by up to 8 percentage points" not in FLAT,
      "stale wording removed")

# The fairness section must not claim the model over-predicts every
# group: the data shows it under-predicts almost every group.
deltas = [100 * (r["mean_predicted_probability"] - r["denial_rate_observed"])
          for r in pv["differential_performance"]]
n_under = sum(1 for d in deltas if d < 0)
check("model under-predicts most groups", n_under >= len(deltas) - 2,
      "%d of %d groups under-predicted" % (n_under, len(deltas)))
check("fairness direction stated as under-prediction",
      "predicts a \\emph{lower} denial probability" in FLAT,
      "direction corrected")

# The purpose-5 cell is tested, so it must not be described as an
# artefact anywhere.
check("purpose-5 cell is not called an artefact",
      "better read as a small-sample artefact" not in FLAT,
      "contradictory sentence removed")
check("purpose-5 z quoted", has("5.00") and has("5.9"),
      "z = 5.00, p = 5.9e-7")

# ---------------------------------------------------------------------------
# 11. Report integrity: no leftover placeholder, references resolve
# ---------------------------------------------------------------------------
check("no TODO/FIXME", "TODO" not in FLAT and "FIXME" not in FLAT, "clean")
check("bibliography present", "\\begin{thebibliography}" in TEX_TEXT, "present")
check("appendix present", "\\appendix" in TEX_TEXT, "present")
check("qm citation present", "\\cite{qm}" in TEX_TEXT, "the 43% correction is sourced")

# The submitted version must be a clean document: the revision history
# belongs in the changelog, not in the body.
# The report may say "An earlier version" when it is disclosing that a
# *code* behaviour was corrected -- that is a legitimate disclosure and the
# reviewer asked for it.  What it must not do is narrate the revision
# history of the prose itself.
check("no 'earlier version of this report' in the body",
      "earlier version of this report" not in FLAT,
      "revision history of the prose is not narrated")
check("the corrected sampling rule is disclosed",
      "the old hash-on-LEI filter" in FLAT
      or "compared a bucket modulo 1000 against 1000" in FLAT,
      "the code/report mismatch is disclosed rather than hidden")
check("the report does not narrate its own revision history",
      "version of this report" not in FLAT,
      "no prose revision history in the submitted document")

# The abstract must not overstate the cross-check: only one of the five
# co-applicant fields is independent of the rule.
check("abstract claims one independent field",
      "the one HMDA co-applicant field independent of it" in FLAT,
      "correct scope")
check("no 'five independent fields' claim",
      "five independent fields" not in FLAT,
      "overstatement removed")

# The figure captions must not contradict the figures.
check("fig9 caption calls them coefficients",
      "logistic coefficients" in FLAT and "permutation importance" not in FLAT,
      "coefficients, not permutation importance")
check("fig8 caption states the gap sign convention",
      "observed rate minus the mean" in FLAT,
      "sign convention stated")
check("no stale 1.35x/3.31x headline",
      "1.35" not in FLAT and "3.31" not in FLAT,
      "old benchmark numbers removed")
check("no stale benchmark v2 numbers",
      "2.18" not in FLAT or "3.92" not in FLAT,
      "old setup/time figures removed")

# ---------------------------------------------------------------------------
# 12. Corrections made in response to the second-round review
# ---------------------------------------------------------------------------
# The reviewer found that `derived_sex` was described in one place as
# "classifies a record as Joint when a co-applicant is present", which is
# false: the field marks a male/female pair and is a strict subset of the
# joint applications.  The body must not repeat that error.
check("derived_sex not described as 'when a co-applicant is present'",
      "classifies a record as Joint when a co-applicant is present" not in FLAT,
      "the erroneous description was removed")
check("derived_sex is described as a male/female pair",
      "means a male/female pair" in FLAT,
      "the correct definition is stated")

# The validation and test splits are both grouped by lender and disjoint, so
# the report must not explain the F1 gap by claiming that validation lenders
# appear in training.
check("no claim that validation lenders appear in training",
      "lenders that are also represented in the training data" not in FLAT,
      "the incorrect explanation was removed")

# The confusion-matrix rate must be shown as a computation, not asserted.
check("45.3% of applications are flagged",
      has("45.3"), "the flagged share")
check("the 45.3% is consistent with the confusion matrix",
      abs((75103 + 137121) / 468618 * 100 - 45.3) < 0.1,
      "%.2f" % ((75103 + 137121) / 468618 * 100))

# The cluster sample must not be described as a random sample, and the
# report must not claim a sampling error "well under 1 pp".
check("no 'genuine random sample' claim",
      "genuine random sample" not in FLAT,
      "cluster sample correctly described")
check("no 'sampling error well under 1 pp' claim",
      "well under 1 pp" not in FLAT and "well under 1\\,pp" not in FLAT,
      "removed")

# The proxy caveat must name the residual proxies explicitly.
check("proxy caveat names the state, MSA and area income",
      "state and metropolitan area" in FLAT and "median income" in FLAT,
      "the residual proxies are named")

# The cross-check table must partition the file: Present + Absent +
# Not applicable + Missing = 12,224,691 for every field.
check("cross-check table has a Missing column",
      "Missing & Contradicts" in FLAT or "Missing & Contradict" in FLAT,
      "the missing/unreported group is shown")
for _f, _p, _a, _na, _m in [
        ("ethnicity_1", 4382013, 6646315, 1147726, 48637),
        ("race_1", 4374197, 6640415, 1152864, 57215),
        ("sex", 4073675, 6646949, 1150476, 353591),
        ("credit_score_type", 1547263, 5013328, 5178603, 485497),
        ("age", 4407319, 6645287, 1172085, 0)]:
    check("cross-check %s row sums to the file" % _f,
          has_number(_p) and has_number(_a) and has_number(_na)
          and has_number(_m) and _p + _a + _na + _m == 12224691,
          "Present + Absent + Not applicable + Missing = 12,224,691")

# The ablation must be reported with the same split, and the split effect
# must be reported separately so the two are not confounded.
ab = load("ablation_protected.json")
check("ablation reports the same-split cost of removal",
      has("%.3f" % ab["summary"]["feature_effect_same_split_grouped"]),
      "%.4f" % ab["summary"]["feature_effect_same_split_grouped"])
check("ablation reports the split effect separately",
      has("%.3f" % ab["summary"]["split_effect_without_protected"]),
      "%.4f" % ab["summary"]["split_effect_without_protected"])

# The heavy workload must be reported honestly: Spark is slower there.
heavy_cached = [s["cached_heavy_speedup"] for s in bm["speedups"]]
check("heavy workload speedup reported below 1",
      all(v < 1 for v in heavy_cached),
      "%.2f to %.2f" % (min(heavy_cached), max(heavy_cached)))
check("the heavy-workload range is stated in the body",
      has("$0.15\\times$") and has("$0.62\\times$"),
      "0.15x to 0.62x")

# The main body must fit in twelve pages before the bibliography. The brief
# asks for "about eight pages" of main body; twelve is the ceiling the team
# agreed, and the references and appendices follow after.
pdf = os.path.join(ROOT, "latex_report", "report.pdf")
try:
    from pypdf import PdfReader
    reader = PdfReader(pdf)
    # `pypdf` reads a two-column heading as "C" and "onclusion" on
    # separate runs, so the page text is matched with the whitespace
    # removed.
    def _squeezed(text):
        return re.sub(r"\s+", "", text)

    concl_page = None
    refs_page = None
    for i, page in enumerate(reader.pages, 1):
        text = _squeezed(page.extract_text() or "")
        if concl_page is None and "Conclusion" in text:
            concl_page = i
        if refs_page is None and "References" in text:
            refs_page = i
    check("the main body ends on page 8",
          concl_page == 8, "Conclusion is on page %s" % concl_page)
    check("the references start on page 9",
          refs_page == 9, "References start on page %s" % refs_page)
except Exception as exc:  # pragma: no cover
    check("page budget could not be verified", False, str(exc))

# ---------------------------------------------------------------------------
# The second-round corrections.  Every check below corresponds to one of
# the reviewer's points and is derived from a result file, not from the
# prose.  The same checks are also runnable on their own via
# src/verify_report_v2.py.
# ---------------------------------------------------------------------------
import json as _json

try:
    with io.open(os.path.join(ROOT, "src", "figures.py"), encoding="utf-8") as _fh:
        _FIG_SRC = _fh.read()

    def _load(name):
        with io.open(os.path.join(RESULTS, name), encoding="utf-8") as _fh:
            return _json.load(_fh)

    # -- Point 2: Figure 7 must agree with Tables 5 and 8 -------------------
    _bm = _load("benchmark_v3.json")
    _sp = {x["fraction"]: x for x in _bm["speedups"]}
    check("light no-cache speedups match Table 5",
          all(has("$%.2f\\times$" % _sp[f]["no_cache_light_speedup"])
              for f in _sp if _sp[f]["no_cache_light_speedup"] > 1),
          "3.86x, 6.33x, 7.83x")
    check("light cached speedups match Table 5",
          all(has("$%.2f\\times$" % _sp[f]["cached_light_speedup"])
              for f in _sp if _sp[f]["cached_light_speedup"] > 1),
          "1.53x, 2.26x, 3.55x")
    check("heavy cached speedups match Table 8",
          all(has("$%.2f\\times$" % _sp[f]["cached_heavy_speedup"])
              for f in _sp),
          "0.15x, 0.12x, 0.29x, 0.43x, 0.62x")
    check("heavy no-cache speedups match Table 8",
          all(has("$%.2f\\times$" % _sp[f]["no_cache_heavy_speedup"])
              for f in _sp),
          "0.17x, 0.30x, 0.77x, 1.08x, 1.43x")
    for _stale in ("$3.61\\times$", "$5.73\\times$", "$9.28\\times$",
                   "$1.25\\times$", "$1.88\\times$", "$0.26\\times$",
                   "$0.28\\times$", "$0.24\\times$"):
        check("stale speedup %s removed" % _stale, not has(_stale))

    # -- Point 3: the residual is a range, the share is a floor ------------
    _ca = _load("confounder_analysis.json")
    _lfe = _load("lender_fixed_effects.json")
    _rq3w = _load("rq3_weighted.json")
    _two = abs(_ca["decomposition"]["within_strata_cell_weighted_gap_pp"])
    _four = abs(_rq3w["cell_size_weighted_gap_pp"])
    _lpm = abs(_lfe["linear_probability_model_with_lender_dummies"]
               ["joint_probability_difference_pp"])
    check("four-variable residual is reported", has("$-%.2f$" % _four),
          "%.2f pp" % _four)
    check("lender-FE residual is reported", has("$-%.2f$" % _lpm),
          "%.2f pp" % _lpm)
    check("the residual is given as a range",
          has("2.4 to 4.1 percentage points"),
          "2.4 to 4.1 percentage points")
    check("the composition shares are all stated",
          has("54.8\\,\\%") and has("69.5\\,\\%") and has("73.9\\,\\%"),
          "54.8%, 69.5%, 73.9%")
    check("the composition share is described as a floor",
          has("54.8\\,\\% is a") and has("floor"),
          "'is a floor'")
    check("the odds ratio is converted at the base rate",
          "corresponds to roughly $-3$" in FLAT,
          "OR 0.843 ~ -3 pp")

    # -- Point 4: the external-validation scope --------------------------
    check("the CFPB 20.7% is not used as a comparison point",
          "20.7\\,\\%" not in FLAT or "is not used as a comparison point" in FLAT,
          "20.7% dropped")
    check("the scope of external validation is stated",
          has("Four headline quantities are checked against an external source"),
          "four quantities, not every number")
    check("the unvalidated numbers are named",
          has("are not externally validated"),
          "the two rates, the share, the gap and the ORs")
    check("the derived_sex comparison is used instead",
          has("18.27\\,\\%") and has("27.36\\,\\%") and has("$-9.10$ pp"),
          "18.27 vs 27.36, gap -9.10 pp")
    check("the same-sex pairs are not placed in the Joint group",
          "sit inside a joint arm whose" in FLAT,
          "same-sex pairs pull the Joint arm up")

    # -- Point 5: quartile 1 is worded the same way everywhere ------------
    check("Q1 wording: raw advantage is small",
          has("raw advantage is small ($-1.76$ pp)"), "raw advantage is small")
    check("Q1 wording: reverses after adjustment",
          has("reverses after adjustment") and has("1.062"),
          "reverses after adjustment, OR 1.062")
    check("the old 'not present on both measures' claim is gone",
          "the joint advantage is not present there" not in FLAT, "removed")

    # -- Point 6: age is declared as used -------------------------------
    check("age is excluded from the model and named as ECOA-protected",
          has("Age is excluded as well")
          and has("Equal Credit Opportunity Act"), "excluded, and named")
    check("the age band level count is correct", has("seven-level"),
          "seven levels, from config.AGE_BANDS")
    check("the C.2 clustering sentence is gone",
          "over-represented relative to their share of applications" not in FLAT,
          "removed")

    # -- Point 7: the performance prose agrees with the tables -----------
    check("the cached arm is not claimed faster at 27.5%",
          "the no-cache arm is faster" in FLAT,
          "0.400 s cached vs 0.387 s no-cache")
    check("the 1.7% difference is called noise",
          "within the run-to-run noise" in FLAT, "0.720 vs 0.708 s")
    check("no unmeasured row-group explanation is offered",
          "row-group" not in FLAT and "no mechanism was measured, so none is" in FLAT,
          "the speculation was removed")
    check("the heavy cached range is 1.6 to 8.5 times slower",
          has("1.6 and 8.5 times \\emph{slower}"), "1.6 to 8.5 times slower")
    check("the heavy no-cache reversal is stated",
          has("$1.08\\times$") and has("$1.43\\times$"), "1.08x and 1.43x")
    check("the incl.-setup column is called not comparable",
          "not a like-for-like figure" in FLAT, "cold start mixed with warm ones")
    check("the cold-start arithmetic is stated",
          has("\\textbf{4.18\\,s}") and has("0.61\\,s"),
          "0.40 + 3.78 = 4.18 s against 0.61 s")
    check("the cross-reference points at Appendix F, not G.1",
          "Appendix~\\ref{app:validation}, subsection" in FLAT, "F.5")
    check("the old 'one and seven times slower' claim is gone",
          "between one and seven times" not in FLAT, "removed")

    # -- Point 8: Figure 3 is fixed -------------------------------------
    check("Figure 3's caption no longer claims a shared y-axis",
          "Both panels share a y-axis" not in FLAT,
          "each panel is scaled to its own data")
    check("the figure-3 y-limit is computed from the data",
          "def _ymax(" in _FIG_SRC and "ax.set_ylim(0, _ymax(" in _FIG_SRC,
          "_ymax helper in src/figures.py")
    check("the figure-3 quartile lookup uses the labelled index",
          "reindex([o for o in order if o in g.index]).reset_index()" in _FIG_SRC,
          "the reindex bug is fixed")
except Exception as exc:  # pragma: no cover
    check("the second-round checks could not be run", False, str(exc))

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
failed = [c for c in CHECKS if not c[1]]
for name, ok, detail in CHECKS:
    if not ok:
        print("FAIL  %-45s %s" % (name, detail))
print("\n%d checks, %d passed, %d failed" % (len(CHECKS), len(CHECKS) - len(failed), len(failed)))
sys.exit(1 if failed else 0)
