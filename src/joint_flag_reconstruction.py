"""
joint_flag_reconstruction.py — reconstruct the CFPB's joint definition
from the raw HMDA fields and compare it with the derived flag.

Why this script exists
-----------------------
The report previously said that the derived joint-application flag "is
also consistent with HMDA's own `derived_sex` field, which independently
classifies records as Joint".  That is a weaker claim than it sounds, and
it needs to be stated precisely:

* `derived_sex` is **not** "does this application have a co-applicant".
  HMDA sets it to `Joint` only when the co-applicant's sex differs from
  the applicant's sex --- that is, when the pair is male/female.  A joint
  application between two borrowers of the same sex is recorded as
  `Male` or `Female`, not as `Joint`.

So `derived_sex == "Joint"` is a *subset* of the derived flag, not an
independent confirmation of it.  The two disagree on every same-sex
joint application, which is a large group.

What this script does
---------------------
It reconstructs the CFPB's own definition from the raw file:

    joint_derived = 1  if  applicant_sex != co_applicant_sex
                    and both are known
                    else 0 / not-applicable

and then compares it with:

1. the flag this project derives,
2. `derived_sex`,
3. and the *independent* `co_applicant_age` witness.

The point is to state exactly how far the project's definition is from
the CFPB's, and how much of the difference is explained by the
same-sex cases.

Output
------
    results/joint_flag_reconstruction.json
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C

OUT_JSON = C.RESULTS_DIR / "joint_flag_reconstruction.json"

#: HMDA codes for sex.
SEX_MALE = "1"
SEX_FEMALE = "2"
#: 4 = "Not applicable", 5 = "Not collected", 9 = blank.
SEX_UNKNOWN = {"4", "5", "9", ""}

#: HMDA codes for `derived_sex`.
DERIVED_JOINT = "Joint"
DERIVED_MALE = "Male"
DERIVED_FEMALE = "Female"

#: `co_applicant_age` sentinel for "no co-applicant".
AGE_NO_CO_APPLICANT = "9999"


def _main() -> None:
    import glob

    files = sorted(glob.glob(str(C.CLEAN_PARQUET / "*.parquet")))
    if not files:
        raise SystemExit(f"no Parquet files under {C.CLEAN_PARQUET}")

    cols = ["applicant_sex", "co_applicant_sex", "derived_sex",
            "co_applicant_age", "joint_flag", "action_taken"]

    parts = []
    for f in files:
        parts.append(pd.read_parquet(f, columns=cols))
    df = pd.concat(parts, ignore_index=True)
    print(f"loaded {len(df):,} cleaned records")

    # ---- restrict to the analysis population ----------------------------
    dec = df[df["action_taken"].isin([1, 2, 3])].copy()
    print(f"{len(dec):,} records with a lender decision")

    a_sex = dec["applicant_sex"].astype("string").str.strip()
    c_sex = dec["co_applicant_sex"].astype("string").str.strip()

    known_a = a_sex.isin([SEX_MALE, SEX_FEMALE])
    known_c = c_sex.isin([SEX_MALE, SEX_FEMALE])

    # ---- the CFPB-style definition --------------------------------------
    # "Joint" means the co-applicant's sex differs from the applicant's.
    cpb_joint = (known_a & known_c & (a_sex != c_sex)).astype("int")
    determinable = known_a & known_c
    same_sex_pair = (known_a & known_c & (a_sex == c_sex)).astype("int")

    flag = dec["joint_flag"].astype("Int64")

    # ---- comparison 1: our flag vs the CFPB-style definition ------------
    known_flag = flag.notna()
    both = determinable & known_flag

    flag_np = flag.astype("float").to_numpy()
    cpb_np = cpb_joint.to_numpy()
    both_np = both.to_numpy()

    # Compare only on the rows where both sides are defined.
    idx = np.flatnonzero(both_np)
    agree = int((cpb_np[idx] == flag_np[idx]).sum())
    n_both = int(len(idx))

    # Of the records where the two disagree, how many are same-sex pairs?
    dis = idx[cpb_np[idx] != flag_np[idx]]
    n_disagree = int(len(dis))
    n_disagree_same_sex = int(same_sex_pair.to_numpy()[dis].sum())

    # ---- comparison 2: derived_sex --------------------------------------
    ds = dec["derived_sex"].astype("string").str.strip()
    ds_joint = (ds == DERIVED_JOINT).astype(int)
    ds_male = (ds == DERIVED_MALE).astype(int)
    ds_female = (ds == DERIVED_FEMALE).astype(int)

    # Within the records this project calls joint, how many does HMDA
    # describe as "Joint" and how many as Male/Female?
    is_joint_np = np.nan_to_num((flag == 1).astype("float").to_numpy()) > 0.5
    n_ours_joint = int(is_joint_np.sum())
    n_ours_joint_derived_joint = int((is_joint_np & (ds_joint.to_numpy() == 1)).sum())
    n_ours_joint_same_sex = int((is_joint_np & (same_sex_pair.to_numpy() == 1)).sum())

    # ---- comparison 3: the independent age witness ----------------------
    age = dec["co_applicant_age"].astype("string").str.strip()
    age_says_co = (age != AGE_NO_CO_APPLICANT) & age.notna() & (age != "")
    witness = age_says_co & known_flag
    w_np = witness.to_numpy()
    widx = np.flatnonzero(w_np)
    n_witness = int(len(widx))
    n_witness_agree = int((age_says_co.to_numpy()[widx]
                            == (flag_np[widx] == 1)).sum())

    out = {
        "population": {
            "cleaned_records": int(len(df)),
            "records_with_decision": int(len(dec)),
            "records_joint_flag_known": int(known_flag.sum()),
            "records_with_both_sexes_known": int(determinable.sum()),
        },
        "our_flag_vs_cfpb_style_definition": {
            "note": (
                "The CFPB's 'Joint' label means the co-applicant's sex "
                "differs from the applicant's.  Where both sexes are "
                "known, that is a well-defined subset of the joint "
                "applications."
            ),
            "n_compared": n_both,
            "n_agree": agree,
            "pct_agree": round(agree / n_both * 100, 4) if n_both else None,
            "n_disagree": n_disagree,
            "n_disagree_that_are_same_sex_pairs": n_disagree_same_sex,
            "pct_of_disagreements_explained_by_same_sex":
                (round(n_disagree_same_sex / n_disagree * 100, 2)
                 if n_disagree else None),
        },
        "derived_sex_is_not_the_same_thing": {
            "note": (
                "derived_sex = 'Joint' marks a male/female pair.  It is a "
                "subset of the joint applications, not an independent "
                "confirmation of them: a joint application between two "
                "borrowers of the same sex is recorded as Male or Female."
            ),
            "n_records_we_call_joint": n_ours_joint,
            "n_ours_joint_that_hmda_calls_derived_Joint":
                n_ours_joint_derived_joint,
            "n_ours_joint_that_are_same_sex_pairs": n_ours_joint_same_sex,
            "pct_of_our_joint_called_derived_Joint":
                (round(n_ours_joint_derived_joint / n_ours_joint * 100, 2)
                 if n_ours_joint else None),
            "pct_of_our_joint_that_are_same_sex_pairs":
                (round(n_ours_joint_same_sex / n_ours_joint * 100, 2)
                 if n_ours_joint else None),
            "derived_sex_counts": {k: int(v) for k, v in
                                   ds.value_counts().items()},
        },
        "independent_age_witness": {
            "note": (
                "co_applicant_age = 9999 means 'no co-applicant'.  This "
                "field is not used by the rule, so it is the only "
                "independent witness available."
            ),
            "n_compared": n_witness,
            "n_agree": n_witness_agree,
            "n_disagree": n_witness - n_witness_agree,
            "pct_agree": (round(n_witness_agree / n_witness * 100, 4)
                          if n_witness else None),
            "pct_disagree": (round((n_witness - n_witness_agree)
                                    / n_witness * 100, 4) if n_witness else None),
        },
    }

    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    print()
    print("=" * 74)
    print("JOINT FLAG RECONSTRUCTION")
    print("=" * 74)
    c = out["our_flag_vs_cfpb_style_definition"]
    print(f"  our flag vs CFPB-style definition: {c['n_agree']:,}/{c['n_compared']:,} "
          f"agree ({c['pct_agree']}%)")
    print(f"    of {c['n_disagree']:,} disagreements, "
          f"{c['n_disagree_that_are_same_sex_pairs']:,} "
          f"({c['pct_of_disagreements_explained_by_same_sex']}%) are same-sex pairs")
    d = out["derived_sex_is_not_the_same_thing"]
    print(f"  of {d['n_records_we_call_joint']:,} records we call joint, "
          f"HMDA calls derived_sex='Joint' for {d['n_ours_joint_that_hmda_calls_derived_Joint']:,} "
          f"({d['pct_of_our_joint_called_derived_Joint']}%)")
    print(f"    same-sex pairs among them: "
          f"{d['n_ours_joint_that_are_same_sex_pairs']:,} "
          f"({d['pct_of_our_joint_that_are_same_sex_pairs']}%)")
    w = out["independent_age_witness"]
    print(f"  independent age witness: {w['n_agree']:,}/{w['n_compared']:,} agree "
          f"({w['pct_agree']}%), disagree on {w['n_disagree']:,} ({w['pct_disagree']}%)")
    print("=" * 74)
    print(f"Written: {OUT_JSON}")


if __name__ == "__main__":
    _main()
