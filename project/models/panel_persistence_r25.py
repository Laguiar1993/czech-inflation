"""R25: the share of the filtered core trend's deviation from a robust norm that survives to each band.

Estimated in real time on a cross-country panel that excludes the evaluation country, with the
unchanged R15 filter run on every panel country exactly as on Czech core. Only this persistence
weight is borrowed; no level, forecast or Czech observation comes from the panel.
"""
import numpy as np
import pandas as pd

from models.core_trend_residual_r15 import state_at

BANDS = (1, 2, 3, 4)
MIN_NORM_MONTHS = 60
MIN_PANEL_ROWS = 200
MIN_OWN_ROWS = 24


def robust_norm(log_rates):
    """Median of complete overlapping twelve-month log changes, per month. NaN below 60 finite months.

    `log_rates` must already be restricted to what was published. Windows across a hole are dropped.
    """
    values = pd.Series(log_rates, dtype=float)
    if values.notna().sum() < MIN_NORM_MONTHS:
        return np.nan
    full = values.reindex(pd.period_range(values.index.min(), values.index.max(), freq='M'))
    annual = full.rolling(12, min_periods=12).sum().dropna()
    return float(annual.median() / 12) if len(annual) else np.nan


def adjusted_band_means(log_by_month, seasonal, months):
    """Mean over each three-month band of log rates less the origin's seasonal pattern; NaN if a month is missing."""
    values = np.array([log_by_month.get(m, np.nan) - seasonal[m.month] for m in months], dtype=float).reshape(4, 3)
    return np.where(np.isfinite(values).all(axis=1), values.mean(axis=1), np.nan)


def country_rows(rates, published, geo, origins):
    """One row per origin and band: FAST forecast mean `f`, realised mean `r`, the norm `mu`, all in log points a month."""
    rates = rates.dropna(); logs = 100 * np.log1p(rates / 100); rows = []
    for s in origins:
        clock = s.to_timestamp() + pd.Timedelta(days=24)                      # month s-1 is published (day 20), month s is not
        state = state_at(rates, published, s, clock)
        if state is None:
            continue
        seasonal = {int(k): float(v) for k, v in state['seasonal'].items()}
        known = logs.loc[logs.index < s]
        mu = robust_norm(known[(published.reindex(known.index) <= clock).to_numpy()])
        months = pd.period_range(s + 1, s + 12, freq='M')
        f = adjusted_band_means({s + int(h): float(v) for h, v in state['forecasts_log']['fast'].items()}, seasonal, months)
        r = adjusted_band_means(logs.to_dict(), seasonal, months)
        for b in BANDS:
            rows.append(dict(geo=geo, origin=s, band=b, label_end=s + 3 * b, f=float(f[b - 1]), r=float(r[b - 1]), mu=mu))
    return rows


def estimate_lambda(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float); denominator = float(x @ x)
    return float(np.clip(x @ y / denominator, 0., 1.)) if denominator > 1e-12 else np.nan


def usable(rows, band, t):
    z = rows[rows.band.eq(band) & (rows.label_end <= pd.Period(t, 'M') - 1)]
    return z[np.isfinite(z[['f', 'r', 'mu']]).all(axis=1)]


def lambda_at(rows, band, t, minimum):
    z = usable(rows, band, t)
    if len(z) < minimum:
        return dict(lam=1., n=len(z), status='fallback_too_few_rows')
    lam = estimate_lambda(z.f - z.mu, z.r - z.mu)
    return dict(lam=lam, n=len(z), status='estimated') if np.isfinite(lam) else dict(lam=1., n=len(z), status='fallback_no_variation')


def two_regime_at(rows, band, t, minimum):
    z = usable(rows, band, t)
    if len(z) < minimum:
        return dict(threshold=np.nan, lam_small=1., lam_large=1., n_small=0, n_large=0, status='fallback_too_few_rows')
    x = (z.f - z.mu).to_numpy(); y = (z.r - z.mu).to_numpy(); threshold = float(np.median(np.abs(x))); small = np.abs(x) <= threshold
    values = [estimate_lambda(x[m], y[m]) for m in (small, ~small)]
    if not np.isfinite(values).all():
        return dict(threshold=threshold, lam_small=1., lam_large=1., n_small=int(small.sum()), n_large=int((~small).sum()), status='fallback_no_variation')
    return dict(threshold=threshold, lam_small=values[0], lam_large=values[1], n_small=int(small.sum()), n_large=int((~small).sum()), status='estimated')


def czech_correction(f_cz, mu_cz, lam):
    """Band corrections to the FAST log rates: move the band mean to mu + lam * (f - mu)."""
    return (np.asarray(lam, float) - 1.) * (np.asarray(f_cz, float) - float(mu_cz))
