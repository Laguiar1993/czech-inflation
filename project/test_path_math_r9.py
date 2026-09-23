"""R9 regression tests: dates, measurement units and visible fit failures."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from models.bvar import minnesota_bvar_forecast
from models.gap_model import _simulate, fit_forecast_gap, unemployment_gap
from models.trend_gap import TrendGap, fit_forecast, target_path


def _fixed_params(mod):
    params = mod.start_params.copy()
    params[mod.param_names.index("phi_raw")] = 0.0
    for i in range(mod.kx):
        params[mod.param_names.index(f"gamma_{i}")] = 1.0
    return params


def _fixed_fit(self, *args, **kwargs):
    return self.filter(_fixed_params(self))


def _history():
    index = pd.period_range("2000-01", periods=120, freq="M")
    return pd.Series(0.2, index=index)


def test_raw_month_three_driver_reaches_month_four_in_estimation(monkeypatch):
    captured = {}

    def fixed_fit(self, *args, **kwargs):
        result = _fixed_fit(self)
        captured["gaps"] = result.predicted_state[1, :self.nobs]
        return result

    monkeypatch.setattr(TrendGap, "fit", fixed_fit)
    y = _history()
    x = pd.DataFrame({"pulse": 0.0}, index=y.index)
    x.iloc[2, 0] = 1.0
    fit_forecast(y, range(1, 3), x_hist=x)
    assert captured["gaps"][3] == pytest.approx(1.0)
    assert captured["gaps"][4] == pytest.approx(0.0)


def test_known_last_driver_crosses_forecast_boundary(monkeypatch):
    monkeypatch.setattr(TrendGap, "fit", _fixed_fit)
    y = _history()
    x = pd.DataFrame({"x": 0.0}, index=y.index)
    base = fit_forecast(y, range(1, 4), x_hist=x)
    x.iloc[-1, 0] = 1.0
    changed = fit_forecast(y, range(1, 4), x_hist=x)
    assert changed["mm"][1] - base["mm"][1] == pytest.approx(1.0)
    assert changed["mm"][2] - base["mm"][2] == pytest.approx(0.0)


def test_explicit_future_driver_enters_one_month_after_reference_month(monkeypatch):
    monkeypatch.setattr(TrendGap, "fit", _fixed_fit)
    y = _history()
    x = pd.DataFrame({"x": 0.0}, index=y.index)
    future = pd.DataFrame({"x": [2.0, 0.0]}, index=pd.period_range(y.index[-1] + 1, periods=2, freq="M"))
    base = fit_forecast(y, range(1, 4), x_hist=x)
    scenario = fit_forecast(y, range(1, 4), x_hist=x, x_future=future)
    assert scenario["mm"][1] == pytest.approx(base["mm"][1])
    assert scenario["mm"][2] - base["mm"][2] == pytest.approx(2.0)


def test_changing_target_uses_destination_month():
    mu = np.array([0.4, 0.4, 0.2, 0.2, 0.2])
    mod = TrendGap(np.full(len(mu), np.nan), mu=mu)
    mod.initialize_known(np.array([mu[0], 0.0]), np.zeros((2, 2)))
    result = mod.filter(_fixed_params(mod))
    np.testing.assert_allclose(result.predicted_state[0, :len(mu)], mu)


def _gap_inputs():
    y = _history()
    index = y.index
    u = pd.Series(5.0 + 0.01 * np.arange(len(index)), index=index)
    fx = pd.Series(25.0 * 1.001 ** np.arange(len(index)), index=index)
    rr = pd.Series(0.1, index=index)
    x = pd.DataFrame({"ugap": unemployment_gap(u).shift(1),
                      "fx12_l3": (100.0 * (fx / fx.shift(12) - 1.0)).shift(3)}, index=index).fillna(0.0)
    t = index[-1] + 1
    rates = pd.Series(3.0, index=pd.period_range(t, periods=48, freq="M"))
    return dict(y_hist=y, X_hist=x, ugap_hist=u, fx_level=fx, rr_hist=rr,
                is_par={"c": 0.0, "sigma": 0.0}, rate_path=rates, pi12_last=2.0, rstar_last=0.0)


def test_gap_simulation_equals_filter_projection_through_target_change():
    data = _gap_inputs()
    t = data["y_hist"].index[-1] + 1
    seas = {month: 0.0 for month in range(1, 13)}
    level0, gap0, phi, rho, gamma = 0.3, 0.1, 0.0, 0.95, [1.0, 1.0]
    sim = _simulate(level0, gap0, phi, rho, gamma, seas, target_path, t,
                    data["ugap_hist"], data["fx_level"], data["rr_hist"], data["is_par"],
                    data["rate_path"], 2.0, 0.0)
    index = pd.period_range(t - 1, periods=len(sim["y"]) + 1, freq="M")
    x = np.column_stack([[sim["ugap"].get(m - 1, 0.0) for m in index],
                         [sim["fx12"].get(m - 3, 0.0) for m in index]])
    mod = TrendGap(np.full(len(index), np.nan), x=x, mu=target_path(index).values)
    mod.initialize_known(np.array([level0, gap0]), np.zeros((2, 2)))
    params = _fixed_params(mod)
    params[mod.param_names.index("rho_raw")] = np.log((rho - 0.90) / (0.999 - rho))
    result = mod.filter(params)
    np.testing.assert_allclose(result.predicted_state[:, 1:len(index)],
                               np.vstack([sim["mu"].values, sim["g"].values]), atol=1e-12)


@pytest.mark.parametrize("expectations", ["A", "M"])
def test_gap_handover_of_own_prediction_preserves_continuation(monkeypatch, expectations):
    monkeypatch.setattr(TrendGap, "fit", _fixed_fit)
    data = _gap_inputs()
    base = fit_forecast_gap(**data, expectations=expectations)
    t = data["y_hist"].index[-1] + 1
    pseudo = pd.Series([base["mm"][1], base["mm"][2]], index=pd.period_range(t, periods=2, freq="M"))
    handover = fit_forecast_gap(**data, expectations=expectations, pseudo_obs=pseudo)
    np.testing.assert_allclose(list(handover["mm"].values()), list(base["mm"].values()), atol=1e-10)


@pytest.mark.parametrize("h", [1, 3, 12])
def test_bvar_geometric_series_forecasts_exact_requested_month(h):
    panel = pd.DataFrame({"y": 1.01 ** np.arange(120)}, index=_history().index)
    forecast = minnesota_bvar_forecast(panel, "y", h, p=1, lambda1=1e6)
    assert forecast == pytest.approx(panel.y.iloc[-1] * 1.01 ** h, rel=1e-9)


@pytest.mark.parametrize("y_scale,x_scale", [(1.0, 100.0), (100.0, 1.0), (0.01, 100.0)])
def test_bvar_forecast_is_invariant_to_predictor_and_target_units(y_scale, x_scale):
    rng = np.random.default_rng(10)
    x = rng.normal(size=240)
    y = np.r_[0.0, 0.8 * x[:-1]] + rng.normal(scale=0.1, size=240)
    panel = pd.DataFrame({"y": y, "x": x}, index=pd.period_range("2000-01", periods=240, freq="M"))
    base = minnesota_bvar_forecast(panel, "y", 1)
    transformed = panel * pd.Series({"y": y_scale, "x": x_scale})
    actual = minnesota_bvar_forecast(transformed, "y", 1) / y_scale
    assert actual == pytest.approx(base, abs=1e-10)


@pytest.mark.parametrize("model", ["trend_gap", "bvar", "gap"])
def test_missing_calendar_month_is_rejected(model):
    y = _history().drop(_history().index[50])
    with pytest.raises(ValueError, match="contiguous"):
        if model == "trend_gap":
            fit_forecast(y, range(1, 2))
        elif model == "bvar":
            minnesota_bvar_forecast(y.to_frame("y"), "y", 1)
        else:
            data = _gap_inputs()
            data["y_hist"] = y
            fit_forecast_gap(**data)


@pytest.mark.parametrize("failure", ["raises", "nonconverged"])
def test_failed_optimization_has_deterministic_visible_fallback(monkeypatch, failure):
    calls = []

    def failed_fit(self, *args, **kwargs):
        calls.append(kwargs.get("method"))
        if failure == "raises":
            raise RuntimeError("injected optimizer failure")
        result = self.filter(self.start_params)
        result.mle_retvals = {"converged": False}
        return result

    monkeypatch.setattr(TrendGap, "fit", failed_fit)
    result = fit_forecast(_history(), range(1, 4), anchored=True)
    assert calls == ["lbfgs", "powell"]
    assert result["converged"] is False
    assert result["fallback_used"] is True
    assert result["fit_diagnostics"]["status"] == "fallback_start_params"
    assert len(result["fit_diagnostics"]["attempts"]) == 2
    assert np.isfinite(list(result["mm"].values())).all()


def test_optimizer_retry_success_is_reported(monkeypatch):
    calls = []

    def retry_fit(self, *args, **kwargs):
        calls.append(kwargs["method"])
        result = self.filter(self.start_params)
        result.mle_retvals = {"converged": len(calls) == 2}
        return result

    monkeypatch.setattr(TrendGap, "fit", retry_fit)
    result = fit_forecast(_history(), range(1, 2))
    assert calls == ["lbfgs", "powell"]
    assert result["converged"] is True
    assert result["fallback_used"] is False
    assert result["fit_diagnostics"]["status"] == "converged_retry"


def test_gap_known_last_driver_reaches_first_forecast(monkeypatch):
    monkeypatch.setattr(TrendGap, "fit", _fixed_fit)
    data = _gap_inputs()
    base = fit_forecast_gap(**data)
    data["X_hist"].iloc[-1, 0] += 1.0
    changed = fit_forecast_gap(**data)
    assert changed["mm"][1] - base["mm"][1] == pytest.approx(1.0)


def test_missing_outcome_inside_contiguous_index_is_not_compressed():
    y = _history()
    y.iloc[50] = np.nan
    with pytest.raises(ValueError, match="contiguous"):
        fit_forecast(y, range(1, 2))


def test_gap_fallback_is_visible_and_finite(monkeypatch):
    def failed_fit(self, *args, **kwargs):
        raise RuntimeError("injected optimizer failure")

    monkeypatch.setattr(TrendGap, "fit", failed_fit)
    result = fit_forecast_gap(**_gap_inputs())
    assert result["converged"] is False
    assert result["fallback_used"] is True
    assert result["fit_diagnostics"]["status"] == "fallback_start_params"
    assert np.isfinite(list(result["mm"].values())).all()


def test_nonfinite_converged_optimizer_is_rejected(monkeypatch):
    def invalid_fit(self, *args, **kwargs):
        return SimpleNamespace(params=np.full(len(self.start_params), np.nan), llf=np.nan,
                               filtered_state=np.full((2, self.nobs), np.nan), mle_retvals={"converged": True})

    monkeypatch.setattr(TrendGap, "fit", invalid_fit)
    result = fit_forecast(_history(), range(1, 2))
    assert result["fallback_used"] is True
    assert all(not attempt["finite"] for attempt in result["fit_diagnostics"]["attempts"])


def test_gap_unemployment_missing_month_cannot_compress_trailing_mean(monkeypatch):
    monkeypatch.setattr(TrendGap, "fit", _fixed_fit)
    data = _gap_inputs()
    data["ugap_hist"].iloc[50] = np.nan
    with pytest.raises(ValueError, match="contiguous"):
        fit_forecast_gap(**data)


def test_bvar_constant_difference_scale_fallback_preserves_units():
    index = pd.period_range("2000-01", periods=240, freq="M")
    panel = pd.DataFrame({"y": np.sin(np.arange(240) / 9), "x": np.arange(240) / 10}, index=index)
    base = minnesota_bvar_forecast(panel, "y", 1)
    scaled = panel.copy()
    scaled["x"] *= 100.0
    assert minnesota_bvar_forecast(scaled, "y", 1) == pytest.approx(base, abs=1e-9)


def test_bvar_prior_limit_and_diagnostics():
    panel = _history().to_frame("y")
    result = minnesota_bvar_forecast(panel, "y", 3, lambda1=1e-8, delta={"y": 1.0}, return_diagnostics=True)
    assert result["forecast"] == pytest.approx(panel.y.iloc[-1], abs=1e-10)
    assert result["status"] == "estimated"
    short = minnesota_bvar_forecast(panel.iloc[:5], "y", 3, return_diagnostics=True)
    assert short["forecast"] == panel.y.iloc[4]
    assert short["fallback_used"] is True


def test_unconverged_expectations_use_declared_geometric_fallback(monkeypatch):
    monkeypatch.setattr(TrendGap, "fit", _fixed_fit)
    data = _gap_inputs()
    data["is_par"]["sigma"] = 10.0  # deliberately strong feedback prevents a fixed point within 60 iterations
    base = fit_forecast_gap(**data, expectations="A")
    result = fit_forecast_gap(**data, expectations="M", w=0.0)
    assert result["fixed_point"]["converged"] is False
    assert result["fixed_point"]["fallback"] == "geometric_A"
    assert result["fallback_used"] is True
    assert result["converged"] is False
    np.testing.assert_allclose(list(result["mm"].values()), list(base["mm"].values()), atol=1e-12)


def test_gap_missing_driver_uses_same_declared_zero_in_fit_and_projection(monkeypatch):
    monkeypatch.setattr(TrendGap, "fit", _fixed_fit)
    data = _gap_inputs()
    data["X_hist"].iloc[-1, 0] = 0.0
    zero = fit_forecast_gap(**data)
    data["X_hist"].iloc[-1, 0] = np.nan
    missing = fit_forecast_gap(**data)
    assert missing["converged"] is True
    np.testing.assert_allclose(list(missing["mm"].values()), list(zero["mm"].values()), atol=1e-12)


@pytest.mark.parametrize("invalid", [np.inf, -np.inf])
def test_trend_rejects_infinite_extended_driver_before_estimation(monkeypatch, invalid):
    monkeypatch.setattr(TrendGap, "fit", lambda *a, **kw: pytest.fail("must validate before fitting"))
    y = _history()
    x = pd.DataFrame({"x": 0.0}, index=pd.period_range(y.index[0], y.index[-1]+1, freq="M"))
    x.iloc[-1, 0] = invalid
    with pytest.raises(ValueError, match="infinite"):
        fit_forecast(y, range(1, 4), x_hist=x)


@pytest.mark.parametrize("name", ["X_hist", "ugap_hist", "fx_level", "rr_hist", "rate_path"])
def test_gap_rejects_infinite_inputs_before_estimation(monkeypatch, name):
    monkeypatch.setattr(TrendGap, "fit", lambda *a, **kw: pytest.fail("must validate before fitting"))
    data = _gap_inputs()
    if name == "X_hist":
        data[name].iloc[-1, 0] = np.inf
    else:
        data[name].iloc[-1] = np.inf
    with pytest.raises(ValueError, match="infinite"):
        fit_forecast_gap(**data)


@pytest.mark.parametrize("model", ["trend", "gap"])
def test_finite_inputs_that_overflow_projection_do_not_claim_success(monkeypatch, model):
    monkeypatch.setattr(TrendGap, "fit", _fixed_fit)
    if model == "trend":
        y = _history()
        x = pd.DataFrame({"one": 0.0, "two": 0.0},
                         index=pd.period_range(y.index[0], y.index[-1]+1, freq="M"))
        x.iloc[-1] = [1e308, 1e308]
        result = fit_forecast(y, range(1, 4), x_hist=x)
    else:
        data = _gap_inputs()
        data["X_hist"].loc[data["y_hist"].index[-1]+1] = [1e308, 1e308]
        result = fit_forecast_gap(**data)
    assert result["converged"] is False
    assert result["projection_diagnostics"]["status"] == "nonfinite"
    assert all(np.isnan(value) for value in result["mm"].values())
