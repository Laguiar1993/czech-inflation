"""Pure helpers for the research-only paper-inspired CPI model.

This module deliberately has no database, file or network dependency.  A caller
supplies a monthly target and a feature panel, chooses an input policy, and can
then run a direct-horizon TVW-QRF or BBIM challenger.  The estimators are
delegated to the existing model implementations only after the origin panel
has been cut and imputed.

The code is an experimental research layer.  It is not part of the operating
nowcast and must not be promoted without a common-window backtest and a
prospective publication-clock audit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd


POLICIES = ("independent", "sentiment", "full")

# Names already used by the current project, plus the names used by the older
# wide panel.  The light name-pattern checks below make the policy safe for a
# caller's source-specific aliases without treating every survey as inflation
# expectations: ESI and confidence remain available to the sentiment policy.
INFLATION_EXPECTATION_COLUMNS = frozenset(
    {
        "exp12",
        "exp36",
        "exp12_x_state",
        "price_expect_survey",
        "price_expect_survey_36m",
        "household_exp",
        "household_price_expect",
        "inflation_expectation",
        "inflation_expectations",
        "cpi_expectation",
        "cpi_expectations",
    }
)
EXPECTATION_COLUMNS = INFLATION_EXPECTATION_COLUMNS

SENTIMENT_COLUMNS = frozenset(
    {
        "esi",
        "de_esi",
        "confidence",
        "confidence_sentiment",
        "conf_business",
        "conf_consumer",
        "conf_economic_sentiment",
        "economic_sentiment",
        "pl_retail_conf",
    }
)

DEFAULT_STALE_TOLERANCE = 2
DEFAULT_MIN_HISTORY = 36


def _is_expectation_column(name: object) -> bool:
    """Return whether a column name denotes an inflation expectation."""

    text = str(name).strip().casefold()
    if text in {str(c).casefold() for c in INFLATION_EXPECTATION_COLUMNS}:
        return True
    # ``expect`` is deliberately narrower than ``survey``.  Confidence and
    # sentiment surveys are independent policy candidates and must survive the
    # sentiment policy.  Require a separator/digit after the short ``exp``
    # prefix so a future ``export_*`` predictor is not silently removed.
    short_exp = text.startswith("exp") and (
        len(text) == 3 or text[3].isdigit() or text[3] in "_-"
    )
    return short_exp or "expect" in text


def _is_sentiment_column(name: object) -> bool:
    """Return whether a column is an identified sentiment/confidence measure."""

    text = str(name).strip().casefold()
    known = {str(c).casefold() for c in SENTIMENT_COLUMNS}
    return (
        text in known
        or text.startswith("conf_")
        or text.endswith("_confidence")
        or "sentiment" in text
    )


def feature_policy(features: pd.DataFrame, policy: str = "independent") -> pd.DataFrame:
    """Apply one of the three paper-panel policies.

    ``independent`` removes expectation and sentiment/confidence columns;
    ``sentiment`` removes expectations but retains sentiment indicators; and
    ``full`` retains every supplied column.  Column order and the index are
    preserved.  Policy filtering is name based and source agnostic.
    """

    if policy not in POLICIES:
        raise ValueError(f"unknown feature policy: {policy}")
    if not isinstance(features, pd.DataFrame):
        raise TypeError("features must be a pandas DataFrame")
    if not features.columns.is_unique:
        raise ValueError("features must have unique columns")

    if policy == "full":
        return features.copy()

    remove = []
    for column in features.columns:
        expectation = _is_expectation_column(column)
        sentiment = _is_sentiment_column(column)
        if expectation or (policy == "independent" and sentiment):
            remove.append(column)
    return features.drop(columns=remove).copy()


def panel_variants(features: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return the three named panel policies used by the big-model runner.

    This is intentionally a thin wrapper around :func:`feature_policy`; keeping
    one filtering implementation prevents the historical runner and the live
    entry point from silently disagreeing about which expectation columns are
    excluded.  The returned frames preserve the input index and column order.
    """

    return {policy: feature_policy(features, policy) for policy in POLICIES}


# Friendly aliases for callers that use the existing model's terminology.
apply_feature_policy = feature_policy
select_features = feature_policy


def _monthly_period_index(index: pd.Index, name: str) -> pd.PeriodIndex:
    """Normalize a one-observation-per-month index and reject non-monthly data."""

    if isinstance(index, pd.PeriodIndex):
        if index.freqstr not in ("M", "ME"):
            raise ValueError(f"{name} must use a monthly PeriodIndex")
        result = index.asfreq("M")
    elif isinstance(index, pd.DatetimeIndex):
        # A DatetimeIndex is accepted only when it contains one observation
        # per calendar month.  Daily data therefore fails through the duplicate
        # monthly periods check below rather than being silently resampled.
        result = index.to_period("M")
    else:
        raise ValueError(f"{name} must use a monthly index")

    if result.hasnans:
        raise ValueError(f"{name} monthly index cannot contain NaT")
    if not result.is_unique:
        raise ValueError(f"{name} monthly index must be unique")
    if not result.is_monotonic_increasing:
        raise ValueError(f"{name} monthly index must be sorted")
    if len(result) > 1 and not np.all(np.diff(result.asi8) == 1):
        raise ValueError(f"{name} must have a contiguous monthly index")
    return result


def validate_monthly_panel(panel: pd.DataFrame, *, name: str = "panel") -> pd.DataFrame:
    """Validate and return a numeric monthly panel copy.

    Missing values are permitted because the origin preparation layer handles
    them.  Infinite values, duplicate columns, duplicate months and calendar
    gaps are rejected.  Datetime month-end/month-start indexes are normalized
    to a monthly ``PeriodIndex``; daily data cannot pass the one-row-per-month
    check.
    """

    if not isinstance(panel, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")
    if panel.empty:
        raise ValueError(f"{name} cannot be empty")
    if not panel.columns.is_unique:
        raise ValueError(f"{name} must have unique columns")
    result = panel.copy()
    result.index = _monthly_period_index(result.index, name)
    try:
        values = result.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain numeric columns") from exc
    if np.isinf(values).any():
        raise ValueError(f"{name} must contain finite values or missing values")
    return result


def validate_monthly_series(series: pd.Series, *, name: str = "target") -> pd.Series:
    """Validate and return a numeric monthly series copy."""

    if not isinstance(series, pd.Series):
        raise TypeError(f"{name} must be a pandas Series")
    if series.empty:
        raise ValueError(f"{name} cannot be empty")
    result = series.copy()
    result.index = _monthly_period_index(result.index, name)
    try:
        values = result.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain numeric values") from exc
    if np.isinf(values).any():
        raise ValueError(f"{name} must contain finite values or missing values")
    return result.astype(float)


def _as_period(value: object, *, name: str = "origin") -> pd.Period:
    try:
        period = value if isinstance(value, pd.Period) else pd.Period(value, freq="M")
    except Exception as exc:  # pandas raises several different exception types
        raise ValueError(f"{name} must identify a monthly period") from exc
    if period.freqstr not in ("M", "ME"):
        raise ValueError(f"{name} must identify a monthly period")
    return period.asfreq("M")


def _check_horizon(horizon: int) -> int:
    if isinstance(horizon, bool) or not isinstance(horizon, (int, np.integer)) or horizon <= 0:
        raise ValueError("horizon must be a positive integer")
    return int(horizon)


def _check_tolerance(stale_tolerance: int) -> int:
    if isinstance(stale_tolerance, bool) or not isinstance(stale_tolerance, (int, np.integer)):
        raise ValueError("stale_tolerance must be a nonnegative integer")
    if stale_tolerance < 0:
        raise ValueError("stale_tolerance must be a nonnegative integer")
    return int(stale_tolerance)


def select_fresh_columns(
    panel: pd.DataFrame,
    origin: object,
    *,
    stale_tolerance: int = DEFAULT_STALE_TOLERANCE,
) -> tuple[str, ...]:
    """Select columns with a finite observation near ``origin``.

    Only rows at or before the origin are inspected.  A column remains fresh
    when its latest finite value is no more than ``stale_tolerance`` months old;
    its missing origin value can consequently be filled from training means.
    """

    frame = validate_monthly_panel(panel)
    r = _as_period(origin)
    tolerance = _check_tolerance(stale_tolerance)
    history = frame.loc[frame.index <= r]
    if history.empty:
        raise ValueError("panel has no rows at or before origin")
    fresh = []
    earliest = r - tolerance
    for column in history.columns:
        finite = history[column].dropna()
        if len(finite) and finite.index[-1] >= earliest:
            fresh.append(column)
    return tuple(fresh)


@dataclass
class OriginPanel:
    """A publication-cut, imputed view of one forecast origin."""

    origin: pd.Period
    horizon: int
    features: pd.DataFrame
    target: pd.Series
    X_train: pd.DataFrame
    y_train: pd.Series
    x_now: pd.Series
    feature_means: pd.Series
    fresh_columns: tuple[str, ...]
    selected_columns: tuple[str, ...]
    dropped_columns: tuple[str, ...]
    train_index: pd.PeriodIndex
    target_index: pd.PeriodIndex

    @property
    def columns(self) -> tuple[str, ...]:
        """Selected feature columns, excluding generated target lags."""

        return self.selected_columns

    @property
    def n_train(self) -> int:
        return len(self.y_train)

    def as_dict(self) -> dict[str, Any]:
        """Return serializable metadata while retaining frame objects."""

        return {
            "origin": str(self.origin),
            "horizon": self.horizon,
            "features": self.features,
            "target": self.target,
            "X_train": self.X_train,
            "y_train": self.y_train,
            "x_now": self.x_now,
            "feature_means": self.feature_means,
            "fresh_columns": list(self.fresh_columns),
            "selected_columns": list(self.selected_columns),
            "dropped_columns": list(self.dropped_columns),
            "train_index": self.train_index,
            "target_index": self.target_index,
        }


def prepare_origin_panel(
    target: pd.Series | pd.DataFrame,
    features: pd.DataFrame | pd.Series,
    *,
    origin: object | None = None,
    horizon: int = 1,
    stale_tolerance: int = DEFAULT_STALE_TOLERANCE,
) -> OriginPanel:
    """Cut, select and mean-impute a panel for a direct forecast.

    Training pairs use feature month ``t`` and target month ``t + horizon``;
    therefore target observations after the origin cannot enter the fit.  Fresh
    columns are selected using only feature rows through the origin.  Means are
    calculated only on eligible training rows, then used to fill both training
    gaps and the origin prediction row.  Rows after the origin are discarded
    before any of these operations.

    The preferred argument order is ``(target, features)``.  The reverse order
    is also accepted for compatibility with common feature-first callers.
    """

    if isinstance(target, pd.DataFrame) and isinstance(features, pd.Series):
        target, features = features, target
    if not isinstance(target, pd.Series) or not isinstance(features, pd.DataFrame):
        raise TypeError("prepare_origin_panel expects a target Series and features DataFrame")

    y = validate_monthly_series(target)
    X = validate_monthly_panel(features)
    h = _check_horizon(horizon)
    tolerance = _check_tolerance(stale_tolerance)
    if origin is None:
        observed = y.dropna()
        if observed.empty:
            raise ValueError("cannot infer origin from an empty target")
        r = observed.index[-1]
    else:
        r = _as_period(origin)
    if r not in X.index:
        raise ValueError("features must contain the forecast origin row")

    X_history = X.loc[X.index <= r]
    fresh = select_fresh_columns(X_history, r, stale_tolerance=tolerance)
    feature_cutoff = r - h
    candidate = X_history.index[X_history.index <= feature_cutoff]
    if len(candidate):
        target_index = candidate + h
        target_values = y.reindex(target_index)
        target_ok = target_values.notna().to_numpy()
        train_index = candidate[target_ok]
        target_index = target_index[target_ok]
    else:
        train_index = pd.PeriodIndex([], freq="M")
        target_index = pd.PeriodIndex([], freq="M")

    raw_train = X.loc[train_index, list(fresh)].astype(float)
    all_means = raw_train.mean(axis=0, skipna=True)
    selected = tuple(column for column in fresh if pd.notna(all_means.get(column, np.nan)))
    means = all_means.reindex(selected).astype(float)
    X_train = raw_train.loc[:, list(selected)].fillna(means)
    x_now = X.loc[[r], list(selected)].iloc[0].astype(float).fillna(means)
    X_cut = X_history.loc[:, list(selected)].astype(float).fillna(means)
    y_cut = y.loc[y.index <= r]
    y_train_values = y.reindex(target_index).to_numpy(dtype=float)
    y_train = pd.Series(y_train_values, index=train_index, name=y.name, dtype=float)
    dropped = tuple(column for column in X.columns if column not in selected)

    return OriginPanel(
        origin=r,
        horizon=h,
        features=X_cut,
        target=y_cut,
        X_train=X_train,
        y_train=y_train,
        x_now=x_now,
        feature_means=means,
        fresh_columns=fresh,
        selected_columns=selected,
        dropped_columns=dropped,
        train_index=train_index,
        target_index=target_index,
    )


# Aliases kept deliberately small and explicit for the forthcoming runner.
origin_panel = prepare_origin_panel
fresh_columns = select_fresh_columns


def _check_y_lags(y_lags: int) -> int:
    if isinstance(y_lags, bool) or not isinstance(y_lags, (int, np.integer)) or y_lags < 0:
        raise ValueError("y_lags must be a nonnegative integer")
    return int(y_lags)


def build_direct_supervised(
    target: pd.Series,
    features: pd.DataFrame,
    horizon: int,
    *,
    origin: object | None = None,
    stale_tolerance: int = DEFAULT_STALE_TOLERANCE,
    y_lags: int = 3,
    include_month: bool = True,
) -> dict[str, Any]:
    """Build direct-horizon arrays after origin selection and imputation.

    ``include_month`` is explicit because the paper-style predictor-only
    specification uses the supplied panel alone.  The default remains the
    project's practical three target lags plus month-of-year feature used by
    the existing challengers.
    """

    lags = _check_y_lags(y_lags)
    if not isinstance(include_month, bool):
        raise TypeError("include_month must be a boolean")
    prepared = prepare_origin_panel(
        target,
        features,
        origin=origin,
        horizon=horizon,
        stale_tolerance=stale_tolerance,
    )
    design = prepared.features.copy()
    for lag in range(lags):
        design[f"y_l{lag}"] = prepared.target.reindex(design.index).shift(lag)
    if include_month:
        design["month"] = design.index.month.astype(float)

    raw_train = design.loc[prepared.train_index]
    means = raw_train.mean(axis=0, skipna=True)
    keep = means.notna()
    columns = tuple(means.index[keep].tolist())
    means = means.loc[list(columns)].astype(float)
    X_train = raw_train.loc[:, list(columns)].astype(float).fillna(means)
    x_now = design.loc[prepared.origin, list(columns)].astype(float).fillna(means)
    return {
        "prepared": prepared,
        "X_train": X_train,
        "y_train": prepared.y_train.copy(),
        "x_now": x_now,
        "feature_columns": columns,
        "feature_means": means,
        "n_train": len(prepared.y_train),
    }


def _infer_origin(target: pd.Series, origin: object | None) -> pd.Period:
    y = validate_monthly_series(target)
    if origin is not None:
        return _as_period(origin)
    observed = y.dropna()
    if observed.empty:
        raise ValueError("cannot infer origin from an empty target")
    return observed.index[-1]


def _base_result(prepared: OriginPanel, *, estimator: str, policy: str | None) -> dict[str, Any]:
    return {
        "forecast": np.nan,
        "point": np.nan,
        "status": "unavailable",
        "fallback_used": False,
        "fallback": False,
        "estimator": estimator,
        "policy": policy,
        "origin": str(prepared.origin),
        "horizon": prepared.horizon,
        "n_train": prepared.n_train,
        "fresh_columns": list(prepared.fresh_columns),
        "selected_columns": list(prepared.selected_columns),
        "dropped_columns": list(prepared.dropped_columns),
    }


def _fallback_result(
    prepared: OriginPanel,
    *,
    estimator: str,
    policy: str | None,
    reason: str,
    error: str | None = None,
) -> dict[str, Any]:
    result = _base_result(prepared, estimator=estimator, policy=policy)
    observed = prepared.target.dropna()
    point = float(observed.iloc[-1]) if len(observed) else np.nan
    result.update(
        forecast=point,
        point=point,
        status="fallback_last_value" if len(observed) else "fallback_no_target",
        fallback_used=True,
        fallback=True,
        fallback_reason=reason,
    )
    if error is not None:
        result["error"] = error
    return result


def _minimum_history(min_history: int) -> int:
    if isinstance(min_history, bool) or not isinstance(min_history, (int, np.integer)) or min_history <= 0:
        raise ValueError("min_history must be a positive integer")
    return int(min_history)


class _SklearnQuantileForest:
    """Small compatibility QRF used only when ``quantile-forest`` is absent.

    A quantile is estimated from the individual tree predictions at the
    forecast row.  This is a useful offline fallback for smoke tests and a
    transparent approximation; it is never reported as an exact CNB TVW-QRF
    replication.  The normal locked environment uses ``TVWQRF`` above.
    """

    def __init__(self, n_estimators: int = 200, min_samples_leaf: int = 3,
                 max_features: float | str = 1.0, seed: int = 42,
                 random_state: int | None = None, **_: Any):
        from sklearn.ensemble import RandomForestRegressor

        self._forest = RandomForestRegressor(
            n_estimators=int(n_estimators),
            min_samples_leaf=int(min_samples_leaf),
            max_features=max_features,
            random_state=seed if random_state is None else random_state,
            n_jobs=-1,
        )

    def fit_predict(self, X_train: np.ndarray, y_train: np.ndarray, x_now: np.ndarray) -> dict[str, Any]:
        self._forest.fit(X_train, y_train)
        draws = np.asarray([tree.predict(x_now.reshape(1, -1))[0] for tree in self._forest.estimators_], dtype=float)
        quantiles = (0.10, 0.25, 0.50, 0.75, 0.90)
        qv = np.quantile(draws, quantiles)
        return {
            "point": float(qv[2]),
            "median": float(qv[2]),
            "quantiles": dict(zip(quantiles, qv.tolist())),
            "weights": {q: round(1.0 / len(quantiles), 3) for q in quantiles},
            "p05_p95": (float(np.quantile(draws, 0.05)), float(np.quantile(draws, 0.95))),
            "engine": "sklearn_random_forest_tree_quantiles",
        }


class SklearnLeafTVWQRF:
    """Leaf-weighted TVW-QRF fallback for the CNB comparison lane.

    ``quantile-forest`` is the reference implementation used by the project,
    but it is not available in every local environment.  Taking quantiles of
    tree point predictions (the older fallback above) is materially different
    from a quantile regression forest: the latter uses the empirical response
    distribution of observations sharing terminal leaves with the forecast
    row.  This class implements that leaf-weighted distribution with
    scikit-learn's ordinary random forest and applies the same TVW3
    validation-weighting rule as :class:`models.horizon_models.TVWQRF`.

    It is an approximation, because bootstrap and tie-handling details may
    differ from the pinned ``quantile-forest`` package.  The explicit class
    name and engine label prevent it being mistaken for an exact paper run.
    """

    def __init__(
        self,
        quantiles=(0.10, 0.25, 0.50, 0.75, 0.90),
        lower=(0.00, 0.15, 0.30, 0.15, 0.00),
        upper=(0.15, 0.35, 0.50, 0.35, 0.15),
        val_window: int = 12,
        half_life: float = 6.0,
        n_estimators: int = 200,
        min_samples_leaf: int = 3,
        seed: int = 42,
        max_features: float | str = 1.0,
        **_: Any,
    ):
        from sklearn.ensemble import RandomForestRegressor

        self.q = np.asarray(quantiles, dtype=float)
        self.lo = np.asarray(lower, dtype=float)
        self.hi = np.asarray(upper, dtype=float)
        if not (len(self.q) == len(self.lo) == len(self.hi)):
            raise ValueError("quantiles and TVW bounds must have equal length")
        if np.any(np.diff(self.q) <= 0):
            raise ValueError("quantiles must be strictly increasing")
        self.val_window = int(val_window)
        self.half_life = float(half_life)
        self._forest_options = {
            "n_estimators": int(n_estimators),
            "min_samples_leaf": int(min_samples_leaf),
            "max_features": max_features,
            "random_state": int(seed),
            "n_jobs": -1,
        }
        self._rf_cls = RandomForestRegressor
        self.w_ = np.full(len(self.q), 1.0 / len(self.q))
        self._X_train: np.ndarray | None = None
        self._y_train: np.ndarray | None = None
        self._forest = None

    @staticmethod
    def _weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
        order = np.argsort(values, kind="mergesort")
        values = np.asarray(values, dtype=float)[order]
        weights = np.asarray(weights, dtype=float)[order]
        total = float(weights.sum())
        if not np.isfinite(total) or total <= 0:
            return float(np.quantile(values, q))
        cdf = np.cumsum(weights) / total
        # The empirical inverse CDF is right-continuous.  ``searchsorted``
        # avoids interpolation between response observations, matching the
        # usual QRF interpretation more closely than np.quantile.
        return float(values[min(int(np.searchsorted(cdf, q, side="left")), len(values) - 1)])

    def _fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self._forest = self._rf_cls(**self._forest_options).fit(X, y)
        self._X_train = np.asarray(X, dtype=float)
        self._y_train = np.asarray(y, dtype=float)

    def _predict_quantiles(self, X: np.ndarray, quantiles: Sequence[float]) -> np.ndarray:
        if self._forest is None or self._X_train is None or self._y_train is None:
            raise RuntimeError("forest has not been fitted")
        X = np.asarray(X, dtype=float)
        train_leaves = np.asarray(self._forest.apply(self._X_train))
        pred_leaves = np.asarray(self._forest.apply(X))
        out = np.empty((len(X), len(quantiles)), dtype=float)
        n_trees = len(self._forest.estimators_)
        for row, leaves in enumerate(pred_leaves):
            values: list[float] = []
            weights: list[float] = []
            for tree_idx, leaf in enumerate(leaves):
                members = np.flatnonzero(train_leaves[:, tree_idx] == leaf)
                if len(members) == 0:
                    values.append(float(self._forest.estimators_[tree_idx].predict(X[row : row + 1])[0]))
                    weights.append(1.0 / n_trees)
                    continue
                values.extend(self._y_train[members].tolist())
                weights.extend([1.0 / (n_trees * len(members))] * len(members))
            vv = np.asarray(values, dtype=float)
            ww = np.asarray(weights, dtype=float)
            out[row] = [self._weighted_quantile(vv, ww, float(q)) for q in quantiles]
        return out

    def _solve_weights(self, q_val: np.ndarray, y_val: np.ndarray) -> np.ndarray:
        from scipy.optimize import minimize

        n = len(y_val)
        age = np.arange(n - 1, -1, -1, dtype=float)
        omega = 2.0 ** (-age / self.half_life)
        omega = omega / omega.sum()
        sqrt_w = np.sqrt(omega)
        A = q_val * sqrt_w[:, None]
        b = y_val * sqrt_w

        def objective(w):
            residual = A @ w - b
            return float(residual @ residual)

        constraints = [{"type": "eq", "fun": lambda w: float(w.sum() - 1.0)}]
        w0 = np.clip(np.full(len(self.q), 1.0 / len(self.q)), self.lo, self.hi)
        # Bounds in the paper are feasible for all three schemes.  A clipped
        # equal-weight vector may not sum to one for a caller's custom bounds,
        # so use a bounded least-squares result only as a defensive fallback.
        if not np.isclose(w0.sum(), 1.0):
            w0 = np.full(len(self.q), 1.0 / len(self.q))
        result = minimize(objective, w0, bounds=list(zip(self.lo, self.hi)),
                          constraints=constraints, method="SLSQP")
        return np.asarray(result.x if result.success else w0, dtype=float)

    def fit_predict(self, X_train: np.ndarray, y_train: np.ndarray, x_now: np.ndarray) -> dict[str, Any]:
        X_train = np.asarray(X_train, dtype=float)
        y_train = np.asarray(y_train, dtype=float)
        x_now = np.asarray(x_now, dtype=float).reshape(1, -1)
        n = len(y_train)
        v = min(self.val_window, max(n // 5, 4))
        if n <= v:
            raise ValueError("not enough rows for TVW validation")
        self._fit(X_train[:-v], y_train[:-v])
        q_val = self._predict_quantiles(X_train[-v:], self.q)
        self.w_ = self._solve_weights(q_val, y_train[-v:])
        self._fit(X_train, y_train)
        all_q = np.r_[0.05, self.q, 0.95]
        q_now = self._predict_quantiles(x_now, all_q)[0]
        point = float(q_now[1:-1] @ self.w_)
        return {
            "point": point,
            "quantiles": dict(zip(self.q.tolist(), q_now[1:-1].tolist())),
            "weights": dict(zip(self.q.tolist(), np.round(self.w_, 3).tolist())),
            "median": float(q_now[len(q_now) // 2]),
            "p05_p95": (float(q_now[0]), float(q_now[-1])),
            "engine": "sklearn_leaf_weighted_tvw_qrf",
        }


def _prepare_with_policy(
    target: pd.Series,
    features: pd.DataFrame,
    horizon: int,
    *,
    origin: object | None,
    policy: str | None,
    stale_tolerance: int,
    y_lags: int,
    include_month: bool,
) -> dict[str, Any]:
    if policy is not None:
        features = feature_policy(features, policy)
    return build_direct_supervised(
        target,
        features,
        horizon,
        origin=origin,
        stale_tolerance=stale_tolerance,
        y_lags=y_lags,
        include_month=include_month,
    )


def direct_tvwqrf_forecast(
    target: pd.Series,
    features: pd.DataFrame,
    horizon: int,
    *,
    origin: object | None = None,
    policy: str | None = None,
    stale_tolerance: int = DEFAULT_STALE_TOLERANCE,
    min_history: int = DEFAULT_MIN_HISTORY,
    y_lags: int = 3,
    include_month: bool = True,
    qrf_options: Mapping[str, Any] | None = None,
    qrf_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run an existing TVW-QRF as a direct h-step research challenger.

    The wrapper returns a diagnostics dictionary, including ``forecast`` and
    ``point``.  A last-observation random-walk value is used deterministically
    when the direct training history is too short, no usable columns remain,
    or the optional estimator cannot be imported/fitted.
    """

    h = _check_horizon(horizon)
    minimum = _minimum_history(min_history)
    try:
        data = _prepare_with_policy(
            target,
            features,
            h,
            origin=origin,
            policy=policy,
            stale_tolerance=stale_tolerance,
            y_lags=y_lags,
            include_month=include_month,
        )
    except Exception:
        # Validation errors are caller errors and should remain visible.
        raise
    prepared = data["prepared"]
    if data["n_train"] < minimum:
        return _fallback_result(
            prepared,
            estimator="TVW_QRF",
            policy=policy,
            reason="insufficient_history",
        )
    if not data["feature_columns"]:
        return _fallback_result(
            prepared,
            estimator="TVW_QRF",
            policy=policy,
            reason="no_usable_features",
        )

    result = _base_result(prepared, estimator="TVW_QRF", policy=policy)
    try:
        if qrf_factory is None:
            try:
                from models.horizon_models import TVWQRF

                qrf_factory = TVWQRF
            except (ImportError, ModuleNotFoundError):
                # The locked research environment includes quantile-forest,
                # but a lightweight local checkout may not.  Keep the runner
                # executable with an explicitly labelled sklearn RF quantile
                # approximation rather than silently turning every challenger
                # into a random walk.
                qrf_factory = _SklearnQuantileForest
        model = qrf_factory(**dict(qrf_options or {}))
        fitted = model.fit_predict(
            data["X_train"].to_numpy(dtype=float),
            data["y_train"].to_numpy(dtype=float),
            data["x_now"].to_numpy(dtype=float),
        )
        if isinstance(fitted, Mapping):
            point = fitted.get("point", fitted.get("forecast"))
            result["estimator_result"] = dict(fitted)
        else:
            point = fitted
        point = float(point)
        if not np.isfinite(point):
            raise ValueError("TVW-QRF returned a nonfinite point forecast")
        result.update(forecast=point, point=point, status="estimated")
        result["engine"] = getattr(qrf_factory, "__name__", str(qrf_factory))
        return result
    except Exception as exc:
        return _fallback_result(
            prepared,
            estimator="TVW_QRF",
            policy=policy,
            reason="estimator_error",
            error=f"{type(exc).__name__}: {exc}",
        )


def _mapping_callback(
    callback: Callable[[str], Any] | Mapping[str, Any] | None,
    *,
    default: Callable[[str], Any],
) -> Callable[[str], Any]:
    if callback is None:
        return default
    if callable(callback):
        return callback
    if isinstance(callback, Mapping):
        return lambda column: callback.get(column, default(column))
    raise TypeError("callback must be callable, a mapping, or None")


def _default_block(column: str) -> str:
    text = column.casefold()
    if "expect" in text or text.startswith("exp") or "service" in text or text in {"y_l0", "y_l1", "y_l2"}:
        return "trend"
    if any(token in text for token in ("esi", "conf", "sentiment", "retail", "unemployment", "wage")):
        return "demand"
    if any(token in text for token in ("fx", "eurczk", "usdczk")):
        return "fx"
    if any(token in text for token in ("fuel", "brent", "gas", "oil")):
        return "global_supply"
    if any(token in text for token in ("ppi", "import", "agri", "food")):
        return "domestic_supply"
    return "other"


def _default_monotonic(column: str) -> int:
    del column
    return 0


def _bbim_unconstrained_forecast(
    y_hist: pd.Series,
    X: pd.DataFrame,
    h: int,
    block_of,
    mono_of,
    rounds: int = 150,
    lr: float = 0.02,
    subsample: float = 0.5,
    val_len: int = 24,
    patience: int = 20,
    seed: int = 42,
    y_lags: int = 3,
    include_month: bool = True,
) -> float:
    """Compatibility BBIM when sklearn predates ``monotonic_cst``.

    ``models.bbim_lite`` uses the monotonic-tree keyword introduced in newer
    sklearn releases.  The paper-inspired challenger is still useful as an
    unconstrained additive block learner on older locked environments, so keep
    a small, explicitly named copy of the training loop here.  It never claims
    to impose signs: the returned model is labelled unconstrained by the
    caller.  This path is only reached after the feature preparation and is
    intentionally isolated from the operating models.
    """

    from sklearn.tree import DecisionTreeRegressor

    feats = X.copy()
    for i in range(int(y_lags)):
        feats[f"y_l{i}"] = y_hist.shift(i)
    if include_month:
        feats["month"] = feats.index.month
    target = y_hist.shift(-int(h)).rename("target")
    frame = pd.concat([target, feats], axis=1).dropna(subset=["target"]).dropna()
    if frame.empty:
        return float(y_hist.dropna().iloc[-1])
    x_now = feats.dropna().iloc[-1].to_numpy(dtype=float)
    cols = list(frame.drop(columns="target").columns)
    Xt = frame[cols].to_numpy(dtype=float)
    yt = frame["target"].to_numpy(dtype=float)

    blocks: dict[str, list[int]] = {}
    for j, column in enumerate(cols):
        blocks.setdefault(block_of(column), []).append(j)
    if not blocks:
        return float(y_hist.dropna().iloc[-1])

    val_len = int(val_len)
    if len(yt) < val_len + 24:
        val_len = max(8, len(yt) // 3)
    if len(yt) <= val_len:
        return float(y_hist.dropna().iloc[-1])
    fit_idx = np.arange(len(yt) - val_len)
    val_idx = np.arange(len(yt) - val_len, len(yt))

    rng = np.random.default_rng(int(seed))
    base = float(yt[fit_idx].mean())
    F_fit = np.full(len(fit_idx), base)
    F_val = np.full(len(val_idx), base)
    trees: list[tuple[str, DecisionTreeRegressor]] = []
    best_val, best_len, stall = np.inf, 0, 0
    names = list(blocks)

    for _ in range(int(rounds)):
        for bi in rng.permutation(len(names)):
            name = names[int(bi)]
            idx = blocks[name]
            residual = yt[fit_idx] - F_fit
            rows = rng.random(len(fit_idx)) < float(subsample)
            if int(rows.sum()) < 10:
                rows[:] = True
            tree = DecisionTreeRegressor(
                max_depth=3,
                min_samples_leaf=5,
                random_state=int(rng.integers(1 << 31)),
            )
            tree.fit(Xt[fit_idx][rows][:, idx], residual[rows])
            F_fit += float(lr) * tree.predict(Xt[fit_idx][:, idx])
            F_val += float(lr) * tree.predict(Xt[val_idx][:, idx])
            trees.append((name, tree))
        val_rmse = float(np.sqrt(np.mean((yt[val_idx] - F_val) ** 2)))
        if val_rmse < best_val - 1e-6:
            best_val, best_len, stall = val_rmse, len(trees), 0
        else:
            stall += 1
            if stall >= int(patience):
                break

    forecast = base
    for name, tree in trees[:best_len]:
        forecast += float(lr) * tree.predict(x_now[None, blocks[name]])[0]
    return float(forecast)


def _monotonic_trees_supported() -> bool:
    """Return whether the installed sklearn accepts ``monotonic_cst``."""

    try:
        import inspect
        from sklearn.tree import DecisionTreeRegressor

        return "monotonic_cst" in inspect.signature(DecisionTreeRegressor).parameters
    except Exception:
        return False


def direct_bbim_forecast(
    target: pd.Series,
    features: pd.DataFrame,
    horizon: int,
    *,
    origin: object | None = None,
    policy: str | None = None,
    stale_tolerance: int = DEFAULT_STALE_TOLERANCE,
    min_history: int = DEFAULT_MIN_HISTORY,
    y_lags: int = 3,
    include_month: bool = True,
    block_of: Callable[[str], str] | Mapping[str, str] | None = None,
    mono_of: Callable[[str], int] | Mapping[str, int] | None = None,
    bbim_options: Mapping[str, Any] | None = None,
    bbim_engine: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run the existing BBIM-lite engine as a direct h-step challenger.

    ``block_of`` and ``mono_of`` may be callables or column mappings.  The
    source-agnostic defaults put columns into broad paper-inspired blocks and
    impose no monotonic restriction; callers should provide economically
    justified mappings before interpreting a production-like run.
    """

    h = _check_horizon(horizon)
    minimum = _minimum_history(min_history)
    data = _prepare_with_policy(
        target,
        features,
        h,
        origin=origin,
        policy=policy,
        stale_tolerance=stale_tolerance,
        y_lags=y_lags,
        include_month=include_month,
    )
    prepared = data["prepared"]
    if data["n_train"] < minimum:
        return _fallback_result(
            prepared,
            estimator="BBIM",
            policy=policy,
            reason="insufficient_history",
        )
    if not data["feature_columns"]:
        return _fallback_result(
            prepared,
            estimator="BBIM",
            policy=policy,
            reason="no_usable_features",
        )

    opts = dict(bbim_options or {})
    if block_of is None and "block_of" in opts:
        block_of = opts.pop("block_of")
    if mono_of is None and "mono_of" in opts:
        mono_of = opts.pop("mono_of")
    block_fn = _mapping_callback(block_of, default=_default_block)
    mono_fn = _mapping_callback(mono_of, default=_default_monotonic)
    # The wrapper builds its eligibility arrays with ``y_lags`` above; pass
    # the same choice through to BBIM's own feature builder as well.  Without
    # this, a caller asking for a lag-12 challenger would silently fit BBIM's
    # hard-coded default of three lags.
    opts.setdefault("y_lags", int(y_lags))
    opts.setdefault("include_month", bool(include_month))
    result = _base_result(prepared, estimator="BBIM", policy=policy)
    constraints_supported: bool | None = None
    try:
        if bbim_engine is None:
            constraints_supported = _monotonic_trees_supported()
            if constraints_supported:
                from models.bbim_lite import bbim_forecast as bbim_engine
            else:
                # sklearn <1.4 cannot accept the monotonicity keyword used by
                # the reference implementation.  Run the same blockwise
                # learner with signs explicitly disabled, preserving a real
                # challenger instead of turning every row into a random walk.
                bbim_engine = _bbim_unconstrained_forecast

        point = bbim_engine(
            prepared.target,
            prepared.features,
            h,
            block_of=block_fn,
            mono_of=mono_fn,
            **opts,
        )
        if isinstance(point, Mapping):
            result["estimator_result"] = dict(point)
            point = point.get("point", point.get("forecast"))
        point = float(point)
        if not np.isfinite(point):
            raise ValueError("BBIM returned a nonfinite point forecast")
        result.update(forecast=point, point=point, status="estimated")
        result["blocks"] = {column: block_fn(column) for column in data["feature_columns"]}
        result["monotonicity"] = {column: int(mono_fn(column)) for column in data["feature_columns"]}
        if constraints_supported is None:
            # A caller-supplied engine owns its constraint semantics; avoid
            # importing sklearn just to label a test/dummy engine.
            result["engine"] = "BBIM-custom"
        else:
            result["engine"] = "BBIM-lite" if constraints_supported else "BBIM-lite-unconstrained-compat"
            result["monotonic_constraints_supported"] = constraints_supported
        return result
    except Exception as exc:
        return _fallback_result(
            prepared,
            estimator="BBIM",
            policy=policy,
            reason="estimator_error",
            error=f"{type(exc).__name__}: {exc}",
        )


# Name variants make the boundary easy to discover without duplicating logic.
direct_tvw_qrf_forecast = direct_tvwqrf_forecast
tvwqrf_forecast = direct_tvwqrf_forecast
tvw_qrf_forecast = direct_tvwqrf_forecast
direct_bbim = direct_bbim_forecast
bbim_forecast = direct_bbim_forecast


__all__ = [
    "POLICIES",
    "INFLATION_EXPECTATION_COLUMNS",
    "EXPECTATION_COLUMNS",
    "SENTIMENT_COLUMNS",
    "OriginPanel",
    "feature_policy",
    "panel_variants",
    "apply_feature_policy",
    "select_features",
    "validate_monthly_panel",
    "validate_monthly_series",
    "select_fresh_columns",
    "fresh_columns",
    "prepare_origin_panel",
    "origin_panel",
    "build_direct_supervised",
    "direct_tvwqrf_forecast",
    "SklearnLeafTVWQRF",
    "direct_tvw_qrf_forecast",
    "tvwqrf_forecast",
    "tvw_qrf_forecast",
    "direct_bbim_forecast",
    "direct_bbim",
    "bbim_forecast",
]
