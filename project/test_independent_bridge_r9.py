"""Independent bridge inputs and conservative CNB quarter matching."""
import importlib

import numpy as np
import pandas as pd
import pytest


def api():
    try:
        return importlib.import_module("independent_bridge_experiment")
    except ModuleNotFoundError:
        pytest.fail("Independent bridge has not been implemented")


def frames():
    from forecast_independent import fixture_frames
    return fixture_frames()


def test_expectation_poisoning_cannot_change_any_bridge_horizon():
    f = frames(); t = pd.Period("2021-03", "M")
    a = api().forecast_bridge(f, t, "2021-04-12T23:59:00+02:00", h0=.25)
    g = {k: v.copy() for k, v in f.items()}
    for key in ("features", "food_features"):
        for col in ("exp12", "exp36", "household_exp", "exp12_x_state", "esi"):
            g[key][col] = np.arange(len(g[key])) * 100000.0
    b = api().forecast_bridge(g, t, "2021-04-12T23:59:00+02:00", h0=.25)
    assert a["path"] == pytest.approx(b["path"])
    assert not set(a["diagnostics"]["core_columns"]) & {"exp12", "exp36", "household_exp", "exp12_x_state", "esi"}


def test_future_outcomes_cannot_change_bridge_and_contributions_add():
    f = frames(); t = pd.Period("2021-03", "M")
    a = api().forecast_bridge(f, t, "2021-04-12T23:59:00+02:00", h0=.25)
    for key in ("headline", "components", "core", "regulated", "alcohol"):
        f[key].loc[f[key].index >= t] = 1000.
    for key in ("features", "food_features"):
        f[key].loc[f[key].index > t] = 1000.
    b = api().forecast_bridge(f, t, "2021-04-12T23:59:00+02:00", h0=.25)
    assert a["path"] == pytest.approx(b["path"])
    assert a["path"][0] == .25
    for h in range(1, 13):
        assert sum(a["contributions"][h].values()) == pytest.approx(a["path"][h])
        assert sum(a["weights"][h].values()) == pytest.approx(1.0)


def test_future_basket_is_not_imported_before_its_publication():
    import cz_struct as s
    current = {"core": .5, "food": .2, "fuel": .05, "alc": .1, "administered": .15}
    future = {**current, "core": .4, "food": .3}
    got = api().future_weights({2024: current, 2026: future}, current,
                              pd.Period("2026-01", "M"), pd.Timestamp("2025-12-01"))
    assert got == current


def test_short_food_history_is_reported_as_failure_and_fallback():
    result = api().forecast_bridge(frames(), "2019-02", "2019-03-10T23:59:00+01:00", h0=.25)
    assert result["diagnostics"]["status"] == "failed_nonfinite"
    assert result["diagnostics"]["fallback_used"] is True
    detail = result["diagnostics"]["horizon_details"]
    assert detail[1]["nonfinite_blocks"] == ["food"]
    assert detail[1]["fallback_used"] is True
    assert detail[1]["status"] == "failed_nonfinite"
    assert detail[4]["status"] == "estimated"
    assert detail[4]["fallback_used"] is False
    assert np.isnan(result["path"][1])
    assert np.isfinite(result["path"][4])


@pytest.mark.parametrize("key", ["core", "food_features"])
def test_deleted_interior_month_is_rejected_before_positional_horizon_shift(key):
    f = frames()
    f[key] = f[key].drop(pd.Period("2020-06", "M"))
    with pytest.raises(ValueError, match="contiguous monthly"):
        api().forecast_bridge(f, "2021-03", "2021-04-12T23:59:00+02:00", h0=.25)


def test_irrelevant_future_index_gap_cannot_change_bridge():
    f = frames()
    a = api().forecast_bridge(f, "2021-03", "2021-04-12T23:59:00+02:00", h0=.25)
    f["core"] = f["core"].drop(pd.Period("2022-06", "M"))
    f["food_features"] = f["food_features"].drop(pd.Period("2022-06", "M"))
    b = api().forecast_bridge(f, "2021-03", "2021-04-12T23:59:00+02:00", h0=.25)
    assert a["path"] == pytest.approx(b["path"])


def test_cnb_matching_uses_prior_origin_and_never_substitutes_future_actuals():
    points = []
    for origin, clock, predicted in [("2024-01", "2024-02-01T23:00:00Z", 2.),
                                      ("2024-02", "2024-02-10T12:00:00Z", 9.)]:
        for h in range(13):
            points.append(dict(origin=origin, as_of_utc=clock, model="A", h=h,
                target=str(pd.Period(origin, "M") + h), yy_exante=predicted))
    cnb = pd.DataFrame([dict(report_date="2024-02-10", quarter="2024Q1", value=3., is_forecast=True)])
    actual = pd.Series(1., index=pd.period_range("2022-01", "2024-12", freq="M"))
    a = api().match_cnb_quarters(pd.DataFrame(points), cnb, actual, ["A"])
    actual.loc["2024-01":] = 20.
    b = api().match_cnb_quarters(pd.DataFrame(points), cnb, actual, ["A"])
    assert a.loc[a.model == "A", "forecast"].iloc[0] == 2.
    assert b.loc[b.model == "A", "forecast"].iloc[0] == 2.
    assert a.loc[a.model == "A", "origin"].iloc[0] == "2024-01"


def test_cnb_complete_quarter_includes_known_preceding_month_and_rejects_partial_end():
    t = pd.Period("2024-02", "M")
    points = pd.DataFrame([dict(origin=str(t), as_of_utc="2024-03-01T23:00:00Z",
        model="A", h=h, target=str(t+h), yy_exante=3.) for h in range(2)])
    cnb = pd.DataFrame([dict(report_date="2024-03-05", quarter=q, value=3., is_forecast=True)
                        for q in ("2024Q1", "2024Q2")])
    actual = pd.Series(0., index=pd.period_range("2022-01", "2024-12", freq="M"))
    got = api().match_cnb_quarters(points, cnb, actual, ["A"])
    model = got[got.model == "A"].set_index("quarter")
    assert model.loc["2024Q1", "forecast"] == pytest.approx(2.)
    assert np.isnan(model.loc["2024Q2", "forecast"])
