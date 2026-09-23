"""Offline R15 scoring and CNB replay. Run with --experiment output/research_r15.

Reads already frozen predictions; never imports a fitter, changes a model choice,
or downloads inputs. Every generated file lives in EXPERIMENT/evaluation/.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
BASE = "STABLE_PIPELINE_R14B"
CONTROLS = ("INDEPENDENT_BRIDGE", BASE, "STABLE_LOCAL_CORE_R14B")
NEW_MODELS = ("STATE_SLOW_R15", "STATE_MID_R15", "STATE_FAST_R15", "STATE_ADAPT_R15",
              "ENET_DOMESTIC_R15", "ENET_IMPORTED_R15", "ENET_BOTH_R15", "ENET_WIDE_R15",
              "RF_RESIDUAL_R15", "BLEND_LINEAR_RF_R15", "BLEND_WIDE_STATE_R15")
ROSTER = (*CONTROLS, *NEW_MODELS)
KEYS = ["origin", "h", "model"]
METRICS = {
    "headline_yy": ("yy_exante", "yy_actual"),
    "headline_mm": ("mm_forecast", "mm_actual"),
    "headline_cumulative_log": ("cumulative_log_forecast", "cumulative_log_actual"),
    "core_mm": ("core_mm_forecast", "core_mm_actual"),
    "core_cumulative_log": ("core_cumulative_log_forecast", "core_cumulative_log_actual"),
}


def unique(frame, keys=KEYS):
    if frame.duplicated(keys).any():
        raise ValueError("Duplicate forecast keys: " + ",".join(keys))


def matched_rows(frame, models, prediction, actual, keys=("origin", "h")):
    """Same finite key support for every named model, including absent models."""
    unique(frame, [*keys, "model"])
    data = frame[frame.model.isin(models)].copy()
    finite = np.isfinite(data[prediction]) & np.isfinite(data[actual])
    if not data.empty and data.groupby(list(keys))[actual].nunique().gt(1).any():
        raise ValueError("Actual outcome differs between models on the same key")
    counts = data.loc[finite].groupby(list(keys)).model.nunique()
    good = counts.index[counts.eq(len(models))]
    return data.set_index(list(keys)).loc[lambda x: x.index.isin(good)].reset_index()


def attach_core(frame, native, core_predictions, core_actual):
    """Join original monthly core outcomes. Cumulation is h1 through h, not h0."""
    unique(frame)
    unique(native)
    unique(core_predictions)
    predicted = core_predictions[[*KEYS, "core_mm"]].rename(columns={"core_mm": "core_mm_forecast"})
    native_core = native[[*KEYS, "value_core"]].rename(columns={"value_core": "core_mm_forecast"})
    native_core = native_core[~native_core.model.isin(predicted.model.unique())]
    predicted = pd.concat([predicted, native_core], ignore_index=True)
    unique(predicted)
    out = frame.merge(predicted, on=KEYS, how="left", validate="one_to_one")
    out["core_mm_actual"] = [core_actual.get(pd.Period(t, "M"), np.nan) for t in out.target]
    out["core_cumulative_log_forecast"] = np.nan
    out["core_cumulative_log_actual"] = np.nan
    for (_, _), g in out.groupby(["origin", "model"]):
        ordered = g.set_index("h").reindex(range(1, 13))
        for suffix in ("forecast", "actual"):
            vals = ordered["core_mm_" + suffix].to_numpy(float)
            logs = 100 * np.log1p(vals / 100)
            # np.cumsum propagates a missing month; pandas' default skips it.
            cumulative = np.cumsum(logs)
            ix = g.index[g.h.gt(0)]
            out.loc[ix, "core_cumulative_log_" + suffix] = cumulative[out.loc[ix, "h"].astype(int) - 1]
    return out


def classify(values, threshold=.25):
    values = np.asarray(values, dtype=float)
    return np.where(values > threshold, 1, np.where(values < -threshold, -1, 0))


def direction_stats(prediction, actual, baseline):
    prediction, actual, baseline = np.broadcast_arrays(prediction, actual, baseline)
    finite = np.isfinite(prediction) & np.isfinite(actual) & np.isfinite(baseline)
    predicted = classify(prediction[finite] - baseline[finite])
    realised = classify(actual[finite] - baseline[finite])
    material, calls = realised != 0, predicted != 0
    wrong = material & calls & (predicted != realised)
    n = len(realised)
    return dict(n=n, direction_match_rate=float(np.mean(predicted == realised)) if n else np.nan,
                actual_material_n=int(material.sum()),
                material_direction_hit_rate=float(np.mean(predicted[material] == realised[material])) if material.any() else np.nan,
                material_calls_n=int(calls.sum()), wrong_way_n=int(wrong.sum()),
                wrong_way_rate=float(wrong.sum() / material.sum()) if material.any() else np.nan,
                wrong_way_share_of_calls=float(wrong.sum() / calls.sum()) if calls.any() else np.nan)


def quarter_months(quarter):
    q = pd.Period(quarter, "Q")
    return pd.period_range(q.asfreq("M", "start"), q.asfreq("M", "end"), freq="M")


def quarter_actual(quarter, actual):
    values = actual.reindex(quarter_months(quarter)).to_numpy(float)
    return float(values.mean()) if np.isfinite(values).all() else np.nan


def quarter_value(quarter, origin, path, actual):
    origin = pd.Period(origin, "M")
    values = np.array([actual.get(t, np.nan) if t < origin else path.get(str(t), np.nan)
                       for t in quarter_months(quarter)], dtype=float)
    return float(values.mean()) if np.isfinite(values).all() else np.nan


def select_snapshot(clocks, day, mode):
    if mode not in ("report", "cutoff"):
        raise ValueError("Clock must be report or cutoff")
    # Add a calendar day before localizing, so DST days retain local midnight.
    boundary = pd.Timestamp(day) + pd.Timedelta(days=int(mode == "cutoff"))
    boundary = boundary.tz_localize("Europe/Prague").tz_convert("UTC")
    eligible = clocks[clocks < boundary].sort_values()
    return (str(eligible.index[-1]), eligible.iloc[-1]) if len(eligible) else None


def gain_fields(prediction, cnb, actual):
    gain = abs(cnb - actual) - abs(prediction - actual)
    return dict(model_cnb_deviation=prediction - cnb, realised_cnb_error=actual - cnb,
                abs_error_gain_vs_cnb=gain, squared_error_gain_vs_cnb=(cnb - actual) ** 2 - (prediction - actual) ** 2,
                material_gain=bool(gain >= .15 - 1e-12), material_loss=bool(gain <= -.15 + 1e-12),
                deviation_direction_correct=bool((prediction - cnb) * (actual - cnb) > 0))


def cnb_comparison(frame, cnb, actual, models):
    """Return per-clock common pairs, coverage, selected clocks and raw projections.

    Repeated report/quarter observations are intentionally retained. No CNB
    value or realised outcome is used to choose a snapshot or model.
    """
    unique(frame)
    if frame.groupby("origin").as_of_utc.nunique().gt(1).any():
        raise ValueError("Inconsistent as_of_utc within a simulated origin")
    clocks = pd.to_datetime(frame.drop_duplicates("origin").set_index("origin").as_of_utc, utc=True)
    selected_cnb = cnb[cnb.is_forecast.astype(str).str.lower().eq("true") & cnb.report_date.ge("2022-01-01")]
    unique(selected_cnb, ["report_date", "quarter"])
    lookup = {(o, m): dict(zip(g.target, g.yy_exante)) for (o, m), g in frame.groupby(["origin", "model"])}
    rows, coverage, clock_rows, projections = [], [], [], []
    columns = ["clock", "report_date", "cutoff_date", "quarter", "quarters_ahead", "origin", "as_of_utc", "model", "forecast", "realised", "error",
               "model_cnb_deviation", "realised_cnb_error", "abs_error_gain_vs_cnb", "squared_error_gain_vs_cnb", "material_gain", "material_loss", "deviation_direction_correct"]
    for (date, cutoff), g in selected_cnb.groupby(["report_date", "cutoff_date"]):
        for mode, day in (("report", date), ("cutoff", cutoff)):
            chosen = select_snapshot(clocks, day, mode)
            origin, clock = chosen if chosen else (None, None)
            clock_rows.append(dict(clock=mode, report_date=date, cutoff_date=cutoff, origin=origin, as_of_utc=str(clock) if clock is not None else None))
            for qr in g.itertuples():
                realised = quarter_actual(qr.quarter, actual)
                predicted = {m: quarter_value(qr.quarter, origin, lookup.get((origin, m), {}), actual) if chosen else np.nan for m in models}
                missing = [m for m, v in predicted.items() if not np.isfinite(v)]
                included = not missing and np.isfinite(realised) and np.isfinite(qr.value)
                common = dict(clock=mode, report_date=date, cutoff_date=cutoff, quarter=qr.quarter,
                              quarters_ahead=pd.Period(qr.quarter, "Q").ordinal - pd.Period(date, "Q").ordinal + 1,
                              origin=origin, as_of_utc=str(clock) if clock is not None else None)
                coverage.append(dict(**common, included=included, actual_complete=bool(np.isfinite(realised)),
                                     missing_models="|".join(missing), n_models_available=len(models) - len(missing),
                                     reason="included" if included else "no_snapshot" if not chosen else "incomplete_actual" if not np.isfinite(realised) else "incomplete_model_quarter"))
                for model, value in {**predicted, "cnb": float(qr.value)}.items():
                    row = dict(**common, model=model, forecast=value, realised=realised, error=value - realised,
                               **gain_fields(value, qr.value, realised))
                    projections.append(dict(**row, included=included))
                    if included:
                        rows.append(row)
    return (pd.DataFrame(rows, columns=columns), pd.DataFrame(coverage), pd.DataFrame(clock_rows),
            pd.DataFrame(projections, columns=[*columns, "included"]))


def revision_pairs(frame):
    unique(frame)
    data = frame.sort_values(["model", "target", "origin"]).copy()
    groups = data.groupby(["model", "target"])
    data["previous_origin"] = groups.origin.shift()
    data["previous_h"] = groups.h.shift()
    data["previous_forecast"] = groups.yy_exante.shift()
    data["revision"] = data.yy_exante - data.previous_forecast
    ordinal = pd.PeriodIndex(data.origin, freq="M").asi8
    previous = pd.PeriodIndex(data.previous_origin, freq="M").asi8
    return data[(ordinal - previous == 1) & data.previous_h.eq(data.h + 1) & np.isfinite(data.revision)].copy()


def block_bootstrap(pairs, block=12, draws=2000, seed=1509):
    """Moving calendar-month blocks. Never bridge a missing matched origin.

    Point estimate uses every paired origin; resamples use only complete
    calendar blocks. Report uncovered origins explicitly when support has gaps.
    """
    data = pairs.sort_values("origin")
    unique(data, ["origin"])
    values = data.loss_difference.to_numpy(float)
    if not np.isfinite(values).all():
        raise ValueError("Bootstrap support must be finite before resampling")
    ordinal = pd.PeriodIndex(data.origin, freq="M").asi8
    starts = [i for i in range(len(data) - block + 1) if np.all(np.diff(ordinal[i:i + block]) == 1)]
    covered = set(j for i in starts for j in range(i, i + block))
    result = dict(n=len(data), block=block, draws=draws, seed=seed, eligible_blocks=len(starts),
                  n_origins_in_blocks=len(covered), mean_loss_difference=float(values.mean()) if len(values) else np.nan,
                  ci_low=np.nan, ci_high=np.nan, bootstrap_probability_improvement=np.nan,
                  status="insufficient_contiguous_support" if not starts else "uncovered_support_origins" if len(covered) < len(data) else "ok")
    if result["status"] == "ok":
        rng = np.random.default_rng(seed)
        indices = rng.choice(starts, size=(draws, int(np.ceil(len(data) / block))))[:, :, None] + np.arange(block)
        samples = values[indices.reshape(draws, -1)[:, :len(data)]].mean(axis=1)
        result.update(ci_low=float(np.quantile(samples, .025)), ci_high=float(np.quantile(samples, .975)),
                      bootstrap_probability_improvement=float(np.mean(samples < 0)))
    return result


def samples(frame):
    return {
        "full": pd.Series(True, index=frame.index),
        "origins_2019_2021": frame.origin.between("2019-01", "2021-12"),
        "origins_2022_2023": frame.origin.between("2022-01", "2023-12"),
        "origins_2024plus": frame.origin.ge("2024-01"),
        "recent_targets": frame.target.ge("2024-01"),
    }


def scopes(models):
    return [("all_models_common", list(models)), *[("paired_" + m, [BASE, m]) for m in models if m != BASE]]


def error_stats(error):
    error = np.asarray(error, dtype=float)
    error = error[np.isfinite(error)]
    return dict(n=len(error), mae=float(np.mean(abs(error))) if len(error) else np.nan,
                rmse=float(np.sqrt(np.mean(error ** 2))) if len(error) else np.nan,
                bias=float(np.mean(error)) if len(error) else np.nan)


def score_tables(frame, models=ROSTER, metrics=METRICS):
    rows, differences = [], []
    for scope, selected in scopes(models):
        for metric, (prediction, actual) in metrics.items():
            matched = matched_rows(frame[frame.h.gt(0)], selected, prediction, actual)
            for h in range(1, 13):
                group = matched[matched.h.eq(h)]
                for sample, mask in samples(group).items():
                    sample_rows = group.loc[mask]
                    for model in selected:
                        own = sample_rows[sample_rows.model.eq(model)]
                        rows.append(dict(scope=scope, sample=sample, metric=metric, h=h, model=model,
                                         **error_stats(own[prediction] - own[actual])))
                if BASE not in selected:
                    continue
                baseline = group[group.model.eq(BASE)][["origin", prediction]].rename(columns={prediction: "baseline"})
                for model in selected:
                    if model == BASE:
                        continue
                    own = group[group.model.eq(model)].merge(baseline, on="origin", validate="one_to_one")
                    for r in own.to_dict("records"):
                        e, b = r[prediction] - r[actual], r["baseline"] - r[actual]
                        differences.append(dict(scope=scope, metric=metric, origin=r["origin"], target=r["target"], h=h, model=model,
                                                forecast=r[prediction], baseline=r["baseline"], actual=r[actual],
                                                loss_difference=e ** 2 - b ** 2, absolute_loss_difference=abs(e) - abs(b)))
    return pd.DataFrame(rows), pd.DataFrame(differences)


def adjacent_quarter_changes(frame, actual):
    rows = []
    for (origin, model), g in frame.groupby(["origin", "model"]):
        path = dict(zip(g.target, g.yy_exante))
        first, last = pd.Period(origin, "M").asfreq("Q"), (pd.Period(origin, "M") + 12).asfreq("Q")
        previous = None
        for q in pd.period_range(first, last, freq="Q"):
            pred, truth = quarter_value(q, origin, path, actual), quarter_actual(q, actual)
            if previous is not None:
                p0, a0 = previous
                if np.isfinite([pred, truth, p0, a0]).all():
                    rows.append(dict(origin=origin, target=str(q.asfreq("M", "end")), model=model, quarter=str(q),
                                     predicted_change=pred - p0, actual_change=truth - a0,
                                     material_actual=abs(truth - a0) > .25))
            previous = pred, truth
    return pd.DataFrame(rows, columns=["origin", "target", "model", "quarter", "predicted_change", "actual_change", "material_actual"])


def core_turn_diagnostics(frame, states):
    """Underlying core is twelve times the band-average monthly log SA rate.

    A material change is >=0.5 pp annualized. Peaks/troughs require two opposite
    material adjacent changes at band 2 or 3. Seasonality is frozen per origin.
    """
    paths, changes, turns = [], [], []
    for (origin, model), g in frame.groupby(["origin", "model"]):
        saved = states.get(origin, {}).get("seasonal", {})
        bands = {}
        for band in range(1, 5):
            own = g[g.h.between(3 * band - 2, 3 * band)].set_index("h").reindex(range(3 * band - 2, 3 * band + 1))
            season = np.array([saved.get(str((pd.Period(origin, "M") + h).month), saved.get((pd.Period(origin, "M") + h).month, np.nan)) for h in own.index])
            values = {}
            for name, col in (("predicted", "core_mm_forecast"), ("actual", "core_mm_actual")):
                monthly = 100 * np.log1p(own[col].to_numpy(float) / 100) - season
                values[name] = float(12 * monthly.mean()) if np.isfinite(monthly).all() else np.nan
            bands[band] = values
            paths.append(dict(origin=origin, model=model, band=band, target=str(pd.Period(origin, "M") + 3 * band),
                              predicted_sa_annualized=values["predicted"], actual_sa_annualized=values["actual"]))
        for band in (2, 3, 4):
            pred = bands[band]["predicted"] - bands[band - 1]["predicted"]
            truth = bands[band]["actual"] - bands[band - 1]["actual"]
            changes.append(dict(origin=origin, model=model, band=band, target=str(pd.Period(origin, "M") + 3 * band),
                                predicted_change=pred, actual_change=truth, material_actual=bool(abs(truth) >= .5 - 1e-12)))
        for band in (2, 3):
            result = {}
            for name in ("predicted", "actual"):
                a, b, c = [bands[k][name] for k in (band - 1, band, band + 1)]
                d1, d2 = b - a, c - b
                turn = None
                if np.isfinite([a, b, c]).all():
                    turn = "peak" if d1 >= .5 - 1e-12 and d2 <= -.5 + 1e-12 else "trough" if d1 <= -.5 + 1e-12 and d2 >= .5 - 1e-12 else "none"
                result[name + "_turn"] = turn
            eligible = result["predicted_turn"] is not None and result["actual_turn"] is not None
            hit = eligible and result["actual_turn"] != "none" and result["predicted_turn"] == result["actual_turn"]
            turns.append(dict(origin=origin, model=model, band=band, target=str(pd.Period(origin, "M") + 3 * band), **result,
                              eligible=eligible, exact_hit=hit,
                              missed_turn=eligible and result["actual_turn"] != "none" and not hit,
                              false_turn=eligible and result["predicted_turn"] != "none" and not hit))
    return pd.DataFrame(paths), pd.DataFrame(changes), pd.DataFrame(turns)


def direction_tables(frame, actual, models=ROSTER):
    rows, pairs = [], []
    data = frame.copy()
    data["latest_known_yy"] = [actual.get(pd.Period(o, "M") - 1, np.nan) for o in data.origin]
    data = data[np.isfinite(data.latest_known_yy)]
    for scope, selected in scopes(models):
        common = matched_rows(data[data.h.isin([3, 6, 9, 12])], selected, "yy_exante", "yy_actual")
        common["predicted_change"] = common.yy_exante - common.latest_known_yy
        common["actual_change"] = common.yy_actual - common.latest_known_yy
        common["predicted_direction"] = classify(common.predicted_change)
        common["actual_direction"] = classify(common.actual_change)
        pairs.append(common.assign(scope=scope))
        for sample, mask in samples(common).items():
            for (h, model), g in common.loc[mask].groupby(["h", "model"]):
                rows.append(dict(scope=scope, sample=sample, h=h, model=model, **direction_stats(g.yy_exante.to_numpy(), g.yy_actual.to_numpy(), g.latest_known_yy.to_numpy())))
    return pd.DataFrame(rows), pd.concat(pairs, ignore_index=True)


def change_summaries(changes, key, models=ROSTER, threshold=.25):
    rows = []
    for scope, selected in scopes(models):
        common = matched_rows(changes, selected, "predicted_change", "actual_change", keys=("origin", key))
        for sample, mask in samples(common).items():
            for (step, model), g in common.loc[mask].groupby([key, "model"]):
                material = g.material_actual.to_numpy(bool)
                pred, truth = g.predicted_change.to_numpy(float), g.actual_change.to_numpy(float)
                calls = abs(pred) >= threshold - 1e-12 if threshold == .5 else abs(pred) > threshold
                hits = (np.sign(pred) == np.sign(truth)) & calls & material
                wrong = (np.sign(pred) != np.sign(truth)) & calls & material
                rows.append(dict(scope=scope, sample=sample, model=model, **{key: step}, n=len(g), actual_material_n=int(material.sum()),
                                 sign_match_rate_on_material_actual=float(np.mean(np.sign(pred[material]) == np.sign(truth[material]))) if material.any() else np.nan,
                                 material_direction_hit_rate=float(hits.sum() / material.sum()) if material.any() else np.nan,
                                 material_calls_n=int(calls.sum()), wrong_way_n=int(wrong.sum())))
    return pd.DataFrame(rows)


def turn_summaries(turns, models=ROSTER):
    rows = []
    for scope, selected in scopes(models):
        data = turns[turns.model.isin(selected) & turns.eligible].copy()
        counts = data.groupby(["origin", "band"]).model.nunique()
        good = counts.index[counts.eq(len(selected))]
        data = data.set_index(["origin", "band"]).loc[lambda x: x.index.isin(good)].reset_index()
        for sample, mask in samples(data).items():
            for model, g in data.loc[mask].groupby("model"):
                truth, pred, hits = int(g.actual_turn.ne("none").sum()), int(g.predicted_turn.ne("none").sum()), int(g.exact_hit.sum())
                rows.append(dict(scope=scope, sample=sample, model=model, n=len(g), actual_turns=truth, predicted_turns=pred,
                                 exact_band_hits=hits, missed_turns=int(g.missed_turn.sum()), false_turns=int(g.false_turn.sum()),
                                 exact_turn_recall=hits / truth if truth else np.nan, exact_turn_precision=hits / pred if pred else np.nan))
    return pd.DataFrame(rows)


def revision_summaries(revisions, models=ROSTER):
    """Stability depends on forecasts only; future realised outcomes are irrelevant."""
    rows = []
    data = revisions.assign(revision_zero=0.)
    for scope, selected in scopes(models):
        common = matched_rows(data, selected, "revision", "revision_zero", keys=("origin", "target"))
        for sample, mask in samples(common).items():
            for model, g in common.loc[mask].groupby("model"):
                rows.append(dict(scope=scope, sample=sample, model=model, **error_stats(g.revision), max_abs=float(abs(g.revision).max())))
    return pd.DataFrame(rows)


def cnb_summaries(pairs, scope="within_clock_common"):
    rows = []
    for sample, f in (("full", pairs), ("reports_2024plus", pairs[pairs.report_date.ge("2024-01-01")])):
        for (clock, model), group in f.groupby(["clock", "model"]):
            for horizon, g in [("all", group), *list(group.groupby("quarters_ahead"))]:
                rows.append(dict(scope=scope, sample=sample, clock=clock, model=model, quarters_ahead=horizon,
                                 **error_stats(g.error), report_count=g.report_date.nunique(), unique_target_quarters=g.quarter.nunique(),
                                 cnb_mae=float(np.mean(abs(g.realised_cnb_error))),
                                 mean_absolute_error_gain_vs_cnb=float(g.abs_error_gain_vs_cnb.mean()),
                                 material_gains=int(g.material_gain.sum()), material_losses=int(g.material_loss.sum()),
                                 immaterial_pairs=int((~g.material_gain & ~g.material_loss).sum()),
                                 mean_model_cnb_deviation=float(g.model_cnb_deviation.mean()),
                                 mean_realised_cnb_error=float(g.realised_cnb_error.mean()),
                                 deviation_direction_correct_rate=float(g.deviation_direction_correct.mean()),
                                 deviation_error_correlation=float(g.model_cnb_deviation.corr(g.realised_cnb_error)) if len(g) > 1 and g.model_cnb_deviation.std() > 0 and g.realised_cnb_error.std() > 0 else np.nan))
    return pd.DataFrame(rows)


def diagnostic_distributions(core_predictions, selections, fits):
    cp = core_predictions.copy()
    mid = cp[cp.model.eq("STATE_MID_R15")][["origin", "h", "core_log"]].rename(columns={"core_log": "state_mid_log"})
    cp = cp.merge(mid, on=["origin", "h"], how="left", validate="many_to_one")
    cp["correction_log"] = cp.core_log - cp.state_mid_log
    cp["band"] = (cp.h - 1) // 3 + 1
    corrections = []
    for (model, band), g in cp.groupby(["model", "band"]):
        v = g.correction_log[np.isfinite(g.correction_log)]
        corrections.append(dict(model=model, band=band, n=len(v), mean=float(v.mean()), mean_abs=float(abs(v).mean()),
                                p05=float(v.quantile(.05)), median=float(v.median()), p95=float(v.quantile(.95)), max_abs=float(abs(v).max())))
    selection_rows = pd.DataFrame(selections)
    if len(selection_rows):
        distribution = selection_rows.groupby(["family", "band", "config", "reason"], dropna=False).size().rename("n").reset_index()
        distribution["share_within_family_band"] = distribution.n / distribution.groupby(["family", "band"]).n.transform("sum")
    else:
        distribution = pd.DataFrame(columns=["family", "band", "config", "reason", "n", "share_within_family_band"])
    coefficients = []
    for fit in fits:
        base = {k: fit.get(k) for k in ("origin", "band", "family", "config", "status", "converged", "n_train")}
        for kind in ("coefficients", "feature_importances"):
            for feature, value in fit.get(kind, {}).items():
                group = feature_group(feature)
                coefficients.append(dict(**base, measure=kind, feature=feature, source_group=group, value=value))
        if fit.get("intercept") is not None:
            coefficients.append(dict(**base, measure="coefficients", feature="penalized_constant", source_group="constant", value=fit["intercept"]))
    details = pd.DataFrame(coefficients, columns=["origin", "band", "family", "config", "status", "converged", "n_train", "measure", "feature", "source_group", "value"])
    if len(details):
        groups = details.assign(absolute_value=abs(details.value)).groupby(["family", "band", "measure", "source_group"]).agg(n=("value", "size"), mean=("value", "mean"), mean_abs=("absolute_value", "mean")).reset_index()
    else:
        groups = pd.DataFrame(columns=["family", "band", "measure", "source_group", "n", "mean", "mean_abs"])
    return cp, pd.DataFrame(corrections), distribution, details, groups


def feature_group(feature):
    if feature in ("core1", "core3", "core12", "core_acceleration", "midtrend", "midcycle", "destination_season"):
        return "own_core_state"
    if feature.startswith(("services", "unemployment", "ip_", "ulc_")) or feature in ("a6_11", "a6_12", "a6_17"):
        return "domestic"
    if feature.startswith(("goods", "fx", "cost_")) or feature in ("a6_23", "a6_26", "a6_45", "a6_47", "a6_56", "a6_62", "a6_65", "a6_66"):
        return "imported_cost"
    return "other_hard_a6" if feature.startswith("a6_") else "other"


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [json_safe(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.integer, np.bool_)):
        return value.item()
    if isinstance(value, (pd.Period, pd.Timestamp, Path)):
        return str(value)
    return value


def write_replay(path, data, template):
    """Adapt the existing local CNB layout in memory; never edit its source."""
    html = Path(template).read_text(encoding="utf-8")
    html = re.sub(r'<link[^>]+>\s*', '', html)
    data = dict(data, reports=data["reportsByClock"]["report"])
    payload = json.dumps(json_safe(data), ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    html = html.replace("/*__DATA__*/null", payload)
    html = html.replace('cnb-rounds-visible-v1', 'cnb-rounds-r15-visible-v1')
    html = html.replace('  <main class="rounds"', '''  <section class="switchboard" aria-label="Replay selection">
    <label for="clock-select">Historical replay clock</label>
    <select id="clock-select"><option value="report">Before report day</option><option value="cutoff">Through CNB cutoff day</option></select>
    <label for="round-select">CNB round</label><select id="round-select"><option value="all">All rounds</option></select>
    <p class="caption">Scores always use the complete 14-model roster, regardless of boxes shown. Current-vintage realised outcomes; simulated historical availability. Repeated overlapping quarters are not independent.</p>
    <p><a href="scoreboard.csv">Full / era / recent-target headline and core scores</a> · <a href="cnb_summary.csv">Both CNB clocks</a> · <a href="coverage_ledger.csv">Forecast coverage</a> · <a href="definitions.json">Calculation definitions</a></p>
  </section>
  <main class="rounds"''')
    html = html.replace('<button type="button" class="chip" data-id="${s.id}" aria-pressed="${visible.has(s.id)}">${swatch(s)}<span>${esc(s.label)}</span></button>',
                        '<label class="chip" aria-pressed="${visible.has(s.id)}"><input type="checkbox" data-id="${s.id}" ${visible.has(s.id) ? "checked" : ""}>${swatch(s)}<span>${esc(s.label)}</span></label>')
    html = html.replace('chips.addEventListener("click", e => {', 'chips.addEventListener("change", e => {')
    html = html.replace('const b = e.target.closest(".chip");', 'const b = e.target.closest("input[data-id]");')
    html = html.replace('b.setAttribute("aria-pressed", String(visible.has(id)));', 'b.closest(".chip").setAttribute("aria-pressed", String(visible.has(id)));')
    html = html.replace('None of this report\'s forecast quarters has fully come in yet, so there is nothing to score.',
                        'No complete realised quarter on the full model roster for this report and clock. See the coverage table for unavailable forecasts or outcomes.')
    html = html.replace('    rounds.innerHTML = html;', '    rounds.innerHTML = html || "<p>No eligible historical snapshots for this selection.</p>";')
    html = html.replace('  const reports = DATA.reports;\n', '''  const clockSelect = document.getElementById("clock-select");
  const roundSelect = document.getElementById("round-select");
  const dates = [...new Set(Object.values(DATA.reportsByClock).flat().map(r => r.report_date))].sort();
  roundSelect.innerHTML += dates.map(d => `<option value="${d}">${dLabel(d)}</option>`).join("");
  const applySelection = () => {
    DATA.reports = DATA.reportsByClock[clockSelect.value].filter(r => roundSelect.value === "all" || r.report_date === roundSelect.value);
    buildPlates(); renderAll();
  };
  clockSelect.addEventListener("change", applySelection);
  roundSelect.addEventListener("change", applySelection);
  const reports = DATA.reports;
''')
    html = html.replace('`${reports.length} CNB Monetary Policy Reports', '`${reports.length} CNB Monetary Policy Reports')
    html = html.replace('`Czech CPI · ${reports.length} CNB Monetary Policy Reports · ${reports[0].season} ${reports[0].year} to ${reports[reports.length - 1].season} ${reports[reports.length - 1].year}`;',
                        '`Czech CPI · R15 · ${dates.length} CNB Monetary Policy Reports · historical replay`;')
    html = html.replace('const max = Math.max(...items.map(x => x[1]));', 'const max = Math.max(0.000001, ...items.map(x => x[1]));')
    extra = '<style>select{font:inherit;margin:8px 18px 8px 6px;padding:7px;border:1px solid var(--rule);border-radius:4px;background:var(--surface);color:var(--ink)}a{color:var(--focus)}input[type=checkbox]{accent-color:var(--focus)}:focus-visible{outline:3px solid var(--focus);outline-offset:3px}</style>'
    colors = ''.join(f'{s["color"]}:{s["hex"]};' for s in data["series"] if "hex" in s)
    html = html.replace('</style>', '</style>' + '<style>:root{' + colors + '}</style>' + extra, 1)
    Path(path).write_text('<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n' + html + '\n</html>\n', encoding="utf-8")


def replay_data(frame, cnb, actual, pairs, clocks):
    labels = {"INDEPENDENT_BRIDGE": "Independent bridge", BASE: "Stable pipeline",
              "STABLE_LOCAL_CORE_R14B": "Current core", "STATE_SLOW_R15": "State · slow",
              "STATE_MID_R15": "State · mid", "STATE_FAST_R15": "State · fast", "STATE_ADAPT_R15": "State · adaptive",
              "ENET_DOMESTIC_R15": "Elastic net · domestic", "ENET_IMPORTED_R15": "Elastic net · imported",
              "ENET_BOTH_R15": "Elastic net · both", "ENET_WIDE_R15": "Elastic net · wide",
              "RF_RESIDUAL_R15": "Residual forest", "BLEND_LINEAR_RF_R15": "Linear + forest",
              "BLEND_WIDE_STATE_R15": "Wide + state"}
    colors = ["#1F5DB4", "#24958A", "#0A7568", "#98AFC1", "#3F739A", "#14496E", "#6595AF",
              "#A086BA", "#9354AB", "#743A97", "#BF639E", "#D4700C", "#AC772B", "#B58454"]
    defaults = {BASE, "STABLE_LOCAL_CORE_R14B", "STATE_FAST_R15"}
    series = [dict(id="realised", label="Realised · current vintage", kind="realised", color="--realised", width=2.4, default=True),
              dict(id="cnb", label="CNB published forecast", kind="cnb", color="--cnb", width=2, default=True)]
    series += [dict(id=m, label=labels[m], short=labels[m], kind="model", color=f"--r15-{i}", hex=colors[i], width=2., default=m in defaults,
                    dash="5 3" if m in CONTROLS else "") for i, m in enumerate(ROSTER)]
    reports = {"report": [], "cutoff": []}
    selected = cnb[cnb.is_forecast.astype(str).str.lower().eq("true") & cnb.report_date.ge("2022-01-01")]
    for clock in clocks.to_dict("records"):
        if clock["origin"] is None:
            continue
        mode, date, origin = clock["clock"], clock["report_date"], clock["origin"]
        g = selected[selected.report_date.eq(date)].sort_values("quarter")
        if g.empty:
            continue
        o = pd.Period(origin, "M")
        quarter = pd.Period(date, "Q")
        start = (quarter - 2).asfreq("M", "start")
        end = pd.Period(g.quarter.iloc[-1], "Q").asfreq("M", "end")
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
            quarter_points[model] = [[q, v] for q in g.quarter if np.isfinite(v := quarter_value(q, o, path, actual))]
        score_rows = pairs[pairs.clock.eq(mode) & pairs.report_date.eq(date)]
        score_quarters = sorted(score_rows.quarter.unique())
        score = dict(n=len(score_quarters), quarters=score_quarters,
                     mae={m: float(abs(z.error).mean()) for m, z in score_rows.groupby("model")})
        season = str(g.season.iloc[0]).capitalize() if "season" in g else {1: "Winter", 2: "Spring", 3: "Summer", 4: "Autumn"}[quarter.quarter]
        reports[mode].append(dict(id=date + "-" + mode, report_date=date, cutoff_date=clock["cutoff_date"], origin=origin,
                                  origin_clock=pd.Timestamp(clock["as_of_utc"]).tz_convert("Europe/Prague").strftime("%Y-%m-%d %H:%M"),
                                  season=season, season_cs={"Winter": "Zima", "Spring": "Jaro", "Summer": "Léto", "Autumn": "Podzim"}.get(season, ""),
                                  year=int(date[:4]), window=dict(start=str(start), end=str(end)),
                                  cnb=[dict(quarter=r.quarter, value=float(r.value)) for r in g.itertuples()],
                                  realised_quarters=[dict(quarter=q, value=v) for q in g.quarter if np.isfinite(v := quarter_actual(q, actual))],
                                  paths=paths, quarter_points=quarter_points, score=score))
    method = [
        "These are simulated historical forecasts using frozen current-vintage inputs with reconstructed release availability. They were calculated later, and are not certified historical vintages or live prospective forecasts.",
        "Report clock: latest existing snapshot strictly before 00:00 Europe/Prague on the report date. Cutoff clock: latest snapshot through the end of the CNB cutoff date (strictly before next-day 00:00 Prague). Both clocks are retained; neither is chosen using accuracy.",
        "Model quarterly averages use three annual-CPI observations: frozen known history for months before the chosen origin and forecasts from that single origin for every subsequent month. There is no borrowing from later-origin paths. All three months and every roster model must be finite for a scored quarter.",
        "Every per-panel score uses identical report/quarter support for all fourteen models and CNB, unaffected by which series are visible. Pooled CSVs retain overlapping quarters across reports; these are descriptive dependent observations, not independent trials. Cross-clock matched scores are also included.",
        "A model materially improves on CNB when CNB absolute error minus model absolute error is at least 0.15 percentage points; a loss is at most -0.15. A forecast on the right side of CNB can overshoot and does not by itself win.",
        "Headline annual levels can move with base effects. The separate underlying-core tables use each origin's saved seasonal pattern and four three-month bands, and identify peaks/troughs only after two opposite changes of at least 0.5 percentage points annualized. They are diagnostics, not tuning targets or a CNB core-forecast comparison.",
        "New headline models retain the same HARD_BASE h0 and fixed non-core path as the stable pipeline. This isolates the core experiment. No CNB outcome chooses coefficients, configurations, model weights or promotion. Default visible models are fast state, current core and pipeline for readability; this display choice is not a model promotion, and all fourteen models remain selectable and scored.",
    ]
    return dict(series=series, reportsByClock=reports, realised={str(k): float(v) for k, v in actual.dropna().items()}, method=method,
                title="CNB Rounds Replayed · R15", vintage="current-vintage simulated historical")


def read_monthly(path, column):
    frame = pd.read_csv(path, float_precision="round_trip")
    index = pd.PeriodIndex(frame.iloc[:, 0], freq="M")
    if not index.is_unique:
        raise ValueError("Duplicate monthly input: " + str(path))
    series = pd.Series(frame[column].to_numpy(float), index=index).sort_index()
    return series.reindex(pd.period_range(series.index.min(), series.index.max(), freq="M"))


def assert_close(left, right, label, tolerance=1e-9):
    left, right = np.asarray(left, float), np.asarray(right, float)
    if not np.allclose(left, right, atol=tolerance, rtol=0, equal_nan=True):
        raise ValueError("Frozen input reconciliation failed: " + label)
    finite = np.isfinite(left) & np.isfinite(right)
    return float(np.max(abs(left[finite] - right[finite]))) if finite.any() else 0.


def verify_arithmetic(frame, headline, actual_yy):
    actual_mm = [headline.get(pd.Period(t, "M"), np.nan) for t in frame.target]
    yy = [actual_yy.get(pd.Period(t, "M"), np.nan) for t in frame.target]
    checks = dict(headline_actual_mm_max=assert_close(frame.mm_actual, actual_mm, "headline monthly actual"),
                  headline_actual_yy_max=assert_close(frame.yy_actual, yy, "headline annual actual"))
    expected_yy, saved_yy, expected_cum, saved_cum = [], [], [], []
    for (origin, _), g in frame.groupby(["origin", "model"]):
        o = pd.Period(origin, "M")
        path = dict(zip(g.h, g.mm_forecast))
        for row in g.itertuples():
            months = pd.period_range(o + row.h - 11, o + row.h, freq="M")
            vals = np.array([headline.get(t, np.nan) if t < o else path.get(t.ordinal - o.ordinal, np.nan) for t in months])
            expected_yy.append(float(100 * np.expm1(np.log1p(vals / 100).sum())) if np.isfinite(vals).all() else np.nan)
            saved_yy.append(row.yy_exante)
            vals = np.array([path.get(h, np.nan) for h in range(1, row.h + 1)])
            expected_cum.append(float(100 * np.log1p(vals / 100).sum()) if np.isfinite(vals).all() else np.nan)
            saved_cum.append(row.cumulative_log_forecast)
    checks["same_origin_annual_compounding_max"] = assert_close(saved_yy, expected_yy, "same-origin annual compounding")
    checks["headline_cumulative_log_max"] = assert_close(saved_cum, expected_cum, "headline cumulative log")
    return checks


def evaluate(experiment, root=ROOT):
    experiment, root = Path(experiment).resolve(), Path(root).resolve()
    out = experiment / "evaluation"
    input_files = [experiment / p for p in ("forecasts.csv", "native_forecasts.csv", "core_predictions.csv", "states.json", "selections.json", "fits.json")]
    input_files += [root / p for p in ("output/research_r14b/integration/forecasts.csv", "output/research_r14b/integration/native_forecasts.csv",
                                     "output/independent_path_frozen_inputs.csv", "tests/fixtures/cleanup/cnb_core_mm.csv", "data/cnb_mpr_cpi_quarterly.csv",
                                     "tools/cnb_rounds/cnb_rounds_template.html")]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in input_files}
    read = lambda p: pd.read_csv(p, float_precision="round_trip")
    frame, native, cp = [read(experiment / p) for p in ("forecasts.csv", "native_forecasts.csv", "core_predictions.csv")]
    unique(frame); unique(native); unique(cp)
    origins = sorted(frame.origin.unique())
    controls = read(root / "output/research_r14b/integration/forecasts.csv")
    controls = controls[controls.model.isin(CONTROLS) & controls.origin.isin(origins)]
    unique(controls)
    overlap = frame[frame.model.isin(CONTROLS)].merge(controls, on=KEYS, suffixes=("", "_frozen"), how="outer", validate="one_to_one", indicator=True)
    if not overlap.empty and not overlap._merge.eq("both").all():
        raise ValueError("Control key support differs from frozen controls")
    for col in ("mm_forecast", "yy_exante", "mm_actual", "yy_actual"):
        if not overlap.empty:
            assert_close(overlap[col], overlap[col + "_frozen"], "control " + col)
    frame = pd.concat([frame[frame.model.isin(NEW_MODELS)], controls], ignore_index=True)
    base_native = read(root / "output/research_r14b/integration/native_forecasts.csv")
    base_native = base_native[base_native.model.isin(CONTROLS) & base_native.origin.isin(origins)]
    all_native = pd.concat([native[native.model.isin(NEW_MODELS)], base_native], ignore_index=True)
    if len(cp):
        assert_close(cp.core_log, 100 * np.log1p(cp.core_mm / 100), "core log reconstruction")
        join = cp.merge(native[[*KEYS, "value_core"]], on=KEYS, how="left", validate="one_to_one")
        assert_close(join.core_mm, join.value_core, "native core vs raw prediction")
    headline = read_monthly(root / "output/independent_path_frozen_inputs.csv", "headline_mm")
    actual_yy = 100 * np.expm1(np.log1p(headline / 100).rolling(12).sum())
    core_actual = read_monthly(root / "tests/fixtures/cleanup/cnb_core_mm.csv", "core")
    checks = verify_arithmetic(frame, headline, actual_yy)
    frame = attach_core(frame, all_native, cp, core_actual)
    cnb = read(root / "data/cnb_mpr_cpi_quarterly.csv")
    states = json.loads((experiment / "states.json").read_text(encoding="utf-8"))
    selections = json.loads((experiment / "selections.json").read_text(encoding="utf-8"))
    fits = json.loads((experiment / "fits.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    generated = []

    def csv(name, data):
        data.to_csv(out / name, index=False)
        generated.append(name)

    def dump(name, data):
        (out / name).write_text(json.dumps(json_safe(data), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        generated.append(name)

    grid = pd.MultiIndex.from_product([origins, range(13), ROSTER], names=KEYS).to_frame(index=False)
    ledger = grid.merge(frame, on=KEYS, how="left", validate="one_to_one", indicator=True)
    ledger["row_present"] = ledger._merge.eq("both")
    ledger["target"] = [str(pd.Period(o, "M") + int(h)) for o, h in zip(ledger.origin, ledger.h)]
    for metric, (pred, truth) in METRICS.items():
        ledger[metric + "_forecast_finite"] = np.isfinite(ledger[pred])
        ledger[metric + "_actual_finite"] = np.isfinite(ledger[truth])
    status_cols = [c for c in ("status", "origin_status", "converged", "fallback_used") if c in all_native]
    ledger = ledger.drop(columns="_merge").merge(all_native[[*KEYS, *status_cols]], on=KEYS, how="left", validate="one_to_one")
    csv("coverage_ledger.csv", ledger)
    csv("forecast_core_outcomes.csv", frame)
    coverage_summary = []
    for sample, mask in samples(ledger).items():
        for (model, h), g in ledger.loc[mask].groupby(["model", "h"]):
            for metric in METRICS:
                coverage_summary.append(dict(sample=sample, model=model, h=h, metric=metric, n_intended=len(g), n_rows_present=int(g.row_present.sum()),
                                             n_forecasts=int(g[metric + "_forecast_finite"].sum()), n_actuals=int(g[metric + "_actual_finite"].sum()),
                                             n_scoreable=int((g[metric + "_forecast_finite"] & g[metric + "_actual_finite"]).sum())))
    csv("coverage_summary.csv", pd.DataFrame(coverage_summary))
    print("R15 evaluation: matched support and diagnostics", flush=True)
    scores, differences = score_tables(frame)
    csv("scoreboard.csv", scores)
    csv("paired_loss_differences.csv", differences)
    directions, direction_pairs = direction_tables(frame, actual_yy)
    csv("headline_direction_summary.csv", directions)
    csv("headline_direction_pairs.csv", direction_pairs)
    quarter_changes = adjacent_quarter_changes(frame, actual_yy)
    csv("headline_quarter_change_pairs.csv", quarter_changes)
    csv("headline_quarter_change_summary.csv", change_summaries(quarter_changes, "quarter"))
    paths, core_changes, core_turns = core_turn_diagnostics(frame, states)
    csv("underlying_core_bands.csv", paths)
    csv("underlying_core_changes.csv", core_changes)
    csv("underlying_core_change_summary.csv", change_summaries(core_changes, "band", threshold=.5))
    csv("underlying_core_turns.csv", core_turns)
    csv("underlying_core_turn_summary.csv", turn_summaries(core_turns))
    revisions = revision_pairs(frame)
    csv("revision_pairs.csv", revisions)
    csv("revision_summary.csv", revision_summaries(revisions))
    correction_rows, correction_stats, selection_stats, coefficient_rows, coefficient_groups = diagnostic_distributions(cp, selections, fits)
    for name, data in (("correction_paths.csv", correction_rows), ("correction_distribution.csv", correction_stats), ("selected_config_distribution.csv", selection_stats),
                       ("coefficient_feature_details.csv", coefficient_rows), ("coefficient_source_groups.csv", coefficient_groups)):
        csv(name, data)
    fit_frame = pd.DataFrame(fits)
    fit_keys = [k for k in ("family", "band", "status", "converged") if k in fit_frame]
    csv("fit_status_distribution.csv", fit_frame.groupby(fit_keys, dropna=False).size().rename("n").reset_index() if fit_keys else pd.DataFrame(columns=["family", "band", "status", "converged", "n"]))
    bootstrap = []
    for (scope, model, h), g in differences[differences.metric.eq("headline_yy") & differences.h.isin([3, 6, 9, 12])].groupby(["scope", "model", "h"]):
        for sample, mask in samples(g).items():
            bootstrap.append(dict(scope=scope, sample=sample, model=model, h=h, metric="headline_yy_squared_error", **block_bootstrap(g.loc[mask])))
    csv("headline_paired_block_bootstrap.csv", pd.DataFrame(bootstrap))
    print("R15 evaluation: both CNB clocks and interactive replay", flush=True)
    pairs, cnb_coverage, clocks, projections = cnb_comparison(frame, cnb, actual_yy, ROSTER)
    csv("cnb_pairs.csv", pairs)
    csv("cnb_coverage.csv", cnb_coverage)
    csv("cnb_clocks.csv", clocks)
    csv("cnb_quarter_projections.csv", projections)
    both = pairs.groupby(["report_date", "quarter"]).clock.nunique()
    both = both.index[both.eq(2)]
    cross = pairs.set_index(["report_date", "quarter"]).loc[lambda x: x.index.isin(both)].reset_index()
    csv("cnb_cross_clock_matched_pairs.csv", cross)
    cnb_scores = pd.concat([cnb_summaries(pairs), cnb_summaries(cross, "cross_clock_common")], ignore_index=True)
    csv("cnb_summary.csv", cnb_scores)
    data = replay_data(frame, cnb, actual_yy, pairs, clocks)
    dump("replay_data.json", data)
    write_replay(out / "cnb_rounds_replayed_r15.html", data, root / "tools/cnb_rounds/cnb_rounds_template.html")
    generated.append("cnb_rounds_replayed_r15.html")
    definitions = dict(
        vintage="Frozen current-vintage data with reconstructed historical availability; pseudo-out-of-sample, not historical-vintage certification or prospective forecast.",
        scope="No new estimation, downloads, forecast repair, tuning or model promotion. Roster is declared, including failures.",
        roster=ROSTER, baseline=BASE, horizons="h1..12, h0 retained in coverage and annual compounding; origins fixed by experiment forecasts",
        scores="RMSE=sqrt(mean((forecast-actual)^2)); MAE=mean(abs(forecast-actual)); bias=mean(forecast-actual). Score samples intersect finite rows for every named model independently per metric and horizon.",
        support="all_models_common includes the full declared roster. paired_MODEL includes exactly MODEL and STABLE_PIPELINE_R14B. Do not mix sample definitions. Missing forecasts remain in coverage_ledger.",
        samples="Full; origins 2019-21; origins 2022-23; origins 2024+; recent targets from 2024-01. No ex-post shock exclusions.",
        core="Original tests/fixtures/cleanup/cnb_core_mm.csv outcomes. Monthly percent core and cumulative sum of 100*log(1+core_mm/100) from h1 through h. A missing intermediate month makes the cumulative path missing; h0 core is not scored.",
        headline="headline_mm is separate from core_mm. Annual CPI is 100*expm1(sum of 12 monthly log rates), using known history before the origin plus monthly forecasts from that same origin. Cumulated headline logs exclude h0.",
        direction="At h3/6/9/12 compare annual forecast/actual with origin t-1 known annual CPI. Up/down require change>0.25/<-0.25pp, otherwise flat. material_direction_hit_rate requires correct material direction among material actual moves; wrong-way requires opposite material calls. This is a direction diagnostic, separate from exact core peaks/troughs.",
        adjacent_headline_quarters="Calendar-quarter averages from one origin. Consecutive quarter changes; a material actual move means absolute change >0.25pp. Both the direction sign diagnostic and separate material calls are retained.",
        underlying_core="Four bands h1:3, 4:6, 7:9, 10:12; annualized SA log core = 12*mean(100*log1p(mm/100)-saved_origin_seasonal[month]). A material adjacent change is >=0.5pp annualized. A peak/trough at band2/3 requires two opposite material changes. Exact-band hits, missed actual turns and false predicted turns are evaluated on matched support. No CNB core-forecast claim.",
        revisions="Consecutive calendar origins, identical target month, newh=oldh-1; annual CPI revisions. MAE and maximum absolute revision, raw finite pairs and matched-roster summaries. Realised outcomes never gate stability support; latest forecasts with future target dates remain included.",
        corrections="Monthly log core minus STATE_MID_R15 at identical origin,h; mean absolute and quantiles. Selection/fits band indexes are original 0..3; core diagnostic bands 1..4. Coefficients multiply train-standardized predictors; the penalized constant is retained separately. Forest importance is impurity importance, not a causal effect.",
        cnb_report_clock="Latest existing as_of_utc strictly before report_date 00:00 Europe/Prague.",
        cnb_cutoff_clock="Latest existing as_of_utc strictly before next-day 00:00 Europe/Prague (through the entire CNB cutoff date). The old independent audit used start of day and reported that end of day did not change selected runs; this comparison explicitly uses end of day.",
        cnb_support="Forecast quarters from 2022 reports onward; each three-month quarterly average uses known annual history for month<origin and the same-origin forecast for month>=origin. Score only complete actual+CNB+all-model quarters within each clock; separate cross_clock_common intersects report/quarter support over both clocks. Repeated overlapping quarters are dependent and remain visible.",
        cnb_gain="Absolute error gain = abs(CNB-actual)-abs(model-actual). Material gain >=0.15pp; material loss <=-0.15pp (1e-12 numerical tolerance). Model-CNB deviation is compared with actual-CNB error. Correct direction alone is not a win. CNB outcomes never enter fitting or selection.",
        bootstrap="Paired mean squared-loss difference model minus pipeline. Moving 12-consecutive-calendar-origin blocks, 2000 draws seed1509, 2.5/97.5 percentile interval; negative favours model. Keep exact finite paired support, never bridge calendar holes, report origins coverable by blocks. Suppress the CI if any paired origin lies in no complete block. CI is descriptive under dependent overlapping forecasts; no multiplicity adjustment or promotion threshold.",
        replay="Original CNB Rounds template adapted in memory; all JS/CSS/data embedded and external font links removed. Checkboxes change visible paths only; the fixed full-roster score basis remains. Separate report/cutoff clock selector and report selector. No network needed. Default visible models are fast state, current core and pipeline; this presentation choice is not a model promotion.")
    dump("definitions.json", definitions)
    dump("checks.json", checks)
    for p, digest in hashes.items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest:
            raise ValueError("Input changed during evaluation: " + p)
    dump("input_manifest.json", dict(created_at_utc=datetime.now(timezone.utc).isoformat(), inputs=hashes,
                                     evaluator=str(Path(__file__).resolve()), evaluator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                     command=f'python tools/review/evaluate_r15.py --experiment "{experiment}"',
                                     packages=dict(numpy=np.__version__, pandas=pd.__version__), origin_count=len(origins), model_count=len(ROSTER),
                                     outputs={name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in generated}))
    print(f"R15 evaluation finished: {out}", flush=True)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True, type=Path)
    args = parser.parse_args(argv)
    evaluate(args.experiment)


if __name__ == "__main__":
    main()
