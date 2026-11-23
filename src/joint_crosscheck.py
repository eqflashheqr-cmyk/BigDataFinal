"""
joint_crosscheck.py — Cross-validate the inferred `joint_flag` against the
five independent co-applicant fields in HMDA.

Why this exists
---------------
The instructor's review asked for two things that the original report did
not deliver:

1. `joint_flag` was inferred from **four** fields (co-applicant ethnicity,
   race, sex and credit-score type). `co_applicant_age` was not used even
   though HMDA documents `9999` as "no co-applicant" for that field. This
   script adds it as a fifth, independent field.

2. No cross-check table existed. For each record we now ask: does every
   field agree about whether a co-applicant exists, and when they do not,
   how many records are affected? The distinction the review asked for is
   made explicit:

   * *contradiction* — one field says a co-applicant exists while another
     says there is none. This is a genuine logical inconsistency.
   * *not-applicable vs absent* — one field says "not applicable" (the
     co-applicant's ethnicity was not collected) while another says
     "absent" (there is no co-applicant at all). These are different
     statements, not contradictions, and they are counted separately.

The fifth field (`co_applicant_age`) is used **only as an independent
validator**. The report's `joint_flag` definition is left unchanged so the
main results stay comparable with the version already reviewed; what this
script establishes is whether that definition is *corroborated*.

Resource use
------------
Reads only the seven columns it needs from the cleaned Parquet file, in
row-group batches, so peak memory stays in the low hundreds of MB and the
job is single-threaded.

Usage
-----
    python src/joint_crosscheck.py
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C

OUT_JSON = C.RESULTS_DIR / "joint_crosscheck.json"

#: The five co-applicant fields HMDA provides, with the code that means
#: "no co-applicant" and the codes that mean "not applicable".
FIELDS = [
    ("co_applicant_ethnicity_1", "5", ("4",)),
    ("co_applicant_race_1", "8", ("7",)),
    ("co_applicant_sex", "5", ("4",)),
    ("co_applicant_credit_score_type", "10", ("9", "1111")),
    # Fifth field, added on the instructor's suggestion. HMDA documents
    # 9999 as "no co-applicant" and 8888 as "age not available".
    ("co_applicant_age", "9999", ("8888",)),
]

#: Values that count as "a co-applicant value is present" for each field.
#: For age this is any band other than the two sentinels; for the coded
#: fields it is any code outside {absent, not-applicable}.
PRESENT_CODES = {
    "co_applicant_ethnicity_1": {"1", "2", "3"},
    "co_applicant_race_1": {"1", "2", "3", "4", "5", "6"},
    "co_applicant_sex": {"1", "2"},
    "co_applicant_credit_score_type": {"1", "2", "3", "4", "5", "6", "7", "8"},
}

_META = {f[0]: (f[1], f[2]) for f in FIELDS}


def _classify(col: str, s: pd.Series) -> pd.Series:
    """Return 'present' / 'absent' / 'na' / 'missing' for one field."""
    absent, na = _META[col]
    out = s.astype("string").str.strip()

    res = pd.Series("missing", index=s.index, dtype="object")

    if col in PRESENT_CODES:
        res[out.isin(PRESENT_CODES[col])] = "present"
    else:
        # co_applicant_age: any band other than the sentinels means a
        # co-applicant of that age was reported.
        known = out.notna() & ~out.isin(list(C.SPECIAL_CODES))
        res[known] = "present"

    res[out == absent] = "absent"
    res[out.isin(na)] = "na"
    res[out.isna()] = "missing"
    return res


def main() -> None:
    pq_path = Path(C.CLEAN_PARQUET) / "part-00000.parquet"
    if not pq_path.exists():
        candidates = sorted(Path(C.CLEAN_PARQUET).glob("*.parquet"))
        if not candidates:
            raise SystemExit(f"No Parquet file under {C.CLEAN_PARQUET}")
        pq_path = candidates[0]

    cols = [f[0] for f in FIELDS] + ["joint_flag"]
    pf = pq.ParquetFile(pq_path)

    n_rows = 0
    jf_counts = {"joint": 0, "single": 0, "indeterminate": 0}
    per_field = {c: {"present": 0, "absent": 0, "na": 0, "missing": 0,
                      "flag_joint": 0, "flag_single": 0, "flag_indeterminate": 0,
                      "contradicts": 0} for c, _a, _n in FIELDS}
    pair_counts = {}

    for batch in pf.iter_batches(batch_size=500_000, columns=cols):
        df = batch.to_pandas()
        n_rows += len(df)

        classified = {c: _classify(c, df[c]) for c, _a, _n in FIELDS}

        jf = df["joint_flag"]
        is_joint = (jf == 1)
        is_single = (jf == 0)
        is_indet = jf.isna()
        jf_counts["joint"] += int(is_joint.sum())
        jf_counts["single"] += int(is_single.sum())
        jf_counts["indeterminate"] += int(is_indet.sum())

        for col, _a, _n in FIELDS:
            cls = classified[col]
            d = per_field[col]
            d["present"] += int((cls == "present").sum())
            d["absent"] += int((cls == "absent").sum())
            d["na"] += int((cls == "na").sum())
            d["missing"] += int((cls == "missing").sum())
            d["flag_joint"] += int(((cls == "present") & is_joint).sum())
            d["flag_single"] += int(((cls == "absent") & is_single).sum())
            d["flag_indeterminate"] += int(((cls == "missing") & is_indet).sum())
            # A field claims a co-applicant but the flag says single, or
            # claims none but the flag says joint: a genuine contradiction.
            d["contradicts"] += int(((cls == "present") & is_single).sum())
            d["contradicts"] += int(((cls == "absent") & is_joint).sum())

        names = [f[0] for f in FIELDS]
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = classified[names[i]], classified[names[j]]
                key = f"{names[i]} vs {names[j]}"
                c = pair_counts.setdefault(key, {
                    "both_present": 0, "both_absent": 0,
                    "present_vs_absent": 0, "absent_vs_present": 0,
                    "present_vs_na": 0, "na_vs_present": 0,
                    "absent_vs_na": 0, "na_vs_absent": 0,
                    "at_least_one_unknown": 0,
                })
                c["both_present"] += int(((a == "present") & (b == "present")).sum())
                c["both_absent"] += int(((a == "absent") & (b == "absent")).sum())
                c["present_vs_absent"] += int(((a == "present") & (b == "absent")).sum())
                c["absent_vs_present"] += int(((a == "absent") & (b == "present")).sum())
                c["present_vs_na"] += int(((a == "present") & (b == "na")).sum())
                c["na_vs_present"] += int(((a == "na") & (b == "present")).sum())
                c["absent_vs_na"] += int(((a == "absent") & (b == "na")).sum())
                c["na_vs_absent"] += int(((a == "na") & (b == "absent")).sum())
                c["at_least_one_unknown"] += int(
                    ((a == "missing") | (b == "missing")).sum())

    # ---- assemble -------------------------------------------------------
    field_summary = {}
    for col, absent, na in FIELDS:
        d = per_field[col]
        n = sum(d[k] for k in ("present", "absent", "na", "missing"))
        field_summary[col] = {
            "no_co_applicant_code": absent,
            "not_applicable_codes": list(na),
            "present": d["present"],
            "absent": d["absent"],
            "not_applicable": d["na"],
            "missing_or_unreported": d["missing"],
            "pct_present": round(d["present"] / n * 100, 3),
            "pct_absent": round(d["absent"] / n * 100, 3),
            "pct_not_applicable": round(d["na"] / n * 100, 3),
            "pct_missing": round(d["missing"] / n * 100, 3),
            "agreement_with_joint_flag": {
                "field_present_and_flag_joint": d["flag_joint"],
                "field_absent_and_flag_single": d["flag_single"],
                "field_unreported_and_flag_indeterminate": d["flag_indeterminate"],
                "contradicts_the_flag": d["contradicts"],
            },
        }

    total_contradictions = sum(
        v["agreement_with_joint_flag"]["contradicts_the_flag"]
        for v in field_summary.values())

    pair_summary = {}
    for key, c in pair_counts.items():
        contradictory = c["present_vs_absent"] + c["absent_vs_present"]
        na_vs = (c["present_vs_na"] + c["na_vs_present"]
                 + c["absent_vs_na"] + c["na_vs_absent"])
        pair_summary[key] = {
            "both_present": c["both_present"],
            "both_absent": c["both_absent"],
            "contradiction": contradictory,
            "not_applicable_vs_decided": na_vs,
            "at_least_one_field_unreported": c["at_least_one_unknown"],
            "pct_contradiction": round(contradictory / n_rows * 100, 4),
        }

    result = {
        "source": str(pq_path),
        "rows_examined": n_rows,
        "note": (
            "The five co-applicant fields are cross-checked against each other "
            "and against the shipped joint_flag. 'contradiction' means one "
            "field asserts a co-applicant while another asserts none. "
            "'not_applicable_vs_decided' means one field says the attribute "
            "was not applicable (or not collected) while another gives a "
            "definite answer - a different statement, not a contradiction."
        ),
        "joint_flag_distribution": {
            "joint": jf_counts["joint"],
            "single": jf_counts["single"],
            "indeterminate": jf_counts["indeterminate"],
            "pct_indeterminate": round(jf_counts["indeterminate"] / n_rows * 100, 3),
        },
        "fields": field_summary,
        "pairwise": pair_summary,
        "total_field_level_contradictions": int(total_contradictions),
        "total_field_level_contradictions_pct": round(
            total_contradictions / n_rows * 100, 4),
    }

    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("=" * 78)
    print("JOINT FLAG CROSS-CHECK (5 co-applicant fields)")
    print("=" * 78)
    print(f"  rows examined: {n_rows:,}")
    print(f"  joint={jf_counts['joint']:,}  single={jf_counts['single']:,}  "
          f"indeterminate={jf_counts['indeterminate']:,} "
          f"({result['joint_flag_distribution']['pct_indeterminate']}%)")
    print()
    print(f"  {'field':34s} {'present':>12s} {'absent':>12s} {'N/A':>10s} {'missing':>10s}")
    for col, v in field_summary.items():
        print(f"  {col:34s} {v['present']:12,d} {v['absent']:12,d} "
              f"{v['not_applicable']:10,d} {v['missing_or_unreported']:10,d}")
    print()
    print("  agreement with the shipped joint_flag:")
    for col, v in field_summary.items():
        a = v["agreement_with_joint_flag"]
        print(f"    {col:34s} joint={a['field_present_and_flag_joint']:11,d} "
              f"single={a['field_absent_and_flag_single']:11,d} "
              f"contradicts={a['contradicts_the_flag']:8,d}")
    print()
    print(f"  total field-level contradictions: {total_contradictions:,} "
          f"({result['total_field_level_contradictions_pct']}%)")
    print()
    print("  pairwise disagreements (pct of all rows):")
    for key, v in pair_summary.items():
        if v["contradiction"] or v["not_applicable_vs_decided"]:
            print(f"    {key:66s} contra={v['contradiction']:7,d} "
                  f"({v['pct_contradiction']:.4f}%)  na_vs_decided={v['not_applicable_vs_decided']:8,d}")
    print()
    print(f"  Written: {OUT_JSON}")


if __name__ == "__main__":
    main()
