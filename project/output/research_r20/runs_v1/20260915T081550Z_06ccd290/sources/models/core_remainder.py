"""R11 information-set diagnostic; the five R10 category equations stay fixed.

Caller supplies publication-shifted predictors masked at the decision time.
This function independently masks all dependent-variable histories. No survey
or outcome-based model selection enters forecasting.
"""
from __future__ import annotations

import numpy as np

from models.core_split import CATEGORIES, REMAINDER, own_features, visible_history
from models.core_tuning import _monthly, hard_features, ridge_prediction

MACRO_COLUMNS = ('eurczk_mm', 'import_l2', 'state', 'eurczk_mm_x_state', 'import_l2_x_state')


def remainder_frames(remaining, independent_x):
    x = hard_features(independent_x).drop(columns=['services_l1'], errors='ignore')
    return {
        'TARGET_BASE_REMAINDER': x,
        'TARGET_MACRO_REMAINDER': own_features(remaining).join(x[[v for v in MACRO_COLUMNS if v in x]]),
    }


def forecast_origin(core, categories, independent_x, available, origin, as_of,
                    weights, *, core_weight):
    if not np.isfinite(core_weight) or not 0 < core_weight <= 1:
        raise ValueError('core weight must be finite and in (0,1]')
    if (set(categories.columns) != set(CATEGORIES) or not categories.columns.is_unique
            or set(weights.index) != set(CATEGORIES) or not weights.index.is_unique):
        raise ValueError('the declared five unique categories and weights are required')
    if not np.isfinite(weights).all() or (weights <= 0).any() or weights.sum() >= 1:
        raise ValueError('invalid headline basket weights')
    for values, name in ((core, 'core'), (categories, 'categories'), (independent_x, 'independent_x')):
        _monthly(values, name)
    c = visible_history(core, origin, as_of, available)
    cat = visible_history(categories.reindex(core.index), origin, as_of, available)
    common = cat.notna().all(axis=1) & c.notna()
    ct = cat.where(common, np.nan)
    remaining = (core_weight*c - ct.mul(weights).sum(axis=1, min_count=5)).where(common)
    identity = ct.mul(weights).sum(axis=1, min_count=5)+remaining-core_weight*c.where(common)
    fits = []

    def fit(model, block, target, frame):
        if origin-1 not in target.index or np.isnan(target.loc[origin-1]):
            info = dict(prediction=np.nan, fit_status='previous_target_unavailable', n_train=0)
        else:
            info = ridge_prediction(frame, target, origin, as_of, available)
        fits.append(dict(model=model, block=block, **info))
        return info['prediction']

    category_values = {name: fit('SHARED_OWN_CATEGORIES', name, ct[name], own_features(ct[name]))
                       for name in CATEGORIES}
    # Preserve the R10 summation order to permit exact old-forecast replay.
    total_categories = sum(weights[name]*category_values[name] for name in CATEGORIES)
    own_remainder = fit('OWN_REPLAY', REMAINDER, remaining, own_features(remaining))
    predictions, contributions = {}, []
    frames = remainder_frames(remaining, independent_x.reindex(core.index))
    for model, frame in frames.items():
        r = fit(model, REMAINDER, remaining, frame)
        predictions[model] = (total_categories+r)/core_weight
        for block in (*CATEGORIES, REMAINDER):
            value = category_values[block] if block in category_values else r
            weight = weights[block] if block in category_values else 1.
            contributions.append(dict(model=model, block=block, prediction=value,
                                      weight=weight, contribution=weight*value))
    return dict(predictions=predictions, own_core=(total_categories+own_remainder)/core_weight,
                fits=fits, contributions=contributions,
                max_reconciliation_error=float(identity.abs().max()),
                feature_columns={name:list(frame.columns) for name, frame in frames.items()})
