"""Independent component bridge and conservative CNB report-quarter comparison.

All forecast inputs are supplied as frozen frames; no forecast expectations enter
any horizon. Run python independent_bridge_experiment.py to evaluate 90 origins.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from models.independent_nowcast import policy_frame
from models.path_inputs import compound_path

ROOT = Path(__file__).resolve().parent
BRIDGE = "INDEPENDENT_BRIDGE"


def _monthly_frame(frame, name, through):
    """Validate the relevant monthly grid before any positional horizon shift."""
    if not isinstance(frame, pd.DataFrame) or not isinstance(frame.index, pd.PeriodIndex) or frame.index.freqstr != "M":
        raise ValueError(f"{name} requires a monthly PeriodIndex DataFrame")
    value = frame.loc[frame.index <= through].copy()
    idx = value.index
    if not len(idx) or not idx.is_unique or not idx.is_monotonic_increasing or not idx.equals(pd.period_range(idx.min(), idx.max(), freq="M")):
        raise ValueError(f"{name} requires unique, ordered, contiguous monthly history")
    return value


def future_weights(weight_map, current_weights, target, clock):
    """Unknown future basket regimes retain the current origin's weights."""
    import cz_struct as s
    regime = s._regime(target)
    if s._basket_available_from(regime) <= clock and regime in weight_map:
        return dict(weight_map[regime])
    return dict(current_weights)


def forecast_bridge(frames, target, as_of, h0):
    """Pure calculation over explicit frozen frame dictionary and aware clock.

    Required keys: headline, components(food/fuel), core, regulated, alcohol,
    features, food_features. Series are stored in each frame's first column.
    Static release/announcement/basket policy is read from the existing package.
    Return path[h] for h=0..12, per-horizon contributions, weights and diagnostics.
    """
    import cz_struct as s
    target = pd.Period(target, "M")
    aware = pd.Timestamp(as_of)
    if pd.isna(aware) or aware.tzinfo is None:
        raise ValueError("Bridge as_of must be timezone-aware")
    if not np.isfinite(h0):
        raise ValueError("Bridge requires a finite supplied independent h0")
    clock = aware.tz_convert("Europe/Prague").tz_localize(None)
    known_through = target - 1

    def released(name):
        value = _monthly_frame(frames[name], name, known_through)
        return value.loc[s._released_index(value.index, clock)]

    y = released("headline").iloc[:, 0]
    comp = released("components")
    core = released("core").iloc[:, 0].rename("core")
    reg = released("regulated").iloc[:, 0].rename("reg")
    alc = released("alcohol").iloc[:, 0]
    x = policy_frame(s._mask_row_by_availability(_monthly_frame(frames["features"], "features", target), target, clock), "hard")
    food_features = policy_frame(s._mask_row_by_availability(_monthly_frame(frames["food_features"], "food_features", target), target, clock), "hard")
    if "gated_mtd_fx" in frames and target in frames["gated_mtd_fx"].index:
        for col in ("eurczk_mm", "eurczk_mm_x_state"):
            x.loc[target, col] = frames["gated_mtd_fx"].loc[target, col]
    if target not in x.index or target not in food_features.index:
        raise ValueError(f"Missing frozen feature row for {target}")
    wmap = s.solve_weights(y, comp, core, reg, known_through, as_of=clock, alc=alc)
    current = wmap[s._regime(target)]
    support = pd.concat([y, comp[["food", "fuel"]], alc, core, reg], axis=1).dropna().iloc[:, 0]
    wedge = s._weighted_wedge(y, comp, alc, core, reg, support, wmap, as_of=clock)
    fuel_history, food_history = comp.fuel.dropna(), comp.food.dropna()
    path, contributions, values, weights, detail = {0: float(h0)}, {}, {}, {}, {}
    for h in range(1, 13):
        month = target + h
        wh = future_weights(wmap, current, month, clock)
        cp = s._ridge_predict(x, core, target, h=h, as_of=clock)[0]
        if h <= 3:
            fp = s.food_forecast(food_history, food_features, target, h=h, as_of=clock)
            food_detail = dict(s.FOOD_DIAG)
        else:
            same = food_history.loc[food_history.index.month == month.month]
            fp = float(same.tail(5).mean()) if len(same) else float(food_history.tail(24).mean())
            food_detail = dict(method="seasonal_mean_last_five", history_end=str(food_history.index.max()))
        ap = s.admin_forecast(reg, month, known_through=known_through, as_of=clock,
                              announce_mode="documented", w_adm=wh["administered"])
        alc_p = s.alc_forecast(alc, month, known_through, as_of=clock)
        same_fuel = fuel_history.loc[fuel_history.index.month == month.month]
        fuel = float(same_fuel.tail(8).median()) if len(same_fuel) >= 3 else float(fuel_history.tail(24).median())
        wd = s._wedge_at(wedge, month, known_through)
        block = dict(core=float(cp), food=float(fp), administered=float(ap),
                     alcohol_tobacco=float(alc_p), fuel=float(fuel), wedge=float(wd))
        contribution = dict(core=wh["core"]*cp, food=wh["food"]*fp,
            administered=wh["administered"]*ap, alcohol_tobacco=wh["alc"]*alc_p,
            fuel=wh["fuel"]*fuel, wedge=wd)
        path[h] = float(sum(contribution.values()))
        contributions[h] = {k:float(v) for k,v in contribution.items()}
        values[h], weights[h] = block, wh
        detail[h] = dict(food=food_detail, status="estimated" if np.isfinite(path[h]) else "failed_nonfinite",
            fallback_used=food_detail.get("method") == "fallback",
            nonfinite_blocks=[name for name, value in block.items() if not np.isfinite(value)])
    return dict(path=path, contributions=contributions, block_values=values, weights=weights,
        diagnostics=dict(status="estimated" if np.isfinite(list(path.values())).all() else "failed_nonfinite",
            fallback_used=any(d["fallback_used"] for d in detail.values()),
            as_of_utc=aware.tz_convert("UTC").isoformat(), target=str(target),
            h0_method="supplied HARD_BASE", core_columns=list(x.columns), food_columns=list(food_features.columns),
            headline_edge=str(y.dropna().index.max()), core_edge=str(core.dropna().index.max()),
            horizon_details=detail, future_weights="current unless future regime basket was already published",
            vintage_label="cached historical statistical inputs and publication rules; no forecast expectations"))


def match_cnb_quarters(paths, cnb, headline_actual, models):
    """Latest existing pre-report path; complete quarterly means of monthly YoY.

    Publication time is conservatively 00:00 Europe/Prague on report_date.
    No realized observation at/after the selected origin replaces a forecast.
    Incomplete model quarters are retained with NaN, and scored only in common.
    """
    actual_yoy = 100 * ((1 + headline_actual / 100).rolling(12).apply(np.prod, raw=True) - 1)
    clocks = paths[["origin", "as_of_utc"]].drop_duplicates()
    if clocks.origin.duplicated().any():
        raise ValueError("Conflicting decision clocks for an origin")
    clocks["stamp"] = pd.to_datetime(clocks.as_of_utc, utc=True)
    rows = []
    for report, group in cnb.groupby("report_date"):
        report_clock = pd.Timestamp(report).tz_localize("Europe/Prague").tz_convert("UTC")
        eligible = clocks.loc[clocks.stamp < report_clock].sort_values("stamp")
        if eligible.empty:
            continue
        chosen = eligible.iloc[-1]
        origin = pd.Period(chosen.origin, "M")
        selected = paths.loc[paths.origin == str(origin)]
        for row in group.itertuples():
            if str(row.is_forecast).lower() != "true":
                continue
            quarter = pd.Period(row.quarter, "Q")
            months = pd.period_range(quarter.asfreq("M", "start"), quarter.asfreq("M", "end"), freq="M")
            if months[-1] < origin:
                continue
            truth = actual_yoy.reindex(months)
            realised = float(truth.mean()) if np.isfinite(truth).all() else np.nan
            base = dict(report_date=str(report), report_clock_utc=report_clock.isoformat(),
                origin=str(origin), as_of_utc=chosen.as_of_utc, quarter=str(quarter),
                quarters_ahead=(quarter - (origin - 1).asfreq("Q")).n,
                realised=realised, cnb=float(row.value),
                known_months=int((months < origin).sum()), forecast_months=int((months >= origin).sum()))
            for model in models:
                future = selected.loc[selected.model == model].set_index("target").yy_exante
                values = [actual_yoy.get(m, np.nan) if m < origin else future.get(str(m), np.nan) for m in months]
                finite = bool(np.isfinite(values).all())
                rows.append(dict(**base, model=model, forecast=float(np.mean(values)) if finite else np.nan,
                                 complete=finite))
            rows.append(dict(**base, model="CNB", forecast=float(row.value), complete=True))
    result = pd.DataFrame(rows)
    if not result.empty and result.duplicated(["report_date", "quarter", "model"]).any():
        raise ValueError("Duplicate CNB report/quarter/model keys")
    return result


def _quarter_metrics(frame, models, scope, sample):
    rows = []
    for ahead in ["all"] + sorted(frame.quarters_ahead.unique().tolist()):
        group = frame if ahead == "all" else frame.loc[frame.quarters_ahead == ahead]
        group = group.loc[group.model.isin(models)]
        wide = group.pivot(index=["report_date", "quarter"], columns="model", values="forecast").reindex(columns=models)
        truth = group.drop_duplicates(["report_date", "quarter"]).set_index(["report_date", "quarter"]).realised
        common = wide.index[np.isfinite(wide).all(axis=1) & np.isfinite(truth.reindex(wide.index))]
        for model in models:
            error = wide.loc[common, model] - truth.reindex(common)
            rows.append(dict(scope=scope, sample=sample, quarters_ahead=ahead, model=model,
                n_report_quarter_pairs=len(common), n_unique_quarters=len(set(common.get_level_values("quarter"))),
                n_reports=len(set(common.get_level_values("report_date"))),
                rmse=float(np.sqrt(np.mean(error**2))) if len(common) else np.nan,
                mae=float(np.mean(np.abs(error))) if len(common) else np.nan,
                bias=float(np.mean(error)) if len(common) else np.nan))
    return pd.DataFrame(rows)


def _safe(value):
    if isinstance(value, dict): return {str(k):_safe(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)): return [_safe(v) for v in value]
    if isinstance(value, (float,np.floating)): return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.integer,np.bool_)): return value.item()
    return value


def main(argv=None):
    from forecast_independent import fixture_frames
    from independent_path_experiment import PRIMARY, REFERENCES, common_metrics
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--prefix", default="independent_bridge_")
    args = parser.parse_args(argv)
    if not args.prefix.startswith("independent_bridge_") or "/" in args.prefix or "\\" in args.prefix:
        raise ValueError("Invalid output prefix")
    prefix = ROOT / "output" / args.prefix
    frames = fixture_frames()
    h0_path = ROOT / "output/independent_nowcast_forecasts.csv"
    h0 = pd.read_csv(h0_path).set_index("period")
    path_file = ROOT / "output/independent_path_forecasts.csv"
    cnb_file = ROOT / "data/cnb_mpr_cpi_quarterly.csv"
    inputs = [Path(__file__), ROOT/"cz_struct.py", ROOT/"models/independent_nowcast.py", ROOT/"models/path_inputs.py",
        h0_path, path_file, cnb_file, ROOT/"output/independent_path_frozen_inputs.csv",
        ROOT/"data/admin_announcements_history.csv", ROOT/"data/release_calendar_cz_cpi.csv",
        ROOT/"tests/fixtures/cleanup/MANIFEST.json"]
    fingerprints = {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    existing = pd.read_csv(path_file)
    existing = existing.loc[existing.origin.isin(h0.index)]
    actual = pd.read_csv(ROOT / "output/independent_path_frozen_inputs.csv", index_col=0).headline_mm
    actual.index = pd.PeriodIndex(actual.index, freq="M")
    base = existing.loc[existing.model == "TARGET_ML"].set_index(["origin","h"])
    rows, diagnostics = [], []
    origins = list(h0.index)[:args.limit]
    started = time.monotonic()
    for i, name in enumerate(origins):
        target = pd.Period(name, "M")
        clock = pd.Timestamp(h0.loc[name, "as_of_eve"]).tz_localize("Europe/Prague")
        result = forecast_bridge(frames, target, clock, float(h0.loc[name, "HARD_BASE"]))
        hist = actual.loc[actual.index < target]
        for h in range(13):
            row = base.loc[(name, h)].to_dict()
            row.update(origin=name, h=h, model=BRIDGE, mm_forecast=result["path"][h],
                yy_exante=compound_path(hist, result["path"], target, h, result["path"][0]),
                yy_conditional=compound_path(hist, result["path"], target, h, float(actual.get(target,np.nan))),
                native_h0=np.nan, origin_status=result["diagnostics"]["status"],
                status="estimated" if np.isfinite(result["path"][h]) else "failed_nonfinite",
                converged=bool(np.isfinite(result["path"][h])),
                fallback_used=result["diagnostics"]["horizon_details"].get(h, {}).get("fallback_used", False))
            for block, value in result["contributions"].get(h, {}).items(): row[f"contribution_{block}"] = value
            for block, value in result["block_values"].get(h, {}).items(): row[f"value_{block}"] = value
            for block, value in result["weights"].get(h, {}).items(): row[f"weight_{block}"] = value
            rows.append(row)
        diagnostics.append(dict(origin=name, **result["diagnostics"]))
        pd.DataFrame(rows).to_csv(f"{prefix}forecasts.csv",index=False)
        Path(f"{prefix}diagnostics.json").write_text(json.dumps(_safe(diagnostics),indent=2),encoding="utf-8")
        print(f"{name}: {i+1}/{len(origins)} bridge origins; {time.monotonic()-started:.1f}s elapsed",flush=True)
    bridge = pd.DataFrame(rows)
    merged = pd.concat([existing.loc[existing.origin.isin(origins)], bridge], ignore_index=True)
    merged.to_csv(f"{prefix}comparison_forecasts.csv",index=False)
    summaries = []
    for sample, selection in [("2019_plus",merged),("2024_plus_targets",merged.loc[merged.target>="2024-01"]),
        ("crisis_2020_2023_targets",merged.loc[(merged.target>="2020-01")&(merged.target<="2023-12")])]:
        summaries.append(common_metrics(selection,PRIMARY+[BRIDGE],"independent_plus_bridge",sample))
        summaries.append(common_metrics(selection,PRIMARY+[BRIDGE]+REFERENCES,"including_references",sample))
    summary = pd.concat(summaries,ignore_index=True)
    summary.to_csv(f"{prefix}summary.csv",index=False)
    cnb = pd.read_csv(cnb_file)
    quarters = match_cnb_quarters(merged,cnb,actual,PRIMARY+[BRIDGE]+REFERENCES)
    quarters.to_csv(f"{prefix}cnb_quarters.csv",index=False)
    qs = []
    for label, selected in [("all_reports",quarters),("2024_plus_reports",quarters.loc[quarters.report_date>="2024-01-01"])]:
        qs.append(_quarter_metrics(selected,PRIMARY+[BRIDGE,"CNB"],"independent_plus_bridge",label))
        qs.append(_quarter_metrics(selected,PRIMARY+[BRIDGE]+REFERENCES+["CNB"],"including_references",label))
    pd.concat(qs,ignore_index=True).to_csv(f"{prefix}cnb_summary.csv",index=False)
    changed = [p.relative_to(ROOT).as_posix() for p in inputs
        if fingerprints[p.relative_to(ROOT).as_posix()] != hashlib.sha256(p.read_bytes()).hexdigest()]
    if changed:
        raise RuntimeError(f"Inputs changed during bridge evaluation: {changed}")
    manifest=dict(completed_at=datetime.now(timezone.utc).isoformat(),origins=len(origins),rows=len(bridge),
        elapsed_seconds=time.monotonic()-started,fingerprints=fingerprints,
        fixture_manifest_sha256=hashlib.sha256((ROOT/"tests/fixtures/cleanup/MANIFEST.json").read_bytes()).hexdigest(),
        core_policy="hard at every horizon; no slow blocks",food_policy="origin-fitted X13/ridge h1..3; seasonal last5mean h4..12",
        weight_policy="current origin weights unless future-regime basket already published",h0="HARD_BASE",
        cnb_clock="latest generated origin strictly before 00:00 Prague on report publication date",
        cnb_accounting="complete-quarter mean of monthly YoY; actual only for months preceding chosen origin; exante forecasts thereafter",
        cnb_dependence="report-quarter pairs overlap in realized targets; rows are not independent observations",
        vintage_limit="cached statistical inputs/publication rules; no forecast expectations; not full historical vintages or untouched holdout")
    Path(f"{prefix}manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(summary.loc[(summary.model==BRIDGE)&(summary["case"]=="exante")][["scope","sample","h","n_common","yy_rmse","yy_mae"]].round(3).to_string(index=False),flush=True)


if __name__ == "__main__":
    main()
