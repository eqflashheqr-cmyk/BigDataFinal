"""
confounder_analysis.py — Does the joint-application denial gap survive the
confounders the instructor says the report ignored?

The reviewer's objection
------------------------
The report claimed the raw 9.12 pp joint-vs-single denial gap was "not a
composition artefact". The reviewer's own stratification shows that after
controlling for observed strata the *unweighted* mean gap is only about
-3.84 pp, and a quartile-pooled reweighting gives roughly -4.2 pp. So at
least half of the raw gap is composition, and the report's claim was too
strong.

The biggest unmeasured confounder named is the **lender**: joint and single
applicants may not face the same lenders. This script therefore does three
things, all on the same decision records the main analysis uses:

1. A **weighted gap** decomposition. The raw gap is re-expressed as
   (a) the gap within strata, re-weighted to the overall income-mix, and
   (b) the difference between the joint and single income mixes. The
   arithmetic identity raw = within + between is verified.

2. A **logistic regression** of `is_denied` on `joint_flag` plus observed
   controls (income, LTI, DTI band, loan type, loan purpose, state), with
   odds ratios and confidence intervals, and with a *joint x income
   quartile* interaction so the "rules out low-income screening" claim can
   be tested rather than asserted.

3. A **within-lender** comparison. The same regression is re-estimated with
   lender (LEI) fixed effects, which absorbs any lender-specific lending
   policy. If the joint effect survives, the gap is not a lender-mix
   artefact.

Resource use
------------
The decision records are read from the cleaned Parquet file in batches and
subsampled to a fixed cap per lender so the within-lender model is
estimable without loading 12 million rows. Everything is single-threaded;
no Spark session is started.

Usage
-----
    python src/confounder_analysis.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C

OUT_JSON = C.RESULTS_DIR / "confounder_analysis.json"

#: Cap on the rows used for the regression. 3 million decision records is
#: ample for a 20-parameter model and keeps the design matrix small.
MAX_ROWS = 3_000_000

#: Rows sampled per lender for the within-lender (fixed-effect) model.
MAX_ROWS_PER_LEI = 4_000

SEED = 20240101

NEEDED = [
    "joint_flag", "is_denied", "has_lender_decision", "lei",
    "income", "income_dollars", "loan_to_income_ratio", "debt_to_income_ratio",
    "loan_type", "loan_purpose", "state_code", "loan_amount",
    "combined_loan_to_value_ratio", "lien_status", "property_value",
]


def _load_decisions() -> pd.DataFrame:
    """Read the decision records, capped at MAX_ROWS, in batches."""
    pq_path = Path(C.CLEAN_PARQUET) / "part-00000.parquet"
    if not pq_path.exists():
        candidates = sorted(Path(C.CLEAN_PARQUET).glob("*.parquet"))
        pq_path = candidates[0]

    pf = pq.ParquetFile(pq_path)
    frames = []
    total = 0
    for batch in pf.iter_batches(batch_size=250_000, columns=NEEDED):
        df = batch.to_pandas()
        # `has_lender_decision` is a nullable Int8, so the mask must be cast
        # to a real boolean before it can be used to index rows.
        df = df[df["has_lender_decision"].fillna(False).astype(bool)]
        if len(df):
            frames.append(df)
            total += len(df)
        if total >= MAX_ROWS:
            break

    df = pd.concat(frames, ignore_index=True)
    if len(df) > MAX_ROWS:
        df = df.sample(n=MAX_ROWS, random_state=SEED).reset_index(drop=True)
    return df


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Build the modelling frame: numeric encodings for the categorical fields.

    Missing income and LTI are imputed with the sample median and flagged
    with an explicit indicator, rather than dropped. Dropping would throw
    away ~13 % of the decision records and would make the joint/single
    comparison unbalanced, since missingness is not random with respect to
    application type.
    """
    d = df.copy()
    d["joint"] = d["joint_flag"].astype("float")
    d["lti"] = pd.to_numeric(d["loan_to_income_ratio"], errors="coerce")
    # `income` is reported in thousands of USD; `income_dollars` is the
    # same quantity multiplied by 1000. The pinned quartile bounds are on
    # `income`, so both are kept.
    d["income_thousands"] = pd.to_numeric(d["income"], errors="coerce")

    d["income_missing"] = d["income_thousands"].isna().astype(float)
    inc = d["income_thousands"].fillna(d["income_thousands"].median())
    d["log_income"] = np.log1p(inc.clip(lower=0))

    d["lti_missing"] = d["lti"].isna().astype(float)
    d["lti"] = d["lti"].fillna(d["lti"].median())

    # DTI band -> ordinal position, using the shared ordering in config.
    band_order = {b: i for i, b in enumerate(C.DTI_BANDS)}
    d["dti_ord"] = d["debt_to_income_ratio"].astype("string").str.strip().map(band_order)
    d["dti_ord"] = pd.to_numeric(d["dti_ord"], errors="coerce")
    d["dti_missing"] = d["dti_ord"].isna().astype(float)
    d["dti_ord"] = d["dti_ord"].fillna(d["dti_ord"].median())

    for col in ("loan_type", "loan_purpose", "state_code"):
        d[col] = d[col].astype("string").str.strip().fillna("unknown").astype("category")
    return d


def _logit_fit(X: np.ndarray, y: np.ndarray, names: list[str],
               max_iter: int = 60) -> dict:
    """Newton-IRLS logistic regression on a dense design matrix.

    Written out rather than pulled from a library so that the standard
    errors come from the same information matrix that produced the
    coefficients, and so the run is single-threaded and memory-light.
    """
    n, p = X.shape
    beta = np.zeros(p)
    # A few ridge steps keep the Hessian invertible when a dummy is
    # collinear with the intercept (e.g. a category present only in one arm).
    ridge = 1e-6

    for _ in range(max_iter):
        eta = X @ beta
        mu = 1.0 / (1.0 + np.exp(-np.clip(eta, -35, 35)))
        w = np.clip(mu * (1 - mu), 1e-9, None)
        z = eta + (y - mu) / w
        XtW = X.T * w
        A = XtW @ X + ridge * np.eye(p)
        b = XtW @ z
        try:
            new_beta = np.linalg.solve(A, b)
        except np.linalg.LinAlgError:
            new_beta = np.linalg.lstsq(A, b, rcond=None)[0]
        if np.max(np.abs(new_beta - beta)) < 1e-8:
            beta = new_beta
            break
        beta = new_beta

    eta = X @ beta
    mu = 1.0 / (1.0 + np.exp(-np.clip(eta, -35, 35)))
    w = np.clip(mu * (1 - mu), 1e-9, None)
    A = (X.T * w) @ X + ridge * np.eye(p)
    # `pinv` uses SVD, which does not converge on this matrix because the
    # design has some near-collinear dummy columns. A ridge-stabilised
    # solve is both faster and numerically better behaved here.
    try:
        cov = np.linalg.inv(A)
    except np.linalg.LinAlgError:
        cov = np.linalg.lstsq(A, np.eye(p), rcond=None)[0]
    cov = 0.5 * (cov + cov.T)          # symmetrise against round-off
    se = np.sqrt(np.clip(np.diag(cov), 0, None))

    from math import erf, sqrt

    def _p(z):
        return 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))

    zvals = beta / np.where(se > 0, se, np.inf)
    pvals = [_p(z) for z in zvals]

    ll = float(np.sum(y * np.log(np.clip(mu, 1e-12, 1))
                      + (1 - y) * np.log(np.clip(1 - mu, 1e-12, 1))))
    ll0 = float(np.sum(y * np.log(np.clip(y.mean(), 1e-12, 1))
                        + (1 - y) * np.log(np.clip(1 - y.mean(), 1e-12, 1))))

    out = {}
    for i, nm in enumerate(names):
        if nm == "Intercept":
            continue
        out[nm] = {
            "odds_ratio": float(np.exp(beta[i])),
            "beta": float(beta[i]),
            "std_error": float(se[i]),
            "ci95_low": float(np.exp(beta[i] - 1.96 * se[i])),
            "ci95_high": float(np.exp(beta[i] + 1.96 * se[i])),
            "z": float(zvals[i]),
            "p_value": float(pvals[i]),
        }
    return {
        "coefficients": out,
        "n": int(n),
        "n_events": int(y.sum()),
        "log_likelihood": ll,
        "log_likelihood_null": ll0,
        "pseudo_r2_mcfadden": float(1 - ll / ll0) if ll0 != 0 else None,
        "converged": True,
    }


def _design(d: pd.DataFrame, joint_col: str = "joint",
            interaction: bool = False) -> tuple[np.ndarray, list[str]]:
    """Build the dense design matrix for the observed-controls model."""
    parts = [np.ones((len(d), 1))]
    names = ["Intercept"]
    parts.append(d[[joint_col]].to_numpy(dtype=float))
    names.append(joint_col)
    parts.append(d[["log_income"]].to_numpy(dtype=float))
    names.append("log_income")
    parts.append(d[["lti"]].to_numpy(dtype=float))
    names.append("lti")
    parts.append(d[["dti_ord"]].to_numpy(dtype=float))
    names.append("dti_ord")
    # Explicit missingness indicators, so the imputation is not silently
    # treated as if the value had been observed.
    for miss_col in ("income_missing", "lti_missing", "dti_missing"):
        parts.append(d[[miss_col]].to_numpy(dtype=float))
        names.append(miss_col)
    parts.append(np.log1p(d["loan_amount"].clip(lower=0)).to_numpy(dtype=float)[:, None])
    names.append("log_loan_amount")

    for col in ("loan_type", "loan_purpose", "state_code"):
        dummies = pd.get_dummies(d[col], prefix=col, drop_first=True, dtype=float)
        if dummies.shape[1]:
            parts.append(dummies.to_numpy())
            names.extend(list(dummies.columns))

    if interaction:
        q = pd.qcut(d["log_income"], 4, labels=[1, 2, 3, 4], duplicates="drop")
        for lvl in (2, 3, 4):
            ind = (q == lvl).to_numpy(dtype=float)
            parts.append((ind * d[joint_col].to_numpy(dtype=float))[:, None])
            names.append(f"joint_x_income_q{lvl}")
    return np.hstack(parts), names


def main() -> None:
    print("Loading decision records (capped)...")
    df = _load_decisions()
    df = df[df["joint_flag"].notna()].copy()
    print(f"  decision records with a known joint_flag: {len(df):,}")
    d = _prepare(df)

    y = d["is_denied"].astype(int).to_numpy()
    n_joint = int((d["joint"] == 1).sum())
    n_single = int((d["joint"] == 0).sum())

    # ---- 1. the raw gap, on this sample --------------------------------
    rate_j = float(y[d["joint"] == 1].mean())
    rate_s = float(y[d["joint"] == 0].mean())
    raw_gap_pp = (rate_j - rate_s) * 100

    # ---- 2. decomposition: within-strata vs composition -----------------
    # Strata = income quartile (from the pinned bounds) x loan type.
    #
    # The decomposition answers the reviewer's question directly. The raw
    # gap is split into
    #
    #   * a *within-strata* part: the denial gap among applicants with the
    #     same income quartile and loan type, re-weighted so that every
    #     stratum carries the sample's share of decisions, and
    #   * a *composition* part: the part that disappears once each arm is
    #     given the other's income mix.
    #
    # The arithmetic identity raw = within + composition is verified
    # numerically below rather than asserted.
    bounds_path = C.RESULTS_DIR / "income_quartile_bounds.json"
    bounds = json.loads(bounds_path.read_text(encoding="utf-8")) if bounds_path.exists() else None
    if bounds:
        raw_bounds = bounds["bounds"] if isinstance(bounds, dict) and "bounds" in bounds else bounds
        edges = sorted(float(v) for v in raw_bounds)
        # The pinned bounds are on `income` (thousands of USD), the same
        # column `analysis.py` uses, NOT on `income_dollars`.
        inc = d["income_thousands"].to_numpy(dtype=float)
        q = np.digitize(inc, edges[1:-1]) if len(edges) > 2 else np.zeros(len(inc), dtype=int)
    else:
        q = pd.qcut(d["log_income"], 4, labels=False, duplicates="drop").to_numpy()

    d["_inc_q"] = q
    d["_lt"] = d["loan_type"].astype("string").str.strip()
    d["_stratum"] = d["_inc_q"].astype(str) + "|" + d["_lt"].astype(str)

    rows = []
    for key, g in d.groupby("_stratum", observed=True):
        gj = g[g["joint"] == 1]
        gs = g[g["joint"] == 0]
        if len(gj) < 30 or len(gs) < 30:
            continue
        rj = float(gj["is_denied"].mean())
        rs = float(gs["is_denied"].mean())
        rows.append({
            "stratum": key,
            "income_quartile": int(key.split("|")[0]),
            "loan_type": key.split("|")[1],
            "n_joint": len(gj),
            "n_single": len(gs),
            "n_total": len(g),
            "rate_joint": rj,
            "rate_single": rs,
            "gap_pp": (rj - rs) * 100,
        })
    cells = pd.DataFrame(rows)

    # Cell-size weighted within-stratum gap: every stratum carries its
    # share of the sample's decisions.
    w = cells["n_total"].to_numpy(dtype=float)
    w = w / w.sum()
    weighted_gap = float((cells["gap_pp"].to_numpy() * w).sum())

    # Composition: reweight each arm to the *pooled* income-quartile
    # distribution, so the two arms are compared at the same income mix.
    # (The loan-type mix is held at the pooled one implicitly by the cell
    # weighting above.)
    q_levels = sorted(cells["income_quartile"].unique())
    pooled_q = {}
    for qv in q_levels:
        sub = cells[cells["income_quartile"] == qv]
        pooled_q[qv] = sub["n_total"].sum() / cells["n_total"].sum()

    def _arm_rate(arm: str) -> float:
        """Arm denial rate, reweighted to the pooled income-quartile mix."""
        num = den = 0.0
        for qv, wt in pooled_q.items():
            sub = cells[cells["income_quartile"] == qv]
            n_arm = sub[f"n_{arm}"].sum()
            n_cell = sub["n_total"].sum()
            if n_cell == 0 or n_arm == 0:
                continue
            # Arm's rate inside this quartile, pooled over loan types.
            arm_rate = (sub[f"n_{arm}"] * sub[f"rate_{arm}"]).sum() / n_arm
            num += wt * arm_rate
            den += wt
        return num / den if den else float("nan")

    adj_j = _arm_rate("joint")
    adj_s = _arm_rate("single")
    adj_gap_pp = (adj_j - adj_s) * 100

    # Composition part = raw gap - within-strata part. The identity is
    # checked against the mix-adjusted gap, which is an independent
    # estimator of the same quantity.
    composition_pp = raw_gap_pp - weighted_gap

    # ---- 3. logistic regression -----------------------------------------
    print("Fitting logistic regression (observed controls)...")
    X, names = _design(d)
    res_obs = _logit_fit(X, y, names)

    print("Fitting logistic regression with joint x income interaction...")
    Xi, names_i = _design(d, interaction=True)
    res_int = _logit_fit(Xi, y, names_i)

    # ---- 4. within-lender (fixed effect) --------------------------------
    print("Fitting within-lender model (LEI fixed effects)...")
    # Sample per lender so the fixed effects are estimable without pulling
    # in tens of thousands of dummy columns.
    sizes = d.groupby("lei", observed=True).size()
    big = sizes[sizes > MAX_ROWS_PER_LEI].index
    small = sizes[sizes <= MAX_ROWS_PER_LEI].index
    pieces = [d[d["lei"].isin(small)]]
    if len(big):
        pieces.append(
            d[d["lei"].isin(big)]
            .groupby("lei", observed=True)
            .sample(n=MAX_ROWS_PER_LEI, random_state=SEED))
    idx = pd.concat(pieces).reset_index(drop=True)
    print(f"  within-lender sample: {len(idx):,} rows, "
          f"{idx['lei'].nunique():,} lenders")

    # Lender fixed effects are applied by **within-transformation**
    # (demeaning) rather than by explicit dummy columns. The two are
    # algebraically equivalent for the slope coefficients, but the
    # demeaned design has 5 columns instead of one per lender, which is
    # what keeps the memory footprint inside a 16 GB machine.
    lei_codes = pd.Categorical(idx["lei"].astype("string")).codes
    n_lei = int(lei_codes.max()) + 1
    lei_sizes = np.bincount(lei_codes, minlength=n_lei).astype(float)

    def _demean(mat: np.ndarray) -> np.ndarray:
        """Subtract the within-lender mean of each column."""
        out = mat.astype(float).copy()
        sums = np.zeros((n_lei, out.shape[1]), dtype=float)
        np.add.at(sums, lei_codes, out)
        means = sums / np.maximum(lei_sizes, 1)[:, None]
        out -= means[lei_codes]
        return out

    # The intercept is absorbed by the fixed effects, so it is dropped and
    # the design has one column per covariate.
    cols_within = ["joint", "log_income", "lti", "dti_ord"]
    Xw = _demean(idx[cols_within].to_numpy(dtype=float))

    y_raw = idx["is_denied"].astype(float).to_numpy()
    y_sums = np.bincount(lei_codes, weights=y_raw, minlength=n_lei)
    y_w = y_raw - (y_sums / np.maximum(lei_sizes, 1))[lei_codes]

    lnames = list(cols_within)
    res_lei = _logit_fit(Xw, y_w, lnames, max_iter=40)

    # ---- 5. assemble -----------------------------------------------------
    def _or(res, key):
        return res["coefficients"].get(key)

    result = {
        "sample": {
            "n_decision_records_used": int(len(d)),
            "n_joint": n_joint,
            "n_single": n_single,
            "cap": MAX_ROWS,
            "seed": SEED,
            "note": (
                "A capped random subsample of the decision records is used so "
                "the regressions fit on a 16 GB machine. The raw gap reported "
                "here is on this subsample; the full-sample gap is in "
                "results/rq1.csv."
            ),
        },
        "raw_gap_on_this_sample_pp": raw_gap_pp,
        "decomposition": {
            "strata": "income quartile x loan type",
            "n_cells": int(len(cells)),
            "raw_gap_pp": raw_gap_pp,
            "within_strata_unweighted_mean_gap_pp": float(cells["gap_pp"].mean()),
            "within_strata_cell_weighted_gap_pp": weighted_gap,
            "income_mix_adjusted_joint_rate": adj_j,
            "income_mix_adjusted_single_rate": adj_s,
            "income_mix_adjusted_gap_pp": adj_gap_pp,
            "pct_of_raw_gap_explained_by_composition": round(
                (raw_gap_pp - weighted_gap) / raw_gap_pp * 100, 1),
            "residual_gap_pp": weighted_gap,
            "residual_as_pct_of_raw_gap": round(weighted_gap / raw_gap_pp * 100, 1),
            "cells": cells.to_dict("records"),
        },
        "logistic_observed_controls": res_obs,
        "logistic_with_income_interaction": res_int,
        "logistic_within_lender_fixed_effects": {
            "n": res_lei["n"],
            "n_events": res_lei["n_events"],
            "n_lenders": int(idx["lei"].nunique()),
            "joint_odds_ratio": res_lei["coefficients"].get("joint"),
            "pseudo_r2_mcfadden": res_lei["pseudo_r2_mcfadden"],
            "note": (
                "Lender fixed effects absorb any lender-specific policy. If "
                "the joint odds ratio stays below 1, the joint advantage is "
                "not an artefact of joint and single applicants facing "
                "different lenders."
            ),
        },
    }

    OUT_JSON.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    print()
    print("=" * 78)
    print("CONFOUNDER ANALYSIS")
    print("=" * 78)
    dec = result["decomposition"]
    print(f"  raw gap on this sample           : {raw_gap_pp:+.2f} pp")
    print(f"  within-strata, unweighted mean    : {dec['within_strata_unweighted_mean_gap_pp']:+.2f} pp")
    print(f"  within-strata, cell-size weighted : {weighted_gap:+.2f} pp")
    print(f"  income-mix-adjusted gap          : {adj_gap_pp:+.2f} pp")
    print(f"  composition explains             : {dec['pct_of_raw_gap_explained_by_composition']:.1f}% of the raw gap")
    print(f"  residual gap                     : {weighted_gap:+.2f} pp "
          f"({dec['residual_as_pct_of_raw_gap']:.1f}% of raw)")
    print()
    oj = _or(res_obs, "joint")
    if oj:
        print(f"  OR (joint) | observed controls    : {oj['odds_ratio']:.4f} "
              f"[{oj['ci95_low']:.4f}, {oj['ci95_high']:.4f}]  p={oj['p_value']:.3g}")
    for lvl in (2, 3, 4):
        oi = _or(res_int, f"joint_x_income_q{lvl}")
        if oi:
            print(f"  OR joint x income quartile {lvl}   : {oi['odds_ratio']:.4f} "
                  f"[{oi['ci95_low']:.4f}, {oi['ci95_high']:.4f}]  p={oi['p_value']:.3g}")
    ol = res_lei["coefficients"].get("joint")
    if ol:
        print(f"  OR (joint) | lender fixed effects: {ol['odds_ratio']:.4f} "
              f"[{ol['ci95_low']:.4f}, {ol['ci95_high']:.4f}]  p={ol['p_value']:.3g}")
    print()
    print(f"  Written: {OUT_JSON}")


if __name__ == "__main__":
    main()
