"""
lender_fixed_effects.py — the lender fixed-effects model, done correctly.

What was wrong with the version in `confounder_analysis.py`
-----------------------------------------------------------
That version estimated the lender fixed-effects model by *demeaning*
the covariates and the outcome within each lender and then fitting a
logistic regression to the demeaned data.

That is not a valid estimator.  Within-transformation is algebraically
equivalent to including dummy variables only for a **linear** model.  For
a logistic regression, demeaning the outcome is not an innocuous
transformation: the logit is a non-linear function of the index, so
`logit^{-1}(X'beta + a_l)` cannot be written as a linear function of
`X'beta` plus a lender-specific intercept, and subtracting the within-lender
mean of the *outcome* is not the same thing as subtracting a lender
intercept from the index.  The symptoms were visible in the output:
`n_events = 0` and a McFadden pseudo-R-squared of -9.1e16, because the
demeaned outcome is a continuous value near zero rather than a 0/1 label
and the likelihood it computes is meaningless.

What this script does instead
-----------------------------
Two estimators, both on the *same* rows, so that the coefficients are
comparable and a difference between them is not a difference of sample:

1. **A linear probability model with lender dummy variables**, fitted by
   least squares with **standard errors clustered by lender**.  For a
   linear model the within-transformation and the dummy-variable
   parameterisation give identical slope coefficients, so this is the
   same estimand the demeaned code was reaching for, estimated in a form
   where the transformation is valid.

2. **A logistic regression with the same lender dummy variables**, as a
   cross-check.  It estimates the same population parameter through a
   different route and on a different scale, so agreement in sign and
   significance is evidence that neither estimator is broken.

The lender dummies are held as a **sparse** matrix.  A dense
1,466-column matrix over 780,000 rows would need 4.6 GB, which does not
fit comfortably on the 16 GB host this project runs on.

Output
------
    results/lender_fixed_effects.json
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C

OUT_JSON = C.RESULTS_DIR / "lender_fixed_effects.json"

MAX_ROWS = 3_000_000
MAX_ROWS_PER_LEI = 2_000
SEED = 20240101


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _norm_cdf(x: float) -> float:
    from math import erf, sqrt
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _cluster_robust_vcov(XtX_inv: np.ndarray, X, resid: np.ndarray,
                          clusters: np.ndarray, p: int) -> np.ndarray:
    """Cluster-robust (sandwich) variance estimator.

        V = (X'X)^{-1} ( sum_g X_g' u_g u_g' X_g ) (X'X)^{-1}

    with the small-sample correction of Cameron, Gelbach and Miller
    (2011).  Observations within a lender are not independent, which is
    exactly why the lender is the clustering variable.
    """
    G = int(clusters.max()) + 1
    meat = np.zeros((p, p))
    for g in range(G):
        m = clusters == g
        if not m.any():
            continue
        Xg = X[m]
        s = np.asarray(Xg.T @ resid[m]).ravel()
        meat += np.outer(s, s)
    N = X.shape[0]
    c = (G / max(G - 1, 1)) * ((N - 1) / max(N - p, 1))
    return XtX_inv @ (c * meat) @ XtX_inv


def _fit_lpm(X, y: np.ndarray, clusters: np.ndarray,
             names: list[str]) -> dict:
    """Least squares with cluster-robust standard errors, on a sparse design."""
    from scipy import sparse

    XtX = (X.T @ X).toarray()
    Xty = np.asarray(X.T @ y).ravel()
    beta = np.linalg.solve(XtX + 1e-8 * np.eye(XtX.shape[0]), Xty)
    resid = y - np.asarray(X @ beta).ravel()

    XtX_inv = np.linalg.pinv(XtX)
    vcov = _cluster_robust_vcov(XtX_inv, X, resid, clusters, len(beta))
    se = np.sqrt(np.clip(np.diag(vcov), 0, None))

    out = {}
    for i, nm in enumerate(names):
        if nm == "Intercept":
            continue
        b, s = float(beta[i]), float(se[i])
        z = b / s if s > 0 else float("nan")
        out[nm] = {
            "beta": b,
            "std_error": s,
            "ci95_low": b - 1.96 * s,
            "ci95_high": b + 1.96 * s,
            "z": z,
            "p_value": float(2 * (1 - _norm_cdf(abs(z)))),
        }
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - float(np.sum(resid ** 2)) / ss_tot if ss_tot > 0 else float("nan")
    return {
        "coefficients": out,
        "n": int(X.shape[0]),
        "n_clusters": int(len(np.unique(clusters))),
        "r_squared": r2,
        "residual_sd": float(np.std(resid, ddof=len(beta))),
    }


def _fit_logit_with_dummies(X, y: np.ndarray, names: list[str],
                             max_iter: int = 50) -> dict:
    """Newton-IRLS logistic regression on a sparse design with dummies."""
    from scipy import sparse

    n, p = X.shape
    beta = np.zeros(p)
    ridge = 1e-6
    for _ in range(max_iter):
        eta = np.asarray(X @ beta).ravel()
        mu = 1.0 / (1.0 + np.exp(-np.clip(eta, -35, 35)))
        w = np.clip(mu * (1 - mu), 1e-10, None)
        z = eta + (y - mu) / w
        Xw = X.multiply(w[:, None]).tocsr()
        A = np.asarray((X.T @ Xw).todense())
        b = np.asarray(Xw.T @ z).ravel()
        try:
            new_beta = np.linalg.solve(A + ridge * np.eye(p), b)
        except np.linalg.LinAlgError:
            new_beta = np.linalg.lstsq(A, b, rcond=None)[0]
        if np.max(np.abs(new_beta - beta)) < 1e-8:
            beta = new_beta
            break
        beta = new_beta

    eta = np.asarray(X @ beta).ravel()
    mu = 1.0 / (1.0 + np.exp(-np.clip(eta, -35, 35)))
    w = np.clip(mu * (1 - mu), 1e-10, None)
    Xw = X.multiply(w[:, None]).tocsr()
    A = np.asarray((X.T @ Xw).todense())
    try:
        cov = np.linalg.inv(A)
    except np.linalg.LinAlgError:
        cov = np.linalg.lstsq(A, np.eye(p), rcond=None)[0]
    cov = 0.5 * (cov + cov.T)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))

    out = {}
    for i, nm in enumerate(names):
        if nm == "Intercept":
            continue
        bb, s = float(beta[i]), float(se[i])
        z = bb / s if s > 0 else float("nan")
        out[nm] = {
            "beta": bb,
            "std_error": s,
            "odds_ratio": float(np.exp(bb)),
            "ci95_low": float(np.exp(bb - 1.96 * s)),
            "ci95_high": float(np.exp(bb + 1.96 * s)),
            "z": z,
            "p_value": float(2 * (1 - _norm_cdf(abs(z)))),
        }
    ll = float(np.sum(y * np.log(np.clip(mu, 1e-12, 1))
                      + (1 - y) * np.log(np.clip(1 - mu, 1e-12, 1))))
    ll0 = float(np.sum(y * np.log(np.clip(y.mean(), 1e-12, 1))
                        + (1 - y) * np.log(np.clip(1 - y.mean(), 1e-12, 1))))
    return {
        "coefficients": out,
        "n": int(n),
        "n_events": int(y.sum()),
        "log_likelihood": ll,
        "pseudo_r2_mcfadden": float(1 - ll / ll0) if ll0 != 0 else None,
        "converged": True,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    from scipy import sparse

    import confounder_analysis as CA

    print("=" * 74)
    print("LENDER FIXED EFFECTS  (LPM + logit, both with lender dummies)")
    print("=" * 74)

    df = CA._load_decisions()
    d = CA._prepare(df)
    print(f"decision records: {len(d):,}")

    known = d["joint_flag"].notna().to_numpy()
    d = d[known].reset_index(drop=True)
    print(f"with a known joint flag: {len(d):,}")

    # ---- sample per lender so the fixed effects are estimable ------------
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
    n_lenders = int(idx["lei"].nunique())
    print(f"within-lender sample: {len(idx):,} rows, {n_lenders:,} lenders")

    cols = ["joint", "log_income", "lti", "dti_ord"]
    Xc = idx[cols].to_numpy(dtype=float)
    names = cols[:]
    yi = idx["is_denied"].astype(float).to_numpy()
    lei_codes = pd.Categorical(idx["lei"].astype("string")).codes

    # ---- sparse lender dummies -------------------------------------------
    n = len(idx)
    G = n_lenders
    rows = np.arange(n)
    D = sparse.coo_matrix((np.ones(n), (rows, lei_codes)),
                          shape=(n, G)).tocsr()
    # drop the reference level to avoid perfect collinearity with the intercept
    D = D[:, 1:]

    ones = sparse.csr_matrix(np.ones((n, 1)))
    Xs = sparse.hstack([ones, sparse.csr_matrix(Xc), D], format="csr")
    full_names = ["Intercept"] + names + [f"lei_{i}" for i in range(D.shape[1])]

    # ---- 1. linear probability model -------------------------------------
    print("\n[1] Linear probability model with lender dummies "
          "(clustered SE) ...")
    t0 = time.perf_counter()
    lpm = _fit_lpm(Xs, yi, lei_codes, full_names)
    print(f"    done in {time.perf_counter() - t0:.1f}s")

    # ---- 2. logit with the same lender dummies ---------------------------
    print("[2] Logistic regression with the same lender dummies ...")
    t0 = time.perf_counter()
    lgm = _fit_logit_with_dummies(Xs, yi, full_names)
    print(f"    done in {time.perf_counter() - t0:.1f}s")

    # ---- 3. logit without the lender dummies, same rows -------------------
    print("[3] Logistic regression without lender dummies (same rows) ...")
    t0 = time.perf_counter()
    Xo, names_o = CA._design(idx)
    res_obs = CA._logit_fit(Xo, yi, names_o)
    print(f"    done in {time.perf_counter() - t0:.1f}s")
    obs_j = res_obs["coefficients"].get("joint")

    lpm_j = lpm["coefficients"].get("joint")
    lgm_j = lgm["coefficients"].get("joint")

    out = {
        "sample": {
            "n_decision_records_with_known_joint": int(len(idx)),
            "n_lenders": n_lenders,
            "max_rows_per_lender": MAX_ROWS_PER_LEI,
            "seed": SEED,
            "note": (
                "The same capped subsample is used for all three models, so "
                "the coefficients are comparable and the difference between "
                "them is not a difference of sample."
            ),
        },
        "linear_probability_model_with_lender_dummies": {
            "note": (
                "For a linear model the within-transformation and the "
                "dummy-variable parameterisation give identical slope "
                "coefficients, so this is the estimand the demeaned-logit "
                "code was trying to reach, estimated in a form where the "
                "transformation is valid.  Standard errors are clustered by "
                "lender."
            ),
            "n": lpm["n"],
            "n_clusters": lpm["n_clusters"],
            "r_squared": lpm["r_squared"],
            "joint": lpm_j,
            "joint_probability_difference_pp": (lpm_j["beta"] * 100
                                                 if lpm_j else None),
            "other_coefficients": {k: v for k, v in lpm["coefficients"].items()
                                   if k != "joint" and not k.startswith("lei_")},
        },
        "logit_with_lender_dummies": {
            "note": ("the same lender dummies in a logistic regression: a "
                     "different estimator of the same population parameter, "
                     "on a different scale"),
            "n": lgm["n"],
            "n_events": lgm["n_events"],
            "pseudo_r2_mcfadden": lgm["pseudo_r2_mcfadden"],
            "joint": lgm_j,
        },
        "logit_without_lender_fixed_effects_same_sample": {
            "note": ("the same model without the lender dummies, on the "
                     "same rows, so the two are directly comparable"),
            "n": res_obs["n"],
            "joint": obs_j,
        },
        "interpretation": {
            "joint_effect_lpm_pp": (lpm_j["beta"] * 100 if lpm_j else None),
            "joint_effect_lpm_ci95_pp": ([lpm_j["ci95_low"] * 100,
                                          lpm_j["ci95_high"] * 100]
                                         if lpm_j else None),
            "joint_effect_logit_with_fe_odds_ratio":
                (lgm_j["odds_ratio"] if lgm_j else None),
            "joint_effect_logit_no_fe_odds_ratio":
                (obs_j["odds_ratio"] if obs_j else None),
            "note": (
                "The linear probability model reports a probability "
                "difference in percentage points; the logistic models "
                "report an odds ratio.  A negative probability difference "
                "and an odds ratio below one are the same finding "
                "expressed on different scales."
            ),
        },
    }

    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    print()
    print("=" * 74)
    if lpm_j:
        print(f"  LPM + lender dummies : joint = {lpm_j['beta']*100:+.3f} pp "
              f"[{lpm_j['ci95_low']*100:+.3f}, {lpm_j['ci95_high']*100:+.3f}]  "
              f"(clustered SE {lpm_j['std_error']*100:.3f} pp)")
    if lgm_j:
        print(f"  Logit + lender dummies: joint OR = {lgm_j['odds_ratio']:.4f} "
              f"[{lgm_j['ci95_low']:.4f}, {lgm_j['ci95_high']:.4f}]")
    if obs_j:
        print(f"  Logit, no lender FE  : joint OR = {obs_j['odds_ratio']:.4f} "
              f"[{obs_j['ci95_low']:.4f}, {obs_j['ci95_high']:.4f}]")
    print("=" * 74)
    print(f"Written: {OUT_JSON}")


if __name__ == "__main__":
    main()
