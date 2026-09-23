"""Where a path's error sits: exact monthly block accounting and per-call attribution.

A monthly headline forecast error is the sum over blocks of weight x (forecast - actual), plus
the reconciliation wedge. The h0 month is the independent nowcast and is kept as its own
bucket. For a frozen origin o and target month T = o+h, the error of the annual rate is, to a
close approximation, the sum of the monthly errors over the forecast months inside the
twelve-month window: known history cancels. Look at this table before choosing what to model.
"""
import numpy as np
import pandas as pd

BLOCKS = {'core': 'weight_core', 'food': 'weight_food', 'fuel': 'weight_fuel',
          'administered': 'weight_administered', 'alcohol_tobacco': 'weight_alc'}
PARTS = ['h0', *BLOCKS, 'wedge']


def monthly_block_errors(native, actual):
    """Per origin, model and horizon: e_<part> monthly errors and c_<part> cumulative sums.

    `native` holds h0..h12 rows with block values, weights, mm_forecast and mm_actual.
    `actual` is a monthly-period frame of realised block rates. Cumulation propagates a
    missing month, so unmatured targets stay missing. c_<block> sums h1..h; c_h0 is the
    nowcast error carried in the price level; c_total is their sum with the wedge.
    """
    need = {'origin', 'model', 'h', 'target', 'mm_forecast', 'mm_actual', *BLOCKS.values(), *['value_' + b for b in BLOCKS]}
    missing = need - set(native.columns)
    if missing:
        raise ValueError('Native forecasts lack columns: ' + ', '.join(sorted(missing)))
    if native.duplicated(['origin', 'model', 'h']).any():
        raise ValueError('Duplicate origin/model/horizon rows')
    out = native[['origin', 'model', 'h', 'target', 'mm_forecast', 'mm_actual']].copy()
    targets = pd.PeriodIndex(native.target.astype(str), freq='M')
    future = native.h.gt(0).to_numpy()
    for block, weight in BLOCKS.items():
        truth = actual[block].reindex(targets).to_numpy(float)
        error = native[weight].to_numpy(float) * (native['value_' + block].to_numpy(float) - truth)
        out['e_' + block] = np.where(future, error, 0.)
    out['e_total'] = out.mm_forecast - out.mm_actual
    out['e_h0'] = np.where(future, 0., out.e_total)
    out['e_wedge'] = np.where(future, out.e_total - out[['e_' + b for b in BLOCKS]].sum(axis=1, skipna=False), 0.)
    out = out.sort_values(['model', 'origin', 'h']).reset_index(drop=True)
    columns = ['e_' + p for p in PARTS] + ['e_total']
    cumulative = np.vstack([np.cumsum(g[columns].to_numpy(float), axis=0) for _, g in out.groupby(['model', 'origin'], sort=False)])
    out[['c_' + c[2:] for c in columns]] = cumulative
    return out


def default_samples(frame):
    return {'full': pd.Series(True, index=frame.index), 'origins_2024plus': frame.origin.ge('2024-01')}


def block_error_table(monthly, horizons=(6, 12), samples=default_samples):
    """RMS and bias of cumulative weighted errors, in percentage points of headline."""
    rows = []
    for H in horizons:
        at = monthly[monthly.h.eq(H)]
        for sample, mask in samples(at).items():
            for model, g in at[mask].groupby('model'):
                for part in [*PARTS, 'total']:
                    v = g['c_' + part].dropna().to_numpy(float)
                    rows.append(dict(model=model, H=H, sample=sample, block=part, n=len(v),
                                     rms=float(np.sqrt(np.mean(v ** 2))) if len(v) else np.nan,
                                     bias=float(v.mean()) if len(v) else np.nan))
    return pd.DataFrame(rows)


def quarter_attribution(monthly, model, origin, quarter):
    """Mean contribution of each part to the error of a quarter-average annual rate.

    Months before the origin are known history and contribute zero. The h0 month leaves the
    twelve-month window at h12, so its contribution is dropped there. Returns None when the
    quarter reaches beyond h12 or any needed month is unmatured.
    """
    o = pd.Period(origin, 'M'); q = pd.Period(quarter, 'Q')
    own = monthly[monthly.model.eq(model) & monthly.origin.eq(str(o))].set_index('h')
    if own.empty:
        return None
    columns = ['c_' + p for p in PARTS]
    values = []
    for month in pd.period_range(q.asfreq('M', 'start'), q.asfreq('M', 'end'), freq='M'):
        h = month.ordinal - o.ordinal
        if h < 0:
            values.append(np.zeros(len(columns))); continue
        if h > 12 or h not in own.index:
            return None
        row = own.loc[h, columns].to_numpy(float).copy()
        if h == 12:
            row[0] = 0.
        values.append(row)
    mean = np.mean(values, axis=0)
    if not np.isfinite(mean).all():
        return None
    result = pd.Series(mean, index=columns)
    result['c_total'] = float(mean.sum())
    return result


def call_attribution(calls, clocks, monthly):
    """One row per call: model error, its block decomposition and the dominant block.

    `calls` needs model, clock, report_date, quarter, forecast, realised and deviation.
    The dominant block is the largest contribution in the direction of the model's error.
    """
    lookup = {(r.clock, r.report_date): r.origin for r in clocks.itertuples() if isinstance(r.origin, str)}
    rows = []
    for r in calls.itertuples():
        origin = lookup.get((r.clock, r.report_date))
        parts = quarter_attribution(monthly, r.model, origin, r.quarter) if origin else None
        row = dict(model=r.model, clock=r.clock, report_date=r.report_date, quarter=r.quarter, origin=origin,
                   deviation=r.deviation, model_error=r.forecast - r.realised)
        if parts is None or not np.isfinite(row['model_error']):
            rows.append(dict(**row, approx_error=np.nan, dominant_block=None, **{p: np.nan for p in PARTS})); continue
        signed = {p: float(parts['c_' + p]) * np.sign(row['model_error']) for p in PARTS}
        rows.append(dict(**row, approx_error=float(parts['c_total']), dominant_block=max(signed, key=signed.get),
                         **{p: float(parts['c_' + p]) for p in PARTS}))
    return pd.DataFrame(rows)
