"""
ablation_protected.py — isolate the cost of removing the protected
characteristics, holding everything else fixed.

Why this script exists
----------------------
The report previously stated that "removing the protected characteristics
cost roughly 0.08 of ROC-AUC", comparing the v1 model (0.7742, random
stratified split, 74 features *including* the protected ones) against the
v2 model (0.6943, GroupShuffleSplit by LEI, 44 features without them).

That comparison confounds three separate changes at once:

    1. removing the protected attributes,
    2. changing the split from random-stratified to grouped-by-lender,
    3. (partly) a different sample draw.

So the 0.08 gap cannot be attributed to the protected attributes.

This script runs a clean ablation: the *same* rows, the *same* split by
LEI, the *same* hyper-parameters, the *same* seed.  The only thing that
changes between the two arms is whether the protected characteristics are
in the feature set.

It also reports the v1-style random-stratified split for both arms, so the
split effect and the feature effect can be read separately.

Output
------
    results/ablation_protected.json
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C

ROW_CAP = 2_000_000
SEED = 20240101

OUT_JSON = C.RESULTS_DIR / "ablation_protected.json"

#: The protected characteristics and their proxies.  These are the columns
#: that the instructor asked to keep out of the model.
PROTECTED = [
    "applicant_sex",
    "co_applicant_sex",
    "derived_sex",
    "applicant_ethnicity_1",
    "applicant_ethnicity_2",
    "applicant_ethnicity_3",
    "applicant_ethnicity_4",
    "applicant_ethnicity_5",
    "co_applicant_ethnicity_1",
    "co_applicant_ethnicity_2",
    "co_applicant_ethnicity_3",
    "co_applicant_ethnicity_4",
    "co_applicant_ethnicity_5",
    "applicant_race_1",
    "applicant_race_2",
    "applicant_race_3",
    "applicant_race_4",
    "applicant_race_5",
    "co_applicant_race_1",
    "co_applicant_race_2",
    "co_applicant_race_3",
    "co_applicant_race_4",
    "co_applicant_race_5",
    "tract_minority_population_percent",
]


def _load_frame() -> pd.DataFrame:
    """Load the modelling rows *plus* every protected column.

    Everything is loaded once; the two arms then select their feature
    subsets from the same frame, so the rows are provably identical.
    """
    import predictive as P

    original_read = P.READ_COLUMNS
    original_num = P.NUMERIC_FEATURES
    original_cats = P.CATEGORICAL_FEATURES
    original_keep = P.KEEP_EXTRA_COLUMNS

    P.NUMERIC_FEATURES = list(original_num)
    P.CATEGORICAL_FEATURES = list(original_cats)
    P.KEEP_EXTRA_COLUMNS = ["lei"] + PROTECTED
    P.READ_COLUMNS = list(dict.fromkeys(
        list(original_num)
        + [c for c in original_cats
           if c not in ("property_ownership", "applicant_age_band", "dti_band")]
        + ["is_denied", "has_lender_decision", "applicant_age",
           "dti_band_order", "lei"]
        + PROTECTED))

    try:
        df = P.load_features(cap=ROW_CAP)
    finally:
        P.READ_COLUMNS = original_read
        P.NUMERIC_FEATURES = original_num
        P.CATEGORICAL_FEATURES = original_cats
        P.KEEP_EXTRA_COLUMNS = original_keep
    return df


def _build(df: pd.DataFrame, num: list[str], cats: list[str]):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    real_cats = [c for c in cats
                 if c not in ("property_ownership", "applicant_age_band", "dti_band")]
    nums = [c for c in num if c in df.columns]
    cats = [c for c in real_cats if c in df.columns]

    numeric_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
        ("scale", StandardScaler()),
    ])
    cat_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])

    transformers = []
    if nums:
        transformers.append(("num", numeric_pipe, nums))
    if cats:
        transformers.append(("cat", cat_pipe, cats))

    ct = ColumnTransformer(transformers, remainder="drop")
    X = ct.fit_transform(df)
    if hasattr(X, "toarray"):
        X = X.toarray()
    names = list(ct.get_feature_names_out())
    y = df["is_denied"].astype(int).to_numpy()
    return X, names, y


def _fit_eval(X_train, y_train, X_test, y_test):
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    clf = LogisticRegression(C=0.1, solver="liblinear", max_iter=1000,
                             random_state=SEED)
    clf.fit(X_train, y_train)
    p = clf.predict_proba(X_test)[:, 1]
    return {
        "roc_auc": float(roc_auc_score(y_test, p)),
        "n_features": int(X_train.shape[1]),
    }


def main() -> None:
    import predictive as P

    print("=" * 74)
    print("ABLATION: what do the protected characteristics actually cost?")
    print("=" * 74)

    t0 = time.perf_counter()
    df = _load_frame()
    print(f"loaded {len(df):,} rows in {time.perf_counter() - t0:.1f}s")

    all_num = [c for c in P.NUMERIC_FEATURES if c in df.columns]
    all_cats = [c for c in P.CATEGORICAL_FEATURES if c in df.columns]

    removed_num = [c for c in all_num if c in PROTECTED]
    removed_cats = [c for c in all_cats if c in PROTECTED]
    print(f"protected numeric columns : {len(removed_num)}")
    print(f"protected categorical cols : {len(removed_cats)}")

    kept_num = [c for c in all_num if c not in PROTECTED]
    kept_cats = [c for c in all_cats if c not in PROTECTED]

    # ---- the two splits -------------------------------------------------
    from sklearn.model_selection import GroupShuffleSplit, train_test_split

    groups = df["lei"].astype("string").to_numpy()
    idx = np.arange(len(df))

    results = {}

    # ---- (a) GroupShuffleSplit by LEI  (the split the report uses) -------
    print("\n--- arm A: split by LEI (the report's split) ---")
    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=SEED)
    tr_idx, te_idx = next(gss.split(idx, groups=groups))

    # (a1) without the protected attributes  == the reported model
    X, names, y = _build(df, kept_num, kept_cats)
    a1 = _fit_eval(X[tr_idx], y[tr_idx], X[te_idx], y[te_idx])
    print(f"  without protected : AUC {a1['roc_auc']:.4f} "
          f"({a1['n_features']} features)")
    del X

    # (a2) with the protected attributes, same rows and same split
    Xp, names_p, yp = _build(df, all_num, all_cats)
    a2 = _fit_eval(Xp[tr_idx], yp[tr_idx], Xp[te_idx], yp[te_idx])
    print(f"  with protected    : AUC {a2['roc_auc']:.4f} "
          f"({a2['n_features']} features)")
    del Xp

    results["group_split_by_lei"] = {
        "without_protected": a1,
        "with_protected": a2,
        "auc_cost_of_removal": a2["roc_auc"] - a1["roc_auc"],
        "n_train": int(len(tr_idx)),
        "n_test": int(len(te_idx)),
    }

    # ---- (b) random stratified split (the v1 split) ---------------------
    print("\n--- arm B: random stratified split (the earlier split) ---")
    tr2, te2 = train_test_split(idx, test_size=0.20, random_state=SEED,
                                stratify=y)

    X, _, y = _build(df, kept_num, kept_cats)
    b1 = _fit_eval(X[tr2], y[tr2], X[te2], y[te2])
    print(f"  without protected : AUC {b1['roc_auc']:.4f}")
    del X

    Xp, _, yp = _build(df, all_num, all_cats)
    b2 = _fit_eval(Xp[tr2], yp[tr2], Xp[te2], yp[te2])
    print(f"  with protected    : AUC {b2['roc_auc']:.4f}")
    del Xp

    results["random_stratified_split"] = {
        "without_protected": b1,
        "with_protected": b2,
        "auc_cost_of_removal": b2["roc_auc"] - b1["roc_auc"],
    }

    # ---- summary --------------------------------------------------------
    gs = results["group_split_by_lei"]
    rs = results["random_stratified_split"]
    summary = {
        "feature_effect_same_split_grouped":
            gs["auc_cost_of_removal"],
        "feature_effect_same_split_random":
            rs["auc_cost_of_removal"],
        "split_effect_without_protected":
            rs["without_protected"]["roc_auc"]
            - gs["without_protected"]["roc_auc"],
        "split_effect_with_protected":
            rs["with_protected"]["roc_auc"]
            - gs["with_protected"]["roc_auc"],
        "note": (
            "The first two numbers are the only ones that identify the cost "
            "of removing the protected characteristics, because the rows, "
            "the split and the hyper-parameters are identical in each "
            "comparison. The split effect is reported separately so that the "
            "two are not confounded."
        ),
    }
    results["summary"] = summary

    print("\n" + "=" * 74)
    print(f"cost of removing protected attributes (grouped split): "
          f"{summary['feature_effect_same_split_grouped']:+.4f} AUC")
    print(f"cost of removing protected attributes (random split)  : "
          f"{summary['feature_effect_same_split_random']:+.4f} AUC")
    print(f"effect of the split itself, without protected attrs    : "
          f"{summary['split_effect_without_protected']:+.4f} AUC")
    print(f"effect of the split itself, with protected attrs       : "
          f"{summary['split_effect_with_protected']:+.4f} AUC")
    print("=" * 74)

    results["config"] = {
        "row_cap": ROW_CAP,
        "seed": SEED,
        "n_rows": int(len(df)),
        "protected_columns": PROTECTED,
    }

    OUT_JSON.write_text(json.dumps(results, indent=2, default=str),
                        encoding="utf-8")
    print(f"\nWritten: {OUT_JSON}")


if __name__ == "__main__":
    main()
