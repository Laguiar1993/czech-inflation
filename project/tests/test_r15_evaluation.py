"""Independent arithmetic fixtures for the frozen R15 evaluation."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("evaluate_r15", ROOT / "tools/review/evaluate_r15.py")
ev = importlib.util.module_from_spec(SPEC)
if SPEC.origin and Path(SPEC.origin).exists():
    SPEC.loader.exec_module(ev)


def panel(models=("base", "new"), origins=("2024-01", "2024-02")):
    return pd.DataFrame([
        dict(origin=o, h=h, target=str(pd.Period(o, "M") + h), model=m,
             as_of_utc=str((pd.Period(o, "M") + 1).start_time.tz_localize("UTC")),
             yy_exante=float(h), yy_actual=float(h + 1), mm_forecast=.9, mm_actual=.8)
        for o in origins for h in range(13) for m in models
    ])


def test_common_support_keeps_only_finite_complete_roster_and_rejects_duplicates():
    p = panel()
    p.loc[(p.origin == "2024-01") & (p.model == "new") & (p.h == 3), "yy_exante"] = np.nan
    got = ev.matched_rows(p[p.h == 3], ["base", "new"], "yy_exante", "yy_actual")
    assert set(got.origin) == {"2024-02"}
    assert set(got.model) == {"base", "new"}
    assert ev.matched_rows(p[p.h == 3], ["base", "new", "missing"], "yy_exante", "yy_actual").empty
    with pytest.raises(ValueError, match="Duplicate"):
        ev.matched_rows(pd.concat([p, p.iloc[:1]]), ["base", "new"], "yy_exante", "yy_actual")


def test_core_errors_use_core_fixture_and_cumulative_requires_every_month():
    p = panel(origins=("2024-01",))
    native = p[p.model == "base"].assign(value_core=.3)
    predictions = p[(p.model == "new") & (p.h > 0)][["origin", "h", "model"]].assign(core_mm=.4)
    predictions["core_log"] = 100 * np.log1p(predictions.core_mm / 100)
    predictions.loc[predictions.h == 2, ["core_mm", "core_log"]] = np.nan
    actual = pd.Series(.2, index=pd.period_range("2024-01", periods=13, freq="M"))
    result = ev.attach_core(p, native, predictions, actual)
    one = result[(result.model == "base") & (result.h == 3)].iloc[0]
    assert one.core_mm_actual == .2
    assert one.core_cumulative_log_actual == pytest.approx(3 * 100 * np.log1p(.2 / 100))
    assert one.core_cumulative_log_forecast == pytest.approx(3 * 100 * np.log1p(.3 / 100))
    assert result[(result.model == "new") & (result.h == 3)].core_cumulative_log_forecast.isna().all()
    assert result.mm_actual.eq(.8).all()


def test_direction_has_flat_threshold_and_material_wrong_way_calls():
    result = ev.direction_stats(np.array([3.0, 1., 2.25, 2.]), np.array([3., 3., 2.1, 1.]), np.full(4, 2.))
    assert result["n"] == 4
    assert result["direction_match_rate"] == .5
    assert result["actual_material_n"] == 3
    assert result["material_direction_hit_rate"] == pytest.approx(1 / 3)
    assert result["wrong_way_n"] == 1
    assert result["material_calls_n"] == 2


def test_prague_clock_report_strict_and_cutoff_includes_entire_local_day():
    clocks = pd.Series(pd.to_datetime(["2024-06-10T21:59:00Z", "2024-06-10T22:00:00Z", "2024-06-11T15:00:00Z", "2024-06-11T22:00:00Z"]), index=["2024-01", "2024-02", "2024-03", "2024-04"])
    assert ev.select_snapshot(clocks, "2024-06-11", "report")[0] == "2024-01"
    assert ev.select_snapshot(clocks, "2024-06-11", "cutoff")[0] == "2024-03"


def test_quarter_uses_known_history_then_one_origin_and_requires_three_months():
    actual = pd.Series([1., 2., 99.], index=pd.period_range("2024-01", periods=3, freq="M"))
    assert ev.quarter_value("2024Q1", "2024-03", {"2024-03": 6.}, actual) == 3.
    assert np.isnan(ev.quarter_value("2024Q1", "2024-02", {"2024-03": 6.}, actual))
    assert np.isnan(ev.quarter_actual("2024Q2", actual))


def test_cnb_pair_support_and_material_gain_are_same_round_arithmetic():
    p = panel(origins=("2024-01",))
    p["as_of_utc"] = "2024-02-01T12:00:00Z"
    p["yy_exante"] = np.where(p.model == "new", 3.5, 4.)
    actual = pd.Series(3., index=pd.period_range("2023-01", "2025-12", freq="M"))
    cnb = pd.DataFrame([dict(report_date="2024-02-10", cutoff_date="2024-02-02", quarter="2024Q1", value=5., is_forecast=True)])
    pairs, coverage, clocks, projections = ev.cnb_comparison(p, cnb, actual, ["base", "new"])
    assert len(pairs) == 6  # two clocks, two models plus the same CNB forecast
    row = pairs[(pairs.model == "new") & (pairs.clock == "report")].iloc[0]
    assert row.origin == "2024-01"
    assert row.abs_error_gain_vs_cnb == 1.5
    assert row.model_cnb_deviation == -1.5
    assert row.realised_cnb_error == -2.
    assert row.material_gain and not row.material_loss
    assert coverage.included.all()
    p.loc[(p.model == "new") & (p.target == "2024-03"), "yy_exante"] = np.nan
    pairs, coverage, _, _ = ev.cnb_comparison(p, cnb, actual, ["base", "new"])
    assert pairs.empty
    assert (~coverage.included).all()
    assert coverage.missing_models.str.contains("new").all()


def test_cnb_direction_alone_does_not_count_as_a_win():
    got = ev.gain_fields(5.9, 5., 3.)  # same sign deviation as realised error is false
    assert got["material_loss"]
    got = ev.gain_fields(.9, 5., 3.)  # right direction but overshoots and is worse
    assert got["deviation_direction_correct"]
    assert not got["material_gain"]
    assert got["abs_error_gain_vs_cnb"] == pytest.approx(-.1)
    assert ev.gain_fields(4.85, 5., 3.)["material_gain"]
    assert ev.gain_fields(5.15, 5., 3.)["material_loss"]


def test_revision_only_consecutive_origins_with_identical_target():
    p = pd.DataFrame([dict(model="new", origin=o, target="2024-06", h=h, yy_exante=v)
                      for o, h, v in [("2024-01", 5, 3.), ("2024-02", 4, 3.5), ("2024-04", 2, 5.)]])
    got = ev.revision_pairs(p)
    assert len(got) == 1
    assert got.iloc[0].revision == .5
    assert got.iloc[0].h == 4


def test_revision_summary_does_not_wait_for_future_actual_outcomes():
    p = panel(models=(ev.BASE, "new"), origins=("2024-01", "2024-02"))
    p["yy_actual"] = np.nan
    result = ev.revision_summaries(ev.revision_pairs(p), [ev.BASE, "new"])
    got = result.query("scope == 'all_models_common' and sample == 'full' and model == 'new'").iloc[0]
    assert got.n == 12 and got.mae == got.max_abs == 1.


def test_block_bootstrap_preserves_calendar_gaps_and_reproducibility():
    d = pd.DataFrame(dict(origin=pd.period_range("2020-01", periods=25, freq="M").astype(str), loss_difference=np.repeat(-2., 25)))
    result = ev.block_bootstrap(d, block=12, draws=2000, seed=1509)
    assert result["n"] == 25 and result["eligible_blocks"] == 14
    assert result["mean_loss_difference"] == -2.
    assert result["ci_low"] == result["ci_high"] == -2.
    assert result == ev.block_bootstrap(d, block=12, draws=2000, seed=1509)
    d = d.drop(index=12)
    assert ev.block_bootstrap(d)["eligible_blocks"] == 2
    assert ev.block_bootstrap(d.head(10))["status"] == "insufficient_contiguous_support"


def test_bootstrap_does_not_report_ci_on_subset_of_paired_support():
    origins = [*pd.period_range("2020-01", periods=12, freq="M").astype(str), "2022-01"]
    data = pd.DataFrame(dict(origin=origins, loss_difference=np.arange(13.)))
    got = ev.block_bootstrap(data)
    assert got["n"] == 13 and got["n_origins_in_blocks"] == 12
    assert got["status"] == "uncovered_support_origins"
    assert np.isnan(got["ci_low"])


def test_html_is_self_contained_and_preserves_replay_clock_controls(tmp_path):
    data = dict(series=[], reportsByClock={"report": [], "cutoff": []}, realised={}, method=[])
    out = tmp_path / "replay.html"
    ev.write_replay(out, data, ROOT / "tools/cnb_rounds/cnb_rounds_template.html")
    html = out.read_text(encoding="utf-8")
    assert "fonts.googleapis" not in html
    assert 'id="clock-select"' in html
    assert 'id="round-select"' in html
    assert 'type="checkbox"' in html
    assert "current-vintage" in html and "simulated" in html
    assert "No eligible historical snapshots" in html


def test_replay_default_shows_fast_state_and_controls_without_altering_roster():
    cnb = pd.DataFrame(columns=["is_forecast", "report_date"])
    data = ev.replay_data(pd.DataFrame(), cnb, pd.Series(dtype=float), pd.DataFrame(), pd.DataFrame())
    assert {s["id"] for s in data["series"] if s["default"]} == {"realised", "cnb", ev.BASE, "STABLE_LOCAL_CORE_R14B", "STATE_FAST_R15"}
    assert {s["id"] for s in data["series"] if s["kind"] == "model"} == set(ev.ROSTER)


def test_scoreboard_separates_all_model_and_paired_support_with_era_samples():
    p = panel(models=(ev.BASE, "new", "other"), origins=("2021-12", "2024-01"))
    p.loc[(p.model == "other") & (p.origin == "2021-12"), "yy_exante"] = np.nan
    scores, differences = ev.score_tables(p, [ev.BASE, "new", "other"], {"headline_yy": ("yy_exante", "yy_actual")})
    common = scores.query("scope == 'all_models_common' and sample == 'full' and h == 3 and model == 'new'").iloc[0]
    paired = scores.query("scope == 'paired_new' and sample == 'full' and h == 3 and model == 'new'").iloc[0]
    assert common.n == 1 and paired.n == 2
    assert paired.mae == paired.rmse == 1.
    assert len(differences.query("scope == 'paired_new' and h == 3")) == 2
    assert "origins_2019_2021" in set(scores["sample"])
    assert "recent_targets" in set(scores["sample"])


def test_underlying_core_turns_use_saved_origin_seasonality_and_detect_peak():
    p = panel(origins=("2024-01",))
    seasonal = {str(m): .02 * m for m in range(1, 13)}
    p["core_mm_forecast"] = [100 * np.expm1((([.1, .2, .1, .05][(r.h - 1) // 3] if r.h else .1) + seasonal[str(pd.Period(r.target, 'M').month)]) / 100) for r in p.itertuples()]
    p["core_mm_actual"] = p.core_mm_forecast
    states = {"2024-01": {"seasonal": seasonal}}
    paths, changes, turns = ev.core_turn_diagnostics(p, states)
    got = paths.query("model == 'new'").sort_values("band")
    assert got.predicted_sa_annualized.tolist() == pytest.approx([1.2, 2.4, 1.2, .6])
    peak = turns.query("model == 'new' and band == 2").iloc[0]
    assert peak.predicted_turn == peak.actual_turn == "peak"
    assert peak.exact_hit
    # Poisoning later origin seasonality cannot rewrite this origin's path.
    states["2024-02"] = {"seasonal": dict.fromkeys(seasonal, 999.)}
    assert ev.core_turn_diagnostics(p, states)[0].equals(paths)


def test_adjacent_quarter_changes_compare_forecast_changes_to_actual_changes():
    p = panel(origins=("2024-01",))
    p["yy_exante"] = [float(pd.Period(t, 'M').quarter) for t in p.target]
    actual = pd.Series([float(t.quarter) for t in pd.period_range("2023-01", "2025-12", freq="M")], index=pd.period_range("2023-01", "2025-12", freq="M"))
    rows = ev.adjacent_quarter_changes(p, actual)
    assert rows.predicted_change.eq(1.).all()
    assert rows.actual_change.eq(1.).all()
    assert rows.material_actual.all()


def test_evaluate_cli_writes_only_evaluation_and_keeps_missing_model_ledger(tmp_path):
    root = tmp_path / "repo"
    experiment = root / "output/research_r15"
    control = root / "output/research_r14b/integration"
    control.mkdir(parents=True)
    experiment.mkdir(parents=True)
    (root / "data").mkdir()
    (root / "tests/fixtures/cleanup").mkdir(parents=True)
    (root / "tools/cnb_rounds").mkdir(parents=True)
    (root / "tools/cnb_rounds/cnb_rounds_template.html").write_text((ROOT / "tools/cnb_rounds/cnb_rounds_template.html").read_text(encoding="utf-8"), encoding="utf-8")
    p = panel(models=ev.ROSTER, origins=("2024-01", "2024-02"))
    # Actual/forecast annual columns are required to reconcile to frozen months.
    mm = pd.Series(.2, index=pd.period_range("2022-01", "2025-12", freq="M"))
    p["mm_actual"] = .2
    p["mm_forecast"] = .3
    actual_yy = 100 * np.expm1(np.log1p(mm / 100).rolling(12).sum())
    p["yy_actual"] = [actual_yy[pd.Period(t, "M")] for t in p.target]
    p["yy_exante"] = [100 * np.expm1((12 - min(r.h + 1, 12)) * np.log1p(.2 / 100) + min(r.h + 1, 12) * np.log1p(.3 / 100)) for r in p.itertuples()]
    p["cumulative_log_forecast"] = 100 * p.h * np.log1p(.3 / 100)
    p["cumulative_log_actual"] = 100 * p.h * np.log1p(.2 / 100)
    p[p.model.isin(ev.CONTROLS)].to_csv(control / "forecasts.csv", index=False)
    p[p.model.isin(ev.CONTROLS)].assign(value_core=.3).to_csv(control / "native_forecasts.csv", index=False)
    p.to_csv(experiment / "forecasts.csv", index=False)
    p[p.model.isin(ev.NEW_MODELS)].assign(value_core=.3).to_csv(experiment / "native_forecasts.csv", index=False)
    cp = p[p.model.isin(ev.NEW_MODELS) & p.h.gt(0)][ev.KEYS].assign(core_mm=.3, core_log=100*np.log1p(.3/100))
    cp.to_csv(experiment / "core_predictions.csv", index=False)
    for name, obj in [("states.json", {o: {"seasonal": dict.fromkeys(range(1, 13), 0.)} for o in p.origin.unique()}), ("selections.json", []), ("fits.json", [])]:
        import json
        (experiment / name).write_text(json.dumps(obj), encoding="utf-8")
    pd.DataFrame({"period": mm.index.astype(str), "headline_mm": mm.values}).to_csv(root / "output/independent_path_frozen_inputs.csv", index=False)
    pd.DataFrame({"period": mm.index.astype(str), "core": mm.values}).to_csv(root / "tests/fixtures/cleanup/cnb_core_mm.csv", index=False)
    pd.DataFrame([dict(report_date="2024-02-10", cutoff_date="2024-02-02", quarter="2024Q1", value=3., is_forecast=True)]).to_csv(root / "data/cnb_mpr_cpi_quarterly.csv", index=False)
    before = {str(f): f.read_bytes() for f in root.rglob("*") if f.is_file()}
    ev.evaluate(experiment, root)
    assert all(Path(f).read_bytes() == value for f, value in before.items())
    out = experiment / "evaluation"
    assert (out / "cnb_rounds_replayed_r15.html").exists()
    ledger = pd.read_csv(out / "coverage_ledger.csv")
    assert len(ledger) == 2 * 13 * len(ev.ROSTER)
    assert set(ledger.model) == set(ev.ROSTER)
    assert (out / "input_manifest.json").exists()
    assert (out / "underlying_core_turns.csv").exists()
