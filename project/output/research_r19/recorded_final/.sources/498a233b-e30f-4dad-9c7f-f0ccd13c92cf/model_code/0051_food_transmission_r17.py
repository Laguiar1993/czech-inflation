"""Declared, origin-frozen direct food-rate transmission; no future upstream path."""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.food_path_r14 import _aware, load_inputs, replace_food

MODELS = ('FOOD_SEASONAL_R17', 'FOOD_PERSISTENCE_R17', 'FOOD_OWN_R17',
          'FOOD_SYMMETRIC_R17', 'FOOD_ASYMMETRIC_R17', 'FOOD_HALF_CORRECTION_R17')
LAMBDAS = (0.1, 1.0, 10.0)
PREFERENCE = (1.0, 10.0, 0.1)
MIN_TRAIN = 24
WINDOW = 96
MIN_VALIDATION = 12
VALIDATION_WINDOW = 36
FEATURE_NAMES = ['own1', 'own3'] + [f'{c}_{b}' for c in ('agri4', 'food_ppi') for b in ('1_3', '4_6')] + [
    f'{c}_{sign}_{b}' for c in ('agri4', 'food_ppi') for sign in ('positive', 'negative') for b in ('1_3', '4_6')]
FEATURE_COLUMNS = {'own': [0, 1], 'symmetric': list(range(6)), 'asymmetric': [0, 1] + list(range(6, 14))}


def released_rates(levels, available, origin, as_of):
    """Mask levels before differencing; both released endpoints are necessary."""
    t = pd.Period(origin, 'M'); clock = _aware(as_of)
    if not isinstance(levels.index, pd.PeriodIndex) or not levels.index.is_unique or list(levels.columns) != ['agri4', 'food_ppi', 'food']:
        raise ValueError('Unique declared monthly level panel required')
    history = levels.loc[levels.index < t].copy()
    if history.empty or not history.index.equals(pd.period_range(history.index.min(), t-1, freq='M')):
        raise ValueError('Contiguous level calendar through t-1 required')
    dates = available.reindex(history.index)
    for column in history:
        stamps = pd.to_datetime(dates[column].map(lambda d: _aware(d) if pd.notna(d) else pd.NaT), utc=True)
        history.loc[~(stamps.notna() & stamps.le(clock)), column] = np.nan
    return history.diff()


def lag_summary(values):
    """Six actual calendar lags, sign-split before the two three-month means."""
    values = np.asarray(values, dtype=float)
    if values.shape != (6,):
        raise ValueError('Exactly six ordered calendar lag values required')
    return {name: [float(transform(values)[i:i+3].mean()) for i in (0, 3)]
            for name, transform in [('symmetric', lambda x: x), ('positive', lambda x: np.maximum(x, 0)), ('negative', lambda x: np.minimum(x, 0))]}


def snapshot(levels, available, origin, as_of):
    """Freeze a feature vector and destination seasonality at its OWN origin."""
    t = pd.Period(origin, 'M'); rates = released_rates(levels, available, t, as_of)
    food = rates.food.iloc[-WINDOW:]
    seasonal = food.groupby(food.index.month).mean().reindex(range(1, 13)).to_numpy()
    lags = pd.period_range(t-6, t-1, freq='M')[::-1]
    food_lags = rates.food.reindex(lags).to_numpy()
    centered = food_lags - seasonal[lags.month-1]
    features = [float(centered[0]), float(centered[:3].mean())]
    summaries = {c: lag_summary(rates[c].reindex(lags).to_numpy()) for c in ('agri4', 'food_ppi')}
    for c in ('agri4', 'food_ppi'):
        features.extend(summaries[c]['symmetric'])
    for c in ('agri4', 'food_ppi'):
        features.extend(summaries[c]['positive']); features.extend(summaries[c]['negative'])
    audit = {}
    for c in levels:
        audit[c] = [dict(lag=i+1, reference_month=str(month), log_rate=float(rates[c].get(month, np.nan)),
                         current_release=str(available[c].get(month)), previous_release=str(available[c].get(month-1)),
                         status='released' if np.isfinite(rates[c].get(month, np.nan)) else 'unavailable')
                    for i, month in enumerate(lags)]
    return dict(origin=str(t), as_of=_aware(as_of).isoformat(), seasonal=seasonal.tolist(), features=features,
                feature_names=FEATURE_NAMES, seasonal_dates=[str(m) for m in food.dropna().index], lag_audit=audit,
                status='available' if np.isfinite(seasonal).all() else 'unavailable_seasonality',
                persistence_reason='own3' if np.isfinite(features[1]) else 'missing_own3_use_seasonal',
                no_future_upstream_forecast=True, target_step='h1=t+1; latest permitted food=t-1')


def control_paths(state):
    t = pd.Period(state['origin'], 'M')
    seasonal = np.array([state['seasonal'][(t+h).month-1] for h in range(1, 13)])
    if not np.isfinite(state['seasonal']).all():
        seasonal[:] = np.nan
    own3 = state['features'][1]
    return {MODELS[0]: seasonal, MODELS[1]: seasonal + (own3 if np.isfinite(own3) else 0.)}


def _training_data(saved, rates, available, origin, h, family):
    t = pd.Period(origin, 'M'); columns = FEATURE_COLUMNS[family]
    rows, targets, audit = [], [], []
    for s in sorted(saved):
        source = pd.Period(s, 'M'); target = source + h
        if source >= t or target >= t:
            continue
        state = saved[s]; features = np.asarray(state['features'], dtype=float)
        rate = rates.food.get(target, np.nan)
        offset = state['seasonal'][target.month-1]
        # Identical historical support, including complete upstream windows, for all families.
        if not np.isfinite(features).all() or not np.isfinite(rate) or not np.isfinite(offset):
            continue
        rows.append(features[columns]); targets.append(float(rate-offset))
        audit.append(dict(origin=s, target=str(target), feature_as_of=state['as_of'],
                          response_current_release=str(available.food.get(target)),
                          response_previous_release=str(available.food.get(target-1)), saved_seasonal=float(offset)))
    return (np.asarray(rows[-WINDOW:], dtype=float).reshape(-1, len(columns)),
            np.asarray(targets[-WINDOW:], dtype=float), audit[-WINDOW:])


def training_data(saved, levels, available, origin, as_of, h, family):
    if h not in range(1, 13) or family not in FEATURE_COLUMNS:
        raise ValueError('Declared horizon and family required')
    return _training_data(saved, released_rates(levels, available, origin, as_of), available, origin, h, family)


def ridge_fit(x, y, penalties):
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    if not len(x) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Finite training rows required')
    scale = np.sqrt(np.mean(x*x, axis=0)); scale[scale <= 1e-12] = 1.
    z = x / scale
    beta = np.linalg.solve(z.T @ z / len(y) + np.diag(penalties), z.T @ y / len(y))
    return dict(scale=scale.tolist(), coefficients=beta.tolist())


def _select_penalty(history, rates, origin, family):
    t = pd.Period(origin, 'M'); grouped = {}
    for row in history:
        source = pd.Period(row['origin'], 'M')
        if row['family'] == family and source+12 < t and row['all_estimated']:
            grouped.setdefault(row['origin'], {})[row['penalty']] = row
    eligible, losses = [], {p: [] for p in LAMBDAS}
    for s in sorted(grouped):
        if set(grouped[s]) != set(LAMBDAS):
            continue
        actual = rates.food.reindex(pd.period_range(pd.Period(s, 'M')+1, pd.Period(s, 'M')+12, freq='M')).to_numpy()
        if not np.isfinite(actual).all():
            continue
        predicted = {p: np.asarray(grouped[s][p]['log_rates']) for p in LAMBDAS}
        if any(v.shape != (12,) or not np.isfinite(v).all() for v in predicted.values()):
            continue
        eligible.append(s)
        for p in LAMBDAS:
            losses[p].append(float(np.mean((predicted[p]-actual)**2)))
    eligible = eligible[-VALIDATION_WINDOW:]
    mean_losses = {str(p): float(np.mean(v[-VALIDATION_WINDOW:])) for p, v in losses.items()} if eligible else {}
    ready = len(eligible) >= MIN_VALIDATION
    penalty = min(PREFERENCE, key=lambda p: mean_losses[str(p)]) if ready else 1.0
    return dict(family=family, penalty=penalty, status='selected_matured_paths' if ready else 'default_insufficient_mature_validation',
                validation_origins=eligible, n_validation=len(eligible), mean_path_losses=mean_losses)


def select_penalty(history, levels, available, origin, as_of, family):
    return _select_penalty(history, released_rates(levels, available, origin, as_of), origin, family)


def forecast_origin(saved, levels, available, origin, as_of, candidate_history):
    """Fit only matured labels on saved own-origin features; return LOG-rate paths."""
    t = pd.Period(origin, 'M'); state = saved[str(t)]
    if _aware(state['as_of']) != _aware(as_of):
        raise ValueError('Snapshot clock differs from forecast clock')
    rates = released_rates(levels, available, t, as_of)
    paths = control_paths(state); fits, candidates, selections = [], [], []
    row_status = {MODELS[0]: ['control' if np.isfinite(v) else 'unavailable_seasonality' for v in paths[MODELS[0]]],
                  MODELS[1]: [('control' if state['persistence_reason']=='own3' else 'fallback_seasonal') if np.isfinite(v) else 'unavailable_seasonality' for v in paths[MODELS[1]]]}
    fallback_reasons = {MODELS[0]: ['']*12, MODELS[1]: [state['persistence_reason']]*12}
    for family, name in [('own', MODELS[2]), ('symmetric', MODELS[3]), ('asymmetric', MODELS[4])]:
        selection = _select_penalty(candidate_history, rates, t, family) if family != 'own' else dict(family='own', penalty=.1, status='fixed_own_penalty')
        selections.append(selection); fitted = {}; statuses = {}; reasons = {}
        for penalty in ((.1,) if family == 'own' else LAMBDAS):
            forecast, status_list, reason_list = [], [], []
            for h in range(1, 13):
                x, y, audit = _training_data(saved, rates, available, t, h, family)
                now = np.asarray(state['features'])[FEATURE_COLUMNS[family]]
                reason = ('unavailable_seasonality' if state['status'] != 'available' else
                          'insufficient_training_rows' if len(y) < MIN_TRAIN else
                          'missing_current_predictor' if not np.isfinite(now).all() else '')
                info = dict(origin=str(t), family=family, h=h, penalty=penalty, n_train=len(y), training=audit,
                            features=[FEATURE_NAMES[i] for i in FEATURE_COLUMNS[family]], reason=reason)
                value = paths[MODELS[1]][h-1]
                if not reason:
                    penalties = np.array([.1, .1] + [penalty]*(len(now)-2))
                    fitted_model = ridge_fit(x, y, penalties)
                    value = paths[MODELS[0]][h-1] + (now / fitted_model['scale']) @ fitted_model['coefficients']
                    info.update(fitted_model, penalties=penalties.tolist(), status='estimated')
                else:
                    info['status'] = 'fallback_persistence' if np.isfinite(value) else 'unavailable_seasonality'
                if not np.isfinite(value) and info['status'] == 'estimated':
                    raise ArithmeticError('Nonfinite fitted food path; no silent numerical fallback')
                forecast.append(float(value)); status_list.append(info['status']); reason_list.append(reason); fits.append(info)
            fitted[penalty] = np.array(forecast); statuses[penalty] = status_list; reasons[penalty] = reason_list
            if family != 'own':
                candidates.append(dict(origin=str(t), as_of=state['as_of'], family=family, penalty=penalty,
                                       log_rates=forecast, statuses=status_list, reasons=reason_list,
                                       all_estimated=all(s == 'estimated' for s in status_list)))
        chosen = selection['penalty']; paths[name] = fitted[chosen]; row_status[name] = statuses[chosen]; fallback_reasons[name] = reasons[chosen]
    paths[MODELS[5]] = paths[MODELS[1]] + .5*(paths[MODELS[4]]-paths[MODELS[1]])
    row_status[MODELS[5]] = list(row_status[MODELS[4]]); fallback_reasons[MODELS[5]] = list(fallback_reasons[MODELS[4]])
    return dict(paths=paths, fits=fits, candidates=candidates, selections=selections, statuses=row_status, reasons=fallback_reasons)


def to_monthly_percent(log_rates):
    return 100*np.expm1(np.asarray(log_rates, dtype=float)/100)
