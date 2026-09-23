"""Independent numerical and chronology contracts for the bounded R16 engine."""
import copy
import importlib
import importlib.util

import numpy as np
import pandas as pd
import pytest


def engine():
    assert importlib.util.find_spec("models.core_slope_transmission_r16") is not None, "R16 engine is missing"
    return importlib.import_module("models.core_slope_transmission_r16")


def slope_inputs():
    index = pd.period_range("2000-01", periods=90, freq="M")
    history = pd.Series(.35 + .07 * np.cos(np.arange(len(index)) / 4), index=index)
    seasonal = {month: .03 * np.sin(2 * np.pi * month / 12) for month in range(1, 13)}
    return history, index[-1] + 1, seasonal


def test_slope_states_match_independent_kalman_and_matrix_power_forecasts():
    e = engine()
    history, origin, seasonal = slope_inputs()
    result = e.slope_state(history, origin, seasonal)
    configs = {"p80_q001": (.8, .001), "p80_q010": (.8, .01),
               "p95_q001": (.95, .001), "p95_q010": (.95, .01)}
    assert e.SLOPE_CONFIGS == tuple(configs)
    assert e.SLOPE_DEFAULT == "p80_q001"
    assert result["history_end"] == str(origin - 1)
    assert result["n_history"] == len(history)
    observation = np.array([1., 0., 1.])
    for name, (phi, variance) in configs.items():
        transition = np.array([[1., phi, 0.], [0., phi, 0.], [0., 0., .8]])
        mean = np.array([history.iloc[:12].mean(), 0., 0.])
        covariance = np.diag([1., .01, 1.])
        for value in history.iloc[12:]:
            prior_mean = transition @ mean
            prior_covariance = transition @ covariance @ transition.T + np.diag([.05, variance, .2])
            gain = prior_covariance @ observation / (observation @ prior_covariance @ observation + 1.)
            mean = prior_mean + gain * (value - observation @ prior_mean)
            # Joseph form independently checks covariance symmetry/roundoff.
            residual = np.eye(3) - np.outer(gain, observation)
            covariance = residual @ prior_covariance @ residual.T + np.outer(gain, gain)
        saved = result["filter_states"][name]
        assert [saved["level"], saved["slope"], saved["cycle"]] == pytest.approx(mean)
        np.testing.assert_allclose(saved["covariance"], covariance, atol=1e-14)
        for h in range(1, 13):
            expected = observation @ np.linalg.matrix_power(transition, h + 1) @ mean + seasonal[(origin + h).month]
            assert result["forecasts_log"][name][h] == pytest.approx(expected, abs=1e-13)
        wrong_h1 = observation @ transition @ mean + seasonal[(origin + 1).month]
        assert abs(result["forecasts_log"][name][1] - wrong_h1) > 1e-5


def test_opposing_slope_and_cycle_can_produce_an_interior_reversal():
    e = engine()
    path = e.forecast_slope(np.array([.3, .05, .45]), .95, "2020-01", dict.fromkeys(range(1, 13), 0.))
    values = np.array(list(path.values()))
    changes = np.diff(values)
    assert changes[0] < 0 < changes[-1]
    assert 0 < values.argmin() < len(values) - 1


def test_slope_uses_only_history_before_origin_and_normalizes_seasonal_strings():
    e = engine()
    history, origin, seasonal = slope_inputs()
    original = history.copy()
    baseline = e.slope_state(history, origin, seasonal)
    future = pd.Series(np.inf, index=pd.period_range(origin, periods=12, freq="M"))
    poisoned = pd.concat([history, future]).iloc[::-1]
    assert e.slope_state(poisoned, origin, {str(k): v for k, v in seasonal.items()}) == baseline
    pd.testing.assert_series_equal(history, original)


@pytest.mark.parametrize("problem", ["short", "gap", "missing", "infinite", "end"])
def test_slope_returns_none_for_unusable_history(problem):
    e = engine()
    history, origin, seasonal = slope_inputs()
    if problem == "short":
        history = history.iloc[-35:]
    elif problem == "gap":
        history = history.drop(history.index[-10])
    elif problem == "missing":
        history.iloc[-10] = np.nan
    elif problem == "infinite":
        history.iloc[-10] = np.inf
    else:
        history = history.iloc[:-1]
    assert e.slope_state(history, origin, seasonal) is None


@pytest.mark.parametrize("problem", ["duplicate", "nonmonthly", "season_missing", "season_duplicate", "season_inf"])
def test_slope_rejects_bad_calendar_or_seasonal_keys(problem):
    e = engine()
    history, origin, seasonal = slope_inputs()
    if problem == "duplicate":
        history = pd.concat([history, history.iloc[:1]])
    elif problem == "nonmonthly":
        history.index = history.index.to_timestamp()
    elif problem == "season_missing":
        seasonal.pop(12)
    elif problem == "season_duplicate":
        seasonal["1"] = 0.
    else:
        seasonal[1] = np.inf
    with pytest.raises(ValueError):
        e.slope_state(history, origin, seasonal)


def training(n=145):
    index = pd.period_range("2000-01", periods=n, freq="M")
    sequence = np.arange(n)
    x = pd.DataFrame({"varying": np.linspace(-2, 1, n), "curve": np.cos(sequence / 7),
                      "constant": 3., "absent": np.nan}, index=index)
    y = pd.Series(1.2 + .4 * x.varying - .25 * x.curve, index=index)
    now = pd.Series({"varying": .3, "curve": -.2, "constant": 9e9, "absent": 9e9})
    return x, y, now


@pytest.mark.parametrize("penalty", [.1, 1., 10.])
def test_ridge_matches_independent_sklearn_and_exact_saved_reconstruction(penalty):
    from sklearn.linear_model import Ridge

    e = engine()
    x, y, now = training()
    x.iloc[30, 0] = np.nan
    x.iloc[44, 1] = np.nan
    x.iloc[0, 0] = np.inf  # outside the final 120 labelled months
    prediction, info = e.ridge_fit(x, y, now, penalty)
    window = x.iloc[-120:][["varying", "curve"]]
    means = window.mean()
    scales = window.fillna(means).std(ddof=0)
    standardized = (window.fillna(means) - means) / scales
    design = np.column_stack([np.ones(120), standardized])
    model = Ridge(alpha=120 * penalty, fit_intercept=False, solver="svd").fit(design, y.iloc[-120:])
    current = (now.reindex(means.index) - means) / scales
    expected = model.predict(np.r_[1., current].reshape(1, -1))[0]
    assert prediction == pytest.approx(expected, abs=1e-12)
    assert info["status"] == "estimated" and info["converged"] is True
    assert info["n_train"] == 120
    assert info["columns"] == ["varying", "curve"]
    assert info["means"] == pytest.approx(means.to_dict())
    assert info["scales"] == pytest.approx(scales.to_dict())
    assert info["coefficients"] == pytest.approx(dict(zip(means.index, model.coef_[1:])))
    assert info["intercept"] == pytest.approx(model.coef_[0])
    assert info["lambda_value"] == penalty
    assert info["train_first"] == str(window.index[0])
    assert info["train_last"] == str(window.index[-1])
    reconstructed = info["intercept"] + sum(info["coefficients"][c] *
        (now[c] - info["means"][c]) / info["scales"][c] for c in info["columns"])
    assert prediction == pytest.approx(reconstructed, abs=1e-14)


def test_ridge_ignores_unlabelled_future_poison_and_aligns_unsorted_keys():
    e = engine()
    x, y, now = training()
    baseline = e.ridge_fit(x, y, now)
    future = pd.DataFrame(np.inf, index=pd.period_range(x.index[-1] + 1, periods=12, freq="M"), columns=x.columns)
    poisoned = pd.concat([x, future]).sample(frac=1., random_state=7)
    assert e.ridge_fit(poisoned, y.iloc[::-1], now) == baseline
    assert e.LAMBDAS == (.1, 1., 10.) and e.LAMBDA_DEFAULT == 1.


def test_ridge_penalizes_explicit_constant_without_target_standardization():
    e = engine()
    x, y, now = training(60)
    x = x[["constant", "absent"]]
    y[:] = 4.
    prediction, info = e.ridge_fit(x, y, now, 1.)
    assert prediction == pytest.approx(2.)
    assert info["columns"] == [] and info["coefficients"] == {}
    assert info["intercept"] == pytest.approx(2.)
    assert e.ridge_fit(x, y * 0., now, .1)[0] == 0.


def test_ridge_imputes_missing_ordinary_current_predictors_from_training_only():
    e = engine()
    x, y, now = training(60)
    x.iloc[10:20, 0] = np.nan
    expected = now.copy()
    expected["varying"] = x.varying.mean()
    missing = now.drop("varying")
    assert e.ridge_fit(x, y, missing) == e.ridge_fit(x, y, expected)


def test_ridge_insufficient_matching_finite_targets_has_explicit_status():
    e = engine()
    x, y, now = training(60)
    y.iloc[:13] = np.nan
    prediction, info = e.ridge_fit(x, y, now)
    assert np.isnan(prediction)
    assert info["n_train"] == 47 and info["status"] == "insufficient_history"
    assert info["converged"] is False
    assert info["train_first"] == str(y.index[13])
    assert info["train_last"] == str(y.index[-1])


@pytest.mark.parametrize("problem", ["x_duplicate", "y_duplicate", "columns", "now_keys", "mixed_keys",
                                     "nonmonthly", "x_inf", "y_inf", "now_inf", "lambda"])
def test_ridge_rejects_invalid_keys_infinities_and_unknown_penalty(problem):
    e = engine()
    x, y, now = training(60)
    penalty = 1.
    if problem == "x_duplicate":
        x = pd.concat([x, x.iloc[:1]])
    elif problem == "y_duplicate":
        y = pd.concat([y, y.iloc[:1]])
    elif problem == "columns":
        x.columns = ["a", "a", "b", "c"]
    elif problem == "now_keys":
        now = pd.concat([now, now.iloc[:1]])
    elif problem == "mixed_keys":
        duplicate = x.iloc[:1].copy()
        duplicate.index = [str(x.index[0])]
        x = pd.concat([x, duplicate])
    elif problem == "nonmonthly":
        x.index = x.index.to_timestamp()
    elif problem == "x_inf":
        x.iloc[-1, 0] = np.inf
    elif problem == "y_inf":
        y.iloc[-1] = np.inf
    elif problem == "now_inf":
        now.iloc[0] = np.inf
    else:
        penalty = .01
    with pytest.raises(ValueError):
        e.ridge_fit(x, y, now, penalty)


def release_inputs():
    index = pd.period_range("2000-01", "2016-12", freq="M")
    values = pd.Series(.2 + np.arange(len(index)) / 100., index=index)
    dates = pd.Series([(p + 1).to_timestamp() + pd.Timedelta(days=19, hours=9) for p in index], index=index)
    return values, dates


@pytest.mark.parametrize("band", [(1, 3), (4, 6), (7, 9), (10, 12)])
def test_released_bands_preserve_log_units_and_audit_latest_release(band):
    e = engine()
    values, dates = release_inputs()
    r, t, clock = pd.Period("2010-01", "M"), pd.Period("2015-01", "M"), pd.Timestamp("2015-02-09 09:00")
    dates[r + band[0]] = clock
    y, audit = e.released_band_means(values, dates, [r], t, clock, band)
    expected = values.loc[r + band[0]:r + band[1]].mean()
    assert y.index.equals(pd.PeriodIndex([r], freq="M"))
    assert y[r] == pytest.approx(expected)
    assert audit.columns.tolist() == ["origin", "last_target", "available_from", "actual"]
    assert audit.iloc[0].to_dict() == dict(origin=str(r), last_target=str(r + band[1]),
        available_from=str(clock), actual=pytest.approx(expected))
    aware_dates = dates.dt.tz_localize("Europe/Prague").dt.tz_convert("UTC")
    aware = e.released_band_means(values, aware_dates, [r], t, clock.tz_localize("Europe/Prague").tz_convert("UTC"), band)
    pd.testing.assert_series_equal(y, aware[0])
    pd.testing.assert_frame_equal(audit, aware[1])


@pytest.mark.parametrize("problem", ["future_target", "delayed_last", "delayed_early", "missing_date", "gap", "nonfinite"])
def test_released_bands_require_every_target_before_origin_and_released(problem):
    e = engine()
    values, dates = release_inputs()
    t, clock = pd.Period("2015-01", "M"), pd.Timestamp("2015-02-09 09:00")
    r = t - 13
    if problem == "future_target":
        r = t - 12
    elif problem == "delayed_last":
        dates[r + 12] = clock + pd.Timedelta(seconds=1)
    elif problem == "delayed_early":
        dates[r + 10] = clock + pd.Timedelta(seconds=1)
    elif problem == "missing_date":
        dates[r + 11] = pd.NaT
    elif problem == "gap":
        values = values.drop(r + 11)
    else:
        values[r + 11] = np.inf
    y, audit = e.released_band_means(values, dates, [r], t, clock, (10, 12))
    assert y.empty and audit.empty


def test_released_bands_ignore_later_poison_and_do_not_mutate_sources():
    e = engine()
    values, dates = release_inputs()
    t, clock = pd.Period("2015-01", "M"), "2015-02-09"
    origins = pd.period_range("2013-01", "2016-12", freq="M")
    baseline = e.released_band_means(values, dates, origins, t, clock, (1, 3))
    values.loc[t:] = np.inf
    dates.loc[t:] = pd.Timestamp("1900-01-01")
    before = values.copy()
    actual = e.released_band_means(values, dates, origins, t, clock, (1, 3))
    pd.testing.assert_series_equal(actual[0], baseline[0])
    pd.testing.assert_frame_equal(actual[1], baseline[1])
    pd.testing.assert_series_equal(values, before)


@pytest.mark.parametrize("problem", ["values_duplicate", "dates_duplicate", "origin_duplicate", "annual_origin", "calendar", "band"])
def test_released_bands_reject_ambiguous_calendars(problem):
    e = engine()
    values, dates = release_inputs()
    origins, band = [pd.Period("2010-01", "M")], (1, 3)
    if problem == "values_duplicate":
        values = pd.concat([values, values.iloc[:1]])
    elif problem == "dates_duplicate":
        dates = pd.concat([dates, dates.iloc[:1]])
    elif problem == "origin_duplicate":
        origins.append("2010-01")
    elif problem == "annual_origin":
        origins = [pd.Period("2010", "Y")]
    elif problem == "calendar":
        dates.index = dates.index.to_timestamp()
    else:
        band = (1, 12)
    with pytest.raises(ValueError):
        e.released_band_means(values, dates, origins, "2015-01", "2015-02-09", band)


def saved_paths(n=40):
    configs = ("p80_q001", "p80_q010", "p95_q001", "p95_q010")
    values, dates = release_inputs()
    origins = pd.period_range("2010-01", periods=n, freq="M")
    paths = {r: {c: {h: float(values[r + h]) for h in range(1, 13)} for c in configs} for r in origins}
    return paths, values, dates


def test_slope_selection_is_on_whole_path_not_band_or_average_forecast():
    e = engine()
    paths, values, dates = saved_paths()
    for r, configs in paths.items():
        for h in range(1, 13):
            configs["p80_q001"][h] += 0. if h <= 3 else 2.
            configs["p80_q010"][h] += 1.
            configs["p95_q001"][h] += 4. * (-1.) ** h  # zero mean error still poor path
            configs["p95_q010"][h] += 3.
    result = e.choose_slope(paths, values, dates, "2015-01", "2015-02-09")
    assert result["config"] == "p80_q010"
    assert result["reason"] == "minimum_prior_mse"
    assert result["losses"] == pytest.approx(dict(p80_q001=3., p80_q010=1., p95_q001=16., p95_q010=9.))
    assert result["n_validation"] == 36
    assert result["validation_origins"] == [str(r) for r in list(paths)[-36:]]
    assert pd.Timestamp(result["validation_last_release"]) == dates[max(paths) + 12]


def test_slope_selection_defaults_until_24_common_finite_paths():
    e = engine()
    paths, values, dates = saved_paths(24)
    paths[min(paths)]["p95_q010"][5] = np.nan
    result = e.choose_slope(paths, values, dates, "2015-01", "2015-02-09")
    assert result["config"] == e.SLOPE_DEFAULT
    assert result["reason"] == "insufficient_validation"
    assert result["n_validation"] == 23 and result["losses"] == {}
    assert result["validation_origins"] == [str(r) for r in list(paths)[1:]]


def test_slope_selection_ties_prefer_default_then_declared_order():
    e = engine()
    paths, values, dates = saved_paths()
    result = e.choose_slope(paths, values, dates, "2015-01", "2015-02-09")
    assert result["config"] == e.SLOPE_DEFAULT and result["reason"] == "fixed_tie_order"
    for r, configs in paths.items():
        for h in range(1, 13):
            configs[e.SLOPE_DEFAULT][h] += 2.
            configs["p80_q010"][h] += 1. + 1e-12
            configs["p95_q001"][h] += 1.
            configs["p95_q010"][h] += 3.
    result = e.choose_slope(paths, values, dates, "2015-01", "2015-02-09")
    assert result["config"] == "p80_q010" and result["reason"] == "fixed_tie_order"


def test_slope_selection_excludes_unreleased_and_current_targets_and_later_poison():
    e = engine()
    paths, values, dates = saved_paths()
    baseline = e.choose_slope(paths, values, dates, "2015-01", "2015-02-09")
    for r in [pd.Period("2013-12", "M"), pd.Period("2014-01", "M"), pd.Period("2015-01", "M")]:
        paths[r] = {c: {h: 9e99 for h in range(1, 13)} for c in e.SLOPE_CONFIGS}
    dates[pd.Period("2014-12", "M")] = pd.Timestamp("2015-02-10")
    values.loc[pd.Period("2015-01", "M"):] = np.inf
    frozen = copy.deepcopy(paths)
    assert e.choose_slope(paths, values, dates, "2015-01", "2015-02-09") == baseline
    assert paths == frozen


def test_slope_selection_normalizes_timezone_and_rejects_duplicate_origin_aliases():
    e = engine()
    paths, values, dates = saved_paths()
    plain = e.choose_slope(paths, values, dates, "2015-01", "2015-02-09 09:00")
    aware = e.choose_slope(paths, values, dates.dt.tz_localize("Europe/Prague").dt.tz_convert("UTC"),
                           "2015-01", pd.Timestamp("2015-02-09 08:00", tz="UTC"))
    assert aware == plain
    paths[str(min(paths))] = copy.deepcopy(paths[min(paths)])
    with pytest.raises(ValueError, match="Duplicate"):
        e.choose_slope(paths, values, dates, "2000-01", "2000-01-01")
