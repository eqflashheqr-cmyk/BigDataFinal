"""Add regression checks for the second-round corrections.

The corrections introduced several numbers that were previously absent
from the report, and several claims that used to be made in a form the
report no longer makes.  These checks pin all of that down, so a later
edit cannot silently reintroduce a conflated claim.

    python src/verify_report.py
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
FLAT = re.sub(r"\s+", " ", TEX_TEXT)

FAILED = []
PASSED = 0


def has(text):
    return text in FLAT


def check(name, condition, detail=""):
    global PASSED
    if condition:
        PASSED += 1
    else:
        FAILED.append("%s (%s)" % (name, detail))
    print("  %-4s %s%s" % ("ok" if condition else "FAIL", name,
                           "" if condition else "  <- " + str(detail)))


def load(name):
    with io.open(os.path.join(RESULTS, name), encoding="utf-8") as fh:
        return json.load(fh)


print("=" * 74)
print("SECOND-ROUND CORRECTIONS")
print("=" * 74)

# ---------------------------------------------------------------------------
# Point 2 -- Figure 7 must be plotted from results/benchmark_v3.json, so
# every label on it must equal the speedup in that file.
# ---------------------------------------------------------------------------
bm = load("benchmark_v3.json")
sp = {s["fraction"]: s for s in bm["speedups"]}

check("light no-cache speedups match Table 5",
      all(has("$%.2f\\times$" % sp[f]["no_cache_light_speedup"])
          for f in sp if sp[f]["no_cache_light_speedup"] > 1),
      "3.86x, 6.33x, 7.83x")
check("light cached speedups match Table 5",
      all(has("$%.2f\\times$" % sp[f]["cached_light_speedup"])
          for f in sp if sp[f]["cached_light_speedup"] > 1),
      "1.53x, 2.26x, 3.55x")
check("heavy cached speedups match Table 8",
      all(has("$%.2f\\times$" % sp[f]["cached_heavy_speedup"])
          for f in sp),
      "0.15x, 0.12x, 0.29x, 0.43x, 0.62x")
check("heavy no-cache speedups match Table 8",
      all(has("$%.2f\\times$" % sp[f]["no_cache_heavy_speedup"])
          for f in sp),
      "0.17x, 0.30x, 0.77x, 1.08x, 1.43x")

# The stale values from the old benchmark run must be gone from the body.
for stale in ("$3.61\\times$", "$5.73\\times$", "$9.28\\times$",
              "$1.25\\times$", "$1.88\\times$", "$0.26\\times$",
              "$0.28\\times$", "$0.24\\times$"):
    check("stale speedup %s removed" % stale, not has(stale))

# ---------------------------------------------------------------------------
# Point 3 -- the residual gap is reported as a range, and the composition
# share as a lower bound.
# ---------------------------------------------------------------------------
ca = load("confounder_analysis.json")
lfe = load("lender_fixed_effects.json")
rq3w = load("rq3_weighted.json")

two_var = abs(ca["decomposition"]["within_strata_cell_weighted_gap_pp"])
four_var = abs(rq3w["cell_size_weighted_gap_pp"])
lpm = abs(lfe["linear_probability_model_with_lender_dummies"]
          ["joint_probability_difference_pp"])
raw = abs(ca["raw_gap_on_this_sample_pp"])

check("two-variable residual is reported", has("$%.2f$" % two_var) or
      has("%.1f" % two_var), "%.2f pp" % two_var)
check("four-variable residual is reported", has("$-%.2f$" % four_var),
      "%.2f pp" % four_var)
check("lender-FE residual is reported", has("$-%.2f$" % lpm),
      "%.2f pp" % lpm)
check("the residual is given as a range",
      has("2.4 to 4.1 percentage points"),
      "2.4 to 4.1 percentage points")

share_2 = (1 - two_var / raw) * 100
share_4 = (1 - four_var / abs(rq3w["pooled_gap_pp"])) * 100
share_l = (1 - lpm / 9.121376464344255) * 100
check("two-variable composition share is stated", has("54.8\\,\\%"),
      "%.1f%%" % share_2)
check("four-variable composition share is stated", has("69.5\\,\\%"),
      "%.1f%%" % share_4)
check("the three composition shares appear together",
      has("54.8\\,\\% / 69.5\\,\\% / 73.9\\,\\%"),
      "54.8% / 69.5% / 73.9%")
check("lender-FE composition share is stated", has("73.9\\,\\%"),
      "%.1f%%" % share_l)
check("the composition share is described as a floor, not a point estimate",
      has("54.8\\,\\% is a") and has("floor"),
      "'is a floor'")
check("the odds ratio is converted at the base rate, not equated to 4.12 pp",
      "0.843" in FLAT and "corresponds to roughly $-3$" in FLAT,
      "OR 0.843 ~ -3 pp")

# ---------------------------------------------------------------------------
# Point 4 -- the external-validation claim is scoped, and the CFPB 20.7 %
# comparison is dropped.
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Point 5 -- quartile 1 is described the same way everywhere.
# ---------------------------------------------------------------------------
check("Q1 wording: raw advantage is small",
      has("raw advantage is small ($-1.76$ pp)"),
      "raw advantage is small")
check("Q1 wording: reverses after adjustment",
      has("reverses after adjustment") and has("1.062"),
      "reverses after adjustment, OR 1.062")
check("the old 'not present on both measures' claim is gone",
      "the joint advantage is not present there" not in FLAT,
      "removed")
check("the 'reverses sign' wording in section 9 is qualified",
      "to reverse sign in the lowest quartile" not in FLAT
      and "to reverse in the lowest quartile" in FLAT
      and "raw advantage is small" in FLAT,
      "qualified")

# ---------------------------------------------------------------------------
# Point 6 -- age is stated as used, not claimed to be excluded.
# ---------------------------------------------------------------------------
check("age is excluded from the model and named as ECOA-protected",
      has("Age is excluded as well") and has("Equal Credit Opportunity Act"),
      "excluded, and named")
check("neither the numeric age nor the band is a feature",
      has("the raw numeric \\texttt{applicant\\_\\allowbreak age} is not a")
      and has("neither is the seven-level ordinal band"),
      "both forms excluded")
check("the age band level count is correct",
      has("seven-level"),
      "seven levels, from config.AGE_BANDS")
check("the C.2 clustering sentence is gone",
      "over-represented relative to their share of applications" not in FLAT,
      "removed")

# ---------------------------------------------------------------------------
# Point 7 -- the performance prose agrees with the tables.
# ---------------------------------------------------------------------------
check("the cached arm is not claimed faster at 27.5%",
      "at every larger size, including 27.5\\,\\% (0.400\\,s against 0.387\\,s), "
      "the no-cache arm is faster" in FLAT,
      "0.400 s cached vs 0.387 s no-cache")
check("the 1.7% difference is called noise",
      "within the run-to-run noise" in FLAT,
      "0.720 vs 0.708 s")
check("no unmeasured row-group explanation is offered",
      "row-group" not in FLAT and "no mechanism was measured, so none is" in FLAT,
      "the speculation was removed")
check("the heavy cached range is 1.6 to 8.5 times slower",
      has("1.6 and 8.5 times \\emph{slower}"),
      "1.6 to 8.5 times slower")
check("the heavy no-cache reversal is stated",
      has("$1.08\\times$") and has("$1.43\\times$"),
      "1.08x and 1.43x")
check("the incl.-setup column is called not comparable",
      "not a like-for-like figure" in FLAT,
      "cold start mixed with warm ones")
check("the cold-start arithmetic is stated",
      has("\\textbf{4.18\\,s}") and has("0.61\\,s"),
      "0.40 + 3.78 = 4.18 s against 0.61 s")
check("the cold-start consequence is stated",
      has("$1.2\\times$") and has("$0.67\\times$"),
      "1.2x at 12.2M, 0.67x at 5.7M")
check("the cross-reference points at Appendix F, not G.1",
      "Appendix~\\ref{app:validation}, subsection" in FLAT,
      "F.5")
check("the old 'one and seven times slower' claim is gone",
      "between one and seven times" not in FLAT,
      "removed")

# ---------------------------------------------------------------------------
# Point 8 and the structure -- Figure 3 is fixed, and the document order
# is References then Appendix A to K.
# ---------------------------------------------------------------------------
check("Figure 3's caption no longer claims a shared y-axis",
      "Both panels share a y-axis" not in FLAT,
      "each panel is scaled to its own data")
with io.open(os.path.join(ROOT, "src", "figures.py"), encoding="utf-8") as fh:
    FIG_SRC = fh.read()
check("the figure-3 y-limit is computed from the data",
      "def _ymax(" in FIG_SRC and "ax.set_ylim(0, _ymax(" in FIG_SRC,
      "_ymax helper in src/figures.py")
check("the figure-3 quartile lookup uses the labelled index",
      "reindex([o for o in order if o in g.index]).reset_index()" in FIG_SRC,
      "the reindex bug is fixed")

pdf = os.path.join(ROOT, "latex_report", "report.pdf")
try:
    from pypdf import PdfReader
    reader = PdfReader(pdf)
    pages = [(p.extract_text() or "") for p in reader.pages]

    # `pypdf` reads a two-column heading as "C" and "onclusion" on separate
    # runs, and it may insert spaces inside a heading, so both the heading
    # and the page text are matched with the whitespace removed.
    def squeezed(text):
        return re.sub(r"\s+", "", text)

    sq = [squeezed(t) for t in pages]

    def find(snippet):
        key = squeezed(snippet)
        return next((i + 1 for i, t in enumerate(sq) if key in t), None)

    concl = find("Conclusion")
    refs = find("References")
    check("the main body ends on page 8", concl == 8, "page %s" % concl)
    check("the references start on page 9", refs == 9, "page %s" % refs)

    # The appendices must appear in order A, B, C, ... after the references.
    titles = ["Selected Figures", "Limitations in Full",
              "The Predictive Extension in Full",
              "The Three Bugs the Comparison Found", "Method Detail in Full",
              "External Validation in Full", "The Measurement Environment",
              "Reference Tables",
              "Debt-to-Income Figure in Context",
              "Member Contributions", "Repository and Reproduction"]
    positions = [find(t) for t in titles]
    check("all eleven appendices are present",
          all(p is not None for p in positions), str(positions))
    check("the appendices are in order",
          all(positions[i] <= positions[i + 1]
              for i in range(len(positions) - 1) if positions[i]
              and positions[i + 1]),
          str(positions))
    check("the appendices start at or after the references",
          positions[0] is not None and positions[0] >= (refs or 0),
          "page %s, references on page %s" % (positions[0], refs))
    check("the references come before the first appendix",
          refs is not None and positions[0] is not None
          and refs <= positions[0],
          "references on page %s, Appendix A on page %s"
          % (refs, positions[0]))
    check("no page is blank",
          all(len(t.strip()) > 120 for t in pages),
          "every page has content")
except Exception as exc:  # pragma: no cover
    check("the PDF structure could not be verified", False, str(exc))

print()
print("=" * 74)
print("%d checks, %d passed, %d failed"
      % (PASSED + len(FAILED), PASSED, len(FAILED)))
if FAILED:
    print()
    for f in FAILED:
        print("  FAILED: %s" % f)
    sys.exit(1)
