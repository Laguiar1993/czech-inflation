"""Point-in-time drivers, direct targets, and exact path compounding."""
import importlib
import hashlib
import json

import numpy as np
import pandas as pd
import pytest


def api():
    try:
        return importlib.import_module("models.path_inputs")
    except ModuleNotFoundError:
        pytest.fail("Corrected point-in-time path inputs are not implemented")


def fixtures(tmp_path):
    idx = pd.period_range("2015-01", "2021-12", freq="M")
    y = pd.Series(np.sin(np.arange(len(idx))) / 10, index=idx)
    fx = pd.Series(20.0 + np.arange(len(idx)) / 10, index=idx)
    records = []
    for p in pd.period_range("2015-01", "2020-01", freq="M"):
        for when, value in [("2020-03-01T23:00:00Z", 3 + (p.ordinal % 7) / 10),
                            ("2021-03-01T23:00:00Z", 9.0)]:
            records.append(dict(series="unemployment_sa", reference_period=str(p),
                available_from=when, value=value, source="https://csu.gov.cz/file.xlsx",
                sha256=hashlib.sha256(str(value).encode()).hexdigest(),
                adjustment="sa", vintage_kind="historical_release"))
    path = tmp_path / "u.csv"; pd.DataFrame(records).to_csv(path, index=False)
    return y, fx, path


def test_future_headline_fx_and_vintage_revisions_do_not_change_origin_inputs(tmp_path):
    y, fx, path = fixtures(tmp_path)
    t = pd.Period("2020-02", "M")
    a = api().prepare_origin(y, fx, t, "2020-03-10T22:59:00Z", path)
    y2 = y.copy(); y2.loc[t:] = 999
    fx2 = fx.copy(); fx2.loc[t + 1:] = 999
    f = pd.read_csv(path); f.loc[f.available_from.str.startswith("2021"), "value"] = 999
    f.to_csv(path, index=False)
    b = api().prepare_origin(y2, fx2, t, "2020-03-10T22:59:00Z", path)
    pd.testing.assert_series_equal(a["headline"], b["headline"])
    pd.testing.assert_frame_equal(a["drivers"], b["drivers"])
    assert a["headline"].index[-1] == t - 1
    assert a["metadata"]["unemployment_end"] == "2020-01"


def test_transition_source_rows_apply_unemployment_lag_once_and_fx_lag_three(tmp_path):
    y, fx, path = fixtures(tmp_path)
    t = pd.Period("2020-02", "M")
    result = api().prepare_origin(y, fx, t, "2020-03-10T22:59:00Z", path)
    u = result["unemployment"]
    # State transition at source t-1 predicts destination t.
    assert result["drivers"].loc[t - 1, "un_d"] == pytest.approx(u.loc[t - 1] - u.loc[t - 2])
    assert result["drivers"].loc[t - 1, "fx12_l3"] == pytest.approx(100 * (fx.loc[t - 3] / fx.loc[t - 15] - 1))
    assert result["drivers"].loc[t, "un_d"] == 0.0  # February U is unpublished.


def test_known_fx_lags_propagate_beyond_headline_edge_before_flat_level_scenario(tmp_path):
    y, fx, path = fixtures(tmp_path)
    t = pd.Period("2020-02", "M")
    r = api().prepare_origin(y, fx, t, "2020-03-10T22:59:00Z", path)
    # Destination t+3 uses the already-known February FX level.
    assert r["drivers"].loc[t + 2, "fx12_l3"] == pytest.approx(100 * (fx.loc[t] / fx.loc[t - 12] - 1))
    # Destination t+4 assumes March FX level equals the last observed February.
    assert r["drivers"].loc[t + 3, "fx12_l3"] == pytest.approx(100 * (fx.loc[t] / fx.loc[t - 11] - 1))


def test_interior_headline_gap_fails_instead_of_compressing_calendar(tmp_path):
    y, fx, path = fixtures(tmp_path); y.iloc[30] = np.nan
    with pytest.raises(ValueError, match="contiguous|finite|missing"):
        api().prepare_origin(y, fx, pd.Period("2020-02", "M"), "2020-03-10T22:59:00Z", path)


def test_direct_training_uses_labels_released_by_origin_and_h_plus_one_alignment(tmp_path):
    y, fx, path = fixtures(tmp_path)
    t = pd.Period("2020-02", "M")
    r = api().prepare_origin(y, fx, t, "2020-03-10T22:59:00Z", path)
    x, target, now = api().direct_training_data(r["headline"], r["drivers"], t, 3)
    assert target.index[-1] == t - 4
    assert target.iloc[-1] == y.loc[t - 1]
    assert now["headline_l1"] == y.loc[t - 1]
    assert now["headline_l12"] == y.loc[t - 12]
    assert now["un_d"] == r["drivers"].loc[t - 1, "un_d"]


def test_compound_exact_twelve_month_window_and_h0_substitution():
    t = pd.Period("2020-01", "M")
    history = pd.Series(1.0, index=pd.period_range("2018-01", t - 1, freq="M"))
    path = {h: 2.0 for h in range(13)}
    conditional = api().compound_path(history, path, t, 3, h0=3.0)
    assert conditional == pytest.approx(100 * (1.01 ** 8 * 1.03 * 1.02 ** 3 - 1))
    # h12's rolling window no longer contains the nowcast month.
    assert api().compound_path(history, path, t, 12, h0=999) == pytest.approx(100 * (1.02 ** 12 - 1))


def test_compound_missing_intermediate_forecast_does_not_fill_from_actuals():
    t = pd.Period("2020-01", "M")
    history = pd.Series(1.0, index=pd.period_range("2018-01", t - 1, freq="M"))
    assert np.isnan(api().compound_path(history, {0: 2., 1: 2., 3: 2.}, t, 3, h0=3.))


def experiment():
    try:
        return importlib.import_module("independent_path_experiment")
    except ModuleNotFoundError:
        pytest.fail("The independent path harness is not implemented")


def test_model_horizon_is_one_beyond_path_horizon():
    got = experiment().model_path({"mm": {h: float(h) for h in range(1, 14)}})
    assert got[0] == 1.
    assert got[3] == 4.
    assert got[12] == 13.


def test_common_scoring_keeps_failures_visible_and_scores_identical_rows():
    rows = []
    for origin, a, b in [("2020-01", 1., 2.), ("2020-02", 2., np.nan), ("2020-03", 3., 4.)]:
        for model, prediction in [("A", a), ("B", b)]:
            rows.append(dict(origin=origin, h=1, target=str(pd.Period(origin, "M") + 1),
                model=model, mm_forecast=prediction, mm_actual=0., yy_exante=prediction,
                yy_conditional=prediction, yy_actual=0., status="estimated" if np.isfinite(prediction) else "failed"))
    got = experiment().common_metrics(pd.DataFrame(rows), ["A", "B"], "test", "all")
    exante = got.loc[got["case"] == "exante"]
    assert exante["n_common"].tolist() == [2, 2]
    assert exante["n_available_targets"].tolist() == [3, 3]
    assert exante["n_own_forecasts"].tolist() == [3, 2]
    assert exante.loc[exante.model == "A", "yy_rmse"].iloc[0] == pytest.approx(np.sqrt(5))


def test_public_origin_forecast_accepts_explicit_h0_and_preserves_failure_status(tmp_path):
    y, fx, path = fixtures(tmp_path)
    assert hasattr(experiment(), "forecast_origin"), "A reusable explicit-input origin API is required"
    result = experiment().forecast_origin(y, fx, "2020-02", "2020-03-10T22:59:00Z", h0=.7,
                                          vintage_path=path, long_only=True)
    assert result["paths"]["TARGET_ML"][0] == .7
    assert result["paths"]["NAIVE"][0] == .7
    assert result["diagnostics"]["TARGET_ML"]["status"] == "insufficient_history"
    assert result["inputs"]["headline_end"] == "2020-01"


def test_input_hash_covers_exact_values_calendar_and_missingness():
    idx = pd.period_range("2020-01", periods=3, freq="M")
    y = pd.Series([.1, .2, .3], index=idx)
    fx = pd.Series([25., 26., 27.], index=idx)
    baseline = experiment()._data_fingerprints(y, fx)
    assert baseline == experiment()._data_fingerprints(y.copy(), fx.copy())
    for name in ("headline", "fx"):
        a, b = y.copy(), fx.copy()
        changed = a if name == "headline" else b
        changed.iloc[1] = np.nextafter(changed.iloc[1], np.inf)
        assert baseline != experiment()._data_fingerprints(a, b)
    shifted = fx.copy(); shifted.index = shifted.index + 1
    assert baseline != experiment()._data_fingerprints(y, shifted)
    missing = y.copy(); missing.iloc[1] = np.nan
    assert baseline != experiment()._data_fingerprints(missing, fx)


@pytest.mark.parametrize("changed", ["headline_mm_array", "eurczk_array", "output/path_step2.csv", "independent_path_experiment.py"])
def test_resume_rejects_changed_data_reference_or_source(changed):
    hashes = dict(headline_mm_array="a", eurczk_array="b",
                  **{"output/path_step2.csv": "c", "independent_path_experiment.py": "d"})
    saved = {"fingerprints": hashes.copy()}
    experiment()._verify_resume(saved, hashes)
    changed_hashes = {**hashes, changed: "different"}
    with pytest.raises(ValueError, match="Resume.*hash"):
        experiment()._verify_resume(saved, changed_hashes)
    with pytest.raises(ValueError, match="Resume.*hash"):
        experiment()._verify_resume({"fingerprints": {}}, hashes)


def test_frozen_loader_preserves_float_bits_and_interior_missing_months(tmp_path):
    idx = pd.period_range("2020-01", periods=5, freq="M")
    expected = pd.DataFrame({"headline_mm": [np.nan, np.nextafter(.1, np.inf), np.nan, .3, np.nan],
                             "eurczk": [25., 26., 27., 28., 29.]}, index=idx)
    path = tmp_path / "inputs.csv"; expected.to_csv(path, index_label="period")
    y, fx = experiment()._load_frozen_inputs(path)
    pd.testing.assert_series_equal(y, expected.headline_mm.iloc[1:4], check_names=False)
    pd.testing.assert_series_equal(fx, expected.eurczk, check_names=False)
    assert np.isnan(y.iloc[1])
    expected.drop(idx[2]).to_csv(path, index_label="period")
    with pytest.raises(ValueError, match="contiguous|monthly"):
        experiment()._load_frozen_inputs(path)


def test_rejected_resume_does_not_overwrite_any_checkpoint(tmp_path, monkeypatch):
    module = experiment()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "__file__", str(tmp_path / "independent_path_experiment.py"))
    for name in ["independent_path_experiment.py", "models/path_inputs.py", "models/trend_gap.py",
                 "models/bvar.py", "data/vintages.py", "cz_struct.py", "path_experiment.py",
                 "data/release_calendar_cz_cpi.csv", "data/vintages/unemployment.csv.gz"]:
        p = tmp_path / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"current source")
    out = tmp_path / "output"; out.mkdir()
    pd.DataFrame([dict(period="2020-02", HARD_BASE=.1, as_of_eve="2020-03-10 23:59:00")]).to_csv(
        out / "independent_nowcast_forecasts.csv", index=False)
    pd.DataFrame([dict(origin="2020-02", h=1, mm_F1b=.1, mm_F2_D1_fixed=.1)]).to_csv(out / "path_step2.csv", index=False)
    idx = pd.period_range("2010-01", "2020-03", freq="M")
    source = tmp_path / "frozen.csv"
    pd.DataFrame({"headline_mm": .1, "eurczk": 25.}, index=idx).to_csv(source, index_label="period")
    saved = out / "independent_path_manifest.json"
    saved.write_text(json.dumps({"fingerprints": {"old": "unverified"}}), encoding="utf-8")
    preserved = [saved]
    for suffix in ["forecasts.csv", "diagnostics.jsonl", "frozen_inputs.csv", "summary.csv"]:
        p = out / ("independent_path_" + suffix); p.write_bytes(b"preserve exactly"); preserved.append(p)
    before = {p: p.read_bytes() for p in preserved}
    with pytest.raises(ValueError, match="Resume.*hash"):
        module.main(["--resume", "--frozen-inputs", str(source)])
    assert before == {p: p.read_bytes() for p in preserved}
