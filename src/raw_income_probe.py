"""
raw_income_probe.py — How extreme is `income` in the RAW file?

The report claimed that `income` reaches 999,999,999 (thousands of USD) in
the dataset and that this is a "genuine outlier" whose removal would shrink
the denial gap. The value does not appear in the *cleaned* dataset, so it
must either have been removed during cleaning or the claim is wrong.

This script settles it by streaming the raw pipe-delimited file and
counting the extreme values. It reads one line at a time and keeps only
counters, so the memory cost is a few kilobytes and the disk cost is
nothing. It is slow in wall-clock terms because the raw file is 4.3 GB of
text, but it never loads more than a line.

Usage
-----
    python src/raw_income_probe.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C

OUT_JSON = C.RESULTS_DIR / "raw_income_probe.json"

#: HMDA column order (99 fields), 0-based indices.
INCOME_IDX = 45
LOAN_AMOUNT_IDX = 21
ACTION_TAKEN_IDX = 12


def main() -> None:
    raw = C.RAW_FILE
    if not raw.exists():
        raise SystemExit(f"Raw file not found: {raw}")

    n = 0
    n_with_income = 0
    n_sentinel = 0
    n_sentinel_dollars = 0
    n_negative_income = 0
    max_income = None
    max_income_line_no = None
    # The five largest income values, with their counts.
    top_income = {}
    # Denials vs originations among the extreme records.
    extreme_action = {}
    sentinel_action = {}

    with raw.open("r", encoding="latin-1", errors="replace") as fh:
        for line_no, line in enumerate(fh):
            if line_no == 0:
                continue          # header
            n += 1
            parts = line.rstrip("\n").split("|")
            if len(parts) <= INCOME_IDX:
                continue
            raw_income = parts[INCOME_IDX].strip()
            if not raw_income:
                continue
            try:
                inc = int(raw_income)
            except ValueError:
                continue
            n_with_income += 1
            if inc < 0:
                n_negative_income += 1
                continue
            if inc == 999_999_999:
                n_sentinel += 1
                at = parts[ACTION_TAKEN_IDX].strip() if len(parts) > ACTION_TAKEN_IDX else "?"
                sentinel_action[at] = sentinel_action.get(at, 0) + 1
            elif inc == 999_999_999_000:
                n_sentinel_dollars += 1
            if max_income is None or inc > max_income:
                max_income = inc
                max_income_line_no = line_no
            top_income[inc] = top_income.get(inc, 0) + 1
            if inc >= 1_000_000:      # a million thousands = $1 billion
                at = parts[ACTION_TAKEN_IDX].strip() if len(parts) > ACTION_TAKEN_IDX else "?"
                extreme_action[at] = extreme_action.get(at, 0) + 1

    top10 = sorted(top_income.items(), key=lambda kv: -kv[0])[:10]

    result = {
        "raw_file": str(raw),
        "lines_scanned": n,
        "records_with_a_numeric_income": n_with_income,
        "negative_income_records": n_negative_income,
        "income_equals_999999999_thousands": n_sentinel,
        "income_equals_999999999_dollars": n_sentinel_dollars,
        "max_income_thousands": max_income,
        "max_income_line_number": max_income_line_no,
        "records_with_income_at_least_1e6_thousands": sum(extreme_action.values()),
        "extreme_record_action_taken": extreme_action,
        "sentinel_record_action_taken": sentinel_action,
        "ten_largest_income_values": [{"income_thousands": int(k), "count": int(v)}
                                      for k, v in top10],
        "note": (
            "action_taken codes: 1 originated, 2 approved not accepted, "
            "3 denied, 4 withdrawn, 5 file closed, 6 purchased, "
            "7 preapproval denied, 8 preapproval approved."
        ),
    }

    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("=" * 78)
    print("RAW FILE — INCOME EXTREMES")
    print("=" * 78)
    print(f"  lines scanned                : {n:,}")
    print(f"  records with a numeric income : {n_with_income:,}")
    print(f"  negative income               : {n_negative_income:,}")
    print(f"  income == 999,999,999 (k$)    : {n_sentinel:,}")
    print(f"  max income (k$)              : {max_income:,}")
    print(f"  income >= 1,000,000 (k$)     : {sum(extreme_action.values()):,}")
    print("  action_taken of the extreme records:")
    for k, v in sorted(extreme_action.items(), key=lambda kv: -kv[1]):
        print(f"    {k:>3s} : {v:,}")
    print("  ten largest income values:")
    for row in result["ten_largest_income_values"]:
        print(f"    {row['income_thousands']:>15,} k$  x {row['count']:,}")
    print()
    print(f"  Written: {OUT_JSON}")


if __name__ == "__main__":
    main()
