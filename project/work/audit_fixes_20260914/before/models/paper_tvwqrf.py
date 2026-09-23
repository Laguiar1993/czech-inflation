"""TVW-QRF of CNB Working Paper 9/2026 (Section 3) and the paper's benchmarks.

For one forecast origin and horizon the caller supplies the direct training
pairs (predictors dated ``s``, month-on-month inflation dated ``s + h``, all
with ``s + h`` at or before the origin) and the predictor row at the origin.

* A quantile regression forest (Meinshausen 2006, ``quantile_forest``) is fitted
  without the last ``VALIDATION_WINDOW`` pairs.  Its quantiles on those pairs
  estimate the time-varying weights of each quantile-combination scheme by
  kernel-weighted constrained least squares (eq. 3-4: weights sum to one and
  stay inside the scheme's bounds; exponential kernel with a six-month
  half-life, most recent pair weighted most).
* The forest is refitted on all pairs and evaluated at the origin row.  The
  point forecasts returned are the QRF median, the QRF mean and TVW1-TVW3
  (eq. 5-7).

The paper does not report forest hyperparameters; ``FOREST_DEFAULTS`` are the
common random-forest regression defaults (500 trees, a third of the
predictors tried at each split, five observations per leaf) and are declared,
not tuned.
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import t as student_t

SCHEMES: dict[str, tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]] = {
    "TVW1": ((0.25, 0.50, 0.75), (0.20, 0.40, 0.20), (0.40, 0.60, 0.40)),
    "TVW2": ((1 / 3, 0.50, 2 / 3), (0.20, 0.30, 0.20), (0.40, 0.50, 0.40)),
    "TVW3": ((0.10, 0.25, 0.50, 0.75, 0.90), (0.00, 0.15, 0.30, 0.15, 0.00), (0.15, 0.35, 0.50, 0.35, 0.15)),
}
POINT_MODELS = ("QRF_MEDIAN", "QRF_MEAN", "TVW1", "TVW2", "TVW3")
VALIDATION_WINDOW = 12
HALF_LIFE = 6.0
BAND_QUANTILES = (0.05, 0.95)
FOREST_DEFAULTS = {"n_estimators": 500, "min_samples_leaf": 5, "max_features": 1 / 3,
                   "bootstrap": True, "random_state": 42, "n_jobs": 1}
ALL_QUANTILES = tuple(sorted({q for quants, _, _ in SCHEMES.values() for q in quants} | set(BAND_QUANTILES)))


def kernel_weights(n: int, half_life: float = HALF_LIFE) -> np.ndarray:
    """Eq. (4): weight of an observation i periods old is 2^(-(i-1)/HL), normalised.

    Element ``n-1`` of the returned array is the most recent observation.
    """
    age = np.arange(n - 1, -1, -1, dtype=float)
    weights = 2.0 ** (-age / float(half_life))
    return weights / weights.sum()


def _feasible_start(lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    spare = 1.0 - lower.sum()
    room = upper - lower
    if spare < -1e-12 or room.sum() < spare - 1e-12:
        raise ValueError("scheme bounds admit no weights summing to one")
    return lower + (spare * room / room.sum() if room.sum() > 0 else 0.0)


def solve_weights(quantiles: np.ndarray, realised: np.ndarray, lower: Sequence[float],
                  upper: Sequence[float], omega: np.ndarray) -> np.ndarray:
    """Eq. (3): argmin_w (y - Q w)' Omega (y - Q w) with 1'w = 1 and lower <= w <= upper."""
    Q = np.asarray(quantiles, dtype=float)
    y = np.asarray(realised, dtype=float)
    lo = np.maximum(np.asarray(lower, dtype=float), 0.0)
    hi = np.asarray(upper, dtype=float)
    root = np.sqrt(np.asarray(omega, dtype=float))
    A, b = Q * root[:, None], y * root
    start = _feasible_start(lo, hi)

    def objective(w):
        r = A @ w - b
        return float(r @ r)

    def gradient(w):
        return 2.0 * A.T @ (A @ w - b)

    result = minimize(objective, start, jac=gradient, method="SLSQP", bounds=list(zip(lo, hi)),
                      constraints=[{"type": "eq", "fun": lambda w: float(w.sum() - 1.0),
                                    "jac": lambda w: np.ones_like(w)}],
                      options={"ftol": 1e-12, "maxiter": 500})
    w = np.asarray(result.x, dtype=float)
    feasible = np.all(w >= lo - 1e-8) and np.all(w <= hi + 1e-8) and abs(w.sum() - 1.0) < 1e-6
    if not (result.success and feasible) or objective(w) > objective(start) + 1e-12:
        return start
    return np.clip(w, lo, hi) / np.clip(w, lo, hi).sum()


def fit_forecast(X_train: np.ndarray, y_train: np.ndarray, x_now: np.ndarray, *,
                 forest: Mapping | None = None, val_window: int = VALIDATION_WINDOW) -> dict:
    """Point forecasts, quantiles and TVW weights for one origin and horizon."""
    from quantile_forest import RandomForestQuantileRegressor

    X = np.asarray(X_train, dtype=float)
    y = np.asarray(y_train, dtype=float)
    now = np.asarray(x_now, dtype=float).reshape(1, -1)
    if len(y) < val_window + 24:
        raise ValueError(f"{len(y)} training pairs; at least {val_window + 24} needed")
    options = {**FOREST_DEFAULTS, **dict(forest or {})}
    quantiles = list(ALL_QUANTILES)
    column = {q: i for i, q in enumerate(quantiles)}

    held_out = RandomForestQuantileRegressor(**options).fit(X[:-val_window], y[:-val_window])
    q_validation = np.asarray(held_out.predict(X[-val_window:], quantiles=quantiles), dtype=float)
    model = RandomForestQuantileRegressor(**options).fit(X, y)
    q_now = np.asarray(model.predict(now, quantiles=quantiles), dtype=float).reshape(-1)
    mean_now = float(np.asarray(model.predict(now, quantiles="mean"), dtype=float).reshape(-1)[0])

    omega = kernel_weights(val_window)
    points = {"QRF_MEDIAN": float(q_now[column[0.5]]), "QRF_MEAN": mean_now}
    weights = {}
    for name, (quants, lower, upper) in SCHEMES.items():
        cols = [column[q] for q in quants]
        w = solve_weights(q_validation[:, cols], y[-val_window:], lower, upper, omega)
        points[name] = float(q_now[cols] @ w)
        weights[name] = w
    return {"points": points, "quantiles": dict(zip(quantiles, q_now.tolist())), "weights": weights,
            "n_train": int(len(y)), "n_features": int(X.shape[1])}


# ----------------------------------------------------------------- benchmarks

def random_walk(history: pd.Series, horizons: Sequence[int]) -> dict[int, float]:
    last = float(pd.Series(history).dropna().iloc[-1])
    return {int(h): last for h in horizons}


def ar_iterated(history: pd.Series, horizons: Sequence[int], p: int = 3) -> dict[int, float]:
    """AR(p) with a constant by OLS on the history, iterated to each horizon (eq. 11)."""
    y = pd.Series(history).dropna().to_numpy(dtype=float)
    rows = np.column_stack([np.ones(len(y) - p)] + [y[p - i - 1:len(y) - i - 1] for i in range(p)])
    beta = np.linalg.lstsq(rows, y[p:], rcond=None)[0]
    path = list(y[-p:])
    out = {}
    for step in range(1, max(horizons) + 1):
        value = beta[0] + sum(beta[i + 1] * path[-(i + 1)] for i in range(p))
        path.append(value)
        if step in horizons:
            out[step] = float(value)
    return out


def ar_direct(history: pd.Series, horizon: int, p: int = 3) -> float:
    """Direct AR(p): regress y(t+h) on a constant and y(t), ..., y(t-p+1)."""
    y = pd.Series(history).dropna().to_numpy(dtype=float)
    n = len(y) - horizon - p + 1
    rows = np.column_stack([np.ones(n)] + [y[p - 1 - i:p - 1 - i + n] for i in range(p)])
    beta = np.linalg.lstsq(rows, y[p - 1 + horizon:p - 1 + horizon + n], rcond=None)[0]
    return float(np.r_[1.0, y[::-1][:p]] @ beta)


def arima_313(history: pd.Series, horizons: Sequence[int]) -> dict[int, float]:
    """ARIMA(3,1,3) with drift-free differencing, iterated forecasts (eq. 13)."""
    import warnings

    from statsmodels.tsa.arima.model import ARIMA

    y = pd.Series(history).dropna().to_numpy(dtype=float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fitted = ARIMA(y, order=(3, 1, 3)).fit()
    path = np.asarray(fitted.forecast(max(horizons)), dtype=float)
    return {int(h): float(path[h - 1]) for h in horizons}


def lqr_ensemble(X_train: np.ndarray, y_train: np.ndarray, x_now: np.ndarray, lags_train: np.ndarray,
                 lags_now: np.ndarray, *, models: int = 500, predictors: int = 4, seed: int = 0) -> float:
    """Ensemble of median regressions, each on four random predictors plus three target lags.

    The point forecast is the mean of the members' median forecasts.  Members that
    fail to converge are skipped.
    """
    import warnings

    from statsmodels.regression.quantile_regression import QuantReg

    rng = np.random.default_rng(seed)
    X = np.asarray(X_train, dtype=float)
    forecasts = []
    for _ in range(int(models)):
        pick = rng.choice(X.shape[1], size=min(predictors, X.shape[1]), replace=False)
        design = np.column_stack([np.ones(len(y_train)), X[:, pick], lags_train])
        row = np.r_[1.0, np.asarray(x_now, dtype=float)[pick], lags_now]
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                beta = QuantReg(y_train, design).fit(q=0.5, max_iter=2000).params
            forecasts.append(float(row @ beta))
        except Exception:
            continue
    return float(np.mean(forecasts)) if forecasts else float("nan")


# ---------------------------------------------------------------- evaluation

def diebold_mariano(errors_a: np.ndarray, errors_b: np.ndarray, horizon: int) -> tuple[float, float]:
    """Harvey-Leybourne-Newbold DM statistic for squared loss; one-sided p-value that B beats A.

    Negative statistics favour ``errors_b``.  The long-run variance uses
    autocovariances up to lag h-1.
    """
    a = np.asarray(errors_a, dtype=float)
    b = np.asarray(errors_b, dtype=float)
    keep = np.isfinite(a) & np.isfinite(b)
    d = b[keep] ** 2 - a[keep] ** 2
    T = len(d)
    if T < 10:
        return float("nan"), float("nan")
    centred = d - d.mean()
    variance = centred @ centred / T
    for lag in range(1, max(int(horizon), 1)):
        variance += 2.0 * (centred[lag:] @ centred[:-lag]) / T
    if variance <= 0:
        return float("nan"), float("nan")
    statistic = d.mean() / math.sqrt(variance / T)
    h = int(horizon)
    statistic *= math.sqrt((T + 1 - 2 * h + h * (h - 1) / T) / T)
    return float(statistic), float(student_t.cdf(statistic, df=T - 1))
