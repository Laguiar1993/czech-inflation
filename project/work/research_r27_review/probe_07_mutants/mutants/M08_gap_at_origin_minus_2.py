"""R27: an error-correction term for the food block, h1-6, on the R24 research path.

The gap is the residual of retail food's log level on a trend and the producer (and farm) price levels over the
food system's window, centred by calendar month; the speed is the least-squares response of the centred monthly
food rate to the previous month's gap, clipped to [-0.25, 0]. The correction decays from the last month at which
all levels are published. Everything uses observations published by the origin's clock only.
See docs/implementation/R27_FOOD_ERROR_CORRECTION_SPEC_2026-09-18.md.
"""
import numpy as np
import pandas as pd

from models.food_path_r14 import _aware
from models.food_stable_r14b import WINDOW, MIN_TRAIN

MODELS = ('FOOD_ECM_R27', 'FOOD_ECM_PPI_R27')
REGRESSORS = {'FOOD_ECM_R27': ['food_ppi', 'agri4'], 'FOOD_ECM_PPI_R27': ['food_ppi']}
FIXED_ALPHAS = (-.02, -.05, -.10, -.15)
ALPHA_CLIP = (-.25, 0.)
ACTIVE_HORIZONS = range(1, 7)


def published_levels(levels, available, origin, as_of):
    """Levels strictly before the origin, masked to months published by the clock (per column)."""
    t = pd.Period(origin, 'M'); clock = _aware(as_of)
    y = levels.loc[levels.index < t].copy(); a = available.reindex(y.index)
    for col in y:
        dates = pd.to_datetime(a[col].map(lambda v: _aware(v) if pd.notna(v) else pd.NaT), utc=True)
        y.loc[~(dates.notna() & dates.le(clock)), col] = np.nan
    return y


def last_common_month(published):
    complete = published.dropna()
    if complete.empty:
        return None
    return complete.index.max()


def seasonal_centre(series):
    """Series minus its calendar-month means (the window's own pattern); also the raw seasonal share of variance."""
    means = series.groupby(series.index.month).transform('mean')
    total = float(series.var(ddof=0)); explained = float(means.var(ddof=0)) if total > 0 else 0.
    return series - means, (explained / total if total > 0 else np.nan)


def gap_series(published, regressors, last, window=WINDOW, min_window=MIN_TRAIN):
    """Centred residual of retail food on a trend and the upstream levels over the window ending at `last`."""
    frame = published.loc[:last, ['food', *regressors]].dropna().iloc[-window:]
    if len(frame) < min_window:
        return None, dict(status='insufficient_window', n=len(frame))
    trend = (frame.index.asi8 - frame.index.asi8[0]).astype(float)
    x = np.column_stack([np.ones(len(frame)), trend, frame[regressors].to_numpy(float)]); y = frame.food.to_numpy(float)
    beta, *_ = np.linalg.lstsq(x, y, rcond=None); residual = pd.Series(y - x @ beta, index=frame.index)
    centred, raw_share = seasonal_centre(residual)
    _, centred_share = seasonal_centre(centred)
    fitted_var = float(residual.var(ddof=0)); total_var = float(np.var(y))
    return centred, dict(status='estimated', n=len(frame), window_start=str(frame.index[0]), window_end=str(frame.index[-1]), intercept=float(beta[0]),
                         trend_per_month=float(beta[1]), **{f'coef_{r}': float(b) for r, b in zip(regressors, beta[2:])},
                         r2=1 - fitted_var / total_var if total_var > 0 else np.nan, gap_seasonal_share_raw=raw_share, gap_seasonal_share_centred=centred_share,
                         gap_sd=float(centred.std(ddof=0)))


def adjustment_speed(published, gap, window=WINDOW):
    """Least squares through the origin of the centred food rate on the previous month's gap, over the gap's window."""
    rates = published.food.diff().reindex(gap.index).dropna()
    centred, _ = seasonal_centre(rates)
    pairs = pd.concat([centred.rename('rate'), gap.shift(1).rename('gap')], axis=1).dropna()
    if len(pairs) < 12:
        return 0., dict(status='insufficient_pairs', n_pairs=len(pairs), alpha_raw=np.nan, wrong_sign=True)
    denominator = float(pairs.gap @ pairs.gap)
    raw = float(pairs.rate @ pairs.gap) / denominator if denominator > 0 else 0.
    alpha = float(np.clip(raw, *ALPHA_CLIP))
    return alpha, dict(status='estimated', n_pairs=len(pairs), alpha_raw=raw, wrong_sign=bool(raw >= 0))


def correction(alpha, gap_last, last, origin, horizons=ACTIVE_HORIZONS):
    """h -> log points per month added to the food rate; decays from the last gap month, h beyond the active horizons get 0."""
    t = pd.Period(origin, 'M'); out = {h: 0. for h in range(1, 13)}
    for h in horizons:
        steps = (t + h - 1).ordinal - pd.Period(last, 'M').ordinal
        out[h] = float(alpha * gap_last * (1 + alpha) ** steps)
    return out


def candidates_at(levels, available, origin, as_of, baseline_log_rates, fixed_alphas=FIXED_ALPHAS):
    """All R27 paths at one origin on top of the baseline food log rates (index 0 = h1)."""
    base = np.asarray(baseline_log_rates, float)
    if base.shape != (12,) or not np.isfinite(base).all():
        raise ValueError('Twelve finite baseline food log rates required')
    published = published_levels(levels, available, origin, as_of); last = last_common_month(published)
    out = dict(status='estimated', last_common_month=str(last) if last is not None else None, audits={}, log_rates={}, paths={}, corrections={})
    if last is None:
        out['status'] = 'no_common_month'; return out
    for model, regressors in REGRESSORS.items():
        gap, audit = gap_series(published, regressors, last)
        if gap is None:
            out['status'] = audit['status']; out['audits'][model] = audit; continue
        alpha, speed = adjustment_speed(published, gap)
        gap_last = float(gap.loc[pd.Period(last, 'M') - 1]); variants = {model: alpha}
        if model == 'FOOD_ECM_R27':
            variants.update({f'FOOD_ECM_A{abs(a):.2f}_R27'.replace('.', ''): a for a in fixed_alphas})
        for name, a in variants.items():
            corr = correction(a, gap_last, last, origin); rates = base + np.array([corr[h] for h in range(1, 13)])
            out['corrections'][name] = corr; out['log_rates'][name] = rates.tolist()
            out['paths'][name] = {h: float(100 * np.expm1(rates[h - 1] / 100)) for h in range(1, 13)}
        out['audits'][model] = dict(**audit, **{'speed_' + k: v for k, v in speed.items()}, alpha=alpha, gap_last=gap_last,
                                    cumulative_correction_h6=float(sum(out['corrections'][model][h] for h in range(1, 7))))
    if not out['log_rates']:
        return out
    out['status'] = 'estimated'
    return out
