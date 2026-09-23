"""R24: where the food path settles. Only the long-horizon centre of the R14B food system changes.

The frozen R14B system centres monthly rates on calendar-month means of its training window,
so its forecasts decay to a centre that carries the window's average drift. R24 keeps the
seasonal shape and the system's decaying deviation, and replaces that drift with zero, with a
robust median over the same window, or with a robust median over food history from 1996.
"""
import numpy as np
import pandas as pd

from models.food_path_r14 import condition_state, _aware
from models.food_stable_r14b import (MODELS as BASELINE_MODELS, LAGS, WINDOW, MIN_TRAIN, released_rates, design,
                                     fit_rate_var, simulate_rates, forecast_origin)

MODELS = ('FOOD_ZERO_DRIFT_R24', 'FOOD_ROBUST_WINDOW_R24', 'FOOD_NORM_SHIFT_R24', 'FOOD_NORM_REFIT_R24')
LONG_HISTORY = 'data/research_r14/food/coverage_extension/czso_cpi_1995_2025.csv'
LONG_START = pd.Period('1996-01', 'M')
MIN_WINDOWS = 12            # at least twelve complete twelve-month changes before a median is called a drift


def long_food_rates(levels, available, long_csv):
    """Monthly food log changes from 1995-02: CZSO division 01 before 2015-02, the model's own series after."""
    raw = pd.read_csv(long_csv, dtype=str)
    raw = raw[raw.ucel_kod.eq('01') & raw.casz_kod.eq('Z')]
    index = pd.Series(raw.hodnota.astype(float).to_numpy(), index=pd.PeriodIndex(raw.rok + '-' + raw.mesic.str.zfill(2), freq='M')).sort_index()
    if not index.index.is_unique or not index.index.equals(pd.period_range(index.index.min(), index.index.max(), freq='M')) or (index <= 0).any():
        raise ValueError('Contiguous positive base-year food index required')
    old = (100 * np.log(index)).diff().dropna(); own = levels.food.diff().dropna()
    rates = pd.concat([old[old.index < own.index.min()], own]).sort_index()
    if not rates.index.equals(pd.period_range(rates.index.min(), rates.index.max(), freq='M')):
        raise ValueError('Spliced food history must be contiguous')
    rule = pd.Series((rates.index + 1).to_timestamp() + pd.Timedelta(days=9, hours=9), index=rates.index).dt.tz_localize('Europe/Prague').dt.tz_convert('UTC')
    recorded = pd.to_datetime(available.food.reindex(rates.index), utc=True)
    return rates, recorded.where(recorded.notna(), rule)


def median_annual_drift(rates, published, clock, start=LONG_START, allowed=None):
    """Median of complete overlapping twelve-month log changes published by `clock`, per month.

    A window is used only if all twelve months are finite, published and (when given) inside
    `allowed`. Windows across a hole are dropped, never bridged. Fewer than MIN_WINDOWS gives NaN.
    """
    clock = _aware(clock); stamp = pd.to_datetime(published.reindex(rates.index), utc=True)
    usable = rates.notna() & stamp.notna() & (stamp <= clock) & (rates.index >= start)
    if allowed is not None:
        usable &= rates.index.isin(pd.PeriodIndex(allowed, freq='M'))
    full = pd.period_range(rates.index.min(), rates.index.max(), freq='M')
    value = rates.where(usable).reindex(full)
    annual = value.rolling(12, min_periods=12).sum().dropna()
    return float(annual.median() / 12) if len(annual) >= MIN_WINDOWS else np.nan


def decompose(calendar_means):
    means = np.asarray(calendar_means, float)
    if means.shape != (12,) or not np.isfinite(means).all():
        raise ValueError('Twelve finite calendar-month means required')
    mu = float(means.mean())
    return mu, means - mu


def refit_forecast(levels, available, origin, as_of, shift=0.):
    """The R14B pipeline system with its food centre moved by `shift` log points a month.

    Same released rates, training dates, priors, scale, stability contraction, ragged-edge
    conditioning and simulation as `forecast_origin`. With shift=0 it reproduces it exactly.
    """
    t = pd.Period(origin, 'M'); rates, _ = released_rates(levels, available, t, as_of)
    x, target, index = design(rates)
    dates = index[np.isfinite(x).all(axis=1) & np.isfinite(target).all(axis=1)][-WINDOW:]
    if len(dates) < MIN_TRAIN:
        return None
    centre = fit_rate_var(rates, dates)['seasonal_means'].copy(); food = list(rates.columns).index('food')
    centre[:, food] += shift
    fit = fit_rate_var(rates, dates, shared_means=centre); means = fit['seasonal_means']; k = rates.shape[1]
    candidates = [i for i in range(LAGS - 1, len(rates)) if np.isfinite(rates.iloc[i - LAGS + 1:i + 1].to_numpy()).all()]
    anchor = candidates[-1]
    state = np.concatenate([rates.iloc[anchor - l].to_numpy() - means[rates.index[anchor - l].month - 1] for l in range(LAGS)])
    covariance = np.zeros((k * LAGS, k * LAGS)); process = covariance.copy(); process[:k, :k] = fit['Q']
    for i in range(anchor + 1, len(rates)):
        state = fit['A'] @ state; covariance = fit['A'] @ covariance @ fit['A'].T + process
        observed = {j: float(rates.iloc[i, j] - means[rates.index[i].month - 1, j]) for j in range(k) if np.isfinite(rates.iloc[i, j])}
        state, covariance = condition_state(state, covariance, observed)
    predicted = simulate_rates(fit['A'], state, t, 13, means)[:, food]
    return dict(log_rates=predicted.tolist(), spectral_radius=fit['spectral_radius'], contraction=fit['contraction'],
                n_train=fit['n_train'], train_start=fit['train_start'], train_end=fit['train_end'])


def candidates_at(levels, available, long_rates, long_published, origin, as_of):
    t = pd.Period(origin, 'M'); frozen = forecast_origin(levels, available, t, as_of)
    out = dict(status=frozen['diagnostics']['status'], drifts={}, baseline_log_rates=[], log_rates={}, paths={}, baseline_path={}, refit={})
    if out['status'] != 'estimated':
        return out
    fit = frozen['fits'][0]; food = fit['columns'].index('food')
    mu_window, _ = decompose(np.asarray(fit['seasonal_means'])[:, food])
    drifts = dict(mu_window=mu_window, mu_robust=median_annual_drift(long_rates, long_published, as_of, allowed=fit['training_dates']),
                  mu_long=median_annual_drift(long_rates, long_published, as_of))
    if not np.isfinite(list(drifts.values())).all():
        out['status'] = 'missing_drift_estimate'; return out
    base = np.asarray(frozen['forecast_food_rates'][BASELINE_MODELS[0]])[1:13]
    refit = refit_forecast(levels, available, t, as_of, shift=drifts['mu_long'] - mu_window)
    logs = {'FOOD_ZERO_DRIFT_R24': base - mu_window, 'FOOD_ROBUST_WINDOW_R24': base - mu_window + drifts['mu_robust'],
            'FOOD_NORM_SHIFT_R24': base - mu_window + drifts['mu_long'], 'FOOD_NORM_REFIT_R24': np.asarray(refit['log_rates'])[1:13]}
    for name, values in logs.items():
        if not np.isfinite(values).all():
            raise ArithmeticError('Nonfinite food path: ' + name)
        out['log_rates'][name] = values.tolist(); out['paths'][name] = {h: float(100 * np.expm1(values[h - 1] / 100)) for h in range(1, 13)}
    out.update(drifts=drifts, baseline_log_rates=base.tolist(), baseline_path=frozen['paths'][BASELINE_MODELS[0]],
               refit={k: v for k, v in refit.items() if k != 'log_rates'})
    return out
