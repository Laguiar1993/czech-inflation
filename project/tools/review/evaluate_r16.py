"""Read-only R16 scores and CNB replay from frozen predictions.

All writes stay inside EXPERIMENT/evaluation. No fitting or network imports.
R15 scoring helpers are reused with explicit rosters; their frozen defaults and
pipeline-only comparison scopes are never changed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("_frozen_r15_evaluator", Path(__file__).with_name("evaluate_r15.py"))
prior = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prior)

BASE = "STABLE_PIPELINE_R14B"
FAST = "STATE_FAST_R15"
CONTROLS = ("INDEPENDENT_BRIDGE", BASE, "STABLE_LOCAL_CORE_R14B", FAST, "RF_RESIDUAL_R15")
NEW_MODELS = ("DAMPED_P80_Q001_R16", "DAMPED_P80_Q010_R16", "DAMPED_P95_Q001_R16", "DAMPED_P95_Q010_R16",
              "DAMPED_ADAPT_R16", "TRANSMISSION_OWN_R16", "TRANSMISSION_SERVICES_R16", "TRANSMISSION_GOODS_R16",
              "TRANSMISSION_BOTH_R16", "BLEND_DAMPED_TRANSMISSION_R16")
ROSTER = (*CONTROLS, *NEW_MODELS)
KEYS = ["origin", "h", "model"]
METRICS = prior.METRICS
LABELS = dict(zip(ROSTER, ("Independent bridge", "Stable pipeline", "Current core", "State · fast", "Residual forest",
    "Damped · .80 / .001", "Damped · .80 / .010", "Damped · .95 / .001", "Damped · .95 / .010", "Damped · adaptive",
    "Transmission · own", "Transmission · services", "Transmission · goods", "Transmission · both", "Damped + transmission")))


def comparison_scopes(models):
    yield "all_models_common", list(models), [b for b in (BASE, FAST) if b in models]
    for label, benchmark in (("pipeline", BASE), ("fast", FAST)):
        if benchmark in models:
            for model in models:
                if model != benchmark:
                    yield f"paired_{label}_{model}", [benchmark, model], [benchmark]


def score_tables(frame, models=ROSTER, metrics=METRICS):
    """All-model intersection plus separately paired FAST and pipeline support."""
    rows, differences = [], []
    for scope, selected, benchmarks in comparison_scopes(models):
        for metric, (prediction, actual) in metrics.items():
            common = prior.matched_rows(frame[frame.h.gt(0)], selected, prediction, actual)
            for h in range(1, 13):
                group = common[common.h.eq(h)]
                for sample, mask in prior.samples(group).items():
                    for model in selected:
                        own = group.loc[mask & group.model.eq(model)]
                        rows.append(dict(scope=scope, sample=sample, metric=metric, h=h, model=model,
                                         **prior.error_stats(own[prediction] - own[actual])))
                for benchmark in benchmarks:
                    base = group[group.model.eq(benchmark)][["origin", prediction]].rename(columns={prediction: "baseline"})
                    for model in selected:
                        if model == benchmark:
                            continue
                        own = group[group.model.eq(model)].merge(base, on="origin", validate="one_to_one")
                        for r in own.to_dict("records"):
                            e, b = r[prediction] - r[actual], r["baseline"] - r[actual]
                            differences.append(dict(scope=scope, metric=metric, origin=r["origin"], target=r["target"], h=h,
                                model=model, benchmark=benchmark, forecast=r[prediction], baseline=r["baseline"], actual=r[actual],
                                loss_difference=e**2-b**2, absolute_loss_difference=abs(e)-abs(b)))
    columns = ["scope", "metric", "origin", "target", "h", "model", "benchmark", "forecast", "baseline", "actual", "loss_difference", "absolute_loss_difference"]
    return pd.DataFrame(rows), pd.DataFrame(differences, columns=columns)


def scoped_summary(function, *args, models=ROSTER, **kwargs):
    """Retain only each helper's explicit-roster common result.

    R15's extra pipeline pair outputs cannot be used for FAST comparisons.
    They are discarded; no module global or default is mutated.
    """
    collections = None
    for scope, selected, _ in comparison_scopes(models):
        result = function(*args, models=selected, **kwargs)
        parts = result if isinstance(result, tuple) else (result,)
        if collections is None:
            collections = [[] for _ in parts]
        for collection, part in zip(collections, parts):
            if "scope" in part:
                part = part[part.scope.eq("all_models_common")].assign(scope=scope)
            collection.append(part)
    output = tuple(pd.concat(parts, ignore_index=True) for parts in collections)
    return output if len(output) > 1 else output[0]


def signal_scores(projections, broad, origins):
    """Evaluate saved projections against own-origin annual-signal persistence.

    Outcomes are mean future *annual log* inflation over each full band. Warmup
    forecasts remain fitting inputs but are excluded from the outer scoreboard.
    """
    keys = ["origin", "signal", "band"]
    data = projections[projections.stage.eq("signal") & projections.origin.isin(origins)].copy()
    prior.unique(data, keys)
    if not broad.index.is_unique:
        raise ValueError("Duplicate broad signal month")
    broad_log = 100 * np.log1p(broad / 100)
    current = [broad_log[r.signal].get(pd.Period(r.origin, "M") - 1, np.nan) for r in data.itertuples()]
    prior.assert_close(data.current_z, current, "current signal annual log")
    # Missing selected projections remain unavailable, including failed fits.
    made = np.isfinite(data.projected_z)
    prior.assert_close(data.loc[made, "projected_z"], (data.current_z + data.predicted_change)[made], "projected signal identity")
    grid = pd.MultiIndex.from_product([sorted(origins), ("services", "goods"), range(4)], names=keys).to_frame(index=False)
    ledger = grid.merge(data, on=keys, how="left", validate="one_to_one", indicator=True)
    ledger["row_present"] = ledger._merge.eq("both")
    ledger = ledger.drop(columns="_merge")
    actual, targets = [], []
    for r in ledger.itertuples():
        o = pd.Period(r.origin, "M")
        months = pd.period_range(o + 3 * r.band + 1, o + 3 * r.band + 3, freq="M")
        vals = broad_log[r.signal].reindex(months).to_numpy(float)
        actual.append(float(vals.mean()) if np.isfinite(vals).all() else np.nan)
        targets.append(str(months[-1]))
    ledger["target"] = targets
    ledger["actual_z"] = actual
    ledger["unit"] = "annual_log_pp"
    ledger["included"] = np.isfinite(ledger[["current_z", "projected_z", "actual_z"]]).all(axis=1)
    ledger["reason"] = np.where(ledger.included, "included", np.where(~ledger.row_present, "missing_projection_row",
        np.where(~np.isfinite(ledger.actual_z), "incomplete_actual_band", "unavailable_projection")))
    ledger["projection_error"] = ledger.projected_z - ledger.actual_z
    ledger["persistence_error"] = ledger.current_z - ledger.actual_z
    ledger["squared_loss_difference"] = ledger.projection_error**2 - ledger.persistence_error**2
    ledger["absolute_loss_difference"] = abs(ledger.projection_error) - abs(ledger.persistence_error)
    rows = []
    for (signal, band), group in ledger.groupby(["signal", "band"]):
        for sample, mask in prior.samples(group).items():
            own = group.loc[mask & group.included]
            for model, error in (("selected_projection", "projection_error"), ("annual_signal_persistence", "persistence_error")):
                rows.append(dict(signal=signal, band=band, sample=sample, model=model, unit="annual_log_pp",
                    scope="projection_persistence_common", n_intended=int(mask.sum()), **prior.error_stats(own[error])))
    return ledger, pd.DataFrame(rows)


def cnb_leave_one_report_out(pairs):
    """Omit every report in turn; preserve forecasts and original paired support."""
    rows = []
    for sample, data in (("full", pairs), ("reports_2024plus", pairs[pairs.report_date.ge("2024-01-01")])):
        for (clock, model), group in data.groupby(["clock", "model"]):
            full = prior.error_stats(group.error)
            full_cnb = prior.error_stats(group.realised_cnb_error)
            for omitted in sorted(group.report_date.unique()):
                own = group[group.report_date.ne(omitted)]
                stats, cnb = prior.error_stats(own.error), prior.error_stats(own.realised_cnb_error)
                rows.append(dict(sample=sample, clock=clock, model=model, omitted_report=omitted,
                    **stats, report_count=own.report_date.nunique(), unique_target_quarters=own.quarter.nunique(),
                    cnb_rmse=cnb["rmse"], cnb_mae=cnb["mae"], rmse_gain_vs_cnb=cnb["rmse"]-stats["rmse"],
                    mae_gain_vs_cnb=cnb["mae"]-stats["mae"], full_rmse_gain_vs_cnb=full_cnb["rmse"]-full["rmse"],
                    full_mae_gain_vs_cnb=full_cnb["mae"]-full["mae"]))
    return pd.DataFrame(rows, columns=["sample", "clock", "model", "omitted_report", "n", "mae", "rmse", "bias", "report_count",
        "unique_target_quarters", "cnb_rmse", "cnb_mae", "rmse_gain_vs_cnb", "mae_gain_vs_cnb", "full_rmse_gain_vs_cnb", "full_mae_gain_vs_cnb"])


def coefficient_diagnostics(fits, origins):
    rows = []
    for fit in fits:
        metadata = {k: fit.get(k) for k in ("origin", "stage", "family", "band", "config", "status", "converged", "n_train", "lambda_value")}
        metadata["outer_origin"] = fit.get("origin") in origins
        values = dict(fit.get("coefficients", {}))
        if fit.get("intercept") is not None:
            values["penalized_constant"] = fit["intercept"]
        for feature, value in values.items():
            constant = feature == "penalized_constant"
            scale = 1. if constant else fit.get("scales", {}).get(feature, np.nan)
            mean = 0. if constant else fit.get("means", {}).get(feature, np.nan)
            raw = value / scale if np.isfinite(scale) and scale > 0 else np.nan
            annual = raw / 12 if fit.get("stage") == "core" and feature in ("services_projection", "goods_projection") else np.nan
            rows.append(dict(**metadata, feature=feature, value=value, training_mean=mean, training_scale=scale,
                raw_predictor_coefficient=raw, annual_signal_change_coefficient=annual))
    columns = ["origin", "stage", "family", "band", "config", "status", "converged", "n_train", "lambda_value", "outer_origin", "feature",
               "value", "training_mean", "training_scale", "raw_predictor_coefficient", "annual_signal_change_coefficient"]
    details = pd.DataFrame(rows, columns=columns)
    if details.empty:
        return details, pd.DataFrame(columns=["stage", "family", "band", "feature", "n", "mean", "mean_abs"])
    own = details[details.outer_origin].assign(absolute_value=lambda x: abs(x.value))
    groups = own.groupby(["stage", "family", "band", "feature"]).agg(n=("value", "size"), mean=("value", "mean"),
        mean_abs=("absolute_value", "mean"), raw_predictor_mean=("raw_predictor_coefficient", "mean"),
        annual_signal_change_mean=("annual_signal_change_coefficient", "mean")).reset_index()
    return details, groups


def verify_components(native, base_native):
    prior.unique(native)
    base = base_native[base_native.model.eq(BASE)]
    prior.unique(base)
    merged = native.merge(base, on=["origin", "h"], how="left", suffixes=("", "_pipeline"), validate="many_to_one", indicator=True)
    if not merged._merge.eq("both").all():
        raise ValueError("New native row has no frozen pipeline key")
    checks = {"h0_max": prior.assert_close(merged.loc[merged.h.eq(0), "mm_forecast"],
        merged.loc[merged.h.eq(0), "mm_forecast_pipeline"], "h0 unchanged"), "noncore_max": 0.}
    protected = [c for c in base if c.startswith("weight_") or c.startswith("value_") and c != "value_core"
                 or c.startswith("contribution_") and c != "contribution_core"]
    for col in protected:
        if col not in native:
            raise ValueError("Missing noncore native field: " + col)
        checks["noncore_max"] = max(checks["noncore_max"], prior.assert_close(merged[col], merged[col + "_pipeline"], "noncore " + col))
    checks["noncore_fields"] = protected
    return checks


def verify_forecast_exports(frame, native, archive, manifest):
    origins = sorted(frame.origin.unique())
    if int(manifest.get("origin_count", len(origins))) != len(origins):
        raise ValueError("R16 declared origin count differs from forecast export")
    if not set(origins).issubset(archive.origin.unique()):
        raise ValueError("Forecast origin outside frozen R15 outer calendar")
    expected_target = [str(pd.Period(o, "M")+int(h)) for o, h in zip(frame.origin, frame.h)]
    if not frame.target.eq(expected_target).all() or not frame.h.isin(range(13)).all():
        raise ValueError("Forecast target calendar differs from origin plus h")
    clocks = archive.drop_duplicates("origin").set_index("origin").as_of_utc
    if not frame.as_of_utc.eq(frame.origin.map(clocks)).all():
        raise ValueError("Forecast decision clock differs from frozen R15")
    exported = frame[frame.model.isin(NEW_MODELS)]
    paired = exported.merge(native, on=KEYS, how="outer", suffixes=("", "_native"), validate="one_to_one", indicator=True)
    if not paired._merge.eq("both").all():
        raise ValueError("Native headline export key support differs")
    return dict(native_headline_monthly_max=prior.assert_close(paired.mm_forecast, paired.mm_forecast_native, "native headline monthly path"))


def support_comparison(frame, r15_frame, metrics=METRICS):
    rows = []
    for metric, (prediction, actual) in metrics.items():
        if prediction not in r15_frame or actual not in r15_frame:
            continue
        new = prior.matched_rows(frame[frame.h.gt(0)], ROSTER, prediction, actual)
        old = prior.matched_rows(r15_frame[r15_frame.h.gt(0)], prior.ROSTER, prediction, actual)
        for h in range(1, 13):
            a, b = new[new.h.eq(h)], old[old.h.eq(h)]
            for sample in prior.samples(a):
                ao = set(a.loc[prior.samples(a)[sample], "origin"])
                bo = set(b.loc[prior.samples(b)[sample], "origin"])
                rows.append(dict(metric=metric, h=h, sample=sample, r16_n=len(ao), r15_n=len(bo),
                    common_n=len(ao & bo), r16_only_n=len(ao - bo), r15_only_n=len(bo - ao),
                    r16_only_origins="|".join(sorted(ao - bo)), r15_only_origins="|".join(sorted(bo - ao))))
    return pd.DataFrame(rows)


def write_replay(path, data, template):
    """Use the original renderer, adapting its R15 text only in the new file."""
    prior.write_replay(path, data, template)
    html = Path(path).read_text(encoding="utf-8")
    for before, after in (("cnb-rounds-r15-visible-v1", "cnb-rounds-r16-visible-v1"),
                          ("complete 14-model roster", "complete 15-model roster"),
                          ("Czech CPI · R15 ·", "Czech CPI · R16 ·"),
                          ("<title>CNB Rounds Replayed</title>", "<title>CNB Rounds Replayed · R16 · historical</title>")):
        html = html.replace(before, after)
    Path(path).write_text(html, encoding="utf-8")


def replay_data(frame, cnb, actual, pairs, clocks):
    colors = ["#1F5DB4", "#24958A", "#0A7568", "#14496E", "#D4700C", "#98AFC1", "#6C91AA", "#6D71B5",
              "#47439A", "#7047A5", "#A086BA", "#A34683", "#A77422", "#C34F34", "#433B32"]
    defaults = {FAST, "STABLE_LOCAL_CORE_R14B", "DAMPED_ADAPT_R16", "TRANSMISSION_BOTH_R16"}
    series = [dict(id="realised", label="Realised · current vintage", kind="realised", color="--realised", width=2.4, default=True),
              dict(id="cnb", label="CNB published forecast", kind="cnb", color="--cnb", width=2, default=True)]
    series += [dict(id=m, label=LABELS[m], short=LABELS[m], kind="model", color=f"--r16-{i}", hex=colors[i], width=2.,
                    default=m in defaults, dash="5 3" if m in CONTROLS else "") for i, m in enumerate(ROSTER)]
    reports = {"report": [], "cutoff": []}
    selected = cnb[cnb.is_forecast.astype(str).str.lower().eq("true") & cnb.report_date.ge("2022-01-01")]
    for clock in clocks.to_dict("records"):
        if clock["origin"] is None:
            continue
        mode, date, origin = clock["clock"], clock["report_date"], clock["origin"]
        g = selected[selected.report_date.eq(date)].sort_values("quarter")
        if g.empty:
            continue
        o, quarter = pd.Period(origin, "M"), pd.Period(date, "Q")
        start, end = (quarter - 2).asfreq("M", "start"), pd.Period(g.quarter.iloc[-1], "Q").asfreq("M", "end")
        paths, quarter_points = {}, {}
        own = frame[frame.origin.eq(origin)]
        for model in ROSTER:
            mg = own[own.model.eq(model)].sort_values("h")
            path = dict(zip(mg.target, mg.yy_exante))
            anchor = actual.get(o - 1, np.nan)
            points = [[str(o - 1), float(anchor)]] if np.isfinite(anchor) else []
            for h in range(13):
                value = path.get(str(o + h), np.nan)
                if not np.isfinite(value):
                    break
                points.append([str(o + h), float(value)])
            paths[model] = points
            quarter_points[model] = [[q, v] for q in g.quarter if np.isfinite(v := prior.quarter_value(q, o, path, actual))]
        score_rows = pairs[pairs.clock.eq(mode) & pairs.report_date.eq(date)]
        score_quarters = sorted(score_rows.quarter.unique())
        score = dict(n=len(score_quarters), quarters=score_quarters, mae={m: float(abs(z.error).mean()) for m, z in score_rows.groupby("model")})
        season = str(g.season.iloc[0]).capitalize() if "season" in g else {1: "Winter", 2: "Spring", 3: "Summer", 4: "Autumn"}[quarter.quarter]
        reports[mode].append(dict(id=date + "-" + mode, report_date=date, cutoff_date=clock["cutoff_date"], origin=origin,
            origin_clock=pd.Timestamp(clock["as_of_utc"]).tz_convert("Europe/Prague").strftime("%Y-%m-%d %H:%M"),
            season=season, season_cs={"Winter": "Zima", "Spring": "Jaro", "Summer": "Léto", "Autumn": "Podzim"}.get(season, ""),
            year=int(date[:4]), window=dict(start=str(start), end=str(end)),
            cnb=[dict(quarter=r.quarter, value=float(r.value)) for r in g.itertuples()],
            realised_quarters=[dict(quarter=q, value=v) for q in g.quarter if np.isfinite(v := prior.quarter_actual(q, actual))],
            paths=paths, quarter_points=quarter_points, score=score))
    method = [
        "Historical research replay. The latest frozen origin is July 2026, not a live September forecast. Current-vintage historical inputs have reconstructed release availability; these are not certified historical vintages.",
        "Report clock selects the last existing snapshot strictly before report-day midnight in Prague. Cutoff clock includes the whole CNB cutoff day. Both clocks are retained without accuracy-based selection.",
        "Each model quarter averages three annual CPI rates, using known history before the origin and forecasts from that single origin afterward. Annual CPI compounds monthly headline rates from the same origin. No later forecast is borrowed.",
        "Scores use identical complete report/quarter support for all fifteen models and CNB, regardless of visible checkboxes. Repeated overlapping quarters across reports are dependent observations. Separate CSVs show cross-clock common support, pairwise FAST/pipeline comparisons and every-report omission sensitivity.",
        "A material CNB gain means its absolute error minus the model absolute error is at least 0.15 percentage points; a material loss is at most -0.15. Correct deviation direction can overshoot and lose.",
        "Damped slopes and separate services/goods transmission replace only core at h1..12. HARD_BASE h0, every noncore path and weights stay fixed. R15 FAST was chosen as the residual baseline after examining R15; this research sample is not untouched.",
        "Underlying core diagnostics subtract the same saved R15 seasonal pattern for each origin, then annualize four three-month log-core bands. Exact peaks/troughs require two opposite changes of at least 0.5 percentage points. Headline direction can reflect base effects; it is a separate test.",
        "Signal scores concern annual log goods/services inflation, with own-origin annual-signal persistence as benchmark. Dividing projected annual log changes by twelve normalizes a core predictor; it does not create observed monthly component inflation or official basket weights. Corrections are constant within each three-month band.",
        "Visible defaults are FAST, current core, adaptive damped slope and both-signal transmission, plus actual and CNB. All fifteen models remain selectable and scored. This display choice does not tune coefficients, model choices or the fixed half-and-half blend. No CNB or outer outcome is used by the evaluator to refit or select anything.",
    ]
    return dict(series=series, reportsByClock=reports, realised={str(k): float(v) for k, v in actual.dropna().items()},
                method=method, title="CNB Rounds Replayed · R16 · historical", vintage="current-vintage simulated historical")


def evaluate(experiment, root=ROOT):
    experiment, root = Path(experiment).resolve(), Path(root).resolve()
    out = experiment / "evaluation"
    read = lambda p: pd.read_csv(p, float_precision="round_trip")
    read_json = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    archive = root / "output/research_r15"
    integration = root / "output/research_r14b/integration"
    files = [p for p in experiment.iterdir() if p.is_file() and p.suffix in (".csv", ".json")]
    files += [archive / p for p in ("forecasts.csv", "native_forecasts.csv", "states.json")]
    files += [integration / "native_forecasts.csv"]
    files += [root / p for p in ("output/independent_path_frozen_inputs.csv", "tests/fixtures/cleanup/cnb_core_mm.csv",
        "data/core_split/broad_yoy.csv", "data/cnb_mpr_cpi_quarterly.csv", "tools/cnb_rounds/cnb_rounds_template.html")]
    files += [Path(__file__).resolve(), Path(prior.__file__).resolve()]
    hashes = {str(p): sha(p) for p in files}
    checks = {}
    for folder in (archive, experiment):
        manifest_path = folder / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = read_json(manifest_path)
        verified = 0
        for key, parent in (("inputs", root), ("outputs", folder)):
            for name, digest in manifest.get(key, {}).items():
                path = parent / name
                if sha(path) != digest:
                    raise ValueError("Frozen manifest mismatch: " + str(path))
                hashes[str(path)] = digest
                verified += 1
        checks[folder.name + "_manifest_hashes_verified"] = verified
        if folder == experiment:
            if tuple(manifest.get("models", NEW_MODELS)) != NEW_MODELS or tuple(manifest.get("controls", CONTROLS)) != CONTROLS:
                raise ValueError("R16 declaration roster differs from evaluator roster")
    frame, native, cp = [read(experiment / p) for p in ("forecasts.csv", "native_forecasts.csv", "core_predictions.csv")]
    for data in (frame, native, cp):
        prior.unique(data)
    if not set(frame.model).issubset(ROSTER) or not set(cp.model).issubset(NEW_MODELS):
        raise ValueError("Undeclared R16 forecast model")
    origins = sorted(frame.origin.unique())
    old = read(archive / "forecasts.csv")
    run_manifest = read_json(experiment / "manifest.json") if (experiment / "manifest.json").exists() else {}
    checks.update(verify_forecast_exports(frame, native, old, run_manifest))
    controls = old[old.model.isin(CONTROLS) & old.origin.isin(origins)]
    overlap = frame[frame.model.isin(CONTROLS)].merge(controls, on=KEYS, suffixes=("", "_frozen"), how="outer", validate="one_to_one", indicator=True)
    if not overlap._merge.eq("both").all():
        raise ValueError("Control key support differs from frozen R15 controls")
    for col in ("mm_forecast", "yy_exante", "mm_actual", "yy_actual", "cumulative_log_forecast", "cumulative_log_actual"):
        checks["control_" + col + "_max"] = prior.assert_close(overlap[col], overlap[col + "_frozen"], "control " + col)
    if not overlap.as_of_utc.eq(overlap.as_of_utc_frozen).all() or not overlap.target.eq(overlap.target_frozen).all():
        raise ValueError("Control target or decision clock changed")
    # Use the exact saved controls after reconciling the runner's copied values.
    frame = pd.concat([frame[frame.model.isin(NEW_MODELS)], controls], ignore_index=True)
    base_native = read(integration / "native_forecasts.csv")
    first_three = base_native[base_native.model.isin(CONTROLS[:3]) & base_native.origin.isin(origins)]
    old_native = read(archive / "native_forecasts.csv")
    last_two = old_native[old_native.model.isin(CONTROLS[3:]) & old_native.origin.isin(origins)]
    native = native[native.model.isin(NEW_MODELS)]
    checks.update(verify_components(native, first_three))
    all_native = pd.concat([native, first_three, last_two], ignore_index=True)
    prior.unique(all_native)
    checks["core_log_reconstruction_max"] = prior.assert_close(cp.core_log, 100*np.log1p(cp.core_mm/100), "core log reconstruction")
    native_join = cp.merge(native[[*KEYS, "value_core"]], on=KEYS, how="left", validate="one_to_one")
    checks["native_core_prediction_max"] = prior.assert_close(native_join.core_mm, native_join.value_core, "native core vs prediction")
    headline = prior.read_monthly(root / "output/independent_path_frozen_inputs.csv", "headline_mm")
    actual_yy = 100*np.expm1(np.log1p(headline/100).rolling(12).sum())
    core_actual = prior.read_monthly(root / "tests/fixtures/cleanup/cnb_core_mm.csv", "core")
    checks.update(prior.verify_arithmetic(frame, headline, actual_yy))
    frame = prior.attach_core(frame, all_native, cp, core_actual)
    cnb = read(root / "data/cnb_mpr_cpi_quarterly.csv")
    states = read_json(experiment / "states.json")
    old_states = read_json(archive / "states.json")
    for origin, state in states.items():
        if origin not in old_states or state.get("seasonal") != old_states[origin].get("seasonal"):
            raise ValueError("Saved R15 seasonal reference changed: " + origin)
    if not set(origins).issubset(states):
        raise ValueError("Missing outer-origin R15 seasonal reference")
    checks["seasonal_origins_verified"] = len(states)
    selections, fits = [read_json(experiment / p) for p in ("selections.json", "fits.json")]
    out.mkdir(parents=True, exist_ok=True)
    generated = []

    def csv(name, data):
        data.to_csv(out / name, index=False)
        generated.append(name)

    def dump(name, data):
        (out / name).write_text(json.dumps(prior.json_safe(data), indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
        generated.append(name)

    print("R16 evaluation: fixed monthly support, both benchmarks and integrity", flush=True)
    grid = pd.MultiIndex.from_product([origins, range(13), ROSTER], names=KEYS).to_frame(index=False)
    ledger = grid.merge(frame, on=KEYS, how="left", validate="one_to_one", indicator=True)
    ledger["row_present"] = ledger._merge.eq("both")
    ledger["target"] = [str(pd.Period(o, "M")+int(h)) for o, h in zip(ledger.origin, ledger.h)]
    for metric, (prediction, actual) in METRICS.items():
        ledger[metric+"_forecast_finite"] = np.isfinite(ledger[prediction])
        ledger[metric+"_actual_finite"] = np.isfinite(ledger[actual])
    status_cols = [c for c in ("status", "origin_status", "converged", "fallback_used") if c in all_native]
    ledger = ledger.drop(columns="_merge").merge(all_native[[*KEYS, *status_cols]], on=KEYS, how="left", validate="one_to_one")
    csv("coverage_ledger.csv", ledger)
    csv("forecast_core_outcomes.csv", frame)
    csv("forecast_failures.csv", ledger[~ledger.row_present | (ledger.h.gt(0) & ~ledger[[m+"_forecast_finite" for m in METRICS]].all(axis=1))])
    coverage_rows = []
    for sample, mask in prior.samples(ledger).items():
        for (model, h), group in ledger.loc[mask].groupby(["model", "h"]):
            for metric in METRICS:
                coverage_rows.append(dict(sample=sample, model=model, h=h, metric=metric, n_intended=len(group), n_rows_present=int(group.row_present.sum()),
                    n_forecasts=int(group[metric+"_forecast_finite"].sum()), n_actuals=int(group[metric+"_actual_finite"].sum()),
                    n_scoreable=int((group[metric+"_forecast_finite"] & group[metric+"_actual_finite"]).sum())))
    csv("coverage_summary.csv", pd.DataFrame(coverage_rows))
    scores, differences = score_tables(frame, models=ROSTER, metrics=METRICS)
    csv("scoreboard.csv", scores)
    csv("paired_loss_differences.csv", differences)
    # Reconstruct original R15 core metrics from its own native forecasts, not
    # from R16 outcomes or a previously written evaluation table.
    r15_native = pd.concat([old_native, base_native[base_native.model.isin(CONTROLS[:3])]], ignore_index=True)
    empty_predictions = old_native.iloc[:0][KEYS].assign(core_mm=pd.Series(dtype=float))
    old_core = prior.attach_core(old, r15_native, empty_predictions, core_actual)
    csv("r15_support_comparison.csv", support_comparison(frame, old_core))
    print("R16 evaluation: direction, saved-seasonal core turns and future revisions", flush=True)
    direction, direction_pairs = scoped_summary(prior.direction_tables, frame, actual_yy, models=ROSTER)
    csv("headline_direction_summary.csv", direction)
    csv("headline_direction_pairs.csv", direction_pairs)
    quarters = prior.adjacent_quarter_changes(frame, actual_yy)
    csv("headline_quarter_change_pairs.csv", quarters)
    csv("headline_quarter_change_summary.csv", scoped_summary(prior.change_summaries, quarters, "quarter", models=ROSTER))
    bands, changes, turns = prior.core_turn_diagnostics(frame, states)
    for name, data in (("underlying_core_bands.csv", bands), ("underlying_core_changes.csv", changes), ("underlying_core_turns.csv", turns)):
        csv(name, data)
    csv("underlying_core_change_summary.csv", scoped_summary(prior.change_summaries, changes, "band", models=ROSTER, threshold=.5))
    csv("underlying_core_turn_summary.csv", scoped_summary(prior.turn_summaries, turns, models=ROSTER))
    revisions = prior.revision_pairs(frame)
    csv("revision_pairs.csv", revisions)
    csv("revision_summary.csv", scoped_summary(prior.revision_summaries, revisions, models=ROSTER))
    print("R16 evaluation: signals, mapping coefficients and blocked uncertainty", flush=True)
    broad = read(root / "data/core_split/broad_yoy.csv")
    broad.index = pd.PeriodIndex(broad.iloc[:, 0], freq="M")
    signal_coverage, signal_board = signal_scores(read(experiment / "signal_projections.csv"), broad[["goods", "services"]], origins)
    csv("signal_coverage.csv", signal_coverage)
    csv("signal_scoreboard.csv", signal_board)
    csv("signal_paired_loss_differences.csv", signal_coverage[signal_coverage.included])
    coefficients, coefficient_groups = coefficient_diagnostics(fits, origins)
    csv("coefficient_feature_details.csv", coefficients)
    csv("coefficient_source_groups.csv", coefficient_groups)
    fast = last_two[last_two.model.eq(FAST)][["origin", "h", "value_core"]].copy()
    fast["fast_core_log"] = 100*np.log1p(fast.value_core/100)
    corrections = cp.merge(fast[["origin", "h", "fast_core_log"]], on=["origin", "h"], how="left", validate="many_to_one")
    corrections["correction_log"] = corrections.core_log-corrections.fast_core_log
    corrections["band"] = (corrections.h-1)//3+1
    csv("correction_paths.csv", corrections)
    correction_summary = []
    for (model, band), group in corrections.groupby(["model", "band"]):
        values = group.correction_log[np.isfinite(group.correction_log)]
        correction_summary.append(dict(model=model, band=band, n=len(values), mean=values.mean(), mean_abs=abs(values).mean(),
            p05=values.quantile(.05), median=values.median(), p95=values.quantile(.95), max_abs=abs(values).max()))
    csv("correction_distribution.csv", pd.DataFrame(correction_summary))
    selection_frame = pd.DataFrame(selections)
    selection_rows = []
    if not selection_frame.empty:
        selection_frame["band"] = selection_frame.band.astype(str)
        for sample, data in (("outer_origins", selection_frame[selection_frame.origin.isin(origins)]), ("all_saved_origins", selection_frame)):
            dist = data.groupby(["stage", "family", "band", "config", "reason"], dropna=False).size().rename("n").reset_index()
            dist["share_within_stage_family_band"] = dist.n/dist.groupby(["stage", "family", "band"]).n.transform("sum")
            selection_rows.append(dist.assign(sample=sample))
    csv("selected_config_distribution.csv", pd.concat(selection_rows, ignore_index=True) if selection_rows else pd.DataFrame(columns=["stage", "family", "band", "config", "reason", "n", "share_within_stage_family_band", "sample"]))
    fit_frame = pd.DataFrame(fits)
    status_rows = []
    if not fit_frame.empty:
        for sample, data in (("outer_origins", fit_frame[fit_frame.origin.isin(origins)]), ("all_saved_origins", fit_frame)):
            status_rows.append(data.groupby(["stage", "family", "band", "status", "converged"], dropna=False).size().rename("n").reset_index().assign(sample=sample))
    csv("fit_status_distribution.csv", pd.concat(status_rows, ignore_index=True) if status_rows else pd.DataFrame(columns=["stage", "family", "band", "status", "converged", "n", "sample"]))
    csv("fit_failures.csv", fit_frame.loc[~fit_frame.converged.fillna(False).astype(bool)] if not fit_frame.empty else pd.DataFrame(columns=["origin", "stage", "family", "band", "status"]))
    bootstrap = []
    for (scope, benchmark, model, metric, h), group in differences.groupby(["scope", "benchmark", "model", "metric", "h"]):
        for sample, mask in prior.samples(group).items():
            bootstrap.append(dict(scope=scope, benchmark=benchmark, model=model, metric=metric, h=h, sample=sample,
                **prior.block_bootstrap(group.loc[mask], block=12, draws=2000, seed=1509)))
    bootstrap = pd.DataFrame(bootstrap)
    csv("paired_block_bootstrap.csv", bootstrap)
    csv("headline_paired_block_bootstrap.csv", bootstrap[bootstrap.metric.eq("headline_yy")])
    signal_bootstrap = []
    for (signal, band), group in signal_coverage[signal_coverage.included].groupby(["signal", "band"]):
        for sample, mask in prior.samples(group).items():
            own = group.loc[mask].rename(columns={"squared_loss_difference": "loss_difference"})
            signal_bootstrap.append(dict(signal=signal, band=band, sample=sample, unit="annual_log_pp_squared",
                **prior.block_bootstrap(own, block=12, draws=2000, seed=1509)))
    csv("signal_paired_block_bootstrap.csv", pd.DataFrame(signal_bootstrap))
    print("R16 evaluation: both CNB clocks, every-report sensitivity and local replay", flush=True)
    pairs, cnb_coverage, clocks, projections = prior.cnb_comparison(frame, cnb, actual_yy, models=ROSTER)
    for name, data in (("cnb_pairs.csv", pairs), ("cnb_coverage.csv", cnb_coverage), ("cnb_clocks.csv", clocks), ("cnb_quarter_projections.csv", projections)):
        csv(name, data)
    both = pairs.groupby(["report_date", "quarter"]).clock.nunique()
    both = both.index[both.eq(2)]
    cross = pairs.set_index(["report_date", "quarter"]).loc[lambda x: x.index.isin(both)].reset_index()
    csv("cnb_cross_clock_matched_pairs.csv", cross)
    csv("cnb_summary.csv", pd.concat([prior.cnb_summaries(pairs), prior.cnb_summaries(cross, "cross_clock_common")], ignore_index=True))
    sensitivity = [cnb_leave_one_report_out(data).assign(scope=scope) for scope, data in (("within_clock_common", pairs), ("cross_clock_common", cross))]
    csv("cnb_leave_one_report_out.csv", pd.concat(sensitivity, ignore_index=True))
    paired_rows, paired_summary = [], []
    for scope, selected, _ in comparison_scopes(ROSTER):
        if scope == "all_models_common":
            continue
        own = prior.matched_rows(projections, [*selected, "cnb"], "forecast", "realised", keys=("clock", "report_date", "quarter"))
        paired_rows.append(own.assign(scope=scope))
        paired_summary.append(prior.cnb_summaries(own, scope=scope))
    csv("cnb_pairwise_pairs.csv", pd.concat(paired_rows, ignore_index=True))
    csv("cnb_pairwise_summary.csv", pd.concat(paired_summary, ignore_index=True))
    data = replay_data(frame, cnb, actual_yy, pairs, clocks)
    dump("replay_data.json", data)
    write_replay(out / "cnb_rounds_replayed_r16.html", data, root / "tools/cnb_rounds/cnb_rounds_template.html")
    generated.append("cnb_rounds_replayed_r16.html")
    definitions = dict(
        vintage="Frozen current-vintage historical inputs with reconstructed availability; pseudo-out-of-sample research, not historical-vintage certification or a prospective/live forecast. Latest frozen origin July 2026.",
        scope="No fitting, downloads, forecast repairs, tuning or model promotion. R15 FAST was selected as the R16 residual baseline after examining R15. Repeated historical experimentation means this is not an untouched holdout.",
        roster=ROSTER, benchmarks=[BASE, FAST], horizons="All frozen outer origins, h1..12; h0 retained for coverage and headline compounding. No outcome-based origin selection.",
        scores="RMSE=sqrt(mean(error squared)); MAE=mean(abs(error)); bias=mean(forecast-actual). Each metric/horizon uses finite forecast and actual intersection for every model in its declared scope.",
        support="all_models_common includes all fifteen models. paired_pipeline_MODEL contains only pipeline and MODEL; paired_fast_MODEL contains only FAST and MODEL. All-model losses are reported separately against each benchmark. The R15 support comparison reconstructs the original fourteen-model intersection independently; it never changes R16 support. Failures remain in coverage.",
        samples="Full; origins 2019-21; origins 2022-23; origins 2024+; recent target months from 2024-01. Band target is its final month. No ex-post shock exclusions.",
        headline="Annual CPI=100*expm1(sum of twelve monthly log rates), known history before the origin plus monthly forecasts from that same origin. Headline and core monthly rates are distinct. Cumulative headline logs sum h1 through h; a missing intermediate forecast propagates.",
        core="Original cnb_core_mm.csv monthly outcomes. Cumulative core is sum 100*log1p(core_mm/100) over h1 through h. No h0 core score. New component paths and all controls reconcile to their saved source forecasts.",
        direction="Headline h3/6/9/12 annual level versus latest known t-1 annual CPI: up >0.25pp; down <-0.25pp; otherwise flat. Wrong way requires opposite material calls. Calendar-quarter change diagnostics use same-origin quarterly averages and absolute actual change >0.25pp.",
        underlying_core="Four bands h1:3,4:6,7:9,10:12. Annualized SA log core=12*mean(100*log1p(core_mm/100)-origin's saved R15 seasonal[month]). The same seasonal vector is used for actual and every model. Material adjacent change >=0.5pp annualized. Exact peak/trough at band2/3 requires two opposite material adjacent changes. Hits, misses and false turns use fixed common support; no CNB core-forecast claim.",
        revisions="Consecutive calendar origins, identical forecast target, new h=old h-1. Finite annual-CPI forecast differences only. Realised outcomes never gate revision support; unobserved future targets remain included.",
        signals="Only outer experiment origins are scored. z=100*log1p(broad annual NSA rate/100), in annual log percentage points. Outcome is mean z over all three future band months; transform each month's annual rate before averaging. Saved projected_z competes with own-origin current_z persistence on identical finite support. Require every actual month; no inferred monthly services/goods rate. All warmup projections remain frozen training inputs, outside this scoreboard.",
        coefficients="Saved ridge coefficients multiply training-standardized predictors. Raw-predictor coefficient divides by saved training scale; penalized constant is retained. Core services/goods predictors are saved annual-log change/12; annual_signal_change_coefficient additionally divides the raw coefficient by12. This is a predictive unit translation, not an official weight, observed monthly partition, or causal pass-through. Detail rows retain stage and all saved origins; summaries select the outer origins.",
        corrections="Monthly log-core predictions minus saved R15 FAST at the same origin/h. Selection/fit bands are 0..3; core-path diagnostics are 1..4. Signal-generated regressors are saved own-origin forecasts, never realised future signals. Corrections are constant within each three-month band; fixed blend averages adaptive slope and both-signal transmission at half weights in monthly log units.",
        cnb_report_clock="Latest existing as_of_utc strictly before report_date midnight Europe/Prague.",
        cnb_cutoff_clock="Latest existing as_of_utc strictly before next-day midnight Europe/Prague, including the entire cutoff date.",
        cnb_support="Forecast quarters in reports from 2022 onward. Quarter value is mean of three annual rates: known history before the chosen origin, one chosen forecast origin afterward. All actual/CNB/fifteen-model values must be finite within each clock. Cross-clock table intersects report/quarter support over both clocks. Pairwise tables separately require only the named two models plus CNB. Repeated overlapping quarters are dependent.",
        cnb_gain="Absolute error gain=abs(CNB-actual)-abs(model-actual). Material gain>=0.15pp; material loss<=-0.15pp (1e-12 tolerance). Correct model-CNB deviation sign alone need not improve accuracy.",
        cnb_sensitivity="Each eligible report is omitted in turn from the originally fixed within-clock or cross-clock paired sample. Recompute model/CNB RMSE and MAE and their differences for full and 2024+ reports. No forecasts, choices, controls or mixture weights change.",
        bootstrap="Paired mean squared-loss difference=model minus named benchmark; negative favours model. All metrics/horizons and signal bands use moving twelve-consecutive-calendar-origin blocks,2000draws,seed1509,2.5/97.5percentile intervals. Never bridge a gap; suppress intervals when any support origin cannot enter a full block. Descriptive dependent-sample uncertainty, not independent trials or a promotion rule.",
        replay="Original local CNB Rounds template adapted only in the new artifact. JS/CSS/data embedded; remote font links removed. Clock and round selectors; all fifteen selectable model checkboxes affect visibility only. Full-roster scores are fixed. Defaults FAST,current core,adaptive damped,both transmission plus actual/CNB; these are presentation choices.")
    dump("definitions.json", definitions)
    checks["outer_origin_count"] = len(origins)
    checks["roster_count"] = len(ROSTER)
    for path, digest in hashes.items():
        if sha(path) != digest:
            raise ValueError("Input changed during evaluation: " + path)
    checks["all_inputs_unchanged"] = True
    dump("checks.json", checks)
    dump("input_manifest.json", dict(created_at_utc=datetime.now(timezone.utc).isoformat(), inputs=hashes,
        evaluator=str(Path(__file__).resolve()), evaluator_sha256=sha(__file__), shared_r15_evaluator_sha256=sha(prior.__file__),
        command=f'python tools/review/evaluate_r16.py --experiment "{experiment}"', packages=dict(numpy=np.__version__, pandas=pd.__version__),
        origin_count=len(origins), model_count=len(ROSTER), outputs={name: sha(out / name) for name in generated}))
    print(f"R16 evaluation finished: {out}", flush=True)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    args = parser.parse_args(argv)
    evaluate(args.experiment)


if __name__ == "__main__":
    main()
