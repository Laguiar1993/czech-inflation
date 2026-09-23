"""TVW-QRF engine, panel helpers and path mapping for the CNB WP 9/2026 lane."""
import numpy as np
import pandas as pd
import pytest

from models import paper_tvwqrf as engine
from tools.paper_replication import build_paper_panel as bp


def test_kernel_weights_follow_equation_4():
    w = engine.kernel_weights(12, 6.0)
    assert w.sum() == pytest.approx(1.0)
    assert w[-1] == pytest.approx(2 * w[-7])   # six-month half-life
    assert np.all(np.diff(w) > 0)              # the most recent pair weighs most


@pytest.mark.parametrize("scheme", list(engine.SCHEMES))
def test_weights_sum_to_one_inside_bounds_and_do_not_worsen_the_fit(scheme):
    quants, lower, upper = engine.SCHEMES[scheme]
    rng = np.random.default_rng(1)
    Q = np.sort(rng.normal(size=(12, len(quants))), axis=1)
    y = Q[:, -1] + 0.1 * rng.normal(size=12)
    omega = engine.kernel_weights(12)
    w = engine.solve_weights(Q, y, lower, upper, omega)
    assert w.sum() == pytest.approx(1.0, abs=1e-8)
    assert np.all(w >= np.asarray(lower) - 1e-8) and np.all(w <= np.asarray(upper) + 1e-8)
    start = engine._feasible_start(np.asarray(lower, float), np.asarray(upper, float))

    def loss(v):
        return float(np.sum(omega * (y - Q @ v) ** 2))

    assert loss(w) <= loss(start) + 1e-12


def test_fit_forecast_returns_every_point_model_inside_the_quantiles():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(80, 5))
    y = X[:, 0] + 0.1 * rng.normal(size=80)
    out = engine.fit_forecast(X, y, X[-1], forest={"n_estimators": 50})
    assert set(out["points"]) == set(engine.POINT_MODELS)
    values = [out["quantiles"][q] for q in engine.ALL_QUANTILES]
    assert values == sorted(values)
    tvw3 = [out["quantiles"][q] for q in engine.SCHEMES["TVW3"][0]]
    assert min(tvw3) - 1e-12 <= out["points"]["TVW3"] <= max(tvw3) + 1e-12


def test_fit_forecast_needs_a_validation_history():
    with pytest.raises(ValueError):
        engine.fit_forecast(np.zeros((20, 2)), np.zeros(20), np.zeros(2))


def test_autoregressions_reproduce_a_known_process():
    rng = np.random.default_rng(3)
    y = np.zeros(3000)
    for t in range(3, 3000):
        y[t] = 0.2 + 0.5 * y[t - 1] - 0.2 * y[t - 2] + 0.1 * y[t - 3] + 0.01 * rng.normal()
    s = pd.Series(y[100:])
    expected = 0.2 + 0.5 * y[-1] - 0.2 * y[-2] + 0.1 * y[-3]
    assert engine.ar_iterated(s, [1, 2])[1] == pytest.approx(expected, abs=0.01)
    assert engine.ar_direct(s, 1) == pytest.approx(expected, abs=0.01)
    assert engine.random_walk(s, [3])[3] == y[-1]


def test_diebold_mariano_favours_the_smaller_errors():
    rng = np.random.default_rng(4)
    stat, p = engine.diebold_mariano(rng.normal(scale=2.0, size=200), rng.normal(scale=1.0, size=200), 3)
    assert stat < 0 and p < 0.01


def test_signed_difference_requires_the_declared_row_policy():
    s = pd.Series([1.0, -2.0, 3.0], index=pd.period_range("2020-01", periods=3, freq="M"))
    out, note = bp.transform(s, 2, number=25)
    assert "fixed" in note and "row 25" in note and out.iloc[2] == 5.0
    positive, note = bp.transform(s.abs(), 2, number=61)
    assert note == "T2" and positive.iloc[1] == pytest.approx(np.log(2.0))


def test_factor_imputation_fills_gaps_and_keeps_observed_values():
    rng = np.random.default_rng(5)
    index = pd.period_range("2002-05", periods=120, freq="M")
    factors = rng.normal(size=(120, 2))
    panel = pd.DataFrame(factors @ rng.normal(size=(12, 2)).T + 0.1 * rng.normal(size=(120, 12)),
                         index=index, columns=[f"c{i}" for i in range(12)])
    holed = panel.copy()
    holed.iloc[:40, 0] = np.nan
    filled, _ = bp.factor_impute(holed, factors=2)
    assert filled.notna().all().all()
    pd.testing.assert_frame_equal(filled.iloc[40:], holed.iloc[40:], check_exact=False)
    assert np.corrcoef(filled.iloc[:40, 0], panel.iloc[:40, 0])[0, 1] > 0.9


def test_realtime_alignment_uses_only_published_periods():
    index = pd.period_range("2020-01", periods=4, freq="M")
    values = pd.Series([1.0, 2.0, 3.0, 4.0], index=index)
    available = pd.Series(pd.to_datetime(["2020-02-20", "2020-03-20", "2020-04-20", "2020-05-20"]), index=index)
    eves = pd.Series(pd.to_datetime(["2020-02-19", "2020-03-20", "2020-06-01"]),
                     index=pd.period_range("2020-01", periods=3, freq="M"))
    out = bp._latest_available(values, available, eves)
    assert np.isnan(out.iloc[0]) and out.iloc[1] == 2.0 and out.iloc[2] == 4.0


def test_release_eve_is_the_day_before_the_next_months_first_release(tmp_path):
    calendar = tmp_path / "calendar.csv"
    pd.DataFrame({"target_month": ["2020-02"], "first_release_dt": ["2020-03-10"]}).to_csv(calendar, index=False)
    eves = bp.release_eves(calendar, pd.period_range("2020-01", periods=2, freq="M"))
    assert eves.iloc[0] == pd.Timestamp("2020-03-09")
    assert eves.iloc[1] == pd.Timestamp("2020-04-09")   # rule when the calendar has no row


def test_paper_training_pairs_end_at_the_edge():
    import paper_tvwqrf_experiment as experiment

    index = pd.period_range("2002-05", periods=150, freq="M")
    panel = pd.DataFrame(np.arange(300.0).reshape(150, 2), index=index, columns=["a6_11", "a6_12"])
    target = pd.Series(np.arange(150.0), index=index)
    edge = index[100]
    X, y, x_now, rows, _ = experiment.training_arrays(panel, target, edge, 6, "paper")
    assert rows.max() == edge - 6
    assert np.array_equal(x_now, panel.loc[edge].to_numpy())
    assert np.array_equal(y, target.reindex(rows + 6).to_numpy())


def test_feature_columns_leave_out_listed_rows():
    import paper_tvwqrf_experiment as experiment

    columns = ["a6_11", "a6_14", "a6_15", "a6_16", "a6_29"]
    assert experiment.feature_columns(columns, "full", [14, 15, 16]) == ["a6_11", "a6_29"]
    assert experiment.feature_columns(columns, "independent") == ["a6_11", "a6_14", "a6_15", "a6_16"]


def test_policies_follow_table_a6_kinds():
    import paper_tvwqrf_experiment as experiment

    columns = ["a6_11", "a6_29", "a6_70"]   # hard, survey, expectation
    assert experiment.policy_columns(columns, "full") == columns
    assert experiment.policy_columns(columns, "sentiment") == ["a6_11", "a6_29"]
    assert experiment.policy_columns(columns, "independent") == ["a6_11"]


def test_path_mapping_moves_origin_and_horizon_by_one(tmp_path):
    import paper_tvwqrf_path as path

    pd.DataFrame({"edge": ["2019-01", "2019-01"], "horizon": [1, 13], "model": ["TVW3", "TVW3"],
                  "forecast": [0.1, 0.2]}).to_csv(tmp_path / "forecasts.csv", index=False)
    paths = path.load_paths(tmp_path, "FULL")
    assert paths.origin.astype(str).tolist() == ["2019-02", "2019-02"]
    assert paths.h.tolist() == [0, 12]
    assert paths.target.astype(str).tolist() == ["2019-02", "2020-02"]
    assert paths.model.unique().tolist() == ["TVWQRF_TVW3_FULL"]


def test_seasonal_naive_uses_the_last_five_same_months():
    import paper_tvwqrf_path as path

    index = pd.period_range("2015-01", periods=72, freq="M")
    history = pd.Series(np.where(index.month == 1, 1.0, 0.1), index=index)
    history[index[-12]] = 2.0
    assert path._naive_mm(history, pd.Period("2021-01", freq="M")) == pytest.approx(1.2)


def test_combination_weights_the_bridge_and_keeps_missing_months():
    import paper_tvwqrf_combination as combo

    bridge = pd.DataFrame({"origin": ["2019-02"] * 3, "h": [0, 1, 2], "bridge_mm": [0.2, np.nan, 0.4]})
    paths = pd.DataFrame({"origin": pd.PeriodIndex(["2019-02"] * 3, freq="M"), "h": [0, 1, 2],
                          "target": pd.PeriodIndex(["2019-02", "2019-03", "2019-04"], freq="M"),
                          "model": "TVWQRF_TVW3_FULL", "mm_forecast": [0.0, 0.1, 0.0]})
    out = combo.combine_paths(bridge, paths, 0.5, "FULL")
    assert out.mm_forecast.iloc[0] == pytest.approx(0.1)
    assert np.isnan(out.mm_forecast.iloc[1])
    assert out.mm_forecast.iloc[2] == pytest.approx(0.2)
    assert out.target.astype(str).tolist() == ["2019-02", "2019-03", "2019-04"]
    assert out.model.unique().tolist() == ["COMBO50_BRIDGE_TVW3_FULL"]
    with pytest.raises(ValueError):
        combo.combine_paths(bridge, paths, 1.5, "FULL")


def test_paper_training_arrays_can_add_the_edge_month():
    import paper_tvwqrf_experiment as experiment

    index = pd.period_range("2002-05", periods=150, freq="M")
    panel = pd.DataFrame(np.arange(300.0).reshape(150, 2), index=index, columns=["a6_11", "a6_12"])
    target = pd.Series(np.arange(150.0), index=index)
    edge = index[100]
    X, y, x_now, rows, columns = experiment.training_arrays(panel, target, edge, 6, "paper", include_month=True)
    assert columns == ["a6_11", "a6_12", "month"]
    assert np.array_equal(X[:, -1], rows.month.to_numpy(float))
    assert x_now[-1] == edge.month and X.shape[1] == x_now.shape[0] == 3


def test_realtime_training_arrays_pass_the_month_switch(monkeypatch):
    import models.paper_big as big
    import paper_tvwqrf_experiment as experiment

    seen = {}

    def fake(target, features, horizon, **kwargs):
        seen.update(kwargs)
        prepared = type("Prepared", (), {"train_index": features.index[:3]})()
        return {"X_train": features.iloc[:3], "y_train": target.iloc[:3], "x_now": features.iloc[-1],
                "prepared": prepared, "feature_columns": list(features.columns)}

    monkeypatch.setattr(big, "build_direct_supervised", fake)
    index = pd.period_range("2002-05", periods=40, freq="M")
    panel = pd.DataFrame({"a6_11": np.arange(40.0)}, index=index)
    target = pd.Series(np.arange(40.0), index=index)
    experiment.training_arrays(panel, target, index[-1], 1, "realtime", include_month=True)
    assert seen["include_month"] is True and seen["y_lags"] == 0
    experiment.training_arrays(panel, target, index[-1], 1, "realtime")
    assert seen["include_month"] is False


def test_x13_policy_keeps_existing_decisions_and_honours_do_not_readjust():
    assert bp.needs_x13("NSA; one-sided X-13 required (paper)", "quarterly")
    assert not bp.needs_x13("unknown", "quarterly")
    assert not bp.needs_x13("SA y/y rate published by the CNB; do not re-adjust", "quarterly")
    assert not bp.needs_x13("Eurostat SA; do not re-adjust", "level")
    assert bp.needs_x13("market price; X-13 per paper, little seasonality expected", "level")
    assert not bp.needs_x13("year-on-year change; adjustment not applicable", "level")
    assert not bp.needs_x13("NSA index; one-sided X-13 required (paper)", "components")


def test_overrides_load_monthly_and_quarterly_rows(tmp_path):
    path = tmp_path / "overrides.csv"
    pd.DataFrame({"a6_number": [25, 25, 17], "component": ["", "", ""],
                  "source_id": ["arad:SVEVZM4", "arad:SVEVZM4", "arad:MLULNULXXADJYOYPECQ"],
                  "period": ["2002-05", "2002-06", "2002Q2"], "value": [1.0, 2.0, 3.0], "value_kind": ["level"] * 3,
                  "frequency": ["M", "M", "Q"], "available_from_assumed": ["2002-07-10", "2002-08-09", "2002-09-13"],
                  "seasonal_adjustment": [None, None, "SA; do not re-adjust"]}).to_csv(path, index=False)
    raws, policies = bp.load_overrides(path)
    assert raws[25].kind == "level" and raws[25].values.index.freqstr == "M" and raws[25].values.iloc[1] == 2.0
    assert raws[17].kind == "quarterly" and str(raws[17].values.index[0]) == "2002Q2"
    assert policies == {17: "SA; do not re-adjust"}


def test_benchmarks_with_information_ending_h_months_before_the_edge():
    import paper_tvwqrf_experiment as experiment

    index = pd.period_range("2002-05", periods=120, freq="M")
    target = pd.Series(np.sin(np.arange(120.0)), index=index)
    edge = index[100]
    rows = pd.DataFrame(experiment.benchmark_rows(target, [edge], [3], tmh=True))
    assert rows[rows.model.eq("RW_TMH")].forecast.iloc[0] == target[edge - 3]
    assert rows[rows.model.eq("RW")].forecast.iloc[0] == target[edge]
    assert {"RW", "AR3", "RW_TMH", "AR3_TMH"} <= set(rows.model)
    assert experiment.PAPER_BENCHMARKS["RW_TMH"] == experiment.PAPER_BENCHMARKS["RW"]
