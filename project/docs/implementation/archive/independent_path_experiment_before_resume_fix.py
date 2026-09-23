"""Fixed corrected hard-data path roster; retrospective research, no tuning.

python independent_path_experiment.py [--resume] [--long-extra]
Every completed origin is checkpointed. --limit is for a separate pilot prefix.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from models.bvar import minnesota_bvar_forecast
from models.path_inputs import compound_path, direct_training_data, prepare_origin
from models.trend_gap import fit_forecast, seasonal_means

ROOT = Path(__file__).resolve().parent
PRIMARY = ["TARGET_ML", "TARGET_FX_ML", "TARGET_U_FX_ML", "BVAR_U_FX", "RF_U_FX", "NAIVE"]
REFERENCES = ["F1B_STORED_REF", "SURVEY_TREND_STORED_REF"]
HORIZONS = (1, 3, 6, 12)
RF_OPTIONS = dict(n_estimators=200, min_samples_leaf=5, max_features=1 / 3, random_state=42, n_jobs=1)


def model_path(result):
    """The underlying models forecast last+h; path h counts from last+1."""
    return {h: float(result.get("mm", {}).get(h + 1, np.nan)) for h in range(13)}


def common_metrics(frame, models, scope, sample):
    """Common rows per horizon/case, alongside own and intended coverage."""
    rows = []
    for h in HORIZONS:
        data = frame.loc[(frame.h == h) & frame.model.isin(models)].copy()
        if data.empty:
            continue
        for case in ("exante", "conditional"):
            field = f"yy_{case}"
            wide = data.pivot(index="origin", columns="model", values=field).reindex(columns=models)
            actual = data.drop_duplicates("origin").set_index("origin")["yy_actual"]
            common = wide.index[np.isfinite(wide.to_numpy()).all(axis=1) & np.isfinite(actual.reindex(wide.index))]
            for model in models:
                own = data.loc[data.model == model].set_index("origin")
                eligible = own.loc[np.isfinite(own.yy_actual)]
                score = own.reindex(common)
                ye = score[field] - score.yy_actual
                me = score.mm_forecast - score.mm_actual
                rows.append(dict(scope=scope, sample=sample, h=h, case=case, model=model,
                    n_intended_origins=len(own), n_available_targets=len(eligible),
                    n_own_forecasts=int(np.isfinite(eligible[field]).sum()), n_common=len(common),
                    yy_rmse=float(np.sqrt(np.mean(ye ** 2))) if len(common) else np.nan,
                    yy_mae=float(np.mean(np.abs(ye))) if len(common) else np.nan,
                    yy_bias=float(np.mean(ye)) if len(common) else np.nan,
                    mm_rmse=float(np.sqrt(np.mean(me ** 2))) if len(common) else np.nan,
                    mm_mae=float(np.mean(np.abs(me))) if len(common) else np.nan,
                    mm_bias=float(np.mean(me)) if len(common) else np.nan))
    return pd.DataFrame(rows)


def _json_default(value):
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    if isinstance(value, (pd.Timestamp, pd.Period, Path)):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(type(value).__name__)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _naive(history, target):
    values = history.loc[history.index.month == target.month]
    return float(values.tail(5).mean()) if len(values) >= 3 else float(history.tail(24).mean())


def _fit_one_origin(inputs, origin, long_only=False):
    y = inputs["headline"]
    drivers = inputs["drivers"]
    paths, diagnostics = {}, {}
    specs = {"TARGET_ML": [], "TARGET_FX_ML": ["fx12_l3"],
             "TARGET_U_FX_ML": ["un_d", "fx12_l3"]}
    if long_only:
        specs = {"TARGET_ML": []}
    for model, columns in specs.items():
        started = time.monotonic()
        try:
            if "un_d" in columns and inputs["unemployment"].empty:
                raise ValueError("No historical unemployment vintage at this origin")
            kw = {}
            if columns:
                kw = dict(x_hist=drivers.loc[:y.index[-1], columns],
                          x_future=drivers.loc[y.index[-1] + 1:, columns])
            result = fit_forecast(y, range(1, 14), anchored=True, robust_seasonal=True, **kw)
            paths[model] = model_path(result)
            diagnostics[model] = {k: v for k, v in result.items() if k != "mm"}
            diagnostics[model]["status"] = result.get("fit_diagnostics", {}).get("status", "unknown")
            if (not np.isfinite(list(paths[model].values())).all()
                    and diagnostics[model]["status"] in ("converged", "converged_retry", "fallback_start_params")):
                diagnostics[model]["status"] = "failed_nonfinite_projection"
        except Exception as exc:
            paths[model] = dict.fromkeys(range(13), np.nan)
            diagnostics[model] = dict(status="failed", converged=False, fallback_used=False,
                                      error=f"{type(exc).__name__}: {exc}")
        diagnostics[model]["elapsed_seconds"] = time.monotonic() - started
    if not long_only:
        started = time.monotonic()
        try:
            if inputs["unemployment"].empty:
                raise ValueError("No historical unemployment vintage at this origin")
            seas = seasonal_means(y, robust=True)
            panel = pd.DataFrame({"headline_sa": y - np.array([seas[m.month] for m in y.index])})
            panel = panel.join(drivers.loc[y.index, ["un_d", "fx12_l3"]])
            forecasts, details = {}, {}
            for h in range(13):
                result = minnesota_bvar_forecast(panel, "headline_sa", h + 1, p=3,
                    lambda1=.2, lambda3=1., return_diagnostics=True)
                forecasts[h] = result["forecast"] + seas[(origin + h).month]
                details[h] = result
            paths["BVAR_U_FX"] = forecasts
            diagnostics["BVAR_U_FX"] = dict(status="estimated", converged=True,
                fallback_used=any(d["fallback_used"] for d in details.values()), horizon_details=details)
        except Exception as exc:
            paths["BVAR_U_FX"] = dict.fromkeys(range(13), np.nan)
            diagnostics["BVAR_U_FX"] = dict(status="failed", converged=False, fallback_used=False,
                                               error=f"{type(exc).__name__}: {exc}")
        diagnostics["BVAR_U_FX"]["elapsed_seconds"] = time.monotonic() - started
        started = time.monotonic()
        forecasts, details = {0: np.nan}, {}
        for h in range(1, 13):
            try:
                x, target, now = direct_training_data(y, drivers, origin, h)
                if len(x) < 96 or inputs["unemployment"].empty:
                    raise ValueError("Insufficient historical direct-model inputs")
                model = RandomForestRegressor(**RF_OPTIONS)
                model.fit(x.to_numpy(), target.to_numpy())
                forecasts[h] = float(model.predict(now.to_numpy().reshape(1, -1))[0])
                details[h] = dict(status="estimated", n=len(x), last_training_origin=str(x.index[-1]),
                                  last_training_target=str(x.index[-1] + h))
            except Exception as exc:
                forecasts[h] = np.nan
                details[h] = dict(status="failed", error=f"{type(exc).__name__}: {exc}")
        paths["RF_U_FX"] = forecasts
        okay = np.isfinite([forecasts[h] for h in range(1, 13)]).all()
        diagnostics["RF_U_FX"] = dict(status="estimated" if okay else "failed", converged=bool(okay),
            fallback_used=False, horizon_details=details, elapsed_seconds=time.monotonic() - started)
    paths["NAIVE"] = {h: _naive(y, origin + h) for h in range(13)}
    diagnostics["NAIVE"] = dict(status="seasonal_mean_last_five", converged=True, fallback_used=False)
    return paths, diagnostics


def forecast_origin(headline, fx_levels, origin, as_of, h0,
                    vintage_path=None, long_only=False):
    """Reusable calculation with explicit frames, aware clock and h0 nowcast.

    Headline must already respect its release calendar; any values at/after
    origin are additionally excluded. FX is cut at the clock's last completed
    month. Unemployment is selected from the named historical archive. No DB,
    survey series, global live data or output files are read by this function.
    Pass h0=None only for the separately labelled long-only historical control.
    Returned ``paths`` map model -> {path_h: monthly_percent}; ``native_paths``
    preserve unmodified model h0 estimates, and all diagnostics remain visible.
    """
    from data.vintages import DEFAULT_UNEMPLOYMENT_PATH
    origin = pd.Period(origin, "M")
    inputs = prepare_origin(headline, fx_levels, origin, as_of,
                            DEFAULT_UNEMPLOYMENT_PATH if vintage_path is None else vintage_path)
    native, diagnostics = _fit_one_origin(inputs, origin, long_only=long_only)
    if h0 is None and long_only:
        h0 = native["TARGET_ML"][0]
    elif h0 is None or not np.isfinite(h0):
        raise ValueError("A finite independent h0 is required")
    paths = {model: {**path, 0: float(h0)} for model, path in native.items()}
    return dict(origin=str(origin), h0=float(h0), history=inputs["headline"],
                paths=paths, native_paths=native, diagnostics=diagnostics, inputs=inputs["metadata"])


def _save_summary(frame, prefix):
    outputs = []
    primary = frame.loc[frame.origin >= "2019-02"]
    scopes = [("independent_common", PRIMARY), ("including_references_common", PRIMARY + REFERENCES)]
    for sample, selected in [("2019_plus", primary),
        ("crisis_2020_2023_targets", primary.loc[(primary.target >= "2020-01") & (primary.target <= "2023-12")]),
        ("2024_plus_targets", primary.loc[primary.target >= "2024-01"])]:
        for scope, models in scopes:
            outputs.append(common_metrics(selected, models, scope, sample))
    older = frame.loc[frame.origin < "2019-02"]
    if len(older):
        outputs.append(common_metrics(older, ["TARGET_ML", "NAIVE"], "long_baseline_common", "2008_2019jan_origins"))
        crisis = older.loc[(older.target >= "2008-01") & (older.target <= "2009-12")]
        outputs.append(common_metrics(crisis, ["TARGET_ML", "NAIVE"], "long_baseline_common", "2008_2009_targets"))
    summary = pd.concat(outputs, ignore_index=True)
    summary.to_csv(f"{prefix}summary.csv", index=False)
    fits = frame.loc[frame.h == 1, ["origin", "model", "status", "converged", "fallback_used"]]
    fits.groupby(["model", "status", "converged", "fallback_used"], dropna=False).size().reset_index(name="origins").to_csv(
        f"{prefix}fit_status.csv", index=False)
    return summary


def main(argv=None):
    import cz_struct as S
    from path_experiment import _eve
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="independent_path_")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--long-extra", action="store_true")
    args = parser.parse_args(argv)
    if "/" in args.prefix or "\\" in args.prefix or not args.prefix.startswith("independent_path_"):
        raise ValueError("Prefix must begin independent_path_ and contain no directories")
    prefix = ROOT / "output" / args.prefix
    h0_path = ROOT / "output" / "independent_nowcast_forecasts.csv"
    h0 = pd.read_csv(h0_path).set_index("period")
    if h0.HARD_BASE.isna().any() or h0.index.duplicated().any():
        raise ValueError("Independent h0 table must have unique finite HARD_BASE rows")
    origins = [pd.Period(p, "M") for p in h0.index]
    if args.long_extra:
        origins += list(pd.period_range("2008-01", min(origins) - 1, freq="M"))
    if args.limit is not None:
        origins = origins[:args.limit]
    y = S.la.load_headline_cpi_mm_extended()
    con = S.la._con()
    fx_data = con.sql("SELECT year, month, czk_per_unit FROM monetary.fx_monthly WHERE currency_code='EUR' ORDER BY 1,2").df()
    con.close()
    fx = pd.Series(fx_data.czk_per_unit.to_numpy(dtype=float), index=pd.PeriodIndex(
        pd.to_datetime(dict(year=fx_data.year, month=fx_data.month, day=1)), freq="M"), name="eurczk")
    reference = pd.read_csv(ROOT / "output" / "path_step2.csv").set_index(["origin", "h"])
    archive = ROOT / "data" / "vintages" / "unemployment.csv.gz"
    files = [Path(__file__), ROOT / "models/path_inputs.py", ROOT / "models/trend_gap.py", ROOT / "models/bvar.py", archive, h0_path]
    fingerprints = {p.relative_to(ROOT).as_posix(): _sha(p) for p in files}
    manifest_path = Path(f"{prefix}manifest.json")
    forecast_path = Path(f"{prefix}forecasts.csv")
    diagnostics_path = Path(f"{prefix}diagnostics.jsonl")
    rows, done = [], set()
    if args.resume and forecast_path.exists():
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        if saved["fingerprints"] != fingerprints:
            raise ValueError("Resume input/code hashes differ from the saved experiment")
        previous = pd.read_csv(forecast_path)
        rows = previous.to_dict("records")
        done = set(previous.origin)
    else:
        diagnostics_path.write_text("", encoding="utf-8")
    manifest = dict(started_at=datetime.now(timezone.utc).isoformat(), fingerprints=fingerprints,
        origins_requested=[str(t) for t in origins], primary_models=PRIMARY, references=REFERENCES,
        primary_h0="HARD_BASE from independent nowcast experiment", long_h0="own target-model nowcast for origins before primary sample",
        clock="release eve 23:59 Europe/Prague", target_mapping="path h = model h+1 because released headline ends t-1",
        history="all finite contiguous extended headline history from February1991",
        target_early_approximation="existing target_path uses 4% before2002, including pre1998",
        destination_driver_lags={"unemployment_change":1,"fx_twelve_month_pct":3},
        seasonality="origin-fitted centered same-calendar-month medians for ML/BVAR; RF target-month dummies",
        rf_options=RF_OPTIONS, future_scenario="FX last completed monthly level held; unpublished U changes zero",
        vintage_label="historical unemployment releases; FX month-close assumption; historical CPI as stored; independent h0 inherits cached-driver limitations",
        inference_label="exploratory retrospective comparison; no untouched historical holdout or tuning",
        packages={p:importlib.metadata.version(p) for p in ["numpy","pandas","scikit-learn","statsmodels"]})
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    pd.concat([y.rename("headline_mm"), fx], axis=1).to_csv(f"{prefix}frozen_inputs.csv", index_label="period")
    started = time.monotonic()
    for i, t in enumerate(origins):
        if str(t) in done:
            continue
        local_clock = _eve(t)
        clock = local_clock.tz_localize("Europe/Prague").tz_convert("UTC")
        hist = y.loc[y.index < t]
        hist = hist.loc[S._released_index(hist.index, local_clock)]
        is_primary = str(t) in h0.index
        if is_primary and pd.Timestamp(h0.loc[str(t), "as_of_eve"]) != local_clock:
            raise ValueError(f"Independent h0 clock mismatch for {t}")
        result = forecast_origin(hist, fx, t, clock,
            float(h0.loc[str(t), "HARD_BASE"]) if is_primary else None,
            vintage_path=archive, long_only=not is_primary)
        paths, diagnostics, h0_value = result["native_paths"], result["diagnostics"], result["h0"]
        inputs = {"headline": result["history"], "metadata": result["inputs"]}
        if is_primary:
            for model, column in [("F1B_STORED_REF", "mm_F1b"), ("SURVEY_TREND_STORED_REF", "mm_F2_D1_fixed")]:
                paths[model] = {h: float(reference.loc[(str(t), h), column]) if (str(t), h) in reference.index else np.nan for h in range(1, 13)}
                diagnostics[model] = dict(status="stored_legacy_reference", converged=None, fallback_used=None)
        history = inputs["headline"]
        for model, path in paths.items():
            for h in range(13):
                target = t + h
                actual_window = y.reindex(pd.period_range(target - 11, target, freq="M"))
                actual_yy = (float(100 * np.expm1(np.log1p(actual_window.to_numpy() / 100).sum()))
                             if len(actual_window) == 12 and np.isfinite(actual_window).all() else np.nan)
                diag = diagnostics[model]
                rows.append(dict(origin=str(t), as_of_utc=clock.isoformat(), target=str(target), h=h, model=model,
                    mm_forecast=h0_value if h == 0 else path.get(h, np.nan),
                    native_h0=path.get(0, np.nan), h0_exante=h0_value, h0_actual=float(y.get(t, np.nan)),
                    h0_method="HARD_BASE" if is_primary else "own_TARGET_ML_long",
                    mm_actual=float(y.get(target, np.nan)), yy_actual=actual_yy,
                    yy_exante=compound_path(history, path, t, h, h0_value),
                    yy_conditional=compound_path(history, path, t, h, float(y.get(t, np.nan))),
                    status=diag.get("status"), converged=diag.get("converged"), fallback_used=diag.get("fallback_used"),
                    unemployment_end=inputs["metadata"]["unemployment_end"],
                    unemployment_adjustments="|".join(inputs["metadata"]["unemployment_adjustments"]),
                    fx_end=inputs["metadata"]["fx_end"], headline_n=len(history)))
        with diagnostics_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(origin=str(t), inputs=inputs["metadata"], models=diagnostics), default=_json_default) + "\n")
        pd.DataFrame(rows).to_csv(forecast_path, index=False)
        elapsed = time.monotonic() - started
        statuses = ", ".join(f"{k}:{v.get('status')}" for k,v in diagnostics.items() if k.startswith("TARGET"))
        print(f"{t}: {i+1}/{len(origins)} completed; {elapsed:.1f}s elapsed; {statuses}", flush=True)
    frame = pd.DataFrame(rows)
    summary = _save_summary(frame, prefix)
    manifest.update(completed_at=datetime.now(timezone.utc).isoformat(), origins_completed=int(frame.origin.nunique()),
                    forecast_rows=len(frame), forecast_sha256=_sha(forecast_path), elapsed_seconds=time.monotonic()-started)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    primary_summary = summary.loc[(summary.scope == "independent_common") & (summary["case"] == "exante") & (summary["sample"] == "2019_plus")]
    print(primary_summary[["h", "model", "n_common", "yy_rmse", "yy_mae", "mm_rmse"]].to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
