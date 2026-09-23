"""Fixed-grid, nested rolling-origin ridge tuning for the independent core.

Feature vintages remain the caller's responsibility. This module enforces
forecast/target month alignment and target-publication eligibility, and
never consumes the legacy model's fitted or sequential residual history.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


EXCLUDED = frozenset({"exp12", "exp36", "exp12_x_state", "household_exp", "esi"})
MIN_TRAIN = 48
VALIDATION_WINDOW = 36
MIN_VALIDATION = 24


@dataclass(frozen=True)
class CoreConfig:
    alpha: float
    window: int | None

    def __post_init__(self):
        if not np.isfinite(self.alpha) or self.alpha <= 0:
            raise ValueError("alpha must be positive and finite")
        if self.window is not None and (not isinstance(self.window, int) or self.window < MIN_TRAIN):
            raise ValueError("training window must be at least 48 calendar months")

    @property
    def key(self):
        return f"a{self.alpha:g}_w{self.window if self.window is not None else 'expanding'}"


DEFAULT = CoreConfig(3.0, None)
GRID = tuple(CoreConfig(alpha, window) for alpha in (0.3, 3.0, 30.0, 300.0) for window in (60, 120, None))


def hard_features(features: pd.DataFrame) -> pd.DataFrame:
    return features.drop(columns=list(EXCLUDED), errors="ignore").copy()


def _monthly(obj, name):
    index = obj.index
    if (not isinstance(index, pd.PeriodIndex) or index.freqstr != "M" or index.hasnans
            or not index.is_unique or not index.is_monotonic_increasing
            or (len(index) > 1 and not np.all(np.diff(index.asi8) == 1))):
        raise ValueError(f"{name} must have a contiguous monthly PeriodIndex")


def ridge_prediction(features: pd.DataFrame, target: pd.Series, origin: pd.Period,
                     as_of, available_from: pd.Series, config: CoreConfig = DEFAULT) -> dict:
    """Fit month-s features to month-s core; predict month origin at as_of.

    Missing values are imputed only from the training slice. Rows outside
    the calendar window, at/after origin, or unpublished at as_of cannot
    influence the fit, imputation or scaling. Training metadata is returned
    with every prediction so downstream evidence can audit those cutoffs.
    """
    for obj, name in ((features, "features"), (target, "target"), (available_from, "available_from")):
        _monthly(obj, name)
    if not features.columns.is_unique or origin not in features.index:
        raise ValueError("features need unique columns and the forecast origin row")
    if not target.index.isin(features.index).all() or not target.index.isin(available_from.index).all():
        raise ValueError("features and publication dates must cover every target month")
    as_of = pd.Timestamp(as_of)
    if pd.isna(as_of):
        raise ValueError("a valid decision timestamp is required")
    dates = pd.to_datetime(available_from.reindex(target.index))
    eligible = (target.index < origin) & dates.le(as_of).to_numpy() & target.notna().to_numpy()
    if config.window is not None:
        eligible &= target.index >= origin - config.window
    train_index = target.index[eligible]
    info = {"prediction": np.nan, "n_train": len(train_index),
            "train_start": train_index.min() if len(train_index) else None,
            "train_end": train_index.max() if len(train_index) else None,
            "training_last_release": dates.loc[train_index].max() if len(train_index) else pd.NaT,
            "dropped_columns": [], "fit_status": "insufficient_history"}
    if len(train_index) < MIN_TRAIN:
        return info
    train = features.loc[train_index].astype(float)
    prediction_row = features.loc[[origin]].astype(float)
    yy = target.loc[train_index].to_numpy(dtype=float)
    if np.isinf(train.to_numpy()).any() or np.isinf(prediction_row.to_numpy()).any() or not np.isfinite(yy).all():
        raise ValueError("training data and prediction row must be finite or missing")
    means = train.mean()
    valid = means.notna()
    info["dropped_columns"] = means.index[~valid].tolist()
    train = train.loc[:, valid].fillna(means[valid])
    prediction_row = prediction_row.loc[:, valid].fillna(means[valid])
    center = train.mean()
    scale = train.std().replace(0.0, 1.0)
    z = ((train - center) / scale).to_numpy()
    z_now = ((prediction_row - center) / scale).to_numpy()
    beta = np.linalg.solve(z.T @ z + config.alpha * np.eye(z.shape[1]), z.T @ (yy - yy.mean()))
    info.update(prediction=float(yy.mean() + (z_now @ beta)[0]), fit_status="estimated")
    return info


def select_config(predictions: pd.DataFrame, origin: pd.Period, as_of, *, configs=GRID) -> dict:
    """Select from the latest 36 common, published prior sequential errors."""
    keys = [config.key for config in configs]
    if DEFAULT.key not in keys or len(set(keys)) != len(keys):
        raise ValueError("the candidate set must contain the default and unique configurations")
    as_of = pd.Timestamp(as_of)
    eligible = predictions.loc[(predictions.origin < origin)
                               & pd.to_datetime(predictions.target_available_from).le(as_of)
                               & predictions.config.isin(keys)].copy()
    eligible = eligible[np.isfinite(eligible.prediction) & np.isfinite(eligible.actual)]
    eligible["squared_error"] = (eligible.prediction - eligible.actual) ** 2
    common = eligible.pivot(index="origin", columns="config", values="squared_error")
    common = common.reindex(columns=keys).dropna().sort_index().iloc[-VALIDATION_WINDOW:]
    chosen = {"config": DEFAULT.key, "n_validation": len(common), "selection_reason": "insufficient_validation",
              "validation_start": common.index.min() if len(common) else None,
              "validation_end": common.index.max() if len(common) else None,
              "validation_last_release": eligible.loc[eligible.origin.isin(common.index), "target_available_from"].max(),
              "validation_origins": "|".join(map(str, common.index)),
              "selected_inner_rmse": np.nan, "default_inner_rmse": np.nan}
    if len(common) < MIN_VALIDATION:
        return chosen
    mse = common.mean()
    tied = mse.index[np.isclose(mse.values, mse.min(), rtol=1e-10, atol=1e-12)].tolist()
    if DEFAULT.key in tied:
        winner = DEFAULT.key
        reason = "tie_default" if len(tied) > 1 else "minimum_prior_mse"
    else:
        winner = next(key for key in keys if key in tied)
        reason = "tie_fixed_order" if len(tied) > 1 else "minimum_prior_mse"
    chosen.update(config=winner, selection_reason=reason,
                  selected_inner_rmse=float(np.sqrt(mse[winner])), default_inner_rmse=float(np.sqrt(mse[DEFAULT.key])))
    return chosen


def nested_predictions(features: pd.DataFrame, target: pd.Series, decisions: pd.Series,
                       available_from: pd.Series, outer_origins: pd.PeriodIndex, *, configs=GRID):
    """Return every sequential candidate prediction and the outer schedule.

    Future actuals are included in the first table solely for scoring/export;
    select_config filters their publication timestamps before using errors.
    The schedule contains no realised outer outcome or outer error.
    """
    _monthly(decisions, "decisions")
    _monthly(pd.Series(index=outer_origins, dtype=float), "outer origins")
    if not len(outer_origins) or not outer_origins.isin(decisions.index).all():
        raise ValueError("outer origins must be nonempty and covered by decisions")
    features = hard_features(features)
    rows = []
    for origin in decisions.index[decisions.index <= outer_origins.max()]:
        if origin not in features.index or origin not in target.index:
            continue
        as_of = decisions.loc[origin]
        if pd.isna(as_of):
            continue
        for config in configs:
            fit = ridge_prediction(features, target, origin, as_of, available_from, config)
            rows.append({"origin": origin, "as_of": as_of, "config": config.key, "alpha": config.alpha,
                         "window": config.window if config.window is not None else "expanding", **fit,
                         "actual": target.loc[origin], "target_available_from": available_from.loc[origin],
                         "error": target.loc[origin] - fit["prediction"]})
    predictions = pd.DataFrame(rows)
    schedule = []
    for origin in outer_origins:
        chosen = select_config(predictions, origin, decisions.loc[origin], configs=configs)
        current = predictions[(predictions.origin == origin) & (predictions.config == chosen["config"])]
        if len(current) != 1:
            raise ValueError(f"missing or duplicate forecast for {origin}")
        forecast = current.iloc[0]
        schedule.append({"origin": origin, "as_of": decisions.loc[origin], **chosen,
                         "prediction": forecast.prediction, "n_train": int(forecast.n_train),
                         "train_start": forecast.train_start, "train_end": forecast.train_end,
                         "training_last_release": forecast.training_last_release})
    return predictions, pd.DataFrame(schedule)
