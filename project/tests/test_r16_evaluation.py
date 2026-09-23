"""Independent fixtures for the read-only R16 evaluator."""
import importlib.util
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("evaluate_r16", ROOT / "tools/review/evaluate_r16.py")
ev = importlib.util.module_from_spec(SPEC)
if SPEC.origin and Path(SPEC.origin).exists():
    SPEC.loader.exec_module(ev)


def panel(models, origins=("2024-01", "2024-02")):
    return pd.DataFrame([dict(origin=o, h=h, target=str(pd.Period(o, "M") + h), model=m,
        as_of_utc=str((pd.Period(o, "M") + 1).start_time.tz_localize("UTC")),
        yy_exante=float(h), yy_actual=float(h + 1), mm_forecast=.3, mm_actual=.2)
        for o in origins for h in range(13) for m in models])


def test_declared_roster_has_five_controls_ten_new_and_no_old_extra_models():
    assert len(ev.ROSTER) == len(set(ev.ROSTER)) == 15
    assert len(ev.CONTROLS) == 5 and len(ev.NEW_MODELS) == 10
    assert ev.FAST in ev.CONTROLS and "STATE_MID_R15" not in ev.ROSTER


def test_scores_use_fifteen_common_and_separate_fast_and_pipeline_pairs():
    p = panel(ev.ROSTER, ("2021-12", "2024-01"))
    missing = ev.NEW_MODELS[-1]
    p.loc[p.model.eq(missing) & p.origin.eq("2021-12"), "yy_exante"] = np.nan
    p.loc[p.model.eq(ev.FAST), "yy_exante"] += 2
    scores, differences = ev.score_tables(p, ev.ROSTER, {"headline_yy": ("yy_exante", "yy_actual")})
    model = ev.NEW_MODELS[0]
    common = scores.query("scope == 'all_models_common' and sample == 'full' and h == 3 and model == @model").iloc[0]
    assert common.n == 1
    for name in ("paired_fast_", "paired_pipeline_"):
        own = scores[scores.scope.eq(name + model) & scores["sample"].eq("full") & scores.h.eq(3) & scores.model.eq(model)].iloc[0]
        assert own.n == 2 and own.rmse == own.mae == 1
    assert set(differences.benchmark) == {ev.BASE, ev.FAST}
    assert set(differences[differences.scope.eq("all_models_common")].origin) == {"2024-01"}


def projections(origins=("2024-01", "2024-02")):
    return pd.DataFrame([dict(origin=o, stage="signal", family=s, signal=s, band=b,
        config="l1", predicted_change=1., current_z=2., projected_z=3., status="estimated", as_of="2024-03-01")
        for o in origins for s in ("services", "goods") for b in range(4)])


def test_signal_scores_use_log_of_each_annual_rate_then_band_mean_and_fixed_pairs():
    periods = pd.period_range("2023-12", "2025-03", freq="M")
    z = pd.DataFrame({"services": np.arange(len(periods), dtype=float), "goods": 2.}, index=periods)
    broad = 100 * np.expm1(z / 100)
    p = projections(("2024-01",))
    p["current_z"] = [z.loc["2023-12", s] for s in p.signal]
    p["projected_z"] = p.current_z + p.predicted_change
    p.loc[p.signal.eq("goods") & p.band.eq(1), "projected_z"] = np.nan
    ledger, scores = ev.signal_scores(p, broad, ["2024-01"])
    row = ledger[ledger.signal.eq("services") & ledger.band.eq(0)].iloc[0]
    assert row.actual_z == pytest.approx(3.)  # Feb, Mar, Apr logs = 2,3,4
    assert row.target == "2024-04" and row.unit == "annual_log_pp"
    own = scores[scores.signal.eq("goods") & scores.band.eq(1) & scores["sample"].eq("full")]
    assert len(own) == 2 and own.n.eq(0).all()


def test_signal_scores_exclude_warmup_origins_and_require_all_three_actual_months():
    broad = pd.DataFrame(100 * np.expm1(.02), index=pd.period_range("2005-01", "2025-03", freq="M"), columns=["services", "goods"])
    broad.loc["2024-03", "services"] = np.nan
    ledger, scores = ev.signal_scores(projections(("2006-01", "2024-01")), broad, ["2024-01"])
    assert set(ledger.origin) == {"2024-01"}
    assert not ledger[ledger.signal.eq("services") & ledger.band.eq(0)].included.any()
    assert scores[scores.signal.eq("services") & scores.band.eq(0)].n.eq(0).all()


def test_signal_current_level_and_projection_identity_are_verified():
    broad = pd.DataFrame(100 * np.expm1(.02), index=pd.period_range("2023-01", "2025-03", freq="M"), columns=["services", "goods"])
    p = projections()
    p.loc[0, "current_z"] = 5
    with pytest.raises(ValueError, match="current signal"):
        ev.signal_scores(p, broad, ["2024-01", "2024-02"])
    p = projections(); p.loc[0, "projected_z"] = 99
    with pytest.raises(ValueError, match="projected signal"):
        ev.signal_scores(p, broad, ["2024-01", "2024-02"])


def test_cnb_leave_one_out_includes_every_report_and_recomputes_rmse_mae():
    rows = []
    for clock in ("report", "cutoff"):
        for date, err, cnb_err in [("2022-02-01", 10., 20.), ("2023-02-01", 2., 1.), ("2024-02-01", 0., 1.)]:
            rows.append(dict(clock=clock, report_date=date, quarter="2024Q1", model="new", error=err,
                realised_cnb_error=cnb_err))
    result = ev.cnb_leave_one_report_out(pd.DataFrame(rows))
    full = result[result["sample"].eq("full")]
    assert len(full) == 6 and set(full.omitted_report) == {"2022-02-01", "2023-02-01", "2024-02-01"}
    row = full[full.clock.eq("report") & full.omitted_report.eq("2022-02-01")].iloc[0]
    assert row.rmse == pytest.approx(np.sqrt(2)) and row.mae == 1
    assert row.cnb_rmse == row.cnb_mae == 1 and row.n == 2
    assert row.rmse_gain_vs_cnb == pytest.approx(1 - np.sqrt(2))


def test_revision_scopes_retain_future_targets_without_actuals():
    p = panel(ev.ROSTER); p["yy_actual"] = np.nan
    result = ev.scoped_summary(ev.prior.revision_summaries, ev.prior.revision_pairs(p), models=ev.ROSTER)
    got = result[result.scope.eq("all_models_common") & result["sample"].eq("full")]
    assert len(got) == 15 and got.n.eq(12).all()
    assert any(result.scope.str.startswith("paired_fast_"))


def test_mapping_diagnostics_keep_stage_standardization_and_projection_units():
    fits = [dict(origin="2024-01", stage="core", family="both", band=0, config="l1", status="estimated", n_train=120,
        lambda_value=1., coefficients={"services_projection": .6}, means={"services_projection": 2.},
        scales={"services_projection": .3}, intercept=.1, converged=True)]
    details, summary = ev.coefficient_diagnostics(fits, ["2024-01"])
    row = details[details.feature.eq("services_projection")].iloc[0]
    assert row.value == .6 and row.raw_predictor_coefficient == pytest.approx(2.)
    assert row.annual_signal_change_coefficient == pytest.approx(2 / 12)
    assert row.stage == "core" and row.outer_origin
    assert len(summary) == 2  # standardized feature and penalized constant


def test_component_guard_rejects_noncore_change_and_h0_change():
    native = panel([ev.NEW_MODELS[0]])
    native["value_food"] = 2.; native["weight_core"] = .5; native["value_core"] = .3
    base = native.assign(model=ev.BASE)
    checks = ev.verify_components(native, base)
    assert checks["h0_max"] == 0 and checks["noncore_max"] == 0
    native.loc[1, "value_food"] = 3.
    with pytest.raises(ValueError, match="noncore"):
        ev.verify_components(native, base)
    native.loc[1, "value_food"] = 2.; native.loc[native.h.eq(0), "mm_forecast"] = 9
    with pytest.raises(ValueError, match="h0"):
        ev.verify_components(native, base)


def test_headline_export_matches_native_monthly_path_and_declared_calendar():
    raw = panel(ev.NEW_MODELS)
    native = raw.copy()
    archive = panel(ev.CONTROLS)
    checks = ev.verify_forecast_exports(raw, native, archive, {"origin_count": 2})
    assert checks["native_headline_monthly_max"] == 0
    raw.loc[raw.h.eq(0), "mm_forecast"] += .1
    with pytest.raises(ValueError, match="native headline"):
        ev.verify_forecast_exports(raw, native, archive, {"origin_count": 2})
    with pytest.raises(ValueError, match="origin count"):
        ev.verify_forecast_exports(native, native, archive, {"origin_count": 90})
    raw = native.copy(); raw.loc[0, "target"] = "2030-01"
    with pytest.raises(ValueError, match="target calendar"):
        ev.verify_forecast_exports(raw, native, archive, {"origin_count": 2})


def test_replay_uses_original_template_and_full_r16_defaults_and_fixed_support(tmp_path):
    cnb = pd.DataFrame(columns=["is_forecast", "report_date"])
    data = ev.replay_data(pd.DataFrame(), cnb, pd.Series(dtype=float), pd.DataFrame(), pd.DataFrame())
    assert {s["id"] for s in data["series"] if s["kind"] == "model"} == set(ev.ROSTER)
    assert {s["id"] for s in data["series"] if s["default"]} == {
        "realised", "cnb", ev.FAST, "STABLE_LOCAL_CORE_R14B", "DAMPED_ADAPT_R16", "TRANSMISSION_BOTH_R16"}
    out = tmp_path / "replay.html"
    ev.write_replay(out, data, ROOT / "tools/cnb_rounds/cnb_rounds_template.html")
    html = out.read_text(encoding="utf-8")
    assert "complete 15-model roster" in html and "cnb-rounds-r16-visible-v1" in html
    assert "R15 ·" not in html and "fonts.googleapis" not in html
    assert "clock-select" in html and "round-select" in html and 'type="checkbox"' in html
    assert "July 2026" in html and "historical" in html
    assert chr(65533) not in html
    embedded = json.loads(re.search(r"const DATA = (.*?);\s*\n", html).group(1))
    embedded.pop("reports")
    assert embedded == data


def test_support_comparison_reports_r15_differences_without_changing_r16_support():
    p = panel(ev.ROSTER)
    old = panel(ev.prior.ROSTER)
    old.loc[old.origin.eq("2024-01") & old.h.eq(3), "yy_actual"] = np.nan
    result = ev.support_comparison(p, old, {"headline_yy": ("yy_exante", "yy_actual")})
    row = result[result.h.eq(3) & result["sample"].eq("full")].iloc[0]
    assert row.r16_n == 2 and row.r15_n == 1 and row.r16_only_n == 1


def test_full_evaluator_writes_evaluation_only_and_exports_new_diagnostics(tmp_path):
    root = tmp_path / "repo"; experiment = root / "output/research_r16"
    for folder in (experiment, root / "output/research_r15", root / "output/research_r14b/integration",
                   root / "data/core_split", root / "tests/fixtures/cleanup", root / "tools/cnb_rounds"):
        folder.mkdir(parents=True, exist_ok=True)
    template = root / "tools/cnb_rounds/cnb_rounds_template.html"
    template.write_bytes((ROOT / "tools/cnb_rounds/cnb_rounds_template.html").read_bytes())
    p = panel(ev.ROSTER)
    mm = pd.Series(.2, index=pd.period_range("2022-01", "2025-12", freq="M"))
    p["yy_actual"] = 100 * np.expm1(12 * np.log1p(.2 / 100))
    p["yy_exante"] = [100 * np.expm1((12 - min(h + 1, 12)) * np.log1p(.2 / 100) + min(h + 1, 12) * np.log1p(.3 / 100)) for h in p.h]
    p["cumulative_log_forecast"] = p.h * 100 * np.log1p(.3 / 100)
    p["cumulative_log_actual"] = p.h * 100 * np.log1p(.2 / 100)
    p.to_csv(experiment / "forecasts.csv", index=False)
    new = p[p.model.isin(ev.NEW_MODELS)].assign(value_core=.3, value_food=.2, weight_core=.5)
    new.to_csv(experiment / "native_forecasts.csv", index=False)
    p[p.model.isin(ev.CONTROLS)].to_csv(root / "output/research_r15/forecasts.csv", index=False)
    p[p.model.isin(ev.CONTROLS[-2:])].assign(value_core=.3).to_csv(root / "output/research_r15/native_forecasts.csv", index=False)
    p[p.model.isin(ev.CONTROLS[:3])].assign(value_core=.3, value_food=.2, weight_core=.5).to_csv(root / "output/research_r14b/integration/native_forecasts.csv", index=False)
    cp = new[new.h.gt(0)][ev.KEYS].assign(core_mm=.3, core_log=100*np.log1p(.3/100))
    cp.to_csv(experiment / "core_predictions.csv", index=False)
    states = {o: {"seasonal": dict.fromkeys(range(1, 13), 0.)} for o in p.origin.unique()}
    for name, value in (("states.json", states), ("selections.json", []), ("fits.json", [])):
        (experiment / name).write_text(json.dumps(value), encoding="utf-8")
    (root / "output/research_r15/states.json").write_text(json.dumps(states), encoding="utf-8")
    projections().to_csv(experiment / "signal_projections.csv", index=False)
    pd.DataFrame({"period": mm.index.astype(str), "headline_mm": mm.values}).to_csv(root / "output/independent_path_frozen_inputs.csv", index=False)
    pd.DataFrame({"period": mm.index.astype(str), "core": mm.values}).to_csv(root / "tests/fixtures/cleanup/cnb_core_mm.csv", index=False)
    pd.DataFrame({"period": mm.index.astype(str), "goods": 100*np.expm1(.02), "services": 100*np.expm1(.02)}).to_csv(root / "data/core_split/broad_yoy.csv", index=False)
    pd.DataFrame([dict(report_date="2024-02-10", cutoff_date="2024-02-02", quarter="2024Q1", value=3., is_forecast=True)]).to_csv(root / "data/cnb_mpr_cpi_quarterly.csv", index=False)
    before = {f: f.read_bytes() for f in root.rglob("*") if f.is_file()}
    out = ev.evaluate(experiment, root)
    assert all(f.read_bytes() == value for f, value in before.items())
    ledger = pd.read_csv(out / "coverage_ledger.csv")
    assert len(ledger) == 2 * 13 * 15 and set(ledger.model) == set(ev.ROSTER)
    for name in ("cnb_rounds_replayed_r16.html", "signal_scoreboard.csv", "signal_coverage.csv", "cnb_leave_one_report_out.csv",
                 "coefficient_feature_details.csv", "r15_support_comparison.csv", "underlying_core_turns.csv", "input_manifest.json"):
        assert (out / name).exists()
    manifest = json.loads((out / "input_manifest.json").read_text())
    assert manifest["model_count"] == 15 and manifest["origin_count"] == 2
