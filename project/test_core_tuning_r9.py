"""Nested tuning must select only using released, genuinely sequential errors."""
import numpy as np
import pandas as pd
import pytest


def _data(n=132):
    index = pd.period_range("2010-01", periods=n, freq="M")
    rng = np.random.default_rng(42)
    x = pd.DataFrame({"observed": rng.normal(size=n), "exp12": rng.normal(size=n),
                      "esi": rng.normal(size=n)}, index=index)
    y = pd.Series(0.2 + 0.5 * x.observed + rng.normal(scale=0.08, size=n), index=index)
    release = pd.Series([(m + 1).to_timestamp() + pd.Timedelta(days=10) for m in index], index=index)
    decisions = release - pd.Timedelta(days=1)
    return x, y, release, decisions


def test_hard_policy_and_grid_are_fixed():
    from models.core_tuning import GRID, DEFAULT, hard_features
    x = pd.DataFrame({name: [1.0] for name in ["exp12", "exp36", "exp12_x_state", "household_exp", "esi", "core_l1"]})
    assert list(hard_features(x).columns) == ["core_l1"]
    assert {(c.alpha, c.window) for c in GRID} == {(a, w) for a in (0.3, 3.0, 30.0, 300.0) for w in (60, 120, None)}
    assert (DEFAULT.alpha, DEFAULT.window) == (3.0, None)


def test_core_ridge_rejects_unreleased_labels_and_uses_calendar_window():
    from models.core_tuning import CoreConfig, ridge_prediction
    x, y, release, decisions = _data()
    t = x.index[100]
    release.loc[t - 1] = decisions.loc[t] + pd.Timedelta(days=1)
    result = ridge_prediction(x[["observed"]], y, t, decisions.loc[t], release, CoreConfig(3.0, 60))
    changed = y.copy()
    changed.loc[t - 1:] = 1e9
    other = ridge_prediction(x[["observed"]], changed, t, decisions.loc[t], release, CoreConfig(3.0, 60))
    assert result["prediction"] == other["prediction"]
    assert result["n_train"] == 59
    assert result["train_start"] == t - 60
    assert result["train_end"] == t - 2
    assert result["training_last_release"] <= decisions.loc[t]


def test_missing_month_is_rejected_before_lag_or_window_selection():
    from models.core_tuning import DEFAULT, ridge_prediction
    x, y, release, decisions = _data()
    with pytest.raises(ValueError, match="contiguous"):
        ridge_prediction(x.drop(x.index[20]), y, x.index[100], decisions.iloc[100], release, DEFAULT)


def test_imputation_is_training_only_and_all_missing_column_is_ignored():
    from models.core_tuning import DEFAULT, ridge_prediction
    x, y, release, decisions = _data()
    x = x[["observed"]]
    t = x.index[100]
    x.loc[t, "observed"] = np.nan
    x["unobserved"] = np.nan
    first = ridge_prediction(x, y, t, decisions.loc[t], release, DEFAULT)
    x.loc[t + 1:, :] = 1e10
    second = ridge_prediction(x, y, t, decisions.loc[t], release, DEFAULT)
    assert first["prediction"] == pytest.approx(y.loc[:t - 1].mean(), abs=1e-12)
    assert first["prediction"] == second["prediction"]
    assert first["dropped_columns"] == ["unobserved"]


def _validation_table(n=50):
    from models.core_tuning import CoreConfig, DEFAULT
    index = pd.period_range("2010-01", periods=n, freq="M")
    rows = []
    challenger = CoreConfig(30.0, 60)
    for t in index:
        for config, error in ((DEFAULT, 1.0), (challenger, 0.1)):
            rows.append({"origin": t, "config": config.key, "prediction": error, "actual": 0.0,
                         "target_available_from": (t + 1).to_timestamp() + pd.Timedelta(days=10)})
    return pd.DataFrame(rows), DEFAULT, challenger


def test_selector_uses_last_36_published_errors_and_requires_24():
    from models.core_tuning import select_config
    table, default, challenger = _validation_table()
    t = pd.Period("2014-03", freq="M")
    clock = (t + 1).to_timestamp()
    result = select_config(table, t, clock, configs=(default, challenger))
    assert result["config"] == challenger.key
    assert result["n_validation"] == 36
    assert result["validation_last_release"] <= clock
    short = table[table.origin < table.origin.min() + 23]
    fallback = select_config(short, t, clock, configs=(default, challenger))
    assert fallback["config"] == default.key
    assert fallback["selection_reason"] == "insufficient_validation"


def test_selector_excludes_unreleased_error_and_prefers_default_on_tie():
    from models.core_tuning import select_config
    table, default, challenger = _validation_table()
    t = table.origin.max() + 1
    clock = (t + 1).to_timestamp()
    table.loc[table.config == default.key, "prediction"] = 0.1
    # A future-released outlier would dominate MSE if publication gating failed.
    last = table.origin.max()
    table.loc[(table.origin == last) & (table.config == default.key), "prediction"] = 1e9
    table.loc[table.origin == last, "target_available_from"] = clock + pd.Timedelta(days=1)
    result = select_config(table, t, clock, configs=(default, challenger))
    assert result["config"] == default.key
    assert result["selection_reason"] == "tie_default"
    assert result["validation_end"] < last


def test_nested_predictions_and_choices_ignore_future_targets_features_and_surveys():
    from models.core_tuning import CoreConfig, DEFAULT, nested_predictions
    x, y, release, decisions = _data()
    outer = x.index[85:105]
    configs = (DEFAULT, CoreConfig(30.0, 60))
    first, chosen = nested_predictions(x, y, decisions, release, outer, configs=configs)
    cut = outer[8]
    xx, yy = x.copy(), y.copy()
    yy.loc[cut:] = 1e9
    xx.loc[cut + 1:, "observed"] = -1e9
    xx[["exp12", "esi"]] = 1e9
    second, other = nested_predictions(xx, yy, decisions, release, outer, configs=configs)
    a = first[first.origin <= cut].drop(columns=["actual", "error"])
    b = second[second.origin <= cut].drop(columns=["actual", "error"])
    pd.testing.assert_frame_equal(a, b)
    pd.testing.assert_frame_equal(chosen[chosen.origin <= cut], other[other.origin <= cut])


def test_default_matches_existing_ridge_when_calendar_and_inputs_match():
    import cz_struct as S
    from models.core_tuning import DEFAULT, ridge_prediction
    x, y, release, decisions = _data()
    x = x[["observed"]]
    t = x.index[100]
    # Synthetic label timestamps are exactly the eligibility schedule passed
    # to the new estimator; the legacy as_of=None path allows the same rows.
    result = ridge_prediction(x, y, t, decisions.loc[t], release, DEFAULT)
    legacy = S._ridge_predict(x, y, t, alpha=3.0, as_of=None)[0]
    assert result["prediction"] == pytest.approx(legacy, abs=1e-12)


def test_headline_attribution_holds_noncore_components_fixed():
    from core_tuning_experiment import headline_attribution
    legacy = np.array([0.2, 0.3])
    headline = np.array([0.5, -0.1])
    weights = np.array([0.6, 0.5])
    np.testing.assert_allclose(headline_attribution(headline, weights, legacy, legacy), headline)
    candidate = legacy + np.array([0.1, -0.2])
    np.testing.assert_allclose(headline_attribution(headline, weights, legacy, candidate) - headline, weights * (candidate - legacy))


def test_scores_use_common_origins_and_report_core_and_headline_separately():
    from core_tuning_experiment import score_candidates
    index = pd.period_range("2023-12", periods=4, freq="M")
    rows = []
    for model in ("default", "selected"):
        for i, origin in enumerate(index):
            rows.append({"origin": origin, "model": model, "core_actual": 0.0, "headline_actual": 0.0,
                         "core_forecast": 1.0 if model == "default" else 0.5,
                         "headline_forecast": 2.0 if model == "default" else 1.0})
    scores = score_candidates(pd.DataFrame(rows))
    selected = scores[(scores.model == "selected") & (scores.split == "all")].iloc[0]
    assert selected.n == 4
    assert selected.core_rmse == 0.5
    assert selected.headline_mae == 1.0
    assert scores[(scores.model == "selected") & (scores.split == "2024+")].iloc[0].n == 3
    # Missing one candidate must not silently give it a different scored sample.
    rows[-1]["core_forecast"] = np.nan
    reduced = score_candidates(pd.DataFrame(rows))
    assert set(reduced[reduced.split == "all"].n) == {3}
