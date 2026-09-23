"""LQR Ensemble -- CNB WP 9/2026's actual linear benchmark, faithfully
reproduced (this project's prior "ENSEMBLE" was a different concept: an
inverse-RMSE blend of already-existing model outputs, not a real
alternative model class -- see run_nowcast.py's walk_forward_ensemble).

Paper's definition (Section 5): "the LQR ensemble aggregates forecasts from
approximately 500 individual quantile regression models. Each of these 500
LQR models is randomly fit using four predictors plus three lagged terms."
Point forecast per member = median (0.5) quantile regression (the natural
point-forecast reading of "quantile regression" used as a linear-QRF analog
-- RF's own point forecast is the mean of many trees; here each "tree" is a
median regression on a random 4-predictor + 3-lag subset), ensemble point =
mean across members, mirroring how a Random Forest averages its own trees.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import QuantileRegressor

from models.horizon_models import build_supervised

N_MODELS = 500
N_PREDICTORS_PER_MODEL = 4
N_LAGS = 3


def lqr_ensemble_fn(y_hist, X_hist, h, n_models: int = N_MODELS, seed: int = 0) -> float:
    # Each member only ever sees 4 predictors + 3 lags, so build_supervised
    # is called per-member on that narrow slice -- passing it the full,
    # gappy 30+ column panel up front would dropna() away almost every row
    # (some columns, e.g. admin_mm, only start in 2024).
    edge = X_hist.index.max()
    fresh_cols = [c for c in X_hist.columns
                 if X_hist[c].last_valid_index() is not None
                 and X_hist[c].last_valid_index() >= edge - 2]
    candidates = fresh_cols if fresh_cols else list(X_hist.columns)

    rng = np.random.default_rng(seed)
    preds = np.empty(n_models)
    for m in range(n_models):
        k = min(N_PREDICTORS_PER_MODEL, len(candidates))
        cols = rng.choice(candidates, size=k, replace=False).tolist()
        try:
            Xt, yt, x_now, _ = build_supervised(y_hist, X_hist[cols], h, y_lags=N_LAGS)
            qr = QuantileRegressor(quantile=0.5, alpha=0.0, solver="highs")
            qr.fit(Xt, yt)
            preds[m] = qr.predict(x_now.reshape(1, -1))[0]
        except Exception:
            preds[m] = np.nan
    return float(np.nanmean(preds))
