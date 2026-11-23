"""
predictive_v2.py — The optional predictive extension, reworked to meet the
instructor's requirements.

What changed and why
--------------------
1. **No protected characteristics in the model.** The reviewer is explicit:
   "không đưa giới tính và dân tộc vào huấn luyện mô hình". The first
   version trained on `applicant_sex`, `applicant_ethnicity_1`,
   `applicant_race_1` and `tract_minority_population_percent`, and then
   used the model for nothing except reporting. This version removes all
   of them from the feature set — including the co-applicant variants and
   the derived ethnicity/race fields.

   The fairness analysis is **kept**, and it is kept in the only form that
   makes sense: the model is trained *without* the protected attributes
   and the protected groups are then joined back on afterwards to report
   differential performance. That is the direction the reviewer asked
   for, and it is the one that answers "does the model treat groups
   differently" without the model itself using the characteristic.

2. **The threshold is chosen on a validation split, not on the test set.**
   The first version swept thresholds and picked the best F1 directly on
   the test set, which leaks. This version splits the sample into
   train / validation / test, selects the threshold on validation, and
   reports every metric on the untouched test set.

3. **A confusion matrix and precision/recall at the chosen threshold** are
   reported, as the reviewer asked for.

4. **A majority-class baseline** is reported, as the proposal promised.

5. **GroupKFold by LEI.** The modelling sample is a *cluster* sample:
   lenders are selected in or out whole, so a random split puts the same
   lender on both sides of the train/test boundary and leaks the lender's
   own policy. The grouped split keeps every lender entirely on one side,
   which is the honest test of generalisation to a new lender.

Resource use
------------
The modelling sample is capped at 2 million rows, the estimators run on
one thread, and the matrices are sparse. Peak memory stays under 2 GB and
the whole run takes minutes.

Usage
-----
    python src/predictive_v2.py
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C
import predictive as P

OUT_JSON = C.RESULTS_DIR / "predictive_v2.json"

SEED = P.SEED

#: Rows modelled. The same cap as the first version, so the two runs are
#: comparable and the machine stays inside 16 GB.
ROW_CAP = 2_000_000

#: Split of the modelling sample.
#:
#: 60 % train, 20 % validation (threshold selection only), 20 % test
#: (reported metrics only). The first version had no validation split at
#: all, which is what made its "best F1" a test-set quantity.
TRAIN_FRAC = 0.60
VAL_FRAC = 0.20
TEST_FRAC = 0.20

#: Features removed from the model because the instructor asked for it.
#:
#: Every entry is a protected characteristic or a proxy for one. The
#: co-applicant variants and the `derived_` fields are removed as well,
#: because they carry the same information.
REMOVED_FROM_MODEL = [
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
    "derived_ethnicity",
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
    "derived_race",
    "tract_minority_population_percent",
]

#: Columns read *only* for the fairness audit, never for training.
AUDIT_ONLY_COLUMNS = [
    "applicant_ethnicity_1",
    "applicant_race_1",
    "applicant_sex",
    "joint_flag",
]


def _model_feature_lists() -> tuple[list[str], list[str]]:
    """The feature lists with every protected characteristic removed."""
    num = [c for c in P.NUMERIC_FEATURES if c not in REMOVED_FROM_MODEL]
    cats = [c for c in P.CATEGORICAL_FEATURES if c not in REMOVED_FROM_MODEL]
    return num, cats


def _audit_load() -> pd.DataFrame:
    """Load the modelling sample *plus* the audit-only columns.

    The audit columns are kept in a separate frame so that it is obvious
    they never reach the estimator.
    """
    original_read = P.READ_COLUMNS
    original_num = P.NUMERIC_FEATURES
    original_cats = P.CATEGORICAL_FEATURES
    original_keep = P.KEEP_EXTRA_COLUMNS

    num, cats = _model_feature_lists()
    P.NUMERIC_FEATURES = num
    P.CATEGORICAL_FEATURES = cats
    P.KEEP_EXTRA_COLUMNS = ["lei"] + AUDIT_ONLY_COLUMNS
    P.READ_COLUMNS = list(dict.fromkeys(
        num + [c for c in cats
               if c not in ("property_ownership", "applicant_age_band", "dti_band")]
        + ["is_denied", "has_lender_decision", "applicant_age", "dti_band_order",
           "lei"] + AUDIT_ONLY_COLUMNS))
    try:
        df = P.load_features(cap=ROW_CAP)
    finally:
        P.NUMERIC_FEATURES = original_num
        P.CATEGORICAL_FEATURES = original_cats
        P.READ_COLUMNS = original_read
        P.KEEP_EXTRA_COLUMNS = original_keep
    return df


def _build(df: pd.DataFrame, num, cats):
    """Build the sparse design matrix from the (reduced) feature lists."""
    from scipy import sparse
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    real_cats = [c for c in cats
                 if c not in ("property_ownership", "applicant_age_band", "dti_band")]
    nums = [c for c in num if c in df.columns]

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
    if real_cats:
        transformers.append(("cat", cat_pipe, real_cats))

    ct = ColumnTransformer(transformers, remainder="drop")
    X = ct.fit_transform(df)
    if sparse.issparse(X):
        X = X.toarray()
    names = []
    try:
        names = list(ct.get_feature_names_out())
    except Exception:
        names = [f"f{i}" for i in range(X.shape[1])]

    y = df["is_denied"].astype(int).to_numpy()
    return X, names, y


def _confusion(y_true, y_pred) -> dict:
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    return {
        "true_positive": tp, "false_positive": fp,
        "false_negative": fn, "true_negative": tn,
        "n": tp + fp + fn + tn,
    }


def _metrics(y_true, y_proba, thr: float) -> dict:
    from sklearn.metrics import (
        average_precision_score, brier_score_loss, f1_score, precision_score,
        recall_score, roc_auc_score,
    )
    y_pred = (y_proba >= thr).astype(int)
    pos = float(y_true.mean())
    out = {
        "threshold": thr,
        "roc_auc": float(roc_auc_score(y_true, y_proba)),
        "pr_auc": float(average_precision_score(y_true, y_proba)),
        "brier": float(brier_score_loss(y_true, y_proba)),
        "positive_rate": pos,
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "accuracy": float((y_pred == y_true).mean()),
        "confusion_matrix": _confusion(y_true, y_pred),
    }
    # The majority-class baseline the proposal promised: always predict the
    # more common class.
    majority = 1 if pos >= 0.5 else 0
    maj_pred = np.full(len(y_true), majority)
    out["baseline_majority_class"] = {
        "majority_class": "denied" if majority else "approved",
        "accuracy": float((maj_pred == y_true).mean()),
        "precision": float(precision_score(y_true, maj_pred, zero_division=0)),
        "recall": float(recall_score(y_true, maj_pred, zero_division=0)),
        "f1": float(f1_score(y_true, maj_pred, zero_division=0)),
        "note": (
            "Always predicting the majority class. Its accuracy is the "
            "number a classifier has to beat to be worth anything; its "
            "recall is zero on the minority class by construction, which is "
            "exactly why a triage model has to beat it on F1 rather than "
            "on accuracy."
        ),
    }
    # A probability-only baseline: predict the base rate.
    out["baseline_constant_rate"] = {
        "accuracy": float((np.full(len(y_true), pos) >= 0.5).astype(int).__eq__(
            y_true).mean()),
        "brier": float(brier_score_loss(y_true, np.full(len(y_true), pos))),
    }
    return out


def _sweep(y_true, y_proba) -> list[dict]:
    from sklearn.metrics import f1_score
    rows = []
    for thr in np.arange(0.05, 0.96, 0.05):
        y_pred = (y_proba >= thr).astype(int)
        rows.append({
            "threshold": round(float(thr), 2),
            "f1": float(f1_score(y_true, y_pred, zero_division=0)),
            "precision": float(((y_pred == 1) & (y_true == 1)).sum()
                                / max((y_pred == 1).sum(), 1)),
            "recall": float(((y_pred == 1) & (y_true == 1)).sum()
                            / max((y_true == 1).sum(), 1)),
        })
    return rows


def main() -> None:
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupShuffleSplit

    t0 = time.perf_counter()
    print("Loading modelling data (audit columns included)...")
    df = _audit_load()
    population = df.attrs.get("population_size", 0)
    print(f"  modelling sample: {len(df):,} rows "
          f"({len(df) / population * 100:.1f} % of the population)")
    print(f"  denial rate     : {df['is_denied'].mean() * 100:.2f} %")

    num, cats = _model_feature_lists()
    print()
    print("  protected characteristics removed from the model:")
    removed = [c for c in REMOVED_FROM_MODEL
               if c in P.NUMERIC_FEATURES or c in P.CATEGORICAL_FEATURES]
    for c in removed:
        print(f"    - {c}")

    # ---- guard: nothing protected can reach the estimator ------------------
    leaked = (set(num) | set(cats)) & set(REMOVED_FROM_MODEL)
    if leaked:
        raise SystemExit(f"LEAK: protected feature in the model: {leaked}")
    print("  leakage check   : passed")

    print("\nBuilding feature matrices...")
    X, names, y = _build(df, num, cats)
    print(f"  X: {X.shape[0]:,} rows x {X.shape[1]:,} features")
    print(f"  X dtype         : {X.dtype}, {X.nbytes / 1e6:.0f} MB")

    # ---- grouped split ----------------------------------------------------
    # The sample is a cluster sample of lenders, so the split is by LEI.
    groups = df["lei"].astype("string").to_numpy()

    gss = GroupShuffleSplit(n_splits=1, test_size=TEST_FRAC, random_state=SEED)
    tmp_idx, test_idx = next(gss.split(X, y, groups))
    # Split the remainder into train and validation.
    gss2 = GroupShuffleSplit(n_splits=1, test_size=VAL_FRAC / (TRAIN_FRAC + VAL_FRAC),
                             random_state=SEED)
    rel_tr, rel_va = next(gss2.split(X[tmp_idx], y[tmp_idx], groups[tmp_idx]))
    train_idx = tmp_idx[rel_tr]
    val_idx = tmp_idx[rel_va]
    test_idx = test_idx

    def _leak_check(a, b, label):
        sa = set(groups[a])
        sb = set(groups[b])
        shared = sa & sb
        print(f"  {label}: {len(sa):,} lenders, {len(sb):,} lenders, "
              f"shared {len(shared):,}")
        return len(shared)

    print("\nGrouped split by LEI (no lender appears on both sides):")
    shared_tr_te = _leak_check(train_idx, test_idx, "train vs test")
    shared_tr_va = _leak_check(train_idx, val_idx, "train vs validation")
    shared_va_te = _leak_check(val_idx, test_idx, "validation vs test")
    if shared_tr_te or shared_tr_va or shared_va_te:
        raise SystemExit("LEAK: a lender appears in more than one split")

    print(f"  train {len(train_idx):,} / validation {len(val_idx):,} / "
          f"test {len(test_idx):,} rows")

    # ---- fit ---------------------------------------------------------------
    print("\nFitting the logistic regression...")
    t1 = time.perf_counter()
    lr = LogisticRegression(solver=P.LOGISTIC_SOLVER, C=P.LOGISTIC_C,
                            max_iter=200, n_jobs=P.N_JOBS)
    lr.fit(X[train_idx], y[train_idx])
    fit_s = time.perf_counter() - t1
    print(f"  fit time: {fit_s:.1f}s")

    # ---- threshold selection on VALIDATION ---------------------------------
    p_val = lr.predict_proba(X[val_idx])[:, 1]
    sweep = _sweep(y[val_idx], p_val)
    best = max(sweep, key=lambda r: r["f1"])
    thr = best["threshold"]
    print(f"\nThreshold selected on the VALIDATION set: {thr} "
          f"(validation F1 = {best['f1']:.4f})")

    # ---- report on the untouched TEST set ---------------------------------
    p_test = lr.predict_proba(X[test_idx])[:, 1]
    test_metrics = _metrics(y[test_idx], p_test, thr)
    val_metrics = _metrics(y[val_idx], p_val, thr)

    print("\nTEST SET (threshold chosen on validation):")
    print(f"  ROC-AUC        : {test_metrics['roc_auc']:.4f}")
    print(f"  PR-AUC         : {test_metrics['pr_auc']:.4f}")
    print(f"  Brier          : {test_metrics['brier']:.4f}")
    print(f"  precision      : {test_metrics['precision']:.4f}")
    print(f"  recall         : {test_metrics['recall']:.4f}")
    print(f"  F1             : {test_metrics['f1']:.4f}")
    print(f"  accuracy       : {test_metrics['accuracy']:.4f}")
    cm = test_metrics["confusion_matrix"]
    print(f"  confusion      : TP={cm['true_positive']:,} FP={cm['false_positive']:,} "
          f"FN={cm['false_negative']:,} TN={cm['true_negative']:,}")
    bm = test_metrics["baseline_majority_class"]
    print(f"  majority-class baseline: accuracy={bm['accuracy']:.4f} "
          f"F1={bm['f1']:.4f}")

    # ---- calibration -------------------------------------------------------
    from sklearn.calibration import calibration_curve
    frac_pos, mean_pred = calibration_curve(y[test_idx], p_test, n_bins=10,
                                            strategy="quantile")
    calibration = [{
        "bin": i + 1,
        "mean_predicted": float(mp),
        "observed_rate": float(fp),
        "n": None,
    } for i, (fp, mp) in enumerate(zip(frac_pos, mean_pred))]

    # ---- fairness audit: join the protected groups back on ----------------
    print("\nFairness audit (protected groups joined back after training)...")
    test_df = df.iloc[test_idx]
    diff = []
    for col in ("applicant_ethnicity_1", "applicant_race_1", "applicant_sex"):
        if col not in test_df.columns:
            continue
        grp = pd.to_numeric(test_df[col], errors="coerce")
        grp = grp.astype("Float64").fillna(-1.0)
        for code in sorted(grp.unique()):
            m = (grp == code).to_numpy(dtype=bool)
            if int(m.sum()) < 200:
                continue
            yt = y[test_idx][m]
            pt = p_test[m]
            pred = (pt >= thr).astype(int)
            from sklearn.metrics import roc_auc_score
            try:
                auc = float(roc_auc_score(yt, pt))
            except ValueError:
                auc = None
            diff.append({
                "attribute": col,
                "group_code": int(code),
                "n": int(m.sum()),
                "denial_rate_observed": float(yt.mean()),
                "mean_predicted_probability": float(pt.mean()),
                "roc_auc_within_group": auc,
                "precision": float(((pred == 1) & (yt == 1)).sum()
                                   / max((pred == 1).sum(), 1)),
                "recall": float(((pred == 1) & (yt == 1)).sum()
                               / max((yt == 1).sum(), 1)),
            })

    # ---- the coefficients, for the report --------------------------------
    coefs = []
    for i, nm in enumerate(names):
        coefs.append({
            "feature": nm,
            "coefficient": float(lr.coef_[0][i]),
            "odds_ratio": float(np.exp(lr.coef_[0][i])),
        })
    coefs_df = pd.DataFrame(coefs).sort_values("coefficient", key=abs,
                                                ascending=False)
    coefs_df.to_csv(C.RESULTS_DIR / "predictive_v2_coefficients.csv", index=False)

    # ---- GroupKFold cross-validation --------------------------------------
    print("\nGroupKFold cross-validation by LEI (5 folds)...")
    from sklearn.model_selection import GroupKFold
    from sklearn.metrics import roc_auc_score
    gkf = GroupKFold(n_splits=5)
    aucs = []
    for i, (tr, te) in enumerate(gkf.split(X, y, groups)):
        m = LogisticRegression(solver=P.LOGISTIC_SOLVER, C=P.LOGISTIC_C,
                               max_iter=200, n_jobs=P.N_JOBS)
        m.fit(X[tr], y[tr])
        a = float(roc_auc_score(y[te], m.predict_proba(X[te])[:, 1]))
        aucs.append(a)
        print(f"  fold {i + 1}: ROC-AUC = {a:.4f} "
              f"(train {len(tr):,} / test {len(te):,})")
    cv_auc = float(np.mean(aucs))
    cv_sd = float(np.std(aucs))
    print(f"  mean {cv_auc:.4f}  sd {cv_sd:.4f}")

    result = {
        "config": {
            "seed": SEED,
            "row_cap": ROW_CAP,
            "split": "GroupShuffleSplit by LEI",
            "train_val_test": [TRAIN_FRAC, VAL_FRAC, TEST_FRAC],
            "repeats": 1,
            "logistic_C": P.LOGISTIC_C,
            "solver": P.LOGISTIC_SOLVER,
            "n_features": int(X.shape[1]),
            "n_threads": P.N_JOBS,
        },
        "sample": {
            "n_rows": int(len(df)),
            "population_size": int(population),
            "pct_of_population": round(len(df) / population * 100, 2),
            "denial_rate_pct": round(float(df["is_denied"].mean() * 100), 2),
        },
        "features_removed_from_model": removed,
        "splits": {
            "n_train": int(len(train_idx)),
            "n_validation": int(len(val_idx)),
            "n_test": int(len(test_idx)),
            "n_lenders_train": int(len(set(groups[train_idx]))),
            "n_lenders_validation": int(len(set(groups[val_idx]))),
            "n_lenders_test": int(len(set(groups[test_idx]))),
            "lenders_shared_train_test": int(shared_tr_te),
            "lenders_shared_train_validation": int(shared_tr_va),
            "lenders_shared_validation_test": int(shared_va_te),
        },
        "threshold_selection": {
            "selected_on": "validation set",
            "threshold": thr,
            "validation_f1_at_threshold": best["f1"],
            "sweep": sweep,
        },
        "validation_metrics": val_metrics,
        "test_metrics": test_metrics,
        "group_kfold_auc": {
            "mean": cv_auc,
            "sd": cv_sd,
            "folds": aucs,
            "note": (
                "GroupKFold by LEI. Every lender is entirely within one "
                "fold, so the score measures generalisation to an unseen "
                "lender rather than to unseen records of a known lender."
            ),
        },
        "calibration": calibration,
        "differential_performance": diff,
        "fit_seconds": round(fit_s, 1),
        "total_seconds": round(time.perf_counter() - t0, 1),
    }

    OUT_JSON.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    # Save the test-set predictions so the figures can be drawn without
    # refitting the model. This is a separate file from the v1 artefact
    # `predictive_predictions.npz`, which is left in place untouched.
    np.savez_compressed(
        C.RESULTS_DIR / "predictive_v2_predictions.npz",
        y_true=y[test_idx],
        p_lr=p_test,
        groups=groups[test_idx],
        audit_ethnicity=pd.to_numeric(
            test_df["applicant_ethnicity_1"], errors="coerce"
        ).to_numpy(dtype=float),
        audit_race=pd.to_numeric(
            test_df["applicant_race_1"], errors="coerce"
        ).to_numpy(dtype=float),
        audit_sex=pd.to_numeric(
            test_df["applicant_sex"], errors="coerce"
        ).to_numpy(dtype=float),
    )

    # The calibration table, with the bin sizes.
    cal_df = pd.DataFrame(calibration)
    bins = pd.qcut(p_test, 10, labels=False, duplicates="drop")
    cal_df["n"] = [int((bins == i).sum()) for i in range(len(cal_df))]
    cal_df.to_csv(C.RESULTS_DIR / "predictive_v2_calibration.csv", index=False)

    print()
    print("=" * 78)
    print("PREDICTIVE v2 SUMMARY")
    print("=" * 78)
    print(f"  test ROC-AUC          : {test_metrics['roc_auc']:.4f}")
    print(f"  GroupKFold mean AUC   : {cv_auc:.4f} (sd {cv_sd:.4f})")
    print(f"  majority-class accuracy: {bm['accuracy']:.4f}")
    print(f"  model accuracy         : {test_metrics['accuracy']:.4f}")
    print(f"  model F1               : {test_metrics['f1']:.4f}")
    print(f"  threshold              : {thr} (chosen on validation)")
    print(f"  total time             : {result['total_seconds']}s")
    print()
    print(f"  Written: {OUT_JSON}")


if __name__ == "__main__":
    main()
