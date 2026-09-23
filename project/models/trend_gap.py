"""F2 of PATH_SPEC_v2 / step 3 of PATH_SPEC_v3: trend-and-gap state-space
model for monthly headline inflation, estimated per origin by maximum
likelihood on released data, filtered (not smoothed) state projected
forward.

    y_t   = level_t + gap_t + e_t                    (SA headline m/m, %)
    m_t   = level_t + b + u_t                        (optional survey measurement,
                                                      FMIE one-year expectation / 12)
    level_t = level_{t-1} + eta_t                    (random-walk trend)     [anchored=False]
    level_t - mu_t = rho (level_{t-1} - mu_{t-1}) + eta_t                    [anchored=True]
    gap_t   = phi * gap_{t-1} + gamma' x_{t-1} + eps_t   (AR(1) gap with lagged drivers)

Seasonality is removed before estimation with the expanding same-month
means of the released history (deterministic, no leakage) and added back
to the forecasts. Drivers x are indexed by reference month. The last
observed driver enters the next forecast; unknown future driver values
default to zero, or are supplied explicitly through x_future. With
anchored=True the level mean-reverts to the target path mu at the
estimated speed rho and the forecast converges to mu beyond the sample.

Variants: with / without the survey measurement; ML variances or a fixed
signal-to-noise ratio (var_eta = var_e / SNR_FIXED); anchored or random
walk. No parameter is tuned after seeing forecasts.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import warnings
from statsmodels.tsa.statespace.mlemodel import MLEModel

SNR_FIXED = 50.0
MIN_OBS = 96
RHO_LO, RHO_HI = 0.90, 0.999


def require_monthly_contiguous(obj, name="history"):
    """Reject reordered, duplicate or missing months before positional lags."""
    index = obj.index
    if not isinstance(index, pd.PeriodIndex) or index.freqstr != "M":
        raise ValueError(f"{name} requires a contiguous monthly PeriodIndex")
    if len(index) and (index.hasnans or not index.is_unique or not index.is_monotonic_increasing
                       or not np.all(np.diff(index.asi8) == 1)):
        raise ValueError(f"{name} must have a contiguous monthly index")


def reject_infinite_inputs(obj, name):
    """NaN may denote declared missing data; infinity is never a driver value.

    Check the complete supplied object, including known rows beyond y's
    final observation, before optimization starts.
    """
    if np.isinf(obj.to_numpy(dtype=float)).any():
        raise ValueError(f"{name} contains infinite values")


def failed_projection(horizons, n, fit_diagnostics, stage):
    """Keep fit diagnostics separate from a failed numerical projection."""
    return {"mm": {h: np.nan for h in horizons}, "converged": False, "n": n,
            "fallback_used": fit_diagnostics["fallback_used"], "fit_diagnostics": fit_diagnostics,
            "projection_diagnostics": {"status": "nonfinite", "stage": stage}}


def released_history(y):
    """Trim only unreleased edges; an interior missing outcome is an error."""
    require_monthly_contiguous(y, "y_hist")
    y = y.dropna()
    require_monthly_contiguous(y, "released y_hist")
    if not np.isfinite(y.to_numpy(dtype=float)).all():
        raise ValueError("y_hist must contain finite observations")
    return y


def transition_intercept(rho, x, gamma, target_previous=0.0, target_current=0.0):
    """Intercept for source->destination month, shared by filtering/projection.

    x belongs to the source month; the destination gap uses this one lag.
    Arguments can be scalars/one row or arrays of consecutive transitions.
    """
    return np.asarray([target_current - rho * target_previous, np.asarray(x) @ np.asarray(gamma)])


def transition_state(state, phi, rho, x, gamma, target_previous=0.0, target_current=0.0):
    """One zero-shock state transition using the declared monthly equations."""
    return np.asarray(state) * np.asarray([rho, phi]) + transition_intercept(
        rho, x, gamma, target_previous, target_current)


def fit_with_fallback(mod):
    """Fixed rule: LBFGS, then Powell from the same starts, then start filter.

    Nonconverged or nonfinite fits are never used as estimated parameters.
    The last resort is a labelled zero-driver-coefficient model using the
    deterministic start variances/persistence and all observations to filter
    states. It is a forecast fallback, not a successful ML estimate.
    """
    initial = mod.start_params.copy()
    attempts = []
    for method in ("lbfgs", "powell"):
        attempt = {"method": method, "converged": False}
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                res = mod.fit(start_params=initial.copy(), disp=False, maxiter=400,
                              method=method, cov_type="none")
            attempt["warnings"] = sorted({str(w.message) for w in caught})
            finite = (np.isfinite(res.params).all() and np.isfinite(res.llf)
                      and np.isfinite(res.filtered_state).all())
            converged = bool(getattr(res, "mle_retvals", {}).get("converged", True))
            attempt.update(converged=converged, finite=bool(finite),
                           llf=float(res.llf) if np.isfinite(res.llf) else None)
            attempts.append(attempt)
            if converged and finite:
                mod.update(res.params)
                return res, {"status": "converged" if method == "lbfgs" else "converged_retry",
                             "converged": True, "fallback_used": False, "attempts": attempts}
        except Exception as exc:  # optimizer/backend failure must remain visible
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            attempts.append(attempt)
    diagnostics = {"status": "fallback_start_params", "converged": False,
                   "fallback_used": True, "attempts": attempts}
    try:
        res = mod.filter(initial, cov_type="none")
        if not np.isfinite(res.filtered_state).all() or not np.isfinite(res.llf):
            raise ValueError("fallback filter returned nonfinite results")
        mod.update(initial)
        return res, diagnostics
    except Exception as exc:
        diagnostics.update(status="failed", fallback_error=f"{type(exc).__name__}: {exc}")
        return None, diagnostics


def target_path(index: pd.PeriodIndex) -> pd.Series:
    """CNB inflation target as a monthly rate (percent per month) per month:
    4% 1998-2001 (declared approximation of the net-inflation years), a
    straight line from 4% (Jan 2002) to 3% (Dec 2005), 3% 2006-2009, 2%
    from January 2010; beyond the sample the last value."""
    out = []
    for p in index:
        if p.year <= 2001:
            tau = 4.0
        elif p.year <= 2005:
            k = (p.year - 2002) * 12 + (p.month - 1)          # 0..47
            tau = 4.0 - 1.0 * k / 47.0
        elif p.year <= 2009:
            tau = 3.0
        else:
            tau = 2.0
        out.append(100.0 * ((1.0 + tau / 100.0) ** (1.0 / 12.0) - 1.0))
    return pd.Series(out, index=index)


class TrendGap(MLEModel):
    """States: [level, gap]. Observations: [y] or [y, m]. Exogenous drivers
    enter the gap transition through a time-varying state intercept; the
    target anchor enters the level transition the same way. x[t] is a
    source-month driver: statsmodels applies it to state[t+1]. mu[t] is
    the target for observation month t, so the level intercept at t uses
    mu[t+1] - rho*mu[t]. The unused final target is held flat."""

    def __init__(self, y: np.ndarray, m: np.ndarray | None = None, x: np.ndarray | None = None, fixed_snr: bool = False,
                 mu: np.ndarray | None = None):
        self.has_m = m is not None
        self.x = None if x is None or x.shape[1] == 0 else np.asarray(x, dtype=float)
        self.kx = 0 if self.x is None else self.x.shape[1]
        self.fixed_snr = fixed_snr
        self.anchored = mu is not None
        self.mu = None if mu is None else np.asarray(mu, dtype=float)
        endog = np.column_stack([y, m]) if self.has_m else np.asarray(y, dtype=float).reshape(-1, 1)
        super().__init__(endog, k_states=2, k_posdef=2, initialization="approximate_diffuse")
        self["design"] = np.zeros((self.k_endog, 2))
        self["design", 0, 0] = 1.0; self["design", 0, 1] = 1.0
        if self.has_m:
            self["design", 1, 0] = 1.0
        self["transition"] = np.array([[1.0, 0.0], [0.0, 0.5]])
        self["selection"] = np.eye(2)

    @property
    def param_names(self):
        names = ["log_sd_e", "log_sd_eps", "phi_raw"]
        if not self.fixed_snr:
            names = ["log_sd_eta"] + names
        if self.has_m:
            names += ["log_sd_u", "bias_m"]
        if self.anchored:
            names += ["rho_raw"]
        names += [f"gamma_{i}" for i in range(self.kx)]
        return names

    @property
    def start_params(self):
        y = self.endog[:, 0]; s = float(np.nanstd(np.diff(y[~np.isnan(y)]))) if np.sum(~np.isnan(y)) > 3 else 0.3
        p = [np.log(0.1 * s + 1e-3)] if not self.fixed_snr else []
        p += [np.log(0.5 * s + 1e-3), np.log(0.5 * s + 1e-3), 0.5]
        if self.has_m:
            p += [np.log(0.05 + 1e-3), 0.0]
        if self.anchored:
            p += [1.0]
        p += [0.0] * self.kx
        return np.array(p)

    def transform_params(self, u):
        return np.asarray(u, dtype=float)

    def untransform_params(self, c):
        return np.asarray(c, dtype=float)

    def update(self, params, **kwargs):
        params = super().update(params, **kwargs)
        i = 0
        if self.fixed_snr:
            sd_eta = None
        else:
            sd_eta = np.exp(params[i]); i += 1
        sd_e = np.exp(params[i]); sd_eps = np.exp(params[i + 1]); phi = np.tanh(params[i + 2]) * 0.98; i += 3
        if self.fixed_snr:
            sd_eta = sd_e / np.sqrt(SNR_FIXED)
        obs_cov = np.zeros((self.k_endog, self.k_endog), dtype=params.dtype); obs_cov[0, 0] = sd_e ** 2
        if self.has_m:
            sd_u = np.exp(params[i]); bias = params[i + 1]; i += 2
            obs_cov[1, 1] = sd_u ** 2
            oi = np.zeros((self.k_endog, self.nobs), dtype=params.dtype); oi[1, :] = bias
            self["obs_intercept"] = oi
        self["obs_cov"] = obs_cov
        self["transition", 1, 1] = phi
        if self.anchored:
            rho = RHO_LO + (RHO_HI - RHO_LO) / (1.0 + np.exp(-params[i])); i += 1
            self["transition", 0, 0] = rho
            self._rho = rho
        else:
            self._rho = 1.0
        if self.kx:
            gamma = params[i:i + self.kx]
            self._gamma = np.asarray(gamma)
        else:
            self._gamma = np.zeros(0)
        previous = self.mu if self.anchored else np.zeros(self.nobs)
        current = np.r_[self.mu[1:], self.mu[-1]] if self.anchored else np.zeros(self.nobs)
        drivers = self.x if self.kx else np.empty((self.nobs, 0))
        self["state_intercept"] = transition_intercept(self._rho, drivers, self._gamma, previous, current)
        self["state_cov"] = np.diag([sd_eta ** 2, sd_eps ** 2])
        self._phi = phi


def seasonal_means(y: pd.Series, robust: bool = False) -> dict:
    """Same-calendar-month mean minus the overall mean of a released history;
    robust=True (PATH_SPEC_v4, amendment 1): same-month medians centred so
    the twelve factors sum to zero, so a shock January does not lift every
    later January and the anchored level keeps its target mean."""
    if robust:
        raw = {m: float(y[y.index.month == m].median()) for m in range(1, 13)}
        c = float(np.mean(list(raw.values())))        # PATH_SPEC_v4 amendment 1: factors centred to sum to zero
        return {m: raw[m] - c for m in range(1, 13)}
    mu = float(y.mean())
    return {m: float(y[y.index.month == m].mean() - mu) for m in range(1, 13)}


def fit_forecast(y_hist: pd.Series, horizons: range, m_hist: pd.Series | None = None, x_hist: pd.DataFrame | None = None,
                 fixed_snr: bool = False, anchored: bool = False, robust_seasonal: bool = False,
                 x_future: pd.DataFrame | None = None) -> dict:
    """Fit on the released history (index = monthly Periods, contiguous),
    return {'mm': {h: forecast m/m for last+h}, 'level', 'gap', 'phi', 'rho', 'gamma', 'converged', 'n'}.
    y_hist NSA m/m; seasonal means are removed inside and added back.
    x_hist and x_future rows refer to driver months, before the model's lag.
    x_future may start only after the final observed month; omitted future
    rows mean zero. Already-known x_hist values beyond the y origin are
    preserved too. Explicit future scenarios take precedence there.
    """
    y_hist = released_history(y_hist)
    horizons = list(horizons)
    if any(not isinstance(h, (int, np.integer)) or h < 1 for h in horizons):
        raise ValueError("horizons must be positive integer months")
    for obj, name in ((m_hist, "m_hist"), (x_hist, "x_hist"), (x_future, "x_future")):
        if obj is not None:
            require_monthly_contiguous(obj, name)
            reject_infinite_inputs(obj, name)
    if len(y_hist) < MIN_OBS:
        return {"mm": {h: np.nan for h in horizons}, "converged": False, "n": len(y_hist), "fallback_used": False,
                "fit_diagnostics": {"status": "insufficient_history", "converged": False, "fallback_used": False, "attempts": []}}
    seas = seasonal_means(y_hist, robust=robust_seasonal)
    y_sa = y_hist - np.array([seas[p.month] for p in y_hist.index])
    m = None
    if m_hist is not None:
        m = m_hist.reindex(y_hist.index).values / 12.0
        if np.isnan(m).all():
            m = None
    x = None
    if x_hist is not None and x_hist.shape[1]:
        x = x_hist.reindex(y_hist.index).fillna(0.0).values
        if not np.isfinite(x).all():
            raise ValueError("x_hist drivers must be finite")
    if x_future is not None:
        if x_hist is None or not x_future.columns.equals(x_hist.columns):
            raise ValueError("x_future must have the same columns as x_hist")
        if len(x_future) and x_future.index[0] <= y_hist.index[-1]:
            raise ValueError("x_future must start after the final observed month")
        if not np.isfinite(x_future.to_numpy(dtype=float)).all():
            raise ValueError("explicit x_future values must be finite")
    mu = target_path(y_hist.index).values if anchored else None
    mod = TrendGap(y_sa.values, m, x, fixed_snr=fixed_snr, mu=mu)
    res, diagnostics = fit_with_fallback(mod)
    if res is None:
        return {"mm": {h: np.nan for h in horizons}, "converged": False, "n": len(y_hist),
                "fallback_used": diagnostics["fallback_used"], "fit_diagnostics": diagnostics}
    state = res.filtered_state[:, -1]           # filtered at the origin, never smoothed
    level, gap = float(state[0]), float(state[1])
    phi, rho = float(mod._phi), float(mod._rho)
    last = y_hist.index[-1]
    months = pd.period_range(last, last + max(horizons, default=0), freq="M")
    targets = target_path(months) if anchored else pd.Series(0.0, index=months)
    scenario = pd.DataFrame(index=months, columns=[] if x_hist is None else x_hist.columns, dtype=float)
    if x is not None:
        scenario = x_hist.reindex(months).fillna(0.0)
        if x_future is not None:
            overlap = scenario.index.intersection(x_future.index)
            scenario.loc[overlap] = x_future.loc[overlap]
    projected, out = state.copy(), {}
    for h in range(1, max(horizons, default=0) + 1):
        tgt = last + h
        with np.errstate(over="ignore", invalid="ignore"):
            projected = transition_state(projected, phi, rho, scenario.loc[tgt - 1].to_numpy(), mod._gamma,
                                         float(targets.loc[tgt - 1]), float(targets.loc[tgt]))
            predicted_mm = float(projected.sum()) + seas[tgt.month]
        if not np.isfinite(projected).all() or not np.isfinite(predicted_mm):
            return failed_projection(horizons, len(y_hist), diagnostics, f"horizon_{h}")
        if h in horizons:
            out[h] = predicted_mm
    return {"mm": out, "level": level, "gap": gap, "phi": phi, "rho": rho, "gamma": mod._gamma.tolist(), "converged": diagnostics["converged"], "n": len(y_hist),
            "fallback_used": diagnostics["fallback_used"], "fit_diagnostics": diagnostics,
            "projection_diagnostics": {"status": "finite"},
            "driver_scenario": "explicit_future" if x_future is not None else "known_then_zero",
            "bias_m": float(res.params[mod.param_names.index("bias_m")]) if mod.has_m else np.nan,
            "sd_eta": float(np.sqrt(mod["state_cov", 0, 0])), "sd_eps": float(np.sqrt(mod["state_cov", 1, 1])), "sd_e": float(np.sqrt(mod["obs_cov", 0, 0]))}
