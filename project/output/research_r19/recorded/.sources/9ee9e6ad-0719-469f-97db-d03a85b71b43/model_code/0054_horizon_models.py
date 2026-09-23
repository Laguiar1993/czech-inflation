"""
Horizon models (h >= 1): benchmarks + TVW-QRF (replication of CNB WP 9/2026).

TVW-QRF = Quantile Regression Forest (Meinshausen 2006) whose point forecast is
a convex combination of conditional quantiles with time-varying weights,
estimated by kernel-weighted constrained least squares over a rolling 12-month
validation window with 6-month half-life (Meligkotsidou et al. 2014 adapted).
CNB WP 9/2026 finds the five-quantile TVW3 spec beats QRF mean/median, AR(3),
ARIMA(3,1,3), RW and an LQR ensemble at h in {3,6,12} for headline CPI m/m.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear, minimize
from quantile_forest import RandomForestQuantileRegressor

from config import CFG

# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------
def rw_forecast(y: pd.Series, h: int) -> float:
    return float(y.dropna().iloc[-1])


def ar_forecast(y: pd.Series, h: int, p: int = 3) -> float:
    """Direct AR(p): regress y_{t+h} on (1, y_t..y_{t-p+1}); avoids iteration bias."""
    yv = y.dropna()
    lags = pd.concat([yv.shift(i) for i in range(p)], axis=1)
    lags.columns = [f"l{i}" for i in range(p)]
    df = pd.concat([yv.shift(-h).rename("target"), lags], axis=1).dropna()
    X = np.column_stack([np.ones(len(df)), df[[f"l{i}" for i in range(p)]].values])
    b = np.linalg.lstsq(X, df["target"].values, rcond=None)[0]
    x_now = np.r_[1.0, yv.iloc[-1:-(p + 1):-1].values]
    return float(x_now @ b)


def arima_forecast(y: pd.Series, h: int, order=(3, 1, 3)) -> float:
    from statsmodels.tsa.arima.model import ARIMA
    try:
        fit = ARIMA(y.dropna().values, order=order).fit(method_kwargs={"maxiter": 200})
        return float(fit.forecast(h)[-1])
    except Exception:
        return ar_forecast(y, h)


def uc_forecast(y: pd.Series, h: int) -> float:
    """Local-level unobserved-components model -- Stock & Watson (2007)'s
    UC-SV minus the stochastic-volatility part (statsmodels has no built-in
    SV state; a fixed-variance local level is the honest simplification).
    Unlike AR3/ARIMA313, the trend here is integrated -- no fixed
    unconditional mean to revert to -- so it tracks a slowly-evolving local
    mean instead. Szafranek (NBP WP 262) finds this specific property is
    what let his non-mean-reverting models (an ANN, and separately a BVAR
    with a tight steady-state prior) beat mean-reverting linear models
    during the 2011-16 Polish disinflation regime break; added here as a
    deliberately different ENSEMBLE member, not to replace AR3/ARIMA313."""
    from statsmodels.tsa.statespace.structural import UnobservedComponents
    yv = y.dropna()
    try:
        fit = UnobservedComponents(yv.values, level="local level").fit(disp=False)
        return float(fit.forecast(h)[-1])
    except Exception:
        return rw_forecast(y, h)

# ---------------------------------------------------------------------------
# TVW-QRF
# ---------------------------------------------------------------------------
class TVWQRF:
    def __init__(self, quantiles=CFG.tvw_quantiles, lower=CFG.tvw_lower,
                 upper=CFG.tvw_upper, val_window=CFG.val_window,
                 half_life=CFG.tvw_half_life, n_estimators=CFG.qrf_trees,
                 min_samples_leaf=CFG.qrf_min_leaf, seed=CFG.seed,
                 max_features=CFG.qrf_max_features, band_max_features=None):
        self.q = np.asarray(quantiles)
        self.lo, self.hi = np.asarray(lower), np.asarray(upper)
        self.val_window, self.half_life = val_window, half_life
        self.model = RandomForestQuantileRegressor(
            n_estimators=n_estimators, min_samples_leaf=min_samples_leaf,
            max_features=max_features, random_state=seed, n_jobs=-1)
        # Optional second forest, used ONLY for the distributional output
        # (all 7 quantile points: band, PIT, CRPS) -- never the point
        # forecast. max_features<1 forces per-split feature subsampling
        # (Breiman random subspace), whose extra tree diversity widens the
        # quantile spread the all-features forest understates. Measured
        # 2026-09-05 on the real panel, same origins: 5-95% coverage h=1
        # 79%->93%, h=6 85%->89% (h=3 already fine, h=12 unchanged), PIT/KS
        # calibrated at all 4 horizons -- while the same setting applied to
        # the POINT forest cost +3-5% RMSE at h<=3 (h0-hybrid confirmed
        # independently: 0.738->0.793). Splitting point vs band this way
        # keeps both measured results. None = single-forest behaviour.
        self.band_model = None
        if band_max_features is not None and band_max_features != max_features:
            self.band_model = RandomForestQuantileRegressor(
                n_estimators=n_estimators, min_samples_leaf=min_samples_leaf,
                max_features=band_max_features, random_state=seed, n_jobs=-1)
        self.w_ = np.full(len(self.q), 1 / len(self.q))

    # -- weights: constrained kernel-weighted least squares (eq. 3-4, WP 9/2026)
    def _solve_weights(self, Q_val: np.ndarray, y_val: np.ndarray) -> np.ndarray:
        n = len(y_val)
        i = np.arange(1, n + 1)[::-1]                     # most recent = i=1
        om = 2.0 ** (-(i - 1) / self.half_life)
        om = om / om.sum()
        W = np.sqrt(np.diag(om))
        A, b = W @ Q_val, W @ y_val
        K = len(self.q)

        def obj(w):
            r = A @ w - b
            return r @ r

        cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
        bounds = list(zip(self.lo, self.hi))
        w0 = np.clip(np.full(K, 1 / K), self.lo, self.hi)
        w0 = w0 / w0.sum()
        res = minimize(obj, w0, bounds=bounds, constraints=cons, method="SLSQP")
        return res.x if res.success else w0

    def fit_predict(self, X_train: np.ndarray, y_train: np.ndarray,
                    x_now: np.ndarray) -> dict:
        """
        Train on all data up to t-h, reserve last `val_window` rows to estimate
        weights, forecast at x_now. Returns point + quantile paths.
        """
        n = len(y_train)
        v = min(self.val_window, max(n // 5, 4))
        Xf, yf = X_train[:-v], y_train[:-v]
        Xv, yv = X_train[-v:], y_train[-v:]
        self.model.fit(Xf, yf)
        Q_val = self.model.predict(Xv, quantiles=list(self.q))
        self.w_ = self._solve_weights(np.atleast_2d(Q_val), yv)
        # refit on full sample for the final prediction (uses all information)
        self.model.fit(X_train, y_train)
        all_q = [0.05] + list(self.q) + [0.95]
        qv = self.model.predict(x_now.reshape(1, -1), quantiles=all_q)[0]
        q_now = qv[1:-1]
        point = float(q_now @ self.w_)  # point locked in from the primary forest
        if self.band_model is not None:
            # distributional grid (band + PIT/CRPS inputs) from the diverse
            # forest; the point above is untouched by this
            self.band_model.fit(X_train, y_train)
            qv = self.band_model.predict(x_now.reshape(1, -1), quantiles=all_q)[0]
            q_now = qv[1:-1]
        return {"point": point,
                "quantiles": dict(zip(self.q.tolist(), q_now.tolist())),
                "weights": dict(zip(self.q.tolist(), np.round(self.w_, 3).tolist())),
                "median": float(q_now[len(self.q) // 2]),
                "p05_p95": (float(qv[0]), float(qv[-1]))}

# ---------------------------------------------------------------------------
# Feature builder for horizon models (direct h-step: X_t -> y_{t+h})
# ---------------------------------------------------------------------------
def build_supervised(y: pd.Series, X: pd.DataFrame, h: int,
                     y_lags: int = 3) -> tuple[np.ndarray, np.ndarray, np.ndarray, pd.PeriodIndex]:
    """Align predictors observable at t with target at t+h."""
    feats = X.copy()
    for i in range(y_lags):
        feats[f"y_l{i}"] = y.shift(i)
    feats["month"] = feats.index.month
    tgt = y.shift(-h).rename("target")
    df = pd.concat([tgt, feats], axis=1).dropna(subset=["target"])
    df = df.dropna()
    x_now_row = feats.dropna().iloc[-1].values.astype(float)
    return (df.drop(columns="target").values.astype(float),
            df["target"].values.astype(float), x_now_row, df.index)

# ---------------------------------------------------------------------------
# Inverse-RMSE ensemble
# ---------------------------------------------------------------------------
def inv_rmse_weights(errors: dict[str, pd.Series]) -> dict[str, float]:
    rmse = {k: float(np.sqrt(np.nanmean(np.square(v)))) for k, v in errors.items()}
    inv = {k: 1.0 / max(r, 1e-9) for k, r in rmse.items()}
    s = sum(inv.values())
    return {k: v / s for k, v in inv.items()}
