"""Pure R16 damped-slope filters, ridge fits, and released-target selection.

All rates passed here are already in log percentage-point units. Callers own
source transformation, own-origin snapshots, and label release gating before
``ridge_fit``. In particular they must remove rows lacking required generated
first-stage predictions; ordinary predictor gaps are train-mean imputed here.
"""
from __future__ import annotations

from collections.abc import Mapping
import re

import numpy as np
import pandas as pd


SLOPE_CONFIGS = ("p80_q001", "p80_q010", "p95_q001", "p95_q010")
SLOPE_DEFAULT = "p80_q001"
LAMBDAS = (.1, 1., 10.)
LAMBDA_DEFAULT = 1.
BANDS = ((1, 3), (4, 6), (7, 9), (10, 12))
_SLOPE_PARAMETERS = dict(zip(SLOPE_CONFIGS, ((.8, .001), (.8, .01), (.95, .001), (.95, .01))))
_OBSERVATION = np.array([1., 0., 1.])


def _monthly_index(index, name):
    if not isinstance(index, pd.PeriodIndex) or index.freqstr != "M" or not index.is_unique or index.hasnans:
        raise ValueError(f"{name} requires unique monthly PeriodIndex keys")


def _monthly_series(values, name):
    if not isinstance(values, pd.Series):
        raise ValueError(f"{name} must be a Series")
    _monthly_index(values.index, name)


def _origin(value):
    if isinstance(value, pd.Period):
        if value.freqstr == "M":
            return value
    elif isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}", value):
        try:
            return pd.Period(value, freq="M")
        except ValueError:
            pass
    raise ValueError("A valid monthly origin is required")


def _origins(values):
    normalized = [_origin(value) for value in values]
    if len(set(normalized)) != len(normalized):
        raise ValueError("Duplicate normalized origin keys")
    return normalized


def _local_clock(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError("A valid decision clock is required")
    return stamp.tz_convert("Europe/Prague").tz_localize(None) if stamp.tzinfo else stamp


def _seasonal(values):
    if not isinstance(values, Mapping):
        raise ValueError("Seasonal factors must map calendar months to finite values")
    result = {}
    for key, value in values.items():
        if isinstance(key, (int, np.integer)) and not isinstance(key, (bool, np.bool_)):
            month = int(key)
        elif isinstance(key, str) and key.isdigit():
            month = int(key)
        else:
            raise ValueError("Seasonal keys must be integer calendar months")
        if month not in range(1, 13) or month in result:
            raise ValueError("Seasonal months must be unique and in 1..12")
        result[month] = float(value)
    if set(result) != set(range(1, 13)) or not np.isfinite(list(result.values())).all():
        raise ValueError("All twelve finite seasonal factors are required")
    return result


def _transition(phi):
    return np.array([[1., phi, 0.], [0., phi, 0.], [0., 0., .8]])


def forecast_slope(mean, phi, origin, seasonal):
    """Forecast t+h from a state measured at t-1, including destination seasonality."""
    mean = np.asarray(mean, dtype=float)
    if mean.shape != (3,) or not np.isfinite(mean).all() or not np.isfinite(phi) or not 0. < phi < 1.:
        raise ValueError("A finite three-state mean and damping between zero and one are required")
    t, factors = _origin(origin), _seasonal(seasonal)
    transition = _transition(phi)
    future = transition @ mean  # state at t; h1 needs the next transition
    result = {}
    for h in range(1, 13):
        future = transition @ future
        result[h] = float(_OBSERVATION @ future + factors[(t + h).month])
    return result


def slope_state(adjusted_history, origin, seasonal):
    """Filter four frozen configurations using contiguous finite history through t-1.

    Return None if history is shorter than 36 months, has a gap/nonfinite value,
    or does not end at t-1. Future rows are discarded before inspecting values.
    Bad calendar keys and malformed seasonal inputs raise ValueError.
    """
    _monthly_series(adjusted_history, "adjusted_history")
    t, factors = _origin(origin), _seasonal(seasonal)
    history = adjusted_history.loc[adjusted_history.index < t].sort_index()
    if len(history) < 36 or history.index[-1] != t - 1:
        return None
    if not history.index.equals(pd.period_range(history.index[0], t - 1, freq="M")):
        return None
    values = history.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        return None
    states, forecasts = {}, {}
    for name, (phi, slope_variance) in _SLOPE_PARAMETERS.items():
        transition = _transition(phi)
        mean = np.array([values[:12].mean(), 0., 0.])
        covariance = np.diag([1., .01, 1.])
        innovation = np.diag([.05, slope_variance, .2])
        for observed in values[12:]:
            mean = transition @ mean
            covariance = transition @ covariance @ transition.T + innovation
            gain = covariance @ _OBSERVATION / (_OBSERVATION @ covariance @ _OBSERVATION + 1.)
            mean = mean + gain * (observed - _OBSERVATION @ mean)
            covariance = covariance - np.outer(gain, _OBSERVATION) @ covariance
        states[name] = dict(level=float(mean[0]), slope=float(mean[1]), cycle=float(mean[2]),
                            covariance=covariance.tolist())
        forecasts[name] = forecast_slope(mean, phi, t, factors)
    return dict(filter_states=states, forecasts_log=forecasts,
                history_end=str(history.index[-1]), n_history=len(history))


def _predictor_keys(index, name):
    if isinstance(index, pd.MultiIndex) or not index.is_unique or index.hasnans:
        raise ValueError(f"{name} requires unique, nonmissing predictor keys")


def ridge_fit(x, y, now, lambda_value=LAMBDA_DEFAULT):
    """Fit mean squared error + lambda * squared coefficients on at most 120 rows.

    Only finite, matching labels define the training window (minimum 48 rows).
    The explicit constant is penalized. Targets retain their original units;
    returned coefficients multiply predictors standardized by the saved means
    and population standard deviations. No fallback fit replaces missing data.
    """
    if not isinstance(x, pd.DataFrame) or not isinstance(y, pd.Series) or not isinstance(now, pd.Series):
        raise ValueError("Expected a training DataFrame, target Series, and current Series")
    _monthly_index(x.index, "Design index")
    _monthly_index(y.index, "Target index")
    _predictor_keys(x.columns, "Design columns")
    _predictor_keys(now.index, "Current predictors")
    if isinstance(lambda_value, (bool, np.bool_)) or lambda_value not in LAMBDAS:
        raise ValueError("Unknown frozen ridge penalty")
    target = y.astype(float)
    if np.isinf(target.to_numpy()).any() or np.isinf(now.to_numpy(dtype=float)).any():
        raise ValueError("Infinite target or current predictor")
    keys = x.index.intersection(target.loc[target.notna()].index).sort_values()[-120:]
    # Fix memory order as well as row order: pandas reductions otherwise vary
    # at roundoff level after appending unlabelled rows or permuting the input.
    train = pd.DataFrame(np.ascontiguousarray(x.loc[keys].to_numpy(dtype=float)), index=keys, columns=x.columns)
    target = target.reindex(keys)
    if np.isinf(train.to_numpy()).any():
        raise ValueError("Infinite training predictor")
    info = dict(status="insufficient_history", n_train=len(train), columns=[], means={}, scales={},
                coefficients={}, intercept=None, lambda_value=float(lambda_value), converged=False,
                train_first=str(keys[0]) if len(keys) else None, train_last=str(keys[-1]) if len(keys) else None)
    if len(train) < 48:
        return np.nan, info
    columns = list(train.columns[train.nunique(dropna=True) > 1])
    train = train.loc[:, columns]
    means = train.mean()
    imputed = train.fillna(means)
    scales = imputed.std(ddof=0)
    standardized = ((imputed - means) / scales).to_numpy(dtype=float)
    current = ((now.reindex(columns).astype(float).fillna(means) - means) / scales).to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(train)), standardized])
    coefficients = np.linalg.solve(design.T @ design + len(train) * lambda_value * np.eye(design.shape[1]),
                                   design.T @ target.to_numpy(dtype=float))
    prediction = float(np.r_[1., current] @ coefficients)
    info.update(columns=columns, means=means.to_dict(), scales=scales.to_dict(),
                coefficients=dict(zip(columns, coefficients[1:].tolist())), intercept=float(coefficients[0]))
    if not np.isfinite(coefficients).all() or not np.isfinite(prediction):
        info.update(status="nonfinite_prediction")
        return np.nan, info
    info.update(status="estimated", converged=True)
    return prediction, info


def _released_targets(series, available, r, t, clock, lo, hi):
    if r + hi >= t:
        return None
    months = pd.period_range(r + lo, r + hi, freq="M")
    dates = available.reindex(months).map(lambda value: pd.NaT if pd.isna(value) else _local_clock(value))
    if dates.isna().any() or dates.gt(clock).any():
        return None
    actual = series.reindex(months).to_numpy(dtype=float)
    if not np.isfinite(actual).all():
        return None
    return actual, dates.max()


def released_band_means(series, available, origins, origin, as_of, band):
    """Return mean already-transformed targets only after every band month matures."""
    _monthly_series(series, "series")
    _monthly_series(available, "available")
    t, clock = _origin(origin), _local_clock(as_of)
    if tuple(band) not in BANDS:
        raise ValueError("Unknown frozen forecast band")
    lo, hi = tuple(band)
    values, audit = {}, []
    for r in sorted(_origins(origins)):
        released = _released_targets(series, available, r, t, clock, lo, hi)
        if released is None:
            continue
        actual, latest_release = released
        values[r] = float(actual.mean())
        audit.append(dict(origin=str(r), last_target=str(r + hi),
                          available_from=str(latest_release), actual=values[r]))
    y = pd.Series(list(values.values()), index=pd.PeriodIndex(list(values), freq="M"), dtype=float)
    return y, pd.DataFrame(audit, columns=["origin", "last_target", "available_from", "actual"])


def choose_slope(saved_paths, core_log, available, origin, as_of):
    """Select one entire h1..12 path using the last 36 common matured origins.

    Each row's loss is the mean of twelve squared forecast errors. At least 24
    common finite paths are required; ties prefer the default then fixed order.
    Metadata names and reason strings match the R15 scalar selector.
    """
    _monthly_series(core_log, "core_log")
    _monthly_series(available, "available")
    if not isinstance(saved_paths, Mapping):
        raise ValueError("Saved paths must be keyed by monthly origin")
    t, clock = _origin(origin), _local_clock(as_of)
    normalized = _origins(saved_paths)
    keyed = sorted(zip(normalized, saved_paths.values()), key=lambda item: item[0])
    result = dict(config=SLOPE_DEFAULT, n_validation=0, validation_origins=[], validation_last_release=None,
                  losses={}, reason="insufficient_validation")
    valid = []
    for r, paths in keyed:
        released = _released_targets(core_log, available, r, t, clock, 1, 12)
        if released is None:
            continue
        actual, latest_release = released
        forecasts = np.array([[paths.get(c, {}).get(h, np.nan) for h in range(1, 13)]
                              for c in SLOPE_CONFIGS], dtype=float)
        if not np.isfinite(forecasts).all():
            continue
        with np.errstate(over="ignore", invalid="ignore"):
            errors = np.mean((forecasts - actual) ** 2, axis=1)
        if np.isfinite(errors).all():
            valid.append((r, latest_release, errors))
    valid = valid[-36:]
    result.update(n_validation=len(valid), validation_origins=[str(r) for r, _, _ in valid])
    if valid:
        result["validation_last_release"] = str(max(date for _, date, _ in valid))
    if len(valid) < 24:
        return result
    losses = np.array([errors for _, _, errors in valid]).mean(axis=0)
    tied = [name for name, loss in zip(SLOPE_CONFIGS, losses)
            if np.isclose(loss, losses.min(), rtol=1e-10, atol=1e-12)]
    result.update(config=SLOPE_DEFAULT if SLOPE_DEFAULT in tied else tied[0],
                  losses=dict(zip(SLOPE_CONFIGS, losses.tolist())),
                  reason="minimum_prior_mse" if len(tied) == 1 else "fixed_tie_order")
    return result
