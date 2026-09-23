"""Complete Subset Regressions (Elliott/Gargano/Timmermann, J.Econometrics 2013).

Equal-weight average over ALL k-predictor OLS models (or a seeded random
sample when the enumeration explodes). Non-diagonal shrinkage that beat
tuned ridge/lasso/bagging in EGT's low-signal settings. k is chosen inside
each origin on a held-out validation tail (last `val_len` rows of the
training sample), never on the evaluation month -- no cross-origin state,
no look-ahead.

EGT caveat that matters here: small-k equal weighting dilutes genuinely
strong predictors, so this is run on the EX-FUEL target (fuel stays
measured) and y-lags + a seasonal-mean feature are always in the candidate
pool so every subset sees the persistence/seasonality backbone candidates.
"""
from __future__ import annotations
from itertools import combinations

import numpy as np
import pandas as pd


def _supervised(y: pd.Series, X: pd.DataFrame, h: int, y_lags: int = 3):
    """Linear-model-friendly variant of build_supervised: month int is
    replaced by an expanding same-calendar-month mean of y (shifted one
    year so the current target never feeds its own feature)."""
    feats = X.copy()
    for i in range(y_lags):
        feats[f"y_l{i}"] = y.shift(i)
    seas = y.groupby(y.index.month).transform(lambda s: s.expanding().mean().shift(1))
    feats["seas_mean"] = seas
    tgt = y.shift(-h).rename("target")
    df = pd.concat([tgt, feats], axis=1).dropna(subset=["target"]).dropna()
    x_now = feats.dropna().iloc[-1].values.astype(float)
    return (df.drop(columns="target").values.astype(float),
            df["target"].values.astype(float), x_now)


def _subset_predict(Xt, yt, x_rows, combos):
    """Mean prediction over OLS fits on each column-subset. x_rows: (m, p)."""
    preds = np.zeros(x_rows.shape[0])
    ones_t = np.ones((Xt.shape[0], 1))
    ones_p = np.ones((x_rows.shape[0], 1))
    n_ok = 0
    for cols in combos:
        A = np.hstack([ones_t, Xt[:, cols]])
        try:
            beta, *_ = np.linalg.lstsq(A, yt, rcond=None)
        except np.linalg.LinAlgError:
            continue
        preds += np.hstack([ones_p, x_rows[:, cols]]) @ beta
        n_ok += 1
    return preds / max(n_ok, 1)


def csr_forecast(y_hist: pd.Series, X: pd.DataFrame, h: int,
                 k_grid=(1, 2, 3), val_len: int = 24,
                 max_models: int = 1500, seed: int = 42) -> float:
    Xt, yt, x_now = _supervised(y_hist, X, h)
    if len(yt) < val_len + 24:
        val_len = max(8, len(yt) // 3)
    mu, sd = Xt.mean(0), Xt.std(0)
    sd[sd == 0] = 1.0
    Xs = (Xt - mu) / sd
    xs_now = (x_now - mu) / sd
    p = Xs.shape[1]
    rng = np.random.default_rng(seed)

    def combos_for(k):
        full = list(combinations(range(p), k))
        if len(full) <= max_models:
            return full
        idx = rng.choice(len(full), size=max_models, replace=False)
        return [full[i] for i in idx]

    fit_X, fit_y = Xs[:-val_len], yt[:-val_len]
    val_X, val_y = Xs[-val_len:], yt[-val_len:]
    best_k, best_rmse = k_grid[0], np.inf
    cached = {}
    for k in k_grid:
        cb = combos_for(k)
        cached[k] = cb
        pv = _subset_predict(fit_X, fit_y, val_X, cb)
        rmse = float(np.sqrt(np.mean((pv - val_y) ** 2)))
        if rmse < best_rmse:
            best_k, best_rmse = k, rmse
    pred = _subset_predict(Xs, yt, xs_now[None, :], cached[best_k])
    return float(pred[0])
