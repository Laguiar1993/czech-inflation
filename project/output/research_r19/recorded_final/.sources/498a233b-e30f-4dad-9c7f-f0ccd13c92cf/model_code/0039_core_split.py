"""Fixed R10 core-disaggregation experiments; no survey input or model search.

The five service groups are raw CPI groups, not a tax-adjusted partition of CNB
core. Their base-basket contributions and a reconciliation remainder are an
explicit statistical projection. The broad ARAD inputs are tax-inclusive YoY
rates; a log-change identity permits their use without inventing monthly levels.
Exogenous frames must already carry publication shifts and origin masking.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
from dateutil.easter import easter

from models.core_tuning import _monthly, hard_features, ridge_prediction

CATEGORIES = ('actual_rent', 'imputed_rent', 'catering', 'accommodation', 'package_holidays')
REMAINDER = 'remaining_core_tax_reconciliation'


def annual_log_change(yoy):
    if (yoy.dropna() <= -100).any():
        raise ValueError('annual inflation requires positive gross price ratios')
    return 100 * np.log1p(yoy / 100).diff()


def monthly_from_annual_change(delta, previous_year_mm):
    return 100 * np.expm1(delta / 100 + np.log1p(previous_year_mm / 100))


def visible_history(values, origin, as_of, available):
    _monthly(values, 'values')
    _monthly(available, 'available')
    if not values.index.isin(available.index).all():
        raise ValueError('publication calendar must cover input values')
    clock = pd.Timestamp(as_of)
    if pd.isna(clock):
        raise ValueError('valid as_of required')
    known = (values.index < origin) & pd.to_datetime(available.reindex(values.index)).le(clock).to_numpy()
    out = values.copy()
    out.loc[~known] = np.nan
    return out


def own_features(target):
    _monthly(target, 'target')
    x = pd.DataFrame({f'own_l{lag}': target.shift(lag) for lag in (1, 2, 12)}, index=target.index)
    for month in range(2, 13):
        x[f'mon_{month}'] = (target.index.month == month).astype(float)
    return x


def easter_exposure(index):
    """Share of Palm Sunday through Easter Monday (nine known calendar days)."""
    result = pd.Series(0., index=index)
    for year in set(index.year):
        sunday = easter(int(year))
        for offset in range(-7, 2):
            period = pd.Period(sunday + timedelta(days=offset), freq='M')
            if period in index:
                result.loc[period] += 1/9
    return result


def past_projection(core_delta, broad_delta, origin, as_of, available):
    """60-calendar-month, no-intercept convex projection; weights are NOT shares."""
    c = visible_history(core_delta, origin, as_of, available)
    b = visible_history(broad_delta, origin, as_of, available)
    z = pd.concat([c.rename('core'), b[['goods', 'services']]], axis=1)
    z = z.loc[(z.index >= origin-60) & (z.index < origin)].dropna()
    info = {'projection_n': len(z), 'projection_start': z.index.min() if len(z) else None,
            'projection_end': z.index.max() if len(z) else None}
    if len(z) < 48:
        return np.nan, c * np.nan, info
    x = z.goods - z.services
    y = z.core - z.services
    denominator = float(x @ x)
    weight = float(np.clip((x @ y) / denominator, 0, 1)) if denominator > 1e-14 else .5
    residual = c - weight * b.goods - (1-weight) * b.services
    return weight, residual, info


def forecast_origin(core, categories, broad_yoy, independent_x, food_x, available,
                    origin, as_of, weights, *, core_weight):
    """Return core-m/m predictions, per-fit cutoffs and projected contributions.

    Forecasting sees only past published component observations. All targets in
    each services fit share one finite training calendar. Fixed origin weights
    are used to reconstruct the ENTIRE past remainder before fitting it.
    """
    if not np.isfinite(core_weight) or not 0 < core_weight <= 1:
        raise ValueError('core weight must be finite and in (0,1]')
    if set(categories.columns) != set(CATEGORIES) or set(weights.index) != set(CATEGORIES):
        raise ValueError('the declared five categories and their weights are required')
    if not np.isfinite(weights).all() or (weights <= 0).any() or weights.sum() >= 1:
        raise ValueError('invalid headline basket weights')
    index = core.index
    _monthly(core, 'core')
    for values, name in ((categories, 'categories'), (broad_yoy, 'broad_yoy'),
                          (independent_x, 'independent_x'), (food_x, 'food_x')):
        _monthly(values, name)
    c = visible_history(core, origin, as_of, available)
    cat = visible_history(categories.reindex(index), origin, as_of, available)
    broad = visible_history(broad_yoy.reindex(index), origin, as_of, available)
    x = hard_features(independent_x.reindex(index)).drop(columns=['services_l1'], errors='ignore')
    preds, fits, contributions, checks = {}, [], [], {}

    def fit(label, block, target, frame, require_previous=True):
        if require_previous and (origin-1 not in target.index or pd.isna(target.loc[origin-1])):
            info = dict(prediction=np.nan, fit_status='previous_target_unavailable', n_train=0)
        else:
            info = ridge_prediction(frame, target, origin, as_of, available)
        fits.append(dict(model=label, block=block, **info))
        return info['prediction']

    preds['NO_PROXY'] = fit('NO_PROXY', 'core', c, x)
    official = x.copy()
    official['goods_yoy_l1'] = broad.goods.shift(1)
    official['services_yoy_l1'] = broad.services.shift(1)
    preds['OFFICIAL_PREDICTORS'] = fit('OFFICIAL_PREDICTORS', 'core', c, official)

    # d(log annual gross inflation) = current log m/m - same-month-last-year log m/m.
    core_delta = 100 * np.log1p(c / 100).diff(12)
    broad_delta = broad.apply(annual_log_change)
    coefficient, residual, projection = past_projection(core_delta, broad_delta, origin, as_of, available)
    checks.update(projection, goods_projection_coefficient=coefficient)
    broad_common = core_delta.notna() & broad_delta.notna().all(axis=1) & residual.notna()
    bp = {}
    for block in ('goods', 'services'):
        bp[block] = fit('BROAD_SPLIT', block, broad_delta[block].where(broad_common), own_features(broad_delta[block]))
    bp['reconciliation'] = fit('BROAD_SPLIT', 'reconciliation', residual.where(broad_common), own_features(residual))
    delta_hat = coefficient * bp['goods'] + (1-coefficient) * bp['services'] + bp['reconciliation']
    anchor = c.loc[origin-12] if origin-12 in c.index else np.nan
    preds['BROAD_SPLIT'] = float(monthly_from_annual_change(delta_hat, anchor))
    direct_delta = fit('BROAD_AGG_CONTROL', 'core_annual_delta', core_delta.where(broad_common), own_features(core_delta))
    preds['BROAD_AGG_CONTROL'] = float(monthly_from_annual_change(direct_delta, anchor))
    for block, weight in [('goods', coefficient), ('services', 1-coefficient), ('reconciliation', 1.)]:
        previous = broad.loc[origin-1, block] if block in broad else np.nan
        contributions.append(dict(model='BROAD_SPLIT', block=block, prediction=bp[block],
            weight=weight, contribution=weight * bp[block], units='core log-annual-change points',
            yoy_prediction=100*np.expm1(np.log1p(previous/100)+bp[block]/100)))

    common = cat.notna().all(axis=1) & c.notna()
    common_core = c.where(common)
    ct = cat.where(common, np.nan)
    remaining = (core_weight*c - ct.mul(weights).sum(axis=1, min_count=5)).where(common)
    targets = {name: ct[name] for name in CATEGORIES}
    targets[REMAINDER] = remaining
    err = ct.mul(weights).sum(axis=1, min_count=5) + remaining - core_weight*common_core
    checks['max_target_reconciliation_error'] = float(err.abs().max())
    preds['AGG_COMMON'] = fit('AGG_COMMON', 'core', common_core, x)
    for variant in ('TARGET_SHARED', 'TARGET_OWN', 'TARGET_CHANNEL'):
        total = 0.
        for block, target in targets.items():
            features = x.copy() if variant == 'TARGET_SHARED' else own_features(target)
            if variant == 'TARGET_CHANNEL':
                if block == 'catering':
                    features = features.join(food_x.reindex(index)[['food_l1', 'food_ppi_l1']])
                if block in ('accommodation', 'package_holidays'):
                    features['eurczk_mm'] = x.eurczk_mm
                    features['easter_exposure'] = easter_exposure(index)
                if block == REMAINDER:
                    channels = [v for v in ('eurczk_mm', 'import_l2', 'state',
                                           'eurczk_mm_x_state', 'import_l2_x_state') if v in x]
                    features = features.join(x[channels])
            value = fit(variant, block, target, features)
            weight = weights[block] if block in weights.index else 1.
            contribution = weight*value
            total += contribution
            history = target.dropna()
            seasonal = history[history.index.month == origin.month].iloc[-5:].mean()
            contributions.append(dict(model=variant, block=block, prediction=value,
                weight=weight, contribution=contribution,
                units='headline percentage-point projection',
                prior_month_actual=target.loc[origin-1], seasonal_norm=seasonal,
                forecast_minus_seasonal=value-seasonal,
                contribution_minus_seasonal=weight*(value-seasonal)))
        preds[variant] = total/core_weight
    checks['shared_design_commutation_error'] = abs(preds['TARGET_SHARED']-preds['AGG_COMMON'])
    return dict(predictions=preds, fits=fits, contributions=contributions, checks=checks)
