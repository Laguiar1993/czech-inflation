"""Pure, origin-frozen core trend filters and delayed residual learning for R15.

Rates are simple monthly percentage changes at the boundary and log percentage
changes inside the engine. Callers must construct labels at the outer decision
clock before passing them to ``fit_residual``; that function cannot infer a
release calendar from a design matrix.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd


BANDS = ((1, 3), (4, 6), (7, 9), (10, 12))
FILTERS = {"slow": .01, "mid": .05, "fast": .20}
RHO = .8
RESIDUAL_VARIANCE = .2
OBSERVATION_VARIANCE = 1.
ENET_CONFIGS = tuple(f"a{alpha:g}_l{ratio:g}" for alpha in (.01, .1, 1.) for ratio in (.2, .8))
ENET_DEFAULT = "a0.1_l0.2"
RF_CONFIGS = ("leaf5", "leaf15")
RF_DEFAULT = "leaf15"


def local_clock(value):
    """Normalize an explicit timestamp to Prague wall time for comparison."""
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError("A valid decision clock is required")
    return stamp.tz_convert("Europe/Prague").tz_localize(None) if stamp.tzinfo else stamp


def _release_dates(values):
    return values.map(lambda value: pd.NaT if pd.isna(value) else local_clock(value))


def _monthly_series(values, name):
    if not isinstance(values, pd.Series):
        raise ValueError(f"{name} must be a Series")
    index = values.index
    if not isinstance(index, pd.PeriodIndex) or index.freqstr != "M" or not index.is_unique or index.hasnans:
        raise ValueError(f"{name} requires unique monthly PeriodIndex keys")


def _origin(value):
    result = pd.Period(value, "M")
    if pd.isna(result):
        raise ValueError("A valid monthly origin is required")
    return result


def _band(value):
    if tuple(value) not in BANDS:
        raise ValueError("Unknown frozen forecast band")
    return tuple(value)


def state_at(core, available, origin, as_of):
    """Freeze all three filters using published contiguous data through t-1.

    Return ``None`` if fewer than 36 usable months, any interior gap, or an
    unavailable last month prevents estimation. ``last_release`` is the latest
    release across all observations actually used, including delayed old data.
    The h=1 forecast is two state transitions beyond the last observation t-1.
    """
    _monthly_series(core, "core")
    _monthly_series(available, "available")
    t, clock = _origin(origin), local_clock(as_of)
    history = core.loc[core.index < t].sort_index()
    release = _release_dates(available.reindex(history.index))
    history = history.loc[release.notna() & release.le(clock)]
    first = history.first_valid_index()
    if first is None:
        return None
    history = history.loc[first:]
    if len(history) < 36 or history.index[-1] != t - 1:
        return None
    if not history.index.equals(pd.period_range(history.index[0], t - 1, freq="M")):
        return None
    values = history.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= -100.).any():
        return None
    log_core = pd.Series(100. * np.log1p(values / 100.), index=history.index)
    detrended = (log_core - log_core.rolling(12, min_periods=12).mean()).dropna().tail(120)
    seasonal = detrended.groupby(detrended.index.month).mean().reindex(range(1, 13))
    if not np.isfinite(seasonal).all():
        return None
    seasonal -= seasonal.mean()
    adjusted = log_core - [seasonal[p.month] for p in log_core.index]
    transition = np.diag([1., RHO])
    observation = np.ones(2)
    filter_states, forecasts = {}, {}
    for name, trend_variance in FILTERS.items():
        mean = np.array([adjusted.iloc[:12].mean(), 0.])
        covariance = np.eye(2)
        innovation = np.diag([trend_variance, RESIDUAL_VARIANCE])
        for observed in adjusted.iloc[12:]:
            mean = transition @ mean
            covariance = transition @ covariance @ transition.T + innovation
            gain = covariance @ observation / (observation @ covariance @ observation + OBSERVATION_VARIANCE)
            mean = mean + gain * (observed - observation @ mean)
            covariance = covariance - np.outer(gain, observation) @ covariance
        filter_states[name] = dict(mu=float(mean[0]), cycle=float(mean[1]), covariance=covariance.tolist())
        forecasts[name] = {h: float(mean[0] + RHO ** (h + 1) * mean[1] + seasonal[(t + h).month])
                           for h in range(1, 13)}
    features = dict(core1=float(adjusted.iloc[-1]), core3=float(adjusted.tail(3).mean()),
                    core12=float(adjusted.tail(12).mean()))
    features["core_acceleration"] = features["core3"] - features["core12"]
    features.update(midtrend=filter_states["mid"]["mu"], midcycle=filter_states["mid"]["cycle"])
    return dict(origin=str(t), as_of=str(clock), x=features,
                seasonal={int(month): float(value) for month, value in seasonal.items()},
                filter_states=filter_states, forecasts_log=forecasts,
                history_end=str(history.index[-1]), last_release=str(release.loc[history.index].max()),
                n_history=len(history), n_seasonal=len(detrended))


def residual_labels(core, available, states, origin, as_of, band):
    """Return eligible residuals and audit rows against saved mid-filter paths.

    Every target must precede the outer origin and be detailed-published by the
    outer clock. Neither the saved seasonal factors nor filters are refitted.
    """
    _monthly_series(core, "core")
    _monthly_series(available, "available")
    t, clock = _origin(origin), local_clock(as_of)
    lo, hi = _band(band)
    keyed = [(_origin(key), state) for key, state in states.items()]
    if len({key for key, _ in keyed}) != len(keyed):
        raise ValueError("Duplicate normalized saved-state origins")
    values, audit = {}, []
    for r, state in sorted(keyed, key=lambda item: item[0]):
        if r + hi >= t:
            continue
        months = pd.period_range(r + lo, r + hi, freq="M")
        dates = _release_dates(available.reindex(months))
        if dates.isna().any() or dates.gt(clock).any():
            continue
        actual = core.reindex(months).to_numpy(dtype=float)
        if not np.isfinite(actual).all() or (actual <= -100.).any():
            continue
        baseline = np.asarray([state["forecasts_log"]["mid"][h] for h in range(lo, hi + 1)], dtype=float)
        if not np.isfinite(baseline).all():
            continue
        residual = float(np.mean(100. * np.log1p(actual / 100.)) - baseline.mean())
        values[r] = residual
        audit.append(dict(origin=str(r), last_target=str(months[-1]), available_from=str(dates.max()), actual=residual))
    target = pd.Series(list(values.values()), index=pd.PeriodIndex(list(values), freq="M"), dtype=float)
    return target, pd.DataFrame(audit, columns=["origin", "last_target", "available_from", "actual"])


def _unique_keys(index, name):
    if isinstance(index, pd.MultiIndex) or not index.is_unique or index.hasnans:
        raise ValueError(f"{name} requires unique, nonmissing, unambiguous keys")
    periods = [isinstance(key, pd.Period) for key in index]
    if any(periods) and not all(periods):
        raise ValueError(f"{name} has ambiguous mixed monthly keys")


def fit_residual(x, y, now, kind, config=None):
    """Fit the last 120 labelled rows, with at least 48 observations.

    ``y`` must already contain only labels eligible at the outer clock. Design
    rows without a finite matching target are excluded before preprocessing.
    Missing predictors are mean-imputed from this training window; allmissing
    or constant training columns are dropped. ENET standardizes the target by
    its training RMS without demeaning it, and penalizes an explicit constant.
    Returned coefficients multiply standardized predictors in residual units.
    """
    if not isinstance(x, pd.DataFrame) or not isinstance(y, pd.Series) or not isinstance(now, pd.Series):
        raise ValueError("Expected a training DataFrame, target Series, and current Series")
    for index, name in ((x.index, "Design index"), (y.index, "Target index"),
                        (x.columns, "Design columns"), (now.index, "Current predictors")):
        _unique_keys(index, name)
    if kind not in ("enet", "rf", "forest"):
        raise ValueError("Unknown residual learner")
    kind = "rf" if kind == "forest" else kind
    config = config or (ENET_DEFAULT if kind == "enet" else RF_DEFAULT)
    if config not in (ENET_CONFIGS if kind == "enet" else RF_CONFIGS):
        raise ValueError("Unknown frozen residual configuration")
    target = y.astype(float)
    if np.isinf(target.to_numpy()).any() or np.isinf(now.to_numpy(dtype=float)).any():
        raise ValueError("Infinite target or current predictor")
    keys = x.index.intersection(target.loc[target.notna()].index)
    try:
        keys = keys.sort_values()[-120:]
    except TypeError as exc:
        raise ValueError("Training keys must have an unambiguous chronological order") from exc
    train = x.loc[keys].astype(float)
    target = target.reindex(keys)
    if np.isinf(train.to_numpy()).any():
        raise ValueError("Infinite training predictor")
    info = dict(status="insufficient_history", n_train=len(train), ntrain=len(train), kind=kind, config=config,
                columns=[], means={}, scales={}, coefficients={}, intercept=None, converged=False)
    if len(train) < 48:
        return np.nan, info
    columns = list(train.columns[train.nunique(dropna=True) > 1])
    train = train.loc[:, columns]
    means = train.mean()
    imputed = train.fillna(means)
    scales = imputed.std(ddof=0)
    standardized = ((imputed - means) / scales).to_numpy(dtype=float)
    current = ((now.reindex(columns).astype(float).fillna(means) - means) / scales).to_numpy(dtype=float)
    yy = target.to_numpy(dtype=float)
    info.update(columns=columns, means=means.to_dict(), scales=scales.to_dict(),
                coefficient_space="standardized_predictors_residual_target")
    if kind == "enet":
        from sklearn.exceptions import ConvergenceWarning
        from sklearn.linear_model import ElasticNet

        alpha_text, ratio_text = config.split("_l")
        alpha, ratio = float(alpha_text[1:]), float(ratio_text)
        target_rms = float(np.sqrt(np.mean(yy ** 2)))
        info.update(alpha=alpha, l1_ratio=ratio, target_rms=target_rms, fit_intercept=False)
        if target_rms == 0.:
            info.update(status="estimated", converged=True, intercept=0.,
                        coefficients=dict.fromkeys(columns, 0.), n_iter=0, dual_gap=0.)
            return 0., info
        design = np.column_stack([np.ones(len(train)), standardized])
        current = np.r_[1., current]
        model = ElasticNet(alpha=alpha, l1_ratio=ratio, fit_intercept=False,
                           max_iter=10000, tol=1e-6, selection="cyclic", random_state=42)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            model.fit(design, yy / target_rms)
        converged = not any(issubclass(w.category, ConvergenceWarning) for w in caught)
        finite = np.isfinite(model.coef_).all() and np.isfinite(model.dual_gap_)
        info.update(converged=bool(converged and finite), n_iter=int(model.n_iter_), dual_gap=float(model.dual_gap_))
        if not info["converged"]:
            info.update(status="nonconvergence")
            return np.nan, info
        coefficients = model.coef_ * target_rms
        prediction = float(current @ coefficients)
        info.update(coefficients=dict(zip(columns, coefficients[1:].tolist())), intercept=float(coefficients[0]))
    else:
        from sklearn.ensemble import RandomForestRegressor

        leaf = int(config.removeprefix("leaf"))
        # A constant feature preserves the defined intercept-only forest when
        # every supplied predictor is unusable in this training window.
        design = standardized if columns else np.zeros((len(train), 1))
        current = current if columns else np.zeros(1)
        model = RandomForestRegressor(n_estimators=150, min_samples_leaf=leaf,
                                      max_features=1. / 3., bootstrap=True, random_state=42, n_jobs=1)
        model.fit(design, yy)
        prediction = float(model.predict(current.reshape(1, -1))[0])
        info.update(converged=True, min_samples_leaf=leaf, n_estimators=150, max_features=1. / 3.,
                    bootstrap=True, random_state=42, n_jobs=1,
                    feature_importances=dict(zip(columns, model.feature_importances_.tolist())))
    if not np.isfinite(prediction):
        info.update(status="nonfinite_prediction", converged=False)
        return np.nan, info
    info.update(status="estimated")
    return prediction, info


def choose_config(predictions, outcomes, origin, as_of, configs, default):
    """Choose by MSE on the latest 36 common, matured own-origin predictions.

    At least 24 rows are required. Equal losses prefer the default, then the
    declared configuration order. Duplicate normalized keys fail even when
    those rows would otherwise be excluded by the current decision clock.
    """
    t, clock = _origin(origin), local_clock(as_of)
    configs = tuple(configs)
    if not configs or len(set(configs)) != len(configs) or default not in configs:
        raise ValueError("Configurations must be unique and include the default")
    result = dict(config=default, n_validation=0, reason="insufficient_validation", validation_origins=[],
                  validation_last_release=None, losses={})
    p, truth = predictions.copy(), outcomes.copy()
    for table in (p, truth):
        if not table.columns.is_unique:
            raise ValueError("Duplicate prediction/outcome columns")
        if "origin" in table:
            table["origin"] = table["origin"].map(lambda value: str(_origin(value)))
    if len(p) and p.duplicated(["origin", "config"]).any():
        raise ValueError("Duplicate sequential prediction origin/config keys")
    if len(truth) and truth.origin.duplicated().any():
        raise ValueError("Duplicate sequential outcome origin keys")
    if p.empty or truth.empty:
        return result
    p = p.loc[p.config.isin(configs) & p.origin.map(lambda value: _origin(value) < t)]
    truth = truth.loc[truth.origin.map(lambda value: _origin(value) < t)].copy()
    truth["available_from"] = _release_dates(truth.available_from)
    truth = truth.loc[truth.available_from.notna() & truth.available_from.le(clock)
                      & truth.last_target.map(lambda value: _origin(value) < t)]
    joined = p.merge(truth, on="origin", how="inner", validate="many_to_one")
    finite = np.isfinite(joined.prediction.to_numpy(dtype=float)) & np.isfinite(joined.actual.to_numpy(dtype=float))
    joined = joined.loc[finite].copy()
    joined["squared_error"] = (joined.prediction.astype(float) - joined.actual.astype(float)) ** 2
    wide = joined.pivot(index="origin", columns="config", values="squared_error")
    wide = wide.reindex(columns=configs).replace([np.inf, -np.inf], np.nan).dropna().sort_index().tail(36)
    result.update(n_validation=len(wide), validation_origins=list(wide.index))
    if len(wide):
        result["validation_last_release"] = str(truth.loc[truth.origin.isin(wide.index), "available_from"].max())
    if len(wide) < 24:
        return result
    losses = wide.mean()
    tied = [name for name in configs if np.isclose(losses[name], losses.min(), rtol=1e-10, atol=1e-12)]
    winner = default if default in tied else tied[0]
    result.update(config=winner, losses=losses.to_dict(),
                  reason="minimum_prior_mse" if len(tied) == 1 else "fixed_tie_order")
    return result


def band_path(state, corrections, filter_name="mid"):
    """Add each band's log correction to the saved path and return simple mm%."""
    if filter_name not in FILTERS:
        raise ValueError("Unknown frozen filter")
    baseline = state["forecasts_log"][filter_name]
    result = {}
    for b, (lo, hi) in enumerate(BANDS):
        correction = corrections.get(b, np.nan)
        for h in range(lo, hi + 1):
            result[h] = float(100. * np.expm1((baseline[h] + correction) / 100.)) if np.isfinite(correction) else np.nan
    return result
