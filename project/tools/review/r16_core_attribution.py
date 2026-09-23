"""Hindsight core-oracle accounting on the original R16 headline score dates.

This is an attribution diagnostic, never a forecast or a model-selection input.
No frozen evaluator, model, forecast, or input file is changed.
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

_spec = importlib.util.spec_from_file_location("_r16_frozen_evaluator", Path(__file__).with_name("evaluate_r16.py"))
evaluation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evaluation)
prior = evaluation.prior
ROOT, ROSTER, NEW_MODELS, FAST = evaluation.ROOT, evaluation.ROSTER, evaluation.NEW_MODELS, evaluation.FAST
CURRENT = "STABLE_LOCAL_CORE_R14B"
MODELS = (FAST, *NEW_MODELS, CURRENT)
KEYS = ["origin", "h", "model"]


def oracle_monthly(native, core_actual, models=MODELS):
    """Retain each original monthly noncore contribution and h0 without filling."""
    data = native[native.model.isin(models)].copy()
    prior.unique(data)
    if not core_actual.index.is_unique:
        raise ValueError("Duplicate actual core month")
    if not data.target.eq([str(pd.Period(o, "M")+int(h)) for o, h in zip(data.origin, data.h)]).all():
        raise ValueError("Native target calendar changed")
    data["retained_mm"] = data.mm_forecast-data.weight_core*data.value_core
    data.loc[data.h.eq(0), "retained_mm"] = data.loc[data.h.eq(0), "mm_forecast"]
    reference = data[data.model.eq(FAST)]
    joined = data.merge(reference, on=["origin", "h"], suffixes=("", "_reference"), how="left", validate="many_to_one", indicator=True)
    if not joined._merge.eq("both").all():
        raise ValueError("Missing intermediate FAST reference")
    positive = joined.h.gt(0)
    checks = dict(common_weight_max=prior.assert_close(joined.loc[positive, "weight_core"], joined.loc[positive, "weight_core_reference"], "common weight_core"))
    protected = [c for c in data if c.startswith("weight_") or c.startswith("value_") and c != "value_core"
                 or c.startswith("contribution_") and c != "contribution_core"]
    checks["retained_component_max"] = 0.
    for col in protected:
        checks["retained_component_max"] = max(checks["retained_component_max"],
            prior.assert_close(joined[col], joined[col+"_reference"], "retained blocks "+col))
    checks["core_contribution_max"] = prior.assert_close(data.loc[data.h.gt(0), "contribution_core"],
        (data.weight_core*data.value_core)[data.h.gt(0)], "core contribution accounting")
    checks["common_retained_monthly_max"] = prior.assert_close(joined.retained_mm, joined.retained_mm_reference, "common retained monthly blocks including h0")
    data["observed_core_mm"] = [core_actual.get(pd.Period(t, "M"), np.nan) for t in data.target]
    data["oracle_mm"] = data.mm_forecast+data.weight_core*(data.observed_core_mm-data.value_core)
    data.loc[data.h.eq(0), "oracle_mm"] = data.loc[data.h.eq(0), "mm_forecast"]
    for col in ("mm_forecast", "oracle_mm", "observed_core_mm", "value_core"):
        if data[col].le(-100).any():
            raise ValueError("Invalid monthly rate for log accounting: "+col)
    return data, checks


def decompose(paths, forecasts, headline, models=MODELS, roster=ROSTER):
    """Fail on an unavailable oracle month within original finite headline support."""
    common = prior.matched_rows(forecasts[forecasts.h.gt(0)], roster, "yy_exante", "yy_actual")
    selected = common[common.model.isin(models)]
    lookup = {(o, m): group.set_index("h") for (o, m), group in paths.groupby(["origin", "model"])}
    rows = []
    for row in selected.itertuples():
        origin = pd.Period(row.origin, "M")
        key = (row.origin, row.model)
        if key not in lookup:
            raise ValueError("Missing intermediate native path: "+str(key))
        path = lookup[key].reindex(range(row.h+1))
        future = path.reindex(range(1, row.h+1))
        needed = [*path.mm_forecast, *path.oracle_mm, *future.value_core, *future.observed_core_mm]
        if not np.isfinite(needed).all():
            raise ValueError("Missing intermediate month on original headline support: "+str((row.origin, row.h, row.model)))
        months = pd.period_range(origin+row.h-11, origin+row.h, freq="M")
        actual_mm = headline.reindex(months).to_numpy(float)
        predicted_mm, oracle_mm = [], []
        for month in months:
            offset = month.ordinal-origin.ordinal
            predicted_mm.append(headline.get(month, np.nan) if offset < 0 else path.at[offset, "mm_forecast"])
            oracle_mm.append(headline.get(month, np.nan) if offset < 0 else path.at[offset, "oracle_mm"])
        if not np.isfinite([*actual_mm, *predicted_mm, *oracle_mm]).all():
            raise ValueError("Missing intermediate headline history on original support")
        actual_log = float(100*np.log1p(actual_mm/100).sum())
        forecast_log = float(100*np.log1p(np.asarray(predicted_mm)/100).sum())
        oracle_log = float(100*np.log1p(np.asarray(oracle_mm)/100).sum())
        prior.assert_close([row.yy_actual, row.yy_exante], 100*np.expm1(np.array([actual_log, forecast_log])/100), "same-origin headline compounding")
        core_error = float(100*(np.log1p(future.value_core.to_numpy(float)/100)-np.log1p(future.observed_core_mm.to_numpy(float)/100)).sum())
        total, core_effect, retained = forecast_log-actual_log, forecast_log-oracle_log, oracle_log-actual_log
        rows.append(dict(origin=row.origin, h=row.h, target=row.target, model=row.model, actual_annual_log=actual_log,
            forecast_annual_log=forecast_log, oracle_annual_log=oracle_log, oracle_headline_yy=100*np.expm1(oracle_log/100),
            total_error_log=total, core_effect_log=core_effect, retained_error_log=retained, core_cumulative_error_log=core_error,
            h0_in_annual_window=row.h<12, additive_identity_residual=total-core_effect-retained))
    result = pd.DataFrame(rows)
    if not result.empty:
        counts = result.groupby(["origin", "h"]).model.nunique()
        if not counts.eq(len(models)).all():
            raise ValueError("Attribution models do not share the original headline support")
        spread = result.groupby(["origin", "h"]).retained_error_log.agg(["min", "max"])
        prior.assert_close(spread["min"], spread["max"], "oracle retained remainder identical across models", tolerance=1e-10)
    return result


def score_attribution(data):
    scores, paired_rows, pair_summary = [], [], []
    for sample, subset in (("full", data), ("origins_2024plus", data[data.origin.ge("2024-01")])):
        for (model, h), group in subset.groupby(["model", "h"]):
            row = dict(sample=sample, model=model, h=h, n=len(group), unit="annual_log_pp")
            for label, col in (("total", "total_error_log"), ("core_effect", "core_effect_log"),
                               ("retained", "retained_error_log"), ("core_cumulative", "core_cumulative_error_log")):
                row.update({label+"_"+key+"_log": value for key, value in prior.error_stats(group[col]).items() if key != "n"})
            row.update(total_mse_log=float(np.mean(group.total_error_log**2)), core_effect_mse_log=float(np.mean(group.core_effect_log**2)),
                retained_mse_log=float(np.mean(group.retained_error_log**2)),
                twice_core_retained_cross_moment=float(2*np.mean(group.core_effect_log*group.retained_error_log)))
            row["squared_identity_residual"] = row["total_mse_log"]-row["core_effect_mse_log"]-row["retained_mse_log"]-row["twice_core_retained_cross_moment"]
            scores.append(row)
    fast = data[data.model.eq(FAST)]
    cols = ["origin", "h", "total_error_log", "core_effect_log", "retained_error_log", "core_cumulative_error_log"]
    paired = data[data.model.ne(FAST)].merge(fast[cols], on=["origin", "h"], suffixes=("", "_fast"), how="left", validate="many_to_one")
    prior.assert_close(paired.retained_error_log, paired.retained_error_log_fast, "paired common retained remainder", tolerance=1e-10)
    paired["benchmark"] = FAST
    paired["total_squared_loss_difference"] = paired.total_error_log**2-paired.total_error_log_fast**2
    paired["core_effect_squared_loss_difference"] = paired.core_effect_log**2-paired.core_effect_log_fast**2
    paired["retained_squared_loss_difference"] = paired.retained_error_log**2-paired.retained_error_log_fast**2
    paired["cross_moment_difference"] = 2*(paired.core_effect_log*paired.retained_error_log-paired.core_effect_log_fast*paired.retained_error_log_fast)
    paired["core_cumulative_squared_loss_difference"] = paired.core_cumulative_error_log**2-paired.core_cumulative_error_log_fast**2
    paired["identity_residual"] = paired.total_squared_loss_difference-paired.core_effect_squared_loss_difference-paired.retained_squared_loss_difference-paired.cross_moment_difference
    for sample, subset in (("full", paired), ("origins_2024plus", paired[paired.origin.ge("2024-01")])):
        for (model, h), group in subset.groupby(["model", "h"]):
            row = dict(sample=sample, model=model, benchmark=FAST, h=h, n=len(group), unit="annual_log_pp_squared")
            for col in ("total_squared_loss_difference", "core_effect_squared_loss_difference", "retained_squared_loss_difference",
                        "cross_moment_difference", "core_cumulative_squared_loss_difference", "identity_residual"):
                row["mean_"+col] = float(group[col].mean())
            for label, col in (("total", "total_error_log"), ("core_cumulative", "core_cumulative_error_log")):
                row[label+"_rmse_log"] = float(np.sqrt(np.mean(group[col]**2)))
                row[label+"_fast_rmse_log"] = float(np.sqrt(np.mean(group[col+"_fast"]**2)))
            pair_summary.append(row)
    return pd.DataFrame(scores), paired, pd.DataFrame(pair_summary)


def evaluate(experiment, root=ROOT):
    experiment, root = Path(experiment).resolve(), Path(root).resolve()
    out = experiment / "attribution"
    files = [experiment / "forecasts.csv", experiment / "native_forecasts.csv",
        root / "output/research_r15/native_forecasts.csv", root / "output/research_r14b/integration/native_forecasts.csv",
        root / "output/independent_path_frozen_inputs.csv", root / "tests/fixtures/cleanup/cnb_core_mm.csv",
        Path(__file__).resolve(), Path(evaluation.__file__).resolve(), Path(prior.__file__).resolve()]
    if (experiment / "manifest.json").exists():
        files.append(experiment / "manifest.json")
    sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    hashes = {str(path): sha(path) for path in files}
    read = lambda path: pd.read_csv(path, float_precision="round_trip")
    raw, native, r15, r14 = [read(path) for path in files[:4]]
    native = pd.concat([native[native.model.isin(NEW_MODELS)], r15[r15.model.eq(FAST)], r14[r14.model.eq(CURRENT)]], ignore_index=True)
    native = native[native.origin.isin(raw.origin.unique())]
    check = raw[raw.model.isin(MODELS)].merge(native[[*KEYS, "mm_forecast"]], on=KEYS, how="outer", suffixes=("", "_native"), validate="one_to_one", indicator=True)
    if not check._merge.eq("both").all():
        raise ValueError("Raw/native forecast key mismatch")
    export_error = prior.assert_close(check.mm_forecast, check.mm_forecast_native, "raw/native headline monthly")
    headline = prior.read_monthly(files[4], "headline_mm")
    core_actual = prior.read_monthly(files[5], "core")
    paths, checks = oracle_monthly(native, core_actual, models=MODELS)
    checks["native_raw_monthly_max"] = export_error
    data = decompose(paths, raw, headline, models=MODELS, roster=ROSTER)
    scores, paired, summary = score_attribution(data)
    checks.update(additive_identity_max=float(abs(data.additive_identity_residual).max()),
        mean_square_identity_max=float(abs(scores.squared_identity_residual).max()), paired_identity_max=float(abs(paired.identity_residual).max()))
    if max(checks["additive_identity_max"], checks["mean_square_identity_max"], checks["paired_identity_max"]) > 1e-9:
        raise ValueError("Attribution accounting identity failed")
    support = raw[raw.h.gt(0)].copy()
    support["finite_headline"] = np.isfinite(support.yy_exante) & np.isfinite(support.yy_actual)
    support = support[support.model.isin(ROSTER)].groupby(["origin", "h", "target"]).agg(
        n_models_present=("model", "nunique"), n_models_finite=("finite_headline", "sum")).reset_index()
    support["original_all15_support"] = support.n_models_present.eq(len(ROSTER)) & support.n_models_finite.eq(len(ROSTER))
    support_counts = data.groupby(["model", "h"]).size().rename("n").reset_index()
    checks["original_support_n"] = support[support.original_all15_support].groupby("h").size().to_dict()
    checks["retained_remainder_spread_max"] = float(data.groupby(["origin", "h"]).retained_error_log.apply(lambda x: x.max()-x.min()).max())
    out.mkdir(parents=True, exist_ok=True)
    outputs = []
    for name, frame in (("monthly_counterfactual_paths.csv", paths), ("attribution.csv", data), ("scoreboard.csv", scores),
        ("paired_vs_fast.csv", paired), ("paired_vs_fast_summary.csv", summary), ("support_ledger.csv", support), ("support_counts.csv", support_counts)):
        frame.to_csv(out / name, index=False)
        outputs.append(name)
    definitions = dict(
        purpose="Hindsight accounting attribution only. Observed future core is unavailable when forecasting; the oracle is not a usable forecast, model proposal, calibration target or selection rule. No frozen forecasts changed.",
        roster=ROSTER, attribution_models=MODELS, support="Exactly the original fifteen-model finite headline annual forecast+actual intersection per origin/horizon. Core cumulative scores and every comparison to FAST use these same dates; no separate larger core sample. A missing required intermediate monthly input raises an error instead of being filled or silently removed.",
        monthly_oracle="For h1..h replace weighted forecast monthly core by the same fixed weight_core times observed monthly core: oracle_mm=forecast_mm+weight_core*(actual_core_mm-forecast_core_mm). Preserve every noncore component, weight and h0. All twelve attribution models must have identical retained monthly blocks and h0, checked against FAST.",
        annual_window="Annual log inflation=100*sum(log1p(headline_mm/100)) across the twelve target-window months, using frozen known history before the origin and a single forecast origin thereafter. At h<12 this window includes unchanged h0, so its error belongs in the retained remainder; h12 excludes h0. No future actual headline month replaces a forecast in the oracle.",
        decomposition="total_error_log=forecast_annual_log-actual_annual_log; core_effect_log=forecast_annual_log-oracle_annual_log; retained_error_log=oracle_annual_log-actual_annual_log. Therefore total=core_effect+retained exactly. The retained remainder is common across all models, up to floating roundoff, and includes noncore/accounting blocks plus h0 when inside the annual window.",
        units="Decomposition and RMSE/MAE use annual log percentage points, not ordinary headline year-on-year percentage-point errors. Core effect is the exact change to headline annual-log error from replacing weighted core, including nonlinear headline compounding. It differs from the unweighted cumulative core error.",
        core_cumulative="Sum over h1..h of 100*(log1p(forecast_core_mm/100)-log1p(actual_core_mm/100)), scored on original common headline dates. No h0 core forecast is required or substituted.",
        mean_squares="E(total^2)=E(core_effect^2)+E(retained^2)+2E(core_effect*retained). The final term is an uncentered cross moment, not covariance unless both component errors have zero mean. A negative cross term identifies offsetting errors; headline accuracy can improve despite a larger own-core error.",
        paired="Every model versus FAST on identical origin/horizon dates. Difference of total squared errors equals difference of core-effect squares plus difference of retained squares (zero within roundoff) plus the cross-moment difference. This is an accounting identity, not a causal finding or statistical significance claim.",
        samples="Full and origins from 2024-01, every h1..12. No outcome-based exclusions beyond original all-fifteen headline support.")
    for name, value in (("definitions.json", definitions), ("checks.json", checks)):
        (out / name).write_text(json.dumps(prior.json_safe(value), indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
        outputs.append(name)
    for path, digest in hashes.items():
        if sha(path) != digest:
            raise ValueError("Attribution input changed: "+path)
    manifest = dict(created_at_utc=datetime.now(timezone.utc).isoformat(), inputs=hashes, models=MODELS, fixed_support_roster=ROSTER,
        origin_count=raw.origin.nunique(), command=f'python tools/review/r16_core_attribution.py --experiment "{experiment}"',
        packages=dict(numpy=np.__version__, pandas=pd.__version__), all_inputs_unchanged=True,
        outputs={name: sha(out / name) for name in outputs})
    (out / "manifest.json").write_text(json.dumps(prior.json_safe(manifest), indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    print("R16 core attribution complete:", out, flush=True)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    args = parser.parse_args(argv)
    evaluate(args.experiment)


if __name__ == "__main__":
    main()
