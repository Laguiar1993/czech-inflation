"""Chronology and numerical contracts for the pure R15 residual engine."""
import copy
import importlib
import importlib.util

import numpy as np
import pandas as pd
import pytest


def engine():
    assert importlib.util.find_spec("models.core_trend_residual_r15") is not None, "R15 engine is missing"
    return importlib.import_module("models.core_trend_residual_r15")


def inputs():
    index = pd.period_range("2000-01", "2021-12", freq="M")
    q = .3 + .12 * np.sin(np.arange(len(index)) * 2 * np.pi / 12) + .08 * np.cos(np.arange(len(index)) / 7)
    core = pd.Series(100 * np.expm1(q / 100), index=index)
    dates = pd.Series([(p + 1).to_timestamp() + pd.Timedelta(days=19, hours=9) for p in index], index=index)
    return core, dates


def state_fixture():
    core, dates = inputs()
    origin = pd.Period("2015-06", "M")
    clock = pd.Timestamp("2015-07-09 23:59")
    return core, dates, origin, clock


def test_state_future_poison_does_not_change_saved_filter():
    e = engine()
    core, dates, origin, clock = state_fixture()
    saved = e.state_at(core, dates, origin, clock)
    core.loc[origin:] = np.inf
    dates.loc[origin:] = pd.Timestamp("1900-01-01")
    assert e.state_at(core, dates, origin, clock) == saved
    assert saved["history_end"] == "2015-05"
    assert saved["n_history"] == 185
    assert sum(saved["seasonal"].values()) == pytest.approx(0., abs=1e-12)


def test_state_matches_origin_seasonality_and_kalman_ar_steps():
    e = engine()
    core, dates, origin, clock = state_fixture()
    saved = e.state_at(core, dates, origin, clock)
    q = 100 * np.log1p(core.loc[:origin - 1] / 100)
    seasonal = (q - q.rolling(12).mean()).dropna().tail(120).groupby(lambda p: p.month).mean()
    seasonal -= seasonal.mean()
    adjusted = q - [seasonal[p.month] for p in q.index]
    assert saved["seasonal"] == pytest.approx(seasonal.to_dict())
    f = np.diag([1., .8])
    h = np.ones(2)
    for name, variance in e.FILTERS.items():
        mean = np.array([adjusted.iloc[:12].mean(), 0.])
        covariance = np.eye(2)
        for observation in adjusted.iloc[12:]:
            mean = f @ mean
            covariance = f @ covariance @ f.T + np.diag([variance, .2])
            gain = covariance @ h / (h @ covariance @ h + 1.)
            mean += gain * (observation - h @ mean)
            covariance -= np.outer(gain, h) @ covariance
        assert saved["filter_states"][name]["mu"] == pytest.approx(mean[0])
        assert saved["filter_states"][name]["cycle"] == pytest.approx(mean[1])
        for horizon in range(1, 13):
            expected = mean[0] + .8 ** (horizon + 1) * mean[1] + seasonal[(origin + horizon).month]
            assert saved["forecasts_log"][name][horizon] == pytest.approx(expected)
        wrong_h1 = mean[0] + .8 * mean[1] + seasonal[(origin + 1).month]
        assert abs(saved["forecasts_log"][name][1] - wrong_h1) > 1e-5
    assert saved["x"] == pytest.approx(dict(core1=adjusted.iloc[-1], core3=adjusted.tail(3).mean(),
        core12=adjusted.tail(12).mean(), core_acceleration=adjusted.tail(3).mean() - adjusted.tail(12).mean(),
        midtrend=saved["filter_states"]["mid"]["mu"], midcycle=saved["filter_states"]["mid"]["cycle"]))


@pytest.mark.parametrize("problem", ["short", "gap", "missing", "unreleased", "invalid_growth"])
def test_state_requires_contiguous_published_valid_history(problem):
    e = engine()
    core, dates, origin, clock = state_fixture()
    if problem == "short":
        core = core.loc[origin - 35:]
    elif problem == "gap":
        core = core.drop(origin - 18)
    elif problem == "missing":
        core.loc[origin - 18] = np.nan
    elif problem == "unreleased":
        dates.loc[origin - 1] = clock + pd.Timedelta(seconds=1)
    else:
        core.loc[origin - 4] = -100.
    assert e.state_at(core, dates, origin, clock) is None


def test_state_handles_timezone_clock_and_audits_max_release():
    e = engine()
    core, dates, origin, clock = state_fixture()
    dates.loc[origin - 10] = clock
    plain = e.state_at(core, dates, origin, clock)
    aware_dates = dates.dt.tz_localize("Europe/Prague")
    aware = e.state_at(core, aware_dates, origin, clock.tz_localize("Europe/Prague").tz_convert("UTC"))
    assert aware == plain
    assert pd.Timestamp(plain["last_release"]) == clock


def test_state_has_no_policy_target_clipping():
    e = engine()
    core, dates, origin, clock = state_fixture()
    core[:] = 1.5
    saved = e.state_at(core, dates, origin, clock)
    assert e.band_path(saved, dict.fromkeys(range(4), 0.))[12] == pytest.approx(1.5)


@pytest.mark.parametrize("source", ["core", "available"])
def test_state_rejects_duplicate_month_keys(source):
    e = engine()
    core, dates, origin, clock = state_fixture()
    if source == "core":
        core = pd.concat([core, core.iloc[:1]])
    else:
        dates = pd.concat([dates, dates.iloc[:1]])
    with pytest.raises(ValueError, match="unique"):
        e.state_at(core, dates, origin, clock)


def test_residual_label_uses_saved_origin_baseline_not_reestimated_seasonality():
    e = engine()
    core, dates, origin, clock = state_fixture()
    r = pd.Period("2014-01", "M")
    state = e.state_at(core, dates, r, "2014-02-09")
    original = copy.deepcopy(state)
    y, audit = e.residual_labels(core, dates, {r: state}, origin, clock, (1, 3))
    actual = np.mean([100 * np.log1p(core[r + h] / 100) for h in range(1, 4)])
    baseline = np.mean([state["forecasts_log"]["mid"][h] for h in range(1, 4)])
    assert y[r] == pytest.approx(actual - baseline)
    assert audit.iloc[0].actual == pytest.approx(y[r])
    assert audit.iloc[0].last_target == "2014-04"
    core.loc[:r] = 87.
    core.loc[origin:] = np.inf
    state["seasonal"] = dict.fromkeys(range(1, 13), 9e10)
    assert e.residual_labels(core, dates, {r: state}, origin, clock, (1, 3))[0][r] == y[r]
    assert original["forecasts_log"] == state["forecasts_log"]


@pytest.mark.parametrize("block", ["partial_release", "missing_release", "last_target", "missing_value"])
def test_residual_label_requires_every_target_published_before_origin(block):
    e = engine()
    core, dates, origin, clock = state_fixture()
    r = origin - 13
    state = e.state_at(core, dates, r, (r + 1).to_timestamp() + pd.Timedelta(days=8))
    assert len(e.residual_labels(core, dates, {r: state}, origin, clock, (10, 12))[0]) == 1
    if block == "partial_release":
        dates.loc[r + 11] = clock + pd.Timedelta(seconds=1)
    elif block == "missing_release":
        dates.loc[r + 10] = pd.NaT
    elif block == "missing_value":
        core.loc[r + 10] = np.nan
    else:
        origin = r + 12
    y, audit = e.residual_labels(core, dates, {r: state}, origin, clock, (10, 12))
    assert y.empty and audit.empty


def training(n=60):
    ix = pd.period_range("2000-01", periods=n, freq="M")
    x = pd.DataFrame({"varying": np.linspace(-1, 1, n), "constant": 3., "absent": np.nan}, index=ix)
    y = pd.Series(.3 + .25 * x.varying, index=ix)
    now = pd.Series({"varying": .6, "constant": 200., "absent": 9e9})
    return x, y, now


@pytest.mark.parametrize("kind", ["enet", "rf"])
def test_fit_uses_training_only_imputation_scaling_and_last_120(kind):
    e = engine()
    x, y, now = training(145)
    x.iloc[30, 0] = np.nan
    x.iloc[0, 0] = np.inf  # discarded before preprocessing
    pred, info = e.fit_residual(x, y, now, kind)
    window = x.iloc[-120:]["varying"]
    mean = window.mean()
    assert info["status"] == "estimated"
    assert info["n_train"] == 120
    assert info["columns"] == ["varying"]
    assert info["means"]["varying"] == pytest.approx(mean)
    assert info["scales"]["varying"] == pytest.approx(window.fillna(mean).std(ddof=0))
    future = x.iloc[[-1]].copy()
    future.index = pd.period_range(x.index[-1] + 1, periods=1, freq="M")
    future[:] = np.inf
    again = e.fit_residual(pd.concat([x, future]), y, now, kind)
    assert again == (pred, info)


def test_enet_constant_is_penalized_and_target_shrinks_towards_zero():
    e = engine()
    x, y, now = training()
    x = x.drop(columns="varying")
    y[:] = 2.
    pred, info = e.fit_residual(x, y, now, "enet", "a0.1_l0.2")
    expected = 2. * (1. - .1 * .2) / (1. + .1 * (1. - .2))
    assert pred == pytest.approx(expected)
    assert pred < y.mean()
    assert info["target_rms"] == pytest.approx(2.)
    assert info["intercept"] == pytest.approx(expected)
    assert info["columns"] == []
    assert info["converged"] is True
    assert info["fit_intercept"] is False
    zero, zero_info = e.fit_residual(x, y * 0, now, "enet")
    assert zero == 0.
    assert zero_info["converged"] is True


@pytest.mark.parametrize("kind", ["enet", "rf"])
def test_missing_current_features_are_train_mean_imputed(kind):
    e = engine()
    x, y, now = training()
    missing = pd.Series(dtype=float)
    mean_row = now.copy()
    mean_row["varying"] = x.varying.mean()
    a, ia = e.fit_residual(x, y, missing, kind)
    b, ib = e.fit_residual(x, y, mean_row, kind)
    assert a == pytest.approx(b)
    assert ia["status"] == ib["status"] == "estimated"


@pytest.mark.parametrize("kind", ["enet", "rf"])
def test_insufficient_training_returns_no_forecast(kind):
    e = engine()
    x, y, now = training(47)
    pred, info = e.fit_residual(x, y, now, kind)
    assert np.isnan(pred)
    assert info["status"] == "insufficient_history"
    assert info["n_train"] == 47


@pytest.mark.parametrize("kind", ["enet", "rf"])
def test_model_fit_is_deterministic_and_targets_align_by_key(kind):
    e = engine()
    x, y, now = training()
    first = e.fit_residual(x, y, now, kind)
    second = e.fit_residual(x.sample(frac=1., random_state=7), y.iloc[::-1], now, kind)
    assert first == second


@pytest.mark.parametrize("problem", ["x_rows", "y_rows", "x_columns", "now_keys", "x_inf", "y_inf", "now_inf"])
def test_fit_rejects_ambiguous_keys_and_infinite_inputs(problem):
    e = engine()
    x, y, now = training()
    if problem == "x_rows":
        x = pd.concat([x, x.iloc[:1]])
    elif problem == "y_rows":
        y = pd.concat([y, y.iloc[:1]])
    elif problem == "x_columns":
        x.columns = ["same", "same", "third"]
    elif problem == "now_keys":
        now = pd.concat([now, now.iloc[:1]])
    elif problem == "x_inf":
        x.iloc[-1, 0] = np.inf
    elif problem == "y_inf":
        y.iloc[-1] = np.inf
    else:
        now.iloc[0] = np.inf
    with pytest.raises(ValueError):
        e.fit_residual(x, y, now, "enet")


def test_fit_rejects_month_keys_aliased_as_period_and_string():
    e = engine()
    x, y, now = training()
    duplicate = x.iloc[:1].copy()
    duplicate.index = [str(x.index[0])]
    x = pd.concat([x, duplicate])
    with pytest.raises(ValueError, match="keys"):
        e.fit_residual(x, y, now, "enet")


def test_nonconverged_enet_never_returns_its_partial_forecast(monkeypatch):
    """Force the real solver's iteration limit to exercise its warning path."""
    import sklearn.linear_model
    e = engine()
    x, y, now = training()
    x["correlated"] = x.varying ** 2 + .9 * x.varying
    now["correlated"] = .3
    real_solver = sklearn.linear_model.ElasticNet

    def one_iteration_solver(**kwargs):
        kwargs["max_iter"] = 1
        return real_solver(**kwargs)

    monkeypatch.setattr(sklearn.linear_model, "ElasticNet", one_iteration_solver)
    prediction, diagnostics = e.fit_residual(x, y, now, "enet", "a0.01_l0.2")
    assert np.isnan(prediction)
    assert diagnostics["status"] == "nonconvergence"
    assert diagnostics["converged"] is False


def test_forest_without_retained_features_remains_an_intercept_model():
    e = engine()
    x, y, now = training()
    x = x.drop(columns="varying")
    y[:] = -.75
    prediction, diagnostics = e.fit_residual(x, y, now, "rf")
    assert prediction == pytest.approx(-.75)
    assert diagnostics["columns"] == []


def selection_fixture(n=40):
    origins = pd.period_range("2010-01", periods=n, freq="M")
    configs = ("first", "default", "last")
    predictions = pd.DataFrame([dict(origin=str(r), config=c, prediction=0.) for r in origins for c in configs])
    outcomes = pd.DataFrame(dict(origin=origins.astype(str), actual=0., last_target=(origins + 3).astype(str),
        available_from=[(r + 4).to_timestamp() + pd.Timedelta(days=19) for r in origins]))
    return predictions, outcomes, configs


def test_selection_uses_common_last36_matured_origins_and_default_tie():
    e = engine()
    p, y, configs = selection_fixture()
    result = e.choose_config(p, y, "2014-01", "2014-02-09", configs, "default")
    assert result["config"] == "default"
    assert result["n_validation"] == 36
    assert result["validation_origins"] == list(y.origin.iloc[-36:])
    assert result["losses"] == dict.fromkeys(configs, 0.)
    p.loc[p.config == "default", "prediction"] = 1.
    result = e.choose_config(p, y, "2014-01", "2014-02-09", configs, "default")
    assert result["config"] == "first"
    assert result["reason"] == "fixed_tie_order"


def test_selection_poison_future_prediction_outcome_and_unreleased_band():
    e = engine()
    p, y, configs = selection_fixture()
    baseline = e.choose_config(p, y, "2014-01", "2014-02-09", configs, "default")
    extras = pd.DataFrame([
        dict(origin="2013-11", actual=9e99, last_target="2014-02", available_from="2013-12-01"),
        dict(origin="2013-09", actual=9e99, last_target="2013-12", available_from="2014-02-10"),
        dict(origin="2014-02", actual=9e99, last_target="2013-12", available_from="2013-12-01"),
    ])
    ep = pd.DataFrame([dict(origin=r, config=c, prediction=9e99 if c == "last" else -9e99)
        for r in extras.origin for c in configs])
    assert e.choose_config(pd.concat([p, ep]), pd.concat([y, extras]), "2014-01", "2014-02-09", configs, "default") == baseline


def test_selection_requires24_common_finite_rows_and_records_release():
    e = engine()
    p, y, configs = selection_fixture(24)
    p.loc[(p.config == "last") & (p.origin == "2010-01"), "prediction"] = np.nan
    result = e.choose_config(p, y, "2014-01", "2014-02-09", configs, "default")
    assert result["config"] == "default"
    assert result["reason"] == "insufficient_validation"
    assert result["n_validation"] == 23
    assert pd.Timestamp(result["validation_last_release"]) == y.available_from.max()


@pytest.mark.parametrize("table", ["predictions", "outcomes"])
def test_selection_rejects_duplicate_normalized_origins_even_future(table):
    e = engine()
    p, y, configs = selection_fixture()
    if table == "predictions":
        duplicate = p.iloc[:1].copy()
        duplicate["origin"] = pd.Period("2010-01", "M")
        p = pd.concat([p, duplicate])
    else:
        duplicate = y.iloc[:1].copy()
        duplicate["origin"] = pd.Period("2010-01", "M")
        y = pd.concat([y, duplicate])
    with pytest.raises(ValueError, match="Duplicate"):
        e.choose_config(p, y, "2000-01", "2000-01-01", configs, "default")


def test_band_path_reconstructs_exact_log_corrections_and_missing_band():
    e = engine()
    core, dates, origin, clock = state_fixture()
    state = e.state_at(core, dates, origin, clock)
    correction = {0: .03, 1: -.07, 3: .4}
    path = e.band_path(state, correction, "fast")
    for b, (lo, hi) in enumerate(e.BANDS):
        for horizon in range(lo, hi + 1):
            if b not in correction:
                assert np.isnan(path[horizon])
            else:
                assert 100 * np.log1p(path[horizon] / 100) == pytest.approx(state["forecasts_log"]["fast"][horizon] + correction[b])
