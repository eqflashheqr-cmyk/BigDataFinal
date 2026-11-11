"""
run_analysis.py — Run the four research questions in one engine and write the
final result files.

Usage
-----
    python src/run_analysis.py pandas
    python src/run_analysis.py spark
    python src/run_analysis.py all
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C
import analysis as A


def main() -> None:
    engine = sys.argv[1] if len(sys.argv) > 1 else "all"

    engines = ["pandas", "spark"] if engine == "all" else [engine]
    for eng in engines:
        print(f"\n{'=' * 78}\nRUNNING ANALYSIS — {eng.upper()}\n{'=' * 78}")
        res = A.run(eng)
        for rq, df in res.items():
            print(f"\n--- {rq}: {A.RQS[rq][0]} ---")
            print(df.to_string(index=False, max_rows=40))

    # ---- consolidate the canonical (pandas) results into the report ------
    print(f"\n{'=' * 78}\nWRITING FINAL RESULT FILES\n{'=' * 78}")
    for rq, (desc, _, _) in A.RQS.items():
        src = C.RESULTS_DIR / f"{rq.lower()}_pandas.csv"
        if not src.exists():
            continue
        df = pd.read_csv(src)
        df.to_csv(C.RESULTS_DIR / f"{rq.lower()}.csv", index=False)
        print(f"  written: results/{rq.lower()}.csv  ({len(df)} rows)")

    # ---- the headline numbers, in one place ------------------------------
    # The record counts are read from the artefacts that actually produced
    # them, never hardcoded: hardcoding them once meant the summary silently
    # kept the pre-dedup numbers after the duplicate fix changed them.
    rq1 = pd.read_csv(C.RESULTS_DIR / "rq1.csv")

    cleaning = {}
    for engine in ("pandas", "spark"):
        p = C.RESULTS_DIR / f"cleaning_report_{engine}.json"
        if p.exists():
            cleaning[engine] = json.loads(p.read_text(encoding="utf-8"))

    def _pick(*values):
        """First value that is not None."""
        for v in values:
            if v is not None:
                return v
        return None

    src = cleaning.get("pandas") or cleaning.get("spark") or {}
    records_after_cleaning = _pick(src.get("records_after_cleaning"))
    records_indeterminate = _pick(src.get("records_indeterminate_joint"))

    # The decision / joint-flag counts live in the equivalence report, which
    # is produced by the pipeline that measures them.
    eq_path = C.RESULTS_DIR / "equivalence_report.json"
    eq_counts = {}
    if eq_path.exists():
        eq = json.loads(eq_path.read_text(encoding="utf-8"))
        for c in eq.get("comparisons", []):
            if c["quantity"].startswith("Record counts"):
                eq_counts = c.get("pandas", {})
                break

    records_with_decision = _pick(
        eq_counts.get("records_with_decision"), src.get("records_with_decision"))
    records_joint_known = _pick(
        eq_counts.get("records_joint_flag_known"), src.get("records_joint_flag_known"))

    indeterminate_rate_pct = (
        round(records_indeterminate / records_after_cleaning * 100, 2)
        if records_indeterminate and records_after_cleaning else None
    )

    summary = {
        "dataset": {
            "source": "FFIEC 2024 Public One-Year National Loan-Level Dataset",
            "raw_file": str(C.RAW_FILE),
            "records_raw": _pick(src.get("records_raw")),
            "records_after_cleaning": records_after_cleaning,
            "records_with_lender_decision": records_with_decision,
            "records_joint_flag_known": records_joint_known,
            "records_indeterminate_joint": records_indeterminate,
            "indeterminate_rate_pct": indeterminate_rate_pct,
        },
        "denial_rate_formula": "D / (O + A + D) with O=action_taken 1, A=2, D=3",
        "rq1_headline": rq1.to_dict("records"),
    }
    out = C.RESULTS_DIR / "analysis_report.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"  written: results/analysis_report.json")
    print()
    print("RQ1 headline:")
    print(rq1.to_string(index=False))


if __name__ == "__main__":
    main()
