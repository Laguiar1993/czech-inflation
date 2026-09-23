"""Block-level benchmarks: is a block's path better than doing nothing?

Every block of a path is scored on its cumulative log change over h1..H against two forecasts
that need no model: zero change, and a seasonal-naive forecast built only from observations
published by the origin's clock.
"""
import numpy as np
import pandas as pd

from tools.path_diagnostics.attribution import BLOCKS, default_samples


def _local(value):
    t = pd.Timestamp(value)
    return t.tz_convert('Europe/Prague').tz_localize(None) if t.tzinfo else t


def seasonal_naive_path(rates, published, origin, clock, years=3):
    """h -> mean of the same calendar month over the latest `years` published observations.

    Only months released by `clock` are used, and never a month at or after the origin.
    Missing (NaN) when fewer than `years` such observations exist.
    """
    origin = pd.Period(origin, 'M'); clock = _local(clock)
    released = pd.to_datetime(published.reindex(rates.index))
    known = rates[(rates.index < origin) & released.notna().to_numpy() & (released <= clock).to_numpy()].dropna()
    path = {}
    for h in range(1, 13):
        same = known[known.index.month == (origin + h).month]
        path[h] = float(same.iloc[-years:].mean()) if len(same) >= years else np.nan
    return path


def block_benchmark_scores(native, actual, published, horizons=(3, 6, 12), samples=default_samples, years=3):
    """Per model, block, horizon and sample: model, zero-change and seasonal-naive RMSE.

    Units are log points of the block's own price level (not weighted). All three forecasts are
    scored on identical origins: those where the model path, the seasonal-naive path and the
    realised outcome are all finite.
    """
    clocks = native[native.h.eq(0)].drop_duplicates('origin').set_index('origin').as_of_utc
    log = lambda v: 100 * np.log1p(np.asarray(v, float) / 100)
    records = []
    for block in BLOCKS:
        naive = {o: seasonal_naive_path(actual[block], published, o, clocks[o], years) for o in clocks.index}
        for (model, origin), g in native[native.h.gt(0)].groupby(['model', 'origin']):
            g = g.set_index('h').reindex(range(1, 13)); t = pd.Period(origin, 'M')
            truth = log(actual[block].reindex(pd.period_range(t + 1, t + 12, freq='M')))
            own = log(g['value_' + block]); season = log([naive[origin][h] for h in range(1, 13)])
            for H in horizons:
                records.append(dict(model=model, origin=origin, block=block, H=H, forecast=own[:H].sum(),
                                    seasonal=season[:H].sum(), actual=truth[:H].sum()))
    frame = pd.DataFrame(records)
    frame = frame[np.isfinite(frame[['forecast', 'seasonal', 'actual']]).all(axis=1)]
    rows = []
    for (model, block, H), g in frame.groupby(['model', 'block', 'H']):
        for sample, mask in samples(g).items():
            z = g[mask]
            if z.empty:
                continue
            rmse = lambda e: float(np.sqrt(np.mean(np.square(e))))
            varies = len(z) > 2 and z.forecast.std() > 1e-12 and z.actual.std() > 1e-12
            rows.append(dict(model=model, block=block, H=H, sample=sample, n=len(z), model_rmse=rmse(z.forecast - z.actual),
                             zero_rmse=rmse(z.actual), seasonal_rmse=rmse(z.seasonal - z.actual),
                             model_bias=float((z.forecast - z.actual).mean()), seasonal_bias=float((z.seasonal - z.actual).mean()),
                             forecast_actual_correlation=float(z.forecast.corr(z.actual)) if varies else np.nan))
    return pd.DataFrame(rows)
