"""BBIM-lite: blockwise boosted trees with monotonicity constraints.

Pure-sklearn re-implementation of the mechanism in Buckmann/Potjagailo/
Schnattinger (BoE SWP 1143, 2025) "Blockwise Boosted Inflation": gradient
boosting where each round adds ONE depth-3 tree PER economic block (block
order shuffled each round), each tree fitted to the current residuals using
only that block's columns, with per-column monotonicity constraints
(sklearn>=1.4 DecisionTreeRegressor monotonic_cst). Additive across blocks,
nonlinear within -- the forecast decomposes exactly into per-block
contributions (returned for diagnostics).

Simplifications vs the paper (documented, deliberate): no 10x-repeated CV
-- early stopping on the last `val_len` training rows with patience;
single model, no 10-model 80%-subsample average (the backtest's expanding
origins already average over data draws); xgboost replaced by sklearn
trees (paper used n_estimators=1 xgboost trees, functionally identical at
depth 3).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeRegressor


def bbim_forecast(y_hist: pd.Series, X: pd.DataFrame, h: int,
                  block_of, mono_of, rounds: int = 150, lr: float = 0.02,
                  subsample: float = 0.5, val_len: int = 24,
                  patience: int = 20, seed: int = 42,
                  y_lags: int = 3, include_month: bool = True) -> float:
    feats = X.copy()
    for i in range(y_lags):
        feats[f"y_l{i}"] = y_hist.shift(i)
    if include_month:
        feats["month"] = feats.index.month
    tgt = y_hist.shift(-h).rename("target")
    df = pd.concat([tgt, feats], axis=1).dropna(subset=["target"]).dropna()
    x_now = feats.dropna().iloc[-1].values.astype(float)
    cols = list(df.drop(columns="target").columns)
    Xt = df[cols].values.astype(float)
    yt = df["target"].values.astype(float)

    blocks: dict[str, list[int]] = {}
    for j, c in enumerate(cols):
        blocks.setdefault(block_of(c), []).append(j)
    mono = {name: [int(mono_of(cols[j])) for j in idx] for name, idx in blocks.items()}

    if len(yt) < val_len + 24:
        val_len = max(8, len(yt) // 3)
    fit_idx = np.arange(len(yt) - val_len)
    val_idx = np.arange(len(yt) - val_len, len(yt))

    rng = np.random.default_rng(seed)
    F_fit = np.full(len(fit_idx), yt[fit_idx].mean())
    F_val = np.full(len(val_idx), yt[fit_idx].mean())
    F_now = yt[fit_idx].mean()
    trees: list[tuple[str, DecisionTreeRegressor]] = []
    best_val, best_len, stall = np.inf, 0, 0
    names = list(blocks)

    for r in range(rounds):
        order = rng.permutation(len(names))
        for bi in order:
            name = names[bi]
            idx = blocks[name]
            resid = yt[fit_idx] - F_fit
            rows = rng.random(len(fit_idx)) < subsample
            if rows.sum() < 10:
                rows[:] = True
            t = DecisionTreeRegressor(max_depth=3, min_samples_leaf=5,
                                      monotonic_cst=mono[name],
                                      random_state=int(rng.integers(1 << 31)))
            t.fit(Xt[fit_idx][rows][:, idx], resid[rows])
            F_fit += lr * t.predict(Xt[fit_idx][:, idx])
            F_val += lr * t.predict(Xt[val_idx][:, idx])
            F_now += lr * t.predict(x_now[None, idx])[0]
            trees.append((name, t))
        val_rmse = float(np.sqrt(np.mean((yt[val_idx] - F_val) ** 2)))
        if val_rmse < best_val - 1e-6:
            best_val, best_len, stall = val_rmse, len(trees), 0
        else:
            stall += 1
            if stall >= patience:
                break

    # replay the winning prefix for the x_now prediction
    F = yt[fit_idx].mean()
    for name, t in trees[:best_len]:
        F += lr * t.predict(x_now[None, blocks[name]])[0]
    return float(F)
