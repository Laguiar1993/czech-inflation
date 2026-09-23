"""R26 benchmark family: the forecasts a block must beat before its model is promoted.

Every member uses only realised block monthly rates published by the origin's clock. `SA_AR` is the
practitioner's benchmark relayed on 18 September 2026: seasonally adjust the monthly rate with a centred
calendar-month pattern, let the adjusted deviation follow an AR(1), and forecast the pattern plus the
decaying deviation. `SA_AR_TARGET` anchors core's mean at 2% a year instead of the window mean.
Nothing here is a forecasting candidate; see docs/implementation/R26_BENCHMARK_FAMILY_AND_PROMOTION_RULE_SPEC_2026-09-18.md.
"""
import numpy as np
import pandas as pd

from tools.path_diagnostics.benchmarks import seasonal_naive_path

MEMBERS = ('ZERO', 'SEASONAL_NAIVE', 'SA_AR', 'SA_AR_TARGET')
BLOCKS = ('core', 'food', 'fuel', 'administered', 'alcohol_tobacco')
MAX_WINDOW = 96
MIN_WINDOW = 36
PHI_CLIP = (0., .95)
TARGET_ANNUAL_PCT = 2.
HORIZONS = range(1, 13)


def to_log(percent):
    return 100 * np.log1p(np.asarray(percent, float) / 100)


def to_percent(log_points):
    return 100 * np.expm1(np.asarray(log_points, float) / 100)


def _local(value):
    t = pd.Timestamp(value)
    return t.tz_convert('Europe/Prague').tz_localize(None) if t.tzinfo else t


def published_before(rates, published, origin, clock):
    """Monthly rates strictly before the origin whose release date is at or before the clock (log points)."""
    origin = pd.Period(origin, 'M'); clock = _local(clock)
    released = pd.to_datetime(published.reindex(rates.index))
    mask = (rates.index < origin) & released.notna().to_numpy() & (released <= clock).to_numpy()
    known = rates[mask].dropna()
    return pd.Series(to_log(known.to_numpy()), index=known.index)


def seasonal_pattern(window):
    """Centred calendar-month means of a window of log rates: twelve numbers summing to zero, and the window mean."""
    mean = float(window.mean())
    by_month = window.groupby(window.index.month).mean()
    pattern = np.array([float(by_month.get(m, mean)) - mean for m in range(1, 13)])
    return pattern - pattern.mean(), mean


def ar1(deviations):
    """Least-squares AR(1) through the origin on consecutive months, clipped to PHI_CLIP."""
    d = deviations.dropna()
    if len(d) < 3:
        return float(PHI_CLIP[0])
    ordinal = d.index.asi8
    pairs = [(d.iloc[i - 1], d.iloc[i]) for i in range(1, len(d)) if ordinal[i] - ordinal[i - 1] == 1]
    if len(pairs) < 3:
        return float(PHI_CLIP[0])
    x = np.array([p[0] for p in pairs]); y = np.array([p[1] for p in pairs])
    denominator = float(x @ x)
    phi = float(x @ y) / denominator if denominator > 0 else 0.
    return float(np.clip(phi, *PHI_CLIP))


def sa_ar_path(rates, published, origin, clock, mean_override=None, max_window=MAX_WINDOW, min_window=MIN_WINDOW):
    """h -> forecast monthly rate in percent, plus diagnostics. NaN path when fewer than `min_window` months are published."""
    origin = pd.Period(origin, 'M')
    known = published_before(rates, published, origin, clock)
    window = known.iloc[-max_window:]
    if len(window) < min_window:
        return {h: np.nan for h in HORIZONS}, dict(status='insufficient_window', n=len(window))
    pattern, mean = seasonal_pattern(window)
    level = mean if mean_override is None else float(mean_override)
    deviations = window - mean - pattern[window.index.month - 1]
    phi = ar1(deviations)
    last_month = deviations.index[-1]; last = float(deviations.iloc[-1])
    path = {}
    for h in HORIZONS:
        month = origin + h
        steps = month.ordinal - last_month.ordinal
        path[h] = float(to_percent(level + pattern[month.month - 1] + phi ** steps * last))
    return path, dict(status='estimated', n=len(window), window_start=str(window.index[0]), window_end=str(window.index[-1]),
                      mean_log=mean, level_log=level, phi=phi, last_deviation=last, last_month=str(last_month),
                      gap_months=int((origin - 1).ordinal - last_month.ordinal))


def family_paths(actual, published, origin, clock, blocks=BLOCKS, years=3):
    """{member: {block: {h: percent}}} and {block: diagnostics of SA_AR} for one origin."""
    out = {m: {} for m in MEMBERS}; diagnostics = {}
    target_log = to_log(TARGET_ANNUAL_PCT) / 12
    for block in blocks:
        rates = actual[block]
        out['ZERO'][block] = {h: 0. for h in HORIZONS}
        out['SEASONAL_NAIVE'][block] = seasonal_naive_path(rates, published, origin, clock, years)
        out['SA_AR'][block], diagnostics[block] = sa_ar_path(rates, published, origin, clock)
        out['SA_AR_TARGET'][block], _ = sa_ar_path(rates, published, origin, clock, mean_override=target_log if block == 'core' else None)
    return out, diagnostics


def constant_oracle(actual_cumulative, horizon):
    """The constant monthly log rate minimising RMSE of the cumulative change over `horizon` months: mean(actual)/horizon."""
    values = np.asarray(actual_cumulative, float)
    values = values[np.isfinite(values)]
    if not len(values):
        return np.nan
    return float(values.mean() / horizon)


def replace_blocks(rows, block_paths):
    """FAST-style native rows for one origin (h0..h12) with h1-12 block values replaced; h0, wedge and weights untouched."""
    out = rows.sort_values('h').reset_index(drop=True).copy()
    if list(out.h) != list(range(13)):
        raise ValueError('h0..h12 required')
    for block, path in block_paths.items():
        weight = 'weight_' + ('alc' if block == 'alcohol_tobacco' else block)
        for h in HORIZONS:
            value = path[h]
            out.loc[h, 'mm_forecast'] += out.loc[h, weight] * (value - out.loc[h, 'value_' + block])
            out.loc[h, 'value_' + block] = value; out.loc[h, 'contribution_' + block] = out.loc[h, weight] * value
    return out
