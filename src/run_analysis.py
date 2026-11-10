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
    rq1 = pd.read_csv(C.RESULTS_DIR / "rq1.csv")
    summary = {
        "dataset": {
            "source": "FFIEC 2024 Public One-Year National Loan-Level Dataset",
            "raw_file": str(C.RAW_FILE),
            "records_raw": 12_259_199,
            "records_after_cleaning": 12_251_439,
            "records_with_lender_decision": 8_654_559,
            "records_joint_flag_known": 11_093_946,
            "records_indeterminate_joint": 1_157_493,
            "indeterminate_rate_pct": round(1_157_493 / 12_251_439 * 100, 2),
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
