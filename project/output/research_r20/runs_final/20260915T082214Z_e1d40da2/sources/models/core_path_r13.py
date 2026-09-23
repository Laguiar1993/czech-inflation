"""Fixed R13 arithmetic core targets; pure calculations on frozen inputs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.core_split import CATEGORIES, REMAINDER, visible_history
from models.core_tuning import _monthly

PRIMARY = ('CORE_AGG_MONTHLY_R13', 'CORE_AGG_CUMULATIVE_R13',
           'CORE_SPLIT_MONTHLY_R13', 'CORE_SPLIT_CUMULATIVE_R13')
LABOUR = ('CORE_AGG_CUMULATIVE_LABOUR_R13', 'CORE_AGG_CUMULATIVE_LABOUR_CONTROL_R13')
EXTERNAL = ('import_mm_l3', 'eurczk_mm_l1')
LABOUR_COLUMN = 'unemployment_rate_l3'
MIN_TRAIN = 48
PENALTY = 1.0


def _local(clock):
    stamp = pd.Timestamp(clock)
    if pd.isna(stamp):
        raise ValueError('A known decision clock is required')
    return stamp.tz_convert('Europe/Prague').tz_localize(None) if stamp.tzinfo else stamp


def external_at(features, labour, origin, historical_clock, current_clock):
    """Exact declared source months; no latest-snapshot or older-month fallback."""
    if not {'import_l2', 'eurczk_mm'}.issubset(features):
        raise ValueError('Required frozen import_l2 and eurczk_mm columns absent')
    r = pd.Period(origin, 'M')
    cap = min(_local(historical_clock), _local(current_clock)).tz_localize('Europe/Prague').tz_convert('UTC')
    values, audit = {}, {'origin': str(r), 'historical_clock': str(historical_clock)}
    for name, column, source, published in (
        ('import_mm_l3', 'import_l2', r-3, (r-1).to_timestamp()+pd.Timedelta(days=15)),
        ('eurczk_mm_l1', 'eurczk_mm', r-1, r.to_timestamp())):
        available = published.tz_localize('Europe/Prague').tz_convert('UTC')
        value = features[column].get(r-1, np.nan)
        values[name] = float(value) if available <= cap and np.isfinite(value) else np.nan
        audit.update({name+'_source': str(source), name+'_fixture_row': str(r-1),
                      name+'_available_from': available.isoformat()})
    rows = labour.loc[(labour.reference_period == str(r-3)) & labour.adjustment.isin(['sa', 'trend_cycle'])].copy()
    if not rows.vintage_kind.eq('historical_release').all():
        raise ValueError('Labour requires historical release vintages')
    if 'series' in rows and not rows.series.eq('unemployment_'+rows.adjustment).all():
        raise ValueError('Labour series and adjustment metadata disagree')
    for value in rows.available_from:
        stamp = pd.Timestamp(value)
        if pd.notna(stamp) and stamp.tzinfo is None:
            raise ValueError('Labour publication timestamps must be timezone-aware')
    stamps = pd.to_datetime(rows.available_from, utc=True, errors='coerce')
    rows = rows.loc[stamps.notna() & stamps.le(cap)].copy()
    rows['_stamp'] = stamps.loc[rows.index]
    rows = rows.sort_values('_stamp')
    values[LABOUR_COLUMN] = np.nan
    audit.update(unemployment_reference=str(r-3), unemployment_adjustment=None,
                 unemployment_available_from=None)
    if len(rows):
        if rows._stamp.duplicated().any():
            raise ValueError('Ambiguous labour adjustment/vintage at identical publication')
        row = rows.iloc[-1]
        values[LABOUR_COLUMN] = float(row.value)
        audit.update(unemployment_adjustment=row.adjustment,
            unemployment_available_from=row._stamp.isoformat(),
            unemployment_source=row.get('source', None), unemployment_sha256=row.get('sha256', None))
    return pd.Series(values), audit


def target_panel(core, categories, weights, core_weight, origin, as_of, available):
    """Rebuild the entire observed projection at the OUTER origin's weights."""
    if not categories.columns.is_unique or not weights.index.is_unique:
        raise ValueError('Category names and weight indices must be unique')
    if set(categories.columns) != set(CATEGORIES) or set(weights.index) != set(CATEGORIES):
        raise ValueError('Exactly the five declared categories and basket fractions required')
    if (not np.isfinite(core_weight) or not 0 < core_weight <= 1 or
        not np.isfinite(weights).all() or (weights <= 0).any() or weights.sum() >= 1):
        raise ValueError('Invalid core or category weights')
    c = visible_history(core, origin, _local(as_of), available)
    cats = visible_history(categories.reindex(core.index), origin, _local(as_of), available)
    common = np.isfinite(c) & np.isfinite(cats).all(axis=1)
    panel = cats.where(common, np.nan).copy()
    panel['core'] = c.where(common)
    panel[REMAINDER] = (core_weight*c-cats.mul(weights).sum(axis=1, min_count=5)).where(common)
    return panel.loc[panel.index <= origin, ['core', *CATEGORIES, REMAINDER]]


def feature_design(target, external, h, *, include_labour=False):
    if not set(external.columns).issubset({*EXTERNAL, LABOUR_COLUMN}):
        raise ValueError('Unsupported external predictor column')
    if not set(EXTERNAL).issubset(external):
        raise ValueError('Missing declared primary external predictor')
    _monthly(target, 'target')
    x = pd.DataFrame({f'own_l{lag}': target.shift(lag) for lag in (1, 2, 12)}, index=target.index)
    columns = list(EXTERNAL) + ([LABOUR_COLUMN] if include_labour else [])
    x = x.join(external[columns].reindex(target.index))
    for month in range(2, 13):
        x[f'destination_mon_{month}'] = ((x.index+h).month == month).astype(float)
    return x


def fit_ridge(x, target, now):
    """Fixed mean-loss ridge, unpenalised intercept, eligible-training-only scale."""
    diag = dict(n_train=len(x), fit_status='insufficient_history', coefficients={},
                training_center={}, training_scale={})
    if len(x) < MIN_TRAIN:
        return np.nan, diag
    if not np.isfinite(now.to_numpy(dtype=float)).all():
        diag['fit_status'] = 'unavailable_current_predictor'
        return np.nan, diag
    if not np.isfinite(x.to_numpy(dtype=float)).all() or not np.isfinite(target).all():
        raise ValueError('Training rows must be complete; no imputation is allowed')
    center, scale = x.mean(), x.std(ddof=0)
    scale = scale.mask((x.nunique(dropna=False) <= 1) | scale.eq(0), 1.)
    z = ((x-center)/scale).to_numpy(dtype=float)
    mean = float(target.mean())
    beta = np.linalg.solve(z.T@z+len(x)*PENALTY*np.eye(z.shape[1]), z.T@(target.to_numpy()-mean))
    prediction = float(mean+((now-center)/scale).to_numpy()@beta)
    diag.update(fit_status='estimated', coefficients=dict(zip(x.columns, beta.tolist())),
        intercept_target_mean=mean, training_center=center.to_dict(), training_scale=scale.to_dict())
    return prediction, diag


def reconstruct_cumulative(cumulative):
    """Difference arithmetic sums; NaN horizons remain missing, never bridged."""
    return {h: float(cumulative[h]-(cumulative[h-1] if h > 1 else 0.)) for h in range(1, 13)}


def replace_core(frame, core_path):
    """Preserve original h0, noncore columns, weights and failed noncore rows."""
    out = frame.copy()
    noncore = [f'contribution_{b}' for b in ('food','administered','alcohol_tobacco','fuel','wedge')]
    for h, value in core_path.items():
        if not 1 <= h <= 12:
            raise ValueError('Only future core horizons h1..12 may be replaced')
        selected = out.h.eq(h)
        out.loc[selected, 'value_core'] = value
        out.loc[selected, 'contribution_core'] = out.loc[selected, 'weight_core']*value
        out.loc[selected, 'mm_forecast'] = out.loc[selected, noncore+['contribution_core']].sum(axis=1,min_count=6)
    return out


def forecast_origin(core, categories, weights, core_weight, available,
                    historical_clocks, external, origin, as_of):
    """All four factorial fits share feature/complete-window calendars per h."""
    t = pd.Period(origin, 'M'); clock = _local(as_of)
    panel = target_panel(core, categories, weights, core_weight, t, clock, available)
    index = panel.index
    dates = pd.to_datetime(available.reindex(index))
    clocks = pd.to_datetime(historical_clocks.reindex(index).map(lambda c: _local(c) if pd.notna(c) else pd.NaT))
    external = external.reindex(index)
    own_public = np.ones(len(index), dtype=bool)
    for lag in (1, 2, 12):
        released = dates.shift(lag)
        own_public &= released.notna().to_numpy() & released.le(clocks).to_numpy() & released.le(clock).to_numpy()
    raw = {name: {} for name in (*PRIMARY, *LABOUR)}
    fits, contributions = [], []
    for h in range(1, 13):
        designs = {block: feature_design(panel[block], external, h) for block in panel}
        design_common = own_public.copy()
        for x in designs.values():
            design_common &= np.isfinite(x.to_numpy(dtype=float)).all(axis=1)
        # The complete interval is eligible for BOTH monthly and cumulative targets.
        label_common = (index+h < t)
        label_sum = panel*0.
        label_sum.iloc[:] = 0.
        last_release = pd.Series(pd.NaT, index=index, dtype='datetime64[ns]')
        for k in range(1, h+1):
            shifted = panel.shift(-k)
            release = dates.shift(-k)
            label_common &= np.isfinite(shifted.to_numpy(dtype=float)).all(axis=1)
            label_common &= release.notna().to_numpy() & release.le(clock).to_numpy()
            label_sum += shifted
            last_release = pd.concat([last_release, release],axis=1).max(axis=1)
        main_mask = design_common & label_common
        now_common = bool(design_common[index.get_loc(t)])
        labour_finite = np.isfinite(external[LABOUR_COLUMN]).to_numpy()
        for name in (*PRIMARY, *LABOUR):
            labour_pair = name in LABOUR
            mask = main_mask & labour_finite if labour_pair else main_mask
            train = index[mask]
            cumulative = 'CUMULATIVE' in name
            blocks = list(CATEGORIES)+[REMAINDER] if 'SPLIT' in name else ['core']
            total = 0.
            for block in blocks:
                x = designs[block]
                if name == LABOUR[0]:
                    x = feature_design(panel[block], external, h, include_labour=True)
                response = label_sum[block]/h if cumulative else panel[block].shift(-h)
                now = x.loc[t].copy()
                if not now_common or (labour_pair and not labour_finite[index.get_loc(t)]):
                    now.iloc[:] = np.nan
                value, info = fit_ridge(x.loc[train], response.loc[train], now)
                multiplier = h if cumulative else 1
                target_prediction = multiplier*value
                coefficient = float(weights[block]) if block in weights.index else (1. if block==REMAINDER else core_weight)
                total += coefficient*target_prediction/core_weight
                fits.append(dict(model=name, block=block, h=h, as_of=str(clock),
                    train_start=str(train.min()) if len(train) else None,
                    train_end=str(train.max()) if len(train) else None,
                    last_training_target=str(train.max()+h) if len(train) else None,
                    training_last_release=str(last_release.loc[train].max()) if len(train) else None,
                    training_origins='|'.join(map(str,train)), current_predictors=now.to_dict(),
                    target_kind='arithmetic_mean_future_mm' if cumulative else 'monthly_mm',
                    prediction=value, **info))
                contributions.append(dict(model=name, block=block, h=h,
                    native_target_prediction=target_prediction, projection_coefficient=coefficient,
                    projected_core_target=coefficient*target_prediction/core_weight))
            raw[name][h] = float(total)
    paths = {name: reconstruct_cumulative(values) if 'CUMULATIVE' in name else values
             for name, values in raw.items()}
    identity = panel[list(CATEGORIES)].mul(weights).sum(axis=1,min_count=5)+panel[REMAINDER]-core_weight*panel.core
    return dict(paths=paths, native_targets=raw, fits=fits, contributions=contributions,
                max_reconciliation_error=float(identity.abs().max()))
