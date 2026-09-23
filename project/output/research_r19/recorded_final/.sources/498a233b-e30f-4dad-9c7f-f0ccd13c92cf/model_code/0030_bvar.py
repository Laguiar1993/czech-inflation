"""Direct horizon regression with an equation-wise Minnesota-style prior.

This is a shrunk direct forecast, not a jointly estimated structural VAR.
For origin s, columns L1..Lp contain z[s]..z[s-p+1], and the target is
 y[s+h]. The public horizon h therefore forecasts the last month T plus h.

With equation innovation scale sigma_y, likelihood SSE/sigma_y**2, and
prior Var(beta_j,l) = lambda1**2 * cross_j**2 / l**(2*lambda3)
                     * sigma_y**2 / sigma_j**2,
where cross_j=1 for own lags and 0.5 otherwise, multiplying the posterior
objective by sigma_y**2 gives the raw-SSE penalty
 l**(2*lambda3) * sigma_j**2 / (lambda1**2 * cross_j**2).
This includes own-lag penalties and is invariant to measurement units.
Innovation scales use first differences, with a level-scale fallback for
constant differences. No hyperparameters are tuned to forecast outcomes.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from models.trend_gap import require_monthly_contiguous


def _lag_matrix(df: pd.DataFrame, p: int) -> pd.DataFrame:
    cols = {}
    for l in range(1, p + 1):
        shifted = df.shift(l)
        for c in df.columns:
            cols[f"{c}_L{l}"] = shifted[c]
    return pd.DataFrame(cols, index=df.index)


def minnesota_bvar_forecast(
    panel: pd.DataFrame,
    target_col: str,
    h: int,
    p: int = 3,
    lambda1: float = 0.2,
    lambda3: float = 1.0,
    delta: dict | None = None,
    return_diagnostics: bool = False,
) -> float | dict:
    """panel: complete (no-NaN) DataFrame, columns = endogenous variables,
    already restricted to the caller's y_hist/X_hist slice (point-in-time
    is the caller's responsibility, same convention as every other model
    function in run_nowcast.py). target_col: which column to forecast
    h steps ahead. delta: prior mean for each variable's own lag-1
    coefficient (1.0 = random-walk prior for persistent levels like
    pribor_3m; 0.0 = white-noise prior for already-stationary growth
    rates -- the right default for everything else in this panel)."""
    require_monthly_contiguous(panel, "BVAR panel")
    if target_col not in panel.columns or panel.empty or not panel.columns.is_unique:
        raise ValueError("BVAR panel requires a target and unique columns")
    if not np.isfinite(panel.to_numpy(dtype=float)).all():
        raise ValueError("BVAR panel must be complete and finite; do not compress missing months")
    if not isinstance(h, (int, np.integer)) or h < 1 or not isinstance(p, (int, np.integer)) or p < 1:
        raise ValueError("h and p must be positive integer months")
    if not np.isfinite(lambda1) or lambda1 <= 0 or not np.isfinite(lambda3) or lambda3 < 0:
        raise ValueError("Minnesota tightness must be positive and lag decay nonnegative")
    cols = panel.columns.tolist()
    delta = delta or {}
    delta = {c: delta.get(c, 0.0) for c in cols}

    magnitude = panel.abs().max().replace(0, 1.0)
    level_scale = panel.std()
    level_scale = level_scale.where(level_scale > np.finfo(float).eps ** 0.5 * magnitude, magnitude)
    sigma = panel.diff().std()
    sigma = sigma.where(sigma > np.finfo(float).eps ** 0.5 * level_scale, level_scale)

    Xlag = _lag_matrix(panel, p)
    # At matrix row t, L1 is z[t-1], so the target must be y[t-1+h].
    y_fwd = panel[target_col].shift(-(h - 1))
    full = pd.concat([y_fwd.rename("y"), Xlag], axis=1).dropna()
    if len(full) < 2 * Xlag.shape[1]:
        forecast = float(panel[target_col].iloc[-1])
        return ({"forecast": forecast, "status": "fallback_last_value", "fallback_used": True,
                 "n": len(full), "h": h} if return_diagnostics else forecast)

    y = full["y"].values
    Xd = full.drop(columns=["y"])

    weights = np.zeros(Xd.shape[1])
    prior_mean = np.zeros(Xd.shape[1])
    for j, name in enumerate(Xd.columns):
        src_col, lag_str = name.rsplit("_L", 1)
        lag = int(lag_str)
        own = src_col == target_col
        weights[j] = (lag ** lambda3) ** 2 * sigma[src_col] ** 2 / (lambda1 ** 2) * (1.0 if own else 4.0)
        if own and lag == 1:
            prior_mean[j] = delta[target_col]

    scale = 1.0 / np.sqrt(weights)
    Xs = Xd.values * scale
    y_demeaned = y - Xd.values @ prior_mean
    # Augmented least squares avoids squaring the condition number or
    # rounding away the ridge identity for weak priors/collinear lags.
    augmented_x = np.vstack([Xs, np.eye(Xs.shape[1])])
    augmented_y = np.r_[y_demeaned, np.zeros(Xs.shape[1])]
    beta_scaled, *_ = np.linalg.lstsq(augmented_x, augmented_y, rcond=None)
    beta = beta_scaled * scale + prior_mean

    x_now = np.array([panel[name.rsplit("_L", 1)[0]].iloc[-int(name.rsplit("_L", 1)[1])]
                      for name in Xd.columns])
    forecast = float(np.dot(beta, x_now))
    return ({"forecast": forecast, "status": "estimated", "fallback_used": False,
             "n": len(full), "h": h} if return_diagnostics else forecast)
