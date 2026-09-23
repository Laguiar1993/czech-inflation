"""PATH_SPEC_v5: semi-structural monthly gap model in the CNB's spirit.

    y_t          = mu_t + g_t + e_t                       SA headline m/m
    mu_t - tau_t = rho (mu_{t-1} - tau_{t-1}) + eta_t     anchored expectations / trend
    g_t          = phi g_{t-1} + b_u ugap_{t-2} + b_q fx12_{t-4} + eps_t
    u_t - u_{t-12} = c + sigma mean(rr_{t-13..t-24}) + nu_t          (IS curve, amendment 1; run 1 used the gap level on its lag)
    rr_t         = i_t - pi12_t - rstar_t

The first two equations reuse TrendGap (models/trend_gap.py, anchored=True,
drivers [ugap, fx12_l3] enter the transition once: source-month ugap
already carries a one-month publication lag and fx12_l3 a three-month
economic lag). The IS curve is OLS. The
forecast is a conditional projection (the estimated equations run forward from the last released month;
no synthetic data anywhere): market rate path, random-walk
exchange rate, IS-projected unemployment, expectations A (geometric) or
M (model-consistent fixed point). Handover: pseudo-observations for the
nowcast months update the filtered states before S continues.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.trend_gap import (TrendGap, seasonal_means, target_path, MIN_OBS, transition_state,
                              released_history, require_monthly_contiguous, fit_with_fallback,
                              reject_infinite_inputs, failed_projection)

UGAP_WINDOW = 60          # months, trailing mean defining the unemployment gap
RSTAR_WINDOW = 120        # months, trailing mean real rate
IS_LAG = 12               # months, real rate to unemployment
SIM_H = 24                # months projected (12 scored)
W_ANCHOR = 0.5            # credibility weight in the model-consistent expectation (declared)


def unemployment_gap(u: pd.Series) -> pd.Series:
    """Unemployment minus a one-sided 60-month mean; vintage validity is separate."""
    require_monthly_contiguous(u, "unemployment")
    return u - u.rolling(UGAP_WINDOW, min_periods=24).mean()


def real_rate_gap(pribor: pd.Series, pi12: pd.Series) -> pd.Series:
    require_monthly_contiguous(pribor, "pribor")
    require_monthly_contiguous(pi12, "pi12")
    rr = (pribor - pi12)
    return rr - rr.rolling(RSTAR_WINDOW, min_periods=36).mean()


def fit_is_curve(u_level: pd.Series, rr: pd.Series, end: pd.Period) -> dict:
    """Amendment 1 (PATH_SPEC_v5): the identifiable form of the IS curve, in annual differences:
    u_t - u_{t-12} = c + sigma x mean(rr_{t-13..t-24}) + nu_t, OLS on rows <= end with everything present.
    (Run 1 used the level of the gap on its own lag; the persistence sat at the unit-root cap and sigma was not identified.)"""
    require_monthly_contiguous(u_level, "unemployment")
    require_monthly_contiguous(rr, "real rates")
    rr_avg = rr.rolling(12, min_periods=12).mean().shift(13)          # mean over t-13..t-24
    df = pd.DataFrame({"du": u_level - u_level.shift(12), "rr": rr_avg})
    df = df[df.index <= end].dropna()
    if len(df) < 60:
        return {"c": 0.0, "sigma": 0.0, "n": len(df), "sd": float("nan"), "fitted": False, "r_u": float("nan")}
    X = np.column_stack([np.ones(len(df)), df.rr.values])
    beta, *_ = np.linalg.lstsq(X, df.du.values, rcond=None)
    resid = df.du.values - X @ beta
    return {"c": float(beta[0]), "sigma": float(beta[1]), "n": len(df), "sd": float(np.std(resid, ddof=2)), "fitted": True, "r_u": float("nan")}


def market_rate_path(quotes: dict, t: pd.Period, horizon: int = SIM_H) -> pd.Series:
    """Monthly 3M-rate path from the money-market curve at the clock: PRIBOR 3M for months t..t+2,
    FRA 3x6 for t+3..t+5, ..., 21x24 for t+21..t+23; missing tenors forward-filled; flat beyond."""
    order = ["pribor3m", "fra3x6", "fra6x9", "fra9x12", "fra12x15", "fra15x18", "fra18x21", "fra21x24"]
    vals, last = [], None
    for k in order:
        v = quotes.get(k)
        if v is None or not np.isfinite(v):
            v = last
        vals.append(v); last = v if v is not None else last
    vals = [v if v is not None else np.nan for v in vals]
    months = pd.period_range(t, t + horizon - 1, freq="M")
    path = []
    for j in range(horizon):
        path.append(vals[min(j // 3, len(vals) - 1)])
    return pd.Series(path, index=months).ffill().bfill()


def _simulate(level0, gap0, phi, rho, gamma, seas, tau_fn, t, ugap_hist, fx_level, rr_hist, is_par, rate_path, pi12_last, rstar_last,
              expectations="A", w=W_ANCHOR, mu_override=None, driver_history=None):
    """Forward projection from the filtered states at t-1 (index t..t+SIM_H-1).
    Order: expectations path -> real-rate path (market rate minus expected inflation) -> unemployment from the IS curve,
    projected from its last public month -> exchange-rate twelve-month change under a random walk -> gap and headline.
    Lags follow the estimation exactly: gap_m uses ugap_{m-2} (publication lag + model lag) and fx12_{m-4}."""
    months = pd.period_range(t, t + SIM_H - 1, freq="M")
    # 1. expectations / trend path
    if mu_override is None:
        lev = level0; tau_prev = float(tau_fn(pd.PeriodIndex([t - 1], freq="M")).iloc[0]); mu = {}
        for m in months:
            tau_m = float(tau_fn(pd.PeriodIndex([m], freq="M")).iloc[0])
            lev = transition_state([lev, 0.0], phi, rho, [], [], tau_prev, tau_m)[0]
            tau_prev = tau_m; mu[m] = lev
        mu_path = pd.Series(mu)
    else:
        mu_path = mu_override.reindex(months).ffill().bfill()
    # 2. real policy rate gap: known through t-1; from t the market path minus expected inflation (12 x mu) minus rstar
    rr = rr_hist.dropna().copy()
    for m in months:
        i_m = float(rate_path.get(m, np.nan))
        rr.loc[m] = (i_m - 12.0 * float(mu_path.loc[m]) - rstar_last) if np.isfinite(i_m) else 0.0
    # 3. unemployment from the IS curve in annual differences, from the month after the last public one;
    #    ugap_hist here is the LEVEL of the unemployment rate (amendment 1); the gap is recomputed along the path
    ul = ugap_hist.dropna().copy()
    require_monthly_contiguous(ul, "finite unemployment history")
    for m in pd.period_range(ul.index[-1] + 1, months[-1], freq="M"):
        win = [rr.get(m - k, np.nan) for k in range(13, 25)]
        win = [v for v in win if np.isfinite(v)]
        rr_avg = float(np.mean(win)) if win else 0.0
        ul.loc[m] = float(ul.get(m - 12, ul.iloc[-1])) + is_par["c"] + is_par["sigma"] * rr_avg
    u = ul - ul.rolling(UGAP_WINDOW, min_periods=24).mean()
    # 4. exchange rate: random walk; twelve-month change fades as the known base rolls off
    L = fx_level.dropna(); Llast = float(L.iloc[-1]); fx12 = {}
    for m in pd.period_range(t - 30, months[-1], freq="M"):
        num = float(L.loc[m]) if m in L.index else Llast
        base = float(L.loc[m - 12]) if (m - 12) in L.index else Llast
        fx12[m] = 100.0 * (num / base - 1.0)
    fx12 = pd.Series(fx12)
    # 5. gap and headline
    driver_months = pd.period_range(t - 1, months[-1], freq="M")
    drivers = pd.DataFrame({"ugap": [u.get(m - 1, 0.0) for m in driver_months],
                            "fx12_l3": [fx12.get(m - 3, 0.0) for m in driver_months]}, index=driver_months).fillna(0.0)
    if driver_history is not None:
        overlap = drivers.index.intersection(driver_history.index)
        # Estimation uses the same declared zero for absent driver values.
        drivers.loc[overlap] = driver_history.loc[overlap, drivers.columns].fillna(0.0)
    g_prev = gap0; out_y, out_ysa, out_g = {}, {}, {}
    for m in months:
        g_m = transition_state([0.0, g_prev], phi, rho, drivers.loc[m - 1].values[:len(gamma)], gamma)[1]
        y_sa = float(mu_path.loc[m]) + g_m
        out_ysa[m] = y_sa; out_y[m] = y_sa + seas[m.month]; out_g[m] = g_m; g_prev = g_m
    return {"y": pd.Series(out_y), "y_sa": pd.Series(out_ysa), "mu": mu_path, "g": pd.Series(out_g), "ugap": u,
            "u_level": ul, "rr": rr, "fx12": fx12, "drivers": drivers}


def fit_forecast_gap(y_hist: pd.Series, X_hist: pd.DataFrame, ugap_hist: pd.Series, fx_level: pd.Series, rr_hist: pd.Series,
                     is_par: dict, rate_path: pd.Series, pi12_last: float, rstar_last: float, expectations: str = "A",
                     w: float = W_ANCHOR, pseudo_obs: pd.Series | None = None) -> dict:
    """Estimate the anchored trend-gap on y_hist (ends t-1) with drivers X_hist (columns ugap, fx12_l3), then simulate.
    pseudo_obs: NSA m/m for months t..t+k (handover) that update the filtered states before S continues from t+k+1.
    Returns {'mm': {h: NSA m/m for (t-1)+h}, params...} with the step-2 convention mm[1] = month t."""
    y_hist = released_history(y_hist)
    for obj, name in ((X_hist, "X_hist"), (ugap_hist, "unemployment"), (fx_level, "FX"),
                      (rr_hist, "real rates"), (rate_path, "rate_path")):
        require_monthly_contiguous(obj, name)
        reject_infinite_inputs(obj, name)
    if list(X_hist.columns) != ["ugap", "fx12_l3"]:
        raise ValueError("X_hist columns must be ['ugap', 'fx12_l3'] in that order")
    if expectations not in ("A", "M") or not 0.0 <= w <= 1.0:
        raise ValueError("expectations must be A or M and w must lie in [0, 1]")
    if len(y_hist) < MIN_OBS:
        return {"mm": {}, "converged": False, "n": len(y_hist), "fallback_used": False,
                "fit_diagnostics": {"status": "insufficient_history", "converged": False, "fallback_used": False, "attempts": []}}
    t = y_hist.index[-1] + 1
    if pseudo_obs is not None and len(pseudo_obs):
        require_monthly_contiguous(pseudo_obs, "pseudo_obs")
        if pseudo_obs.index[0] != t or len(pseudo_obs) > SIM_H or not np.isfinite(pseudo_obs.values).all():
            raise ValueError("pseudo_obs must be finite consecutive months starting immediately after y_hist, up to SIM_H")
    seas = seasonal_means(y_hist)
    y_sa = y_hist - np.array([seas[p.month] for p in y_hist.index])
    x = X_hist.reindex(y_hist.index).fillna(0.0).values
    mu = target_path(y_hist.index).values
    mod = TrendGap(y_sa.values, None, x, fixed_snr=False, mu=mu)
    res, diagnostics = fit_with_fallback(mod)
    if res is None:
        return {"mm": {}, "converged": False, "n": len(y_hist), "fallback_used": diagnostics["fallback_used"],
                "fit_diagnostics": diagnostics}
    phi, rho, gamma = float(mod._phi), float(mod._rho), list(mod._gamma)
    state = res.filtered_state[:, -1]; level0, gap0 = float(state[0]), float(state[1])
    tau_fn = target_path
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        sim = _simulate(level0, gap0, phi, rho, gamma, seas, tau_fn, t, ugap_hist, fx_level, rr_hist, is_par, rate_path, pi12_last, rstar_last, "A", w,
                        driver_history=X_hist)
    if not all(np.isfinite(sim[key].values).all() for key in ("y", "y_sa", "mu", "g")):
        return failed_projection(range(1, SIM_H+1), len(y_hist), diagnostics, "simulation")
    geometric = sim
    expectations_used = expectations
    fixed_point = {"required": expectations == "M", "converged": expectations != "M", "iterations": 0, "fallback": None}
    if expectations == "M":
        # fixed point: mu_s = w tau_s + (1 - w) x average model headline over s+1..s+12 (monthly SA terms); beyond the window, variant A
        mu_cur = sim["mu"].copy()
        for iteration in range(60):
            ysa = sim["y_sa"]
            ext = pd.concat([ysa, pd.Series({m: float(mu_cur.iloc[-1]) for m in pd.period_range(ysa.index[-1] + 1, ysa.index[-1] + 12, freq="M")})])
            new = {}
            for m in mu_cur.index:
                tau_m = float(tau_fn(pd.PeriodIndex([m], freq="M")).iloc[0])
                fwd = ext.loc[m + 1:m + 12]
                new[m] = w * tau_m + (1.0 - w) * float(fwd.mean())
            new = pd.Series(new)
            upd = 0.5 * mu_cur + 0.5 * new
            residual = float(np.max(np.abs(upd.values - mu_cur.values)))
            done = np.isfinite(residual) and residual < 1e-7
            mu_cur = upd
            sim = _simulate(level0, gap0, phi, rho, gamma, seas, tau_fn, t, ugap_hist, fx_level, rr_hist, is_par, rate_path, pi12_last, rstar_last, "M", w,
                            mu_override=mu_cur, driver_history=X_hist)
            finite = np.isfinite(sim["y_sa"].values).all()
            fixed_point.update(converged=bool(done and finite), iterations=iteration + 1,
                               max_update=residual if np.isfinite(residual) else None)
            if done or not finite:
                break
        if not fixed_point["converged"]:
            # Keep difficult origins: a failed fixed point uses the already
            # computed geometric expectation path and is explicitly flagged.
            sim, expectations_used = geometric, "A"
            fixed_point["fallback"] = "geometric_A"
    handover_from = None
    if pseudo_obs is not None and len(pseudo_obs):
        # Condition the SAME monthly transition and frozen driver scenario on
        # the handover observations. Start with the origin's filtered state
        # AND covariance; a missing origin observation avoids updating twice.
        # For M, the solved conditional mean path supplies the level forcing;
        # subsequent measurement innovations decay around it at rate rho.
        months = pd.period_range(t - 1, t + SIM_H - 1, freq="M")
        y_cond = pd.Series(np.nan, index=months)
        y_cond.loc[pseudo_obs.index] = pseudo_obs.values - np.array([seas[m.month] for m in pseudo_obs.index])
        anchors = (np.r_[level0, sim["mu"].values] if expectations_used == "M" else target_path(months).values)
        mod2 = TrendGap(y_cond.values, x=sim["drivers"].reindex(months).values, mu=anchors)
        mod2.initialize_known(state, res.filtered_state_cov[:, :, -1])
        res2 = mod2.filter(res.params, cov_type="none")
        conditional = res2.filtered_state[:, 1:]
        sim["mu"] = pd.Series(conditional[0], index=months[1:])
        sim["g"] = pd.Series(conditional[1], index=months[1:])
        y_path = sim["mu"] + sim["g"] + np.array([seas[m.month] for m in months[1:]])
        y_path.loc[pseudo_obs.index] = pseudo_obs
        handover_from = str(pseudo_obs.index[-1] + 1)
    else:
        y_path = sim["y"]
    if not all(np.isfinite(path.values).all() for path in (y_path, sim["mu"], sim["g"])):
        return failed_projection(range(1, SIM_H+1), len(y_hist), diagnostics, "handover")
    mm = {h: float(y_path.get(t - 1 + h, np.nan)) for h in range(1, SIM_H + 1)}
    return {"mm": mm, "level": level0, "gap": gap0, "phi": phi, "rho": rho, "gamma": gamma,
            "converged": diagnostics["converged"] and fixed_point["converged"], "n": len(y_hist),
            "fallback_used": diagnostics["fallback_used"] or fixed_point["fallback"] is not None,
            "fit_diagnostics": diagnostics, "fixed_point": fixed_point, "expectations_used": expectations_used,
            "projection_diagnostics": {"status": "finite"},
            "is": is_par, "handover_from": handover_from, "mu_path": sim["mu"], "ugap_path": sim["ugap"],
            "driver_path": sim["drivers"], "handover_scenario": "fixed_conditional_drivers"}
