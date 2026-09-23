"""Focused tests for the source-agnostic paper-inspired model helpers."""

import numpy as np
import pandas as pd
import pytest


def _panel(n=72):
    index = pd.period_range("2015-01", periods=n, freq="M")
    t = np.arange(n, dtype=float)
    target = pd.Series(0.2 + 0.01 * t + 0.15 * np.sin(t / 3), index=index, name="cpi_mm")
    features = pd.DataFrame(
        {
            "core": 0.1 * np.cos(t / 4),
            "exp12": 2.0 + 0.01 * t,
            "household_price_expect": 1.5 + 0.02 * t,
            "esi": 100.0 + np.sin(t / 5),
            "conf_business": 95.0 + np.cos(t / 7),
        },
        index=index,
    )
    return target, features


def test_policies_remove_expectations_and_preserve_sentiment():
    from models.paper_big import feature_policy

    _, features = _panel(6)
    assert list(feature_policy(features, "independent").columns) == ["core"]
    assert list(feature_policy(features, "sentiment").columns) == [
        "core",
        "esi",
        "conf_business",
    ]
    assert list(feature_policy(features, "full").columns) == list(features.columns)
    with pytest.raises(ValueError, match="unknown feature policy"):
        feature_policy(features, "typo")


def test_independent_policy_does_not_mistake_exports_for_expectations():
    from models.paper_big import feature_policy

    index = pd.period_range("2020-01", periods=3, freq="M")
    frame = pd.DataFrame({"export_yoy": [1.0, 2.0, 3.0], "exp12": [2.0, 2.1, 2.2]}, index=index)
    assert list(feature_policy(frame, "independent").columns) == ["export_yoy"]


def test_monthly_panel_validation_rejects_gaps_duplicates_and_nonmonthly():
    from models.paper_big import validate_monthly_panel

    _, features = _panel(6)
    normalized = validate_monthly_panel(features)
    assert isinstance(normalized.index, pd.PeriodIndex)
    with pytest.raises(ValueError, match="contiguous monthly"):
        validate_monthly_panel(features.drop(features.index[2]))
    duplicate = pd.concat([features, features.iloc[[0]]])
    with pytest.raises(ValueError, match="unique"):
        validate_monthly_panel(duplicate)
    daily = features.copy()
    daily.index = pd.date_range("2015-01-01", periods=len(daily), freq="D")
    with pytest.raises(ValueError, match="monthly"):
        validate_monthly_panel(daily)


def test_origin_panel_selects_fresh_columns_and_imputes_from_training_only():
    from models.paper_big import prepare_origin_panel

    target, features = _panel(72)
    origin = pd.Period("2020-12", freq="M")
    # Accepted stale edge: last value is two months before the origin.
    features.loc[origin - 1, "core"] = np.nan
    features.loc[origin, "core"] = np.nan
    features.loc[origin + 1 :, "core"] = 777.0
    # Too stale, even though it has a finite history.
    features.loc[origin - 3 :, "old"] = np.nan
    features.loc[origin - 4, "old"] = 3.0
    # A future-only field must never become eligible.
    features["future_only"] = np.nan
    features.loc[origin + 1 :, "future_only"] = 1e12

    prepared = prepare_origin_panel(
        target,
        features,
        origin=origin,
        horizon=1,
        stale_tolerance=2,
    )
    assert prepared.origin == origin
    assert prepared.x_now.index.tolist() == ["core", "exp12", "household_price_expect", "esi", "conf_business"]
    assert "old" not in prepared.selected_columns
    assert "future_only" not in prepared.selected_columns
    assert prepared.features.index.max() == origin
    assert prepared.X_train.index.max() == origin - 1
    expected = features.loc[prepared.X_train.index, "core"].mean()
    assert prepared.x_now["core"] == pytest.approx(expected)

    # Extreme post-origin values cannot affect either selection or imputation.
    changed = features.copy()
    changed.loc[origin + 1 :, "core"] = -1e15
    changed.loc[origin + 1 :, "exp12"] = -1e15
    changed.loc[origin + 1 :, "future_only"] = -1e15
    other = prepare_origin_panel(
        target,
        changed,
        origin=origin,
        horizon=1,
        stale_tolerance=2,
    )
    pd.testing.assert_frame_equal(prepared.X_train, other.X_train)
    pd.testing.assert_series_equal(prepared.x_now, other.x_now)
    pd.testing.assert_series_equal(prepared.feature_means, other.feature_means)


def test_origin_panel_rejects_nonfinite_values_and_invalid_horizon():
    from models.paper_big import prepare_origin_panel

    target, features = _panel(48)
    features.iloc[5, 0] = np.inf
    with pytest.raises(ValueError, match="finite"):
        prepare_origin_panel(target, features, origin=features.index[-1], horizon=1)
    target, features = _panel(48)
    with pytest.raises(ValueError, match="positive integer"):
        prepare_origin_panel(target, features, origin=features.index[-1], horizon=0)


def test_direct_tvwqrf_wrapper_uses_prepared_arrays_and_has_deterministic_fallback():
    from models.paper_big import direct_tvwqrf_forecast

    target, features = _panel(72)
    calls = {}

    class FakeQRF:
        def __init__(self, **options):
            calls["options"] = options

        def fit_predict(self, X_train, y_train, x_now):
            calls["shape"] = (X_train.shape, y_train.shape, x_now.shape)
            calls["last"] = x_now.copy()
            return {"point": float(np.mean(y_train) + 0.25), "quantiles": {}, "weights": {}}

    result = direct_tvwqrf_forecast(
        target,
        features,
        horizon=3,
        min_history=24,
        qrf_factory=FakeQRF,
    )
    assert result["status"] == "estimated"
    assert result["fallback_used"] is False
    # Direct h-step training pairs use feature t -> target t+h, so the
    # available labels are the last 69 observations (target[3:]) when the
    # origin is the final row.  Using target[:-3] here would silently reverse
    # the alignment and train on the wrong months.
    assert result["forecast"] == pytest.approx(target.iloc[3:].mean() + 0.25)
    assert calls["shape"][1] == (target.iloc[:-3].shape[0],)

    short_target, short_features = _panel(12)
    fallback = direct_tvwqrf_forecast(
        short_target,
        short_features,
        horizon=3,
        min_history=24,
        qrf_factory=FakeQRF,
    )
    assert fallback["status"] == "fallback_last_value"
    assert fallback["fallback_used"] is True
    assert fallback["forecast"] == short_target.iloc[-1]


def test_direct_bbim_wrapper_delegates_and_falls_back_without_enough_history():
    from models.paper_big import direct_bbim_forecast

    target, features = _panel(72)
    calls = {}

    def fake_bbim(y_hist, X, h, block_of, mono_of, **options):
        calls["index"] = X.index.copy()
        calls["h"] = h
        calls["y_lags"] = options.get("y_lags")
        calls["blocks"] = [block_of(column) for column in X.columns]
        calls["monotonic"] = [mono_of(column) for column in X.columns]
        return float(y_hist.iloc[:-h].mean() + 0.5)

    result = direct_bbim_forecast(
        target,
        features,
        horizon=3,
        min_history=24,
        y_lags=5,
        bbim_engine=fake_bbim,
    )
    assert result["status"] == "estimated"
    # The fake engine deliberately computes its own check from the history it
    # receives; the wrapper must pass the full origin history through unchanged.
    assert result["forecast"] == pytest.approx(target.iloc[:-3].mean() + 0.5)
    assert calls["index"].max() == target.index[-1]
    assert calls["h"] == 3
    assert calls["y_lags"] == 5
    assert all(value == 0 for value in calls["monotonic"])

    short_target, short_features = _panel(12)
    fallback = direct_bbim_forecast(
        short_target,
        short_features,
        horizon=3,
        min_history=24,
        bbim_engine=fake_bbim,
    )
    assert fallback["status"] == "fallback_last_value"
    assert fallback["forecast"] == short_target.iloc[-1]


def test_direct_design_can_match_paper_predictor_only_specification():
    """The CNB A6 comparison must not silently add target lags or a month dummy."""

    from models.paper_big import build_direct_supervised

    target, features = _panel(72)
    design = build_direct_supervised(
        target,
        features,
        horizon=3,
        y_lags=0,
        include_month=False,
    )
    assert list(design["feature_columns"]) == list(features.columns)
    assert design["X_train"].shape[1] == features.shape[1]
    assert "month" not in design["feature_columns"]
    assert not any(str(c).startswith("y_l") for c in design["feature_columns"])


def test_direct_design_rejects_invalid_include_month_flag():
    from models.paper_big import build_direct_supervised

    target, features = _panel(72)
    with pytest.raises(TypeError, match="include_month"):
        build_direct_supervised(target, features, horizon=1, include_month="no")


def test_leaf_weighted_qrf_fallback_has_tvw_point_and_distribution():
    from models.paper_big import SklearnLeafTVWQRF, direct_tvwqrf_forecast

    target, features = _panel(90)
    result = direct_tvwqrf_forecast(
        target,
        features,
        horizon=3,
        min_history=36,
        y_lags=0,
        include_month=False,
        qrf_factory=SklearnLeafTVWQRF,
        qrf_options={"n_estimators": 25, "min_samples_leaf": 3},
    )
    assert result["status"] == "estimated"
    assert result["engine"] == "SklearnLeafTVWQRF"
    assert np.isfinite(result["forecast"])
    assert "quantiles" in result["estimator_result"]
