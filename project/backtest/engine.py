"""
Expanding-window out-of-sample backtest, mirroring CNB WP 9/2026's evaluation
design and the em-macro-forecaster skill's metric spec (RMSE full-sample +
rolling, direction correlation, residual z-scores, Diebold-Mariano vs AR(3)).
No look-ahead: at each origin t, models see data only up to t-h.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats


def diebold_mariano(e1: np.ndarray, e2: np.ndarray, h: int = 1) -> tuple[float, float]:
    """DM test on squared-error loss differential; HAC variance with h-1 lags.
    Negative stat -> model 1 more accurate. Returns (stat, p_value)."""
    d = e1 ** 2 - e2 ** 2
    d = d[~np.isnan(d)]
    n = len(d)
    if n < 10:
        return np.nan, np.nan
    dbar = d.mean()
    gamma0 = np.var(d, ddof=1)
    var = gamma0
    for k in range(1, h):
        cov = np.cov(d[k:], d[:-k], ddof=1)[0, 1]
        var += 2 * (1 - k / h) * cov
    dm = dbar / np.sqrt(var / n)
    # Harvey-Leybourne-Newbold small-sample correction
    dm *= np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    p = 2 * (1 - stats.t.cdf(abs(dm), df=n - 1))
    return float(dm), float(p)


def run_backtest(y: pd.Series, X: pd.DataFrame, h: int, oos_start: str,
                 models: dict, min_train: int = 60, max_train: int | None = None) -> pd.DataFrame:
    """
    models: name -> callable(y_hist, X_hist, h) returning float forecast of
    y at (origin + h). Expanding window by default; pass max_train to switch
    to a rolling window (trailing max_train months only) — trades long-run
    stability for faster adaptation at turning points, since old-regime
    history stops diluting the fit.
    """
    # .loc[:origin] below silently returns the wrong (future-leaking) rows on
    # a non-monotonic index instead of raising — assert rather than risk it.
    assert y.index.is_monotonic_increasing, "y index must be sorted (look-ahead risk)"
    assert X.index.is_monotonic_increasing, "X index must be sorted (look-ahead risk)"
    origins = y.loc[oos_start:].index
    rows = []
    for t in origins:
        target_p = t  # forecast target period; origin = t - h
        origin = t - h
        y_hist = y.loc[:origin]
        X_hist = X.loc[:origin]
        if max_train is not None:
            y_hist = y_hist.iloc[-max_train:]
            X_hist = X_hist.iloc[-max_train:]
        if len(y_hist.dropna()) < min_train or target_p not in y.index:
            continue
        row = {"period": t, "actual": y.loc[target_p]}
        for name, fn in models.items():
            try:
                row[name] = fn(y_hist, X_hist, h)
            except Exception:
                row[name] = np.nan
        rows.append(row)
    return pd.DataFrame(rows).set_index("period")


def summarize(bt: pd.DataFrame, benchmark: str = "AR3", h: int = 1) -> pd.DataFrame:
    out = []
    model_cols = [c for c in bt.columns if c != "actual"]
    errs = {m: (bt[m] - bt["actual"]).values for m in model_cols}
    for m in model_cols:
        e = errs[m]
        rec = {"model": m,
               "RMSE": float(np.sqrt(np.nanmean(e ** 2))),
               "MAE": float(np.nanmean(np.abs(e))),
               "dir_corr": float(pd.Series(np.sign(bt[m].diff())).corr(
                   pd.Series(np.sign(bt["actual"].diff()))))}
        if m != benchmark and benchmark in errs:
            dm, p = diebold_mariano(e, errs[benchmark], h=max(h, 1))
            rec["DM_vs_" + benchmark], rec["DM_pval"] = dm, p
        out.append(rec)
    return pd.DataFrame(out).set_index("model").sort_values("RMSE")


def residual_zscore(bt: pd.DataFrame, model: str, window: int = 24) -> pd.Series:
    r = bt["actual"] - bt[model]
    return (r - r.rolling(window).mean()) / r.rolling(window).std()
