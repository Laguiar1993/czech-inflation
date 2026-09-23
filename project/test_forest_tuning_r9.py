"""Timing, cache and selection safeguards for independent forest tuning."""
import numpy as np
import pandas as pd
import pytest


def _inputs(n=96):
    index = pd.period_range("2015-01", periods=n, freq="M")
    rng = np.random.default_rng(5)
    x = pd.DataFrame({"hard": rng.normal(size=n), "exp12": rng.normal(size=n), "esi": rng.normal(size=n)}, index=index)
    errors = pd.Series(0.2 * x.hard + rng.normal(scale=0.1, size=n), index=index)
    dates = pd.Series([(m + 1).to_timestamp() + pd.Timedelta(days=10) for m in index], index=index)
    return x, errors, dates


def test_fixed_grid_has_four_forests_and_three_multipliers():
    from forest_tuning_experiment import FORESTS, MULTIPLIERS
    assert {(c.leaf, c.max_features) for c in FORESTS} == {(leaf, features) for leaf in (3, 8) for features in (1.0, 1 / 3)}
    assert MULTIPLIERS == (0.0, 0.5, 1.0)


def test_correction_and_cache_key_ignore_future_or_unpublished_errors(tmp_path):
    from forest_tuning_experiment import FORESTS, forest_prediction
    x, errors, dates = _inputs()
    origin = x.index[75]
    clock = dates.loc[origin] - pd.Timedelta(days=1)
    dates.loc[origin - 1] = clock + pd.Timedelta(days=1)
    first = forest_prediction(x, errors, origin, clock, dates, FORESTS[0], cache_dir=tmp_path)
    changed_x, changed_errors = x.copy(), errors.copy()
    changed_errors.loc[origin - 1:] = 1e8
    changed_x.loc[origin + 1:, "hard"] = -1e8
    changed_x[["exp12", "esi"]] = 1e8
    second = forest_prediction(changed_x, changed_errors, origin, clock, dates, FORESTS[0], cache_dir=tmp_path)
    assert first["correction"] == second["correction"]
    assert first["cache_key"] == second["cache_key"]
    assert second["cache_hit"] is True
    assert first["error_end"] == origin - 2
    assert first["last_error_release"] <= clock


def test_cache_invalidates_when_eligible_data_or_parameters_change(tmp_path):
    from forest_tuning_experiment import FORESTS, forest_prediction
    x, errors, dates = _inputs()
    origin = x.index[70]
    clock = dates.loc[origin] - pd.Timedelta(days=1)
    first = forest_prediction(x, errors, origin, clock, dates, FORESTS[0], cache_dir=tmp_path)
    errors.iloc[50] += 2.0
    changed = forest_prediction(x, errors, origin, clock, dates, FORESTS[0], cache_dir=tmp_path)
    different = forest_prediction(x, errors, origin, clock, dates, FORESTS[1], cache_dir=tmp_path)
    assert len({first["cache_key"], changed["cache_key"], different["cache_key"]}) == 3
    assert changed["cache_hit"] is False


def test_cache_invalidates_when_numerical_runtime_changes(tmp_path, monkeypatch):
    import forest_tuning_experiment as experiment
    x, errors, dates = _inputs()
    origin = x.index[70]
    clock = dates.loc[origin] - pd.Timedelta(days=1)
    first = experiment.forest_prediction(x, errors, origin, clock, dates, experiment.FORESTS[0], cache_dir=tmp_path)
    original_version = experiment.importlib.metadata.version
    monkeypatch.setattr(experiment.importlib.metadata, "version",
                        lambda package: "review-new-runtime" if package == "quantile-forest" else original_version(package))
    second = experiment.forest_prediction(x, errors, origin, clock, dates, experiment.FORESTS[0], cache_dir=tmp_path)
    assert second["cache_key"] != first["cache_key"]
    assert second["cache_hit"] is False
    assert second["correction"] == first["correction"]


@pytest.mark.parametrize("bad_correction", [float("nan"), float("inf"), -float("inf")])
def test_cache_rejects_nonfinite_saved_correction(tmp_path, bad_correction):
    import json
    from forest_tuning_experiment import FORESTS, forest_prediction
    x, errors, dates = _inputs()
    origin = x.index[70]
    clock = dates.loc[origin] - pd.Timedelta(days=1)
    forest_prediction(x, errors, origin, clock, dates, FORESTS[0], cache_dir=tmp_path)
    path = next(tmp_path.glob("*.json"))
    saved = json.loads(path.read_text())
    saved["correction"] = bad_correction
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="nonfinite.*cache|cache.*finite"):
        forest_prediction(x, errors, origin, clock, dates, FORESTS[0], cache_dir=tmp_path)


def test_forests_reserve_exactly_12_errors_and_limit_workers(monkeypatch):
    from forest_tuning_experiment import FORESTS, forest_prediction
    import models.horizon_models as hm
    calls = []

    class Model:
        def set_params(self, **kwargs):
            assert kwargs == {"n_jobs": 2}
            calls.append(("workers", kwargs["n_jobs"]))
        def fit(self, x, y):
            calls.append(("fit", len(y)))
        def predict(self, x, quantiles):
            return np.zeros((len(x), len(quantiles)))

    class Forest:
        def __init__(self, **kwargs):
            assert kwargs["n_estimators"] == 200
            assert kwargs["val_window"] == 12 and kwargs["half_life"] == 6 and kwargs["seed"] == 42
            self.model = Model()
            self.q = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
        def _solve_weights(self, quantiles, target):
            calls.append(("validation", len(target)))
            return np.ones(5) / 5

    monkeypatch.setattr(hm, "TVWQRF", Forest)
    x, errors, dates = _inputs()
    origin = x.index[45]
    result = forest_prediction(x, errors, origin, dates.loc[origin] - pd.Timedelta(days=1), dates, FORESTS[0])
    assert result["status"] == "estimated"
    assert calls == [("workers", 2), ("fit", 33), ("validation", 12), ("fit", 45)]


def _predictions():
    from forest_tuning_experiment import FORESTS
    rows = []
    for origin in pd.period_range("2018-01", periods=50, freq="M"):
        for config in FORESTS:
            rows.append({"origin": origin, "forest": config.key, "correction": 0.8,
                         "residual_actual": 0.5, "target_available_from": (origin + 1).to_timestamp() + pd.Timedelta(days=10),
                         "n_errors": 60, "status": "estimated"})
    return pd.DataFrame(rows)


def test_selector_uses_published_full_core_errors_and_all_three_multipliers():
    from forest_tuning_experiment import select_correction
    table = _predictions()
    origin = table.origin.max() + 1
    clock = (origin + 1).to_timestamp()
    selected = select_correction(table, origin, clock)
    assert selected["multiplier"] == 0.5  # |0.5 - 0.5*0.8| beats both zero and full correction
    assert selected["n_validation"] == 36
    altered = table.copy()
    last = altered.origin.max()
    altered.loc[altered.origin == last, "target_available_from"] = clock + pd.Timedelta(days=1)
    before = select_correction(altered, origin, clock)
    altered.loc[altered.origin == last, "residual_actual"] = 1e9
    after = select_correction(altered, origin, clock)
    assert before == after


def test_selector_defaults_to_zero_with_short_history_or_tied_loss():
    from forest_tuning_experiment import select_correction
    table = _predictions()
    origin = table.origin.max() + 1
    clock = (origin + 1).to_timestamp()
    short = select_correction(table[table.origin < table.origin.min() + 23], origin, clock)
    assert short["multiplier"] == 0.0
    assert short["selection_reason"] == "insufficient_validation"
    table["correction"] = 0.0
    tied = select_correction(table, origin, clock)
    assert tied["multiplier"] == 0.0
    assert tied["selection_reason"] == "tie_zero"


def test_event_scores_match_predeclared_thresholds():
    from forest_tuning_experiment import event_scores
    index = pd.period_range("2024-01", periods=3, freq="M")
    forecasts = pd.DataFrame({"HARD_BASE": [0.0, 0.0, 0.0], "SELECTED": [0.2, -0.2, 0.3]}, index=index)
    actual = pd.Series([0.4, -0.4, 0.0], index=index)
    consensus = pd.Series(0.0, index=index)
    events, scores = event_scores(forecasts, actual, consensus)
    chosen = scores[scores.model == "SELECTED"].set_index("frame")
    assert chosen.loc["big", "n"] == 2
    assert chosen.loc["big", "material_win"] == 2
    assert chosen.loc["alerts", "n"] == 3
    assert chosen.loc["alerts", "material_loss"] == 1
    assert chosen.loc["alerts", "total_gain"] == pytest.approx(0.1)
