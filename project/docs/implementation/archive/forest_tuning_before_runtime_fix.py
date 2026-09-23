"""Predeclared nested independent residual-forest tuning; two CPU workers.

Usage: python forest_tuning_experiment.py
The JSON cache supports resumable runs, keyed by eligible inputs, settings
and implementation. Only output/forest_tuning_* artifacts are written.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib.metadata
import json
import platform
import time

import numpy as np
import pandas as pd

from models.core_tuning import _monthly, hard_features


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "tests" / "fixtures" / "cleanup"
OUTPUT = ROOT / "output"
MIN_ERRORS, INNER_VALIDATION, HALF_LIFE, TREES, WORKERS = 40, 12, 6, 200, 2
MULTIPLIERS = (0.0, 0.5, 1.0)


@dataclass(frozen=True)
class ForestConfig:
    leaf: int
    max_features: float

    @property
    def key(self):
        return f"leaf{self.leaf}_features{'all' if self.max_features == 1.0 else 'third'}"


FORESTS = tuple(ForestConfig(leaf, features) for leaf in (3, 8) for features in (1.0, 1 / 3))


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _atomic_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, default=str, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def _atomic_csv(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    data.to_csv(temporary, index=False)
    temporary.replace(path)


def _preprocess(training, prediction):
    means = training.mean().fillna(0.0)
    filled = training.fillna(means)
    scale = filled.std().replace(0.0, 1.0).fillna(1.0)
    return ((filled - means) / scale).to_numpy(), ((prediction.fillna(means) - means) / scale).to_numpy()


def forest_prediction(features: pd.DataFrame, errors: pd.Series, origin: pd.Period,
                      as_of, available_from: pd.Series, config: ForestConfig, *, cache_dir=None) -> dict:
    """Forecast an independent ridge error using only earlier published errors.

    The cache fingerprint excludes future/unpublished labels and future feature
    rows. Quantile-weight validation reserves exactly the last twelve eligible
    errors; its preprocessing sees only the preceding initial training sample.
    """
    from config import CFG
    from models.horizon_models import TVWQRF

    for obj, name in ((features, "features"), (errors, "errors"), (available_from, "available_from")):
        _monthly(obj, name)
    features = hard_features(features).astype(float)
    as_of = pd.Timestamp(as_of)
    if origin not in features.index or pd.isna(as_of):
        raise ValueError("forest prediction needs the origin feature row and a decision timestamp")
    if not errors.index.isin(features.index).all() or not errors.index.isin(available_from.index).all():
        raise ValueError("features and publication dates must cover the independent error history")
    dates = pd.to_datetime(available_from.reindex(errors.index))
    eligible = errors.loc[(errors.index < origin) & dates.le(as_of).to_numpy()].dropna()
    history = features.loc[eligible.index]
    now = features.loc[[origin]]
    if np.isinf(history.to_numpy()).any() or np.isinf(now.to_numpy()).any() or not np.isfinite(eligible).all():
        raise ValueError("forest inputs must be finite or missing")
    parameters = {"leaf": config.leaf, "max_features": config.max_features, "trees": TREES,
                  "validation_errors": INNER_VALIDATION, "half_life": HALF_LIFE, "seed": 42, "n_jobs": WORKERS,
                  "quantiles": list(CFG.tvw_quantiles), "lower": list(CFG.tvw_lower), "upper": list(CFG.tvw_upper)}
    parameter_hash = hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()
    digest = hashlib.sha256(json.dumps({"origin": str(origin), "as_of": str(as_of),
                                       "history_months": list(map(str, eligible.index)), "features": history.columns.tolist()}, sort_keys=True).encode())
    for data in (history.to_numpy(), eligible.to_numpy(), now.to_numpy()):
        data = np.asarray(data, dtype="<f8")
        digest.update(np.where(np.isnan(data), np.nan, data).tobytes())
    input_hash = digest.hexdigest()
    source_paths = [Path(__file__), ROOT / "models" / "horizon_models.py", ROOT / "models" / "core_tuning.py", ROOT / "config.py"]
    source_hash = hashlib.sha256("|".join(_hash(path) for path in source_paths).encode()).hexdigest()
    key = hashlib.sha256(f"{input_hash}|{parameter_hash}|{source_hash}".encode()).hexdigest()
    info = {"origin": origin, "as_of": as_of, "forest": config.key, "correction": 0.0,
            "n_errors": len(eligible), "error_start": eligible.index.min() if len(eligible) else None,
            "error_end": eligible.index.max() if len(eligible) else None,
            "last_error_release": dates.loc[eligible.index].max() if len(eligible) else None,
            "status": "insufficient_errors", "fallback_used": len(eligible) < MIN_ERRORS,
            "validation_count": 0, "cache_key": key, "input_sha256": input_hash,
            "parameters_sha256": parameter_hash, "source_sha256": source_hash, "cache_hit": False}
    cache_file = None
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{origin}_{config.key}_{key}.json"
        if cache_file.exists():
            saved = json.loads(cache_file.read_text())
            if saved.get("cache_key") != key or saved.get("input_sha256") != input_hash or saved.get("parameters_sha256") != parameter_hash:
                raise ValueError("forest cache fingerprint mismatch")
            for field in ("correction", "status", "fallback_used", "validation_count", "quantile_weights", "failure"):
                if field in saved:
                    info[field] = saved[field]
            info["cache_hit"] = True
            return info
    if len(eligible) >= MIN_ERRORS:
        try:
            forest = TVWQRF(n_estimators=TREES, min_samples_leaf=config.leaf, max_features=config.max_features,
                            val_window=INNER_VALIDATION, half_life=HALF_LIFE, seed=42)
            forest.model.set_params(n_jobs=WORKERS)
            initial = history.iloc[:-INNER_VALIDATION]
            validation = history.iloc[-INNER_VALIDATION:]
            x_initial, x_validation = _preprocess(initial, validation)
            forest.model.fit(x_initial, eligible.iloc[:-INNER_VALIDATION].to_numpy())
            quantiles = forest.model.predict(x_validation, quantiles=list(forest.q))
            weights = forest._solve_weights(np.atleast_2d(quantiles), eligible.iloc[-INNER_VALIDATION:].to_numpy())
            x_full, x_now = _preprocess(history, now)
            forest.model.fit(x_full, eligible.to_numpy())
            current_quantiles = forest.model.predict(x_now, quantiles=list(forest.q))[0]
            correction = float(current_quantiles @ weights)
            if not np.isfinite(correction):
                raise ValueError("nonfinite forest correction")
            info.update(correction=correction, status="estimated", fallback_used=False,
                        validation_count=INNER_VALIDATION, quantile_weights=np.asarray(weights).tolist())
        except Exception as exc:
            info.update(status="forest_failed", fallback_used=True, failure=f"{type(exc).__name__}: {exc}")
    if cache_file is not None:
        _atomic_json(cache_file, info)
    return info


def select_correction(predictions: pd.DataFrame, origin: pd.Period, as_of) -> dict:
    """Select forest and multiplier on past published FULL core forecast loss."""
    eligible = predictions[(predictions.origin < origin)
                           & pd.to_datetime(predictions.target_available_from).le(pd.Timestamp(as_of))
                           & predictions.n_errors.ge(MIN_ERRORS)].copy()
    eligible = eligible[np.isfinite(eligible.correction) & np.isfinite(eligible.residual_actual)]
    # A recorded fit failure is the strategy's zero correction, not a deleted origin.
    wide = eligible.pivot(index="origin", columns="forest", values="correction").reindex(columns=[config.key for config in FORESTS])
    common = wide.dropna().sort_index().iloc[-36:]
    actual = eligible.drop_duplicates("origin").set_index("origin").residual_actual.reindex(common.index)
    choice = {"forest": FORESTS[0].key, "multiplier": 0.0, "n_validation": len(common),
              "selection_reason": "insufficient_validation", "validation_start": common.index.min() if len(common) else None,
              "validation_end": common.index.max() if len(common) else None,
              "validation_last_release": eligible.loc[eligible.origin.isin(common.index), "target_available_from"].max(),
              "validation_origins": "|".join(map(str, common.index)), "selected_inner_mse": None, "zero_inner_mse": None}
    if len(common) < 24:
        return choice
    losses = [(float(np.mean((actual - multiplier * common[config.key]) ** 2)), multiplier, order, config.key)
              for multiplier in MULTIPLIERS for order, config in enumerate(FORESTS)]
    minimum = min(loss[0] for loss in losses)
    tied = [loss for loss in losses if np.isclose(loss[0], minimum, rtol=1e-10, atol=1e-12)]
    winner = min(tied, key=lambda item: (item[1], item[2]))
    reason = "tie_zero" if winner[1] == 0.0 and len(tied) > 1 else "minimum_prior_mse"
    choice.update(forest=winner[3], multiplier=winner[1], selection_reason=reason,
                  selected_inner_mse=winner[0], zero_inner_mse=float(np.mean(actual ** 2)))
    return choice


def event_scores(forecasts: pd.DataFrame, actual: pd.Series, consensus: pd.Series):
    """Use the independent nowcast experiment's fixed event/alert definitions."""
    events, scores = [], []
    for model, predicted in forecasts.items():
        error = predicted - actual
        surprise = actual - consensus
        deviation = predicted - consensus
        gain = surprise.abs() - error.abs()
        data = pd.DataFrame({"origin": predicted.index, "model": model, "actual": actual, "consensus": consensus,
                             "forecast": predicted, "error": error, "surprise": surprise, "deviation": deviation, "gain": gain,
                             "big": surprise.abs() >= 0.4 - 1e-9, "alert": deviation.abs() >= 0.2 - 1e-9})
        data["capture_ratio"] = (deviation / surprise).where(data.big)
        events.append(data.reset_index(drop=True))
        for frame, mask in (("all", predicted.notna()), ("ex_jan", predicted.index.month != 1),
                            ("2024+", predicted.index >= pd.Period("2024-01", "M")),
                            ("flash2025+", predicted.index >= pd.Period("2025-01", "M")),
                            ("big", data.big), ("big_ex_jan", data.big & (predicted.index.month != 1)), ("alerts", data.alert)):
            sample = data.loc[mask].dropna(subset=["actual", "forecast", "consensus"])
            scores.append({"model": model, "frame": frame, "n": len(sample),
                           "rmse": float(np.sqrt(np.mean(sample.error ** 2))), "mae": float(sample.error.abs().mean()),
                           "bias": float(sample.error.mean()), "mean_gain": float(sample.gain.mean()), "total_gain": float(sample.gain.sum()),
                           "closer": int((sample.gain > 1e-9).sum()), "material_win": int((sample.gain >= 0.15 - 1e-9).sum()),
                           "material_loss": int((sample.gain <= -0.15 + 1e-9).sum()),
                           "direction": int((sample.deviation * sample.surprise > 0).sum())})
    return pd.concat(events, ignore_index=True), pd.DataFrame(scores)


def _read(path):
    data = pd.read_csv(path, index_col=0, float_precision="round_trip")
    data.index = pd.PeriodIndex(data.index, freq="M")
    return data


def main():
    import cz_struct as S
    started = datetime.now(timezone.utc)
    timer = time.perf_counter()
    fixture_manifest = json.loads((FIXTURE / "MANIFEST.json").read_text())
    for name, expected in fixture_manifest.items():
        if _hash(FIXTURE / name) != expected:
            raise ValueError(f"frozen fixture hash mismatch: {name}")
    features = _read(FIXTURE / "core_features.csv")
    core = _read(FIXTURE / "cnb_core_mm.csv").iloc[:, 0]
    error_path = OUTPUT / "independent_nowcast_hard_errors.csv"
    errors = _read(error_path).iloc[:, 0]
    reference = _read(OUTPUT / "cz_struct_backtest.csv")
    origins = reference.index
    if len(origins) != 90 or not origins.equals(_read(FIXTURE / "expected_backtest.csv").index):
        raise ValueError("the experiment requires all 90 fixed outer origins")
    available = pd.Series({month: S._detail_release_dt(month) for month in core.index})
    decisions = pd.Series({month: S._first_release_dt(month).normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=23, minutes=59)
                           for month in core.index if pd.notna(S._first_release_dt(month))})
    if not np.array_equal(decisions.loc[origins].values, pd.to_datetime(reference.as_of_eve).values):
        raise ValueError("outer release-eve clocks differ from the saved baseline")
    x = hard_features(features)
    for month in decisions.index:
        x = S._mask_row_by_availability(x, month, decisions.loc[month])

    rows = []
    months = pd.period_range(errors.index.min(), origins.max(), freq="M")
    for number, month in enumerate(months):
        if month not in decisions.index:
            raise ValueError(f"missing historical decision date: {month}")
        residual_actual = errors.get(month, np.nan)
        if not np.isfinite(residual_actual) and month in core.index:
            baseline_row = S._mask_row_by_availability(hard_features(features), month, decisions.loc[month])
            baseline_core = S._ridge_predict(baseline_row, core, month, as_of=decisions.loc[month])[0]
            residual_actual = float(core.loc[month] - baseline_core)
        for config in FORESTS:
            result = forest_prediction(x, errors, month, decisions.loc[month], available, config,
                                       cache_dir=OUTPUT / "forest_tuning_cache")
            rows.append({**result, "residual_actual": residual_actual, "target_available_from": available.loc[month]})
        _atomic_csv(OUTPUT / "forest_tuning_predictions.csv", pd.DataFrame(rows))
        _atomic_json(OUTPUT / "forest_tuning_progress.json", {"completed_origins": number + 1, "total_origins": len(months),
                     "last_origin": str(month), "elapsed_seconds": time.perf_counter() - timer})
        if number % 12 == 0 or number == len(months) - 1:
            print(f"Forest tuning {number + 1}/{len(months)} origins, through {month}", flush=True)
    predictions = pd.DataFrame(rows)

    independent_path = OUTPUT / "independent_nowcast_forecasts.csv"
    independent = _read(independent_path)
    if not independent.index.equals(origins):
        raise ValueError("independent baseline must contain all 90 reference origins; cached forests can be resumed")
    forecast_table = independent[[name for name in ("HARD_BASE", "HARD_HALF", "HARD_FULL") if name in independent]].copy()
    residual_replay_differences = []
    for month in origins.intersection(errors.index):
        baseline_row = S._mask_row_by_availability(hard_features(features), month, decisions.loc[month])
        baseline_core = S._ridge_predict(baseline_row, core, month, as_of=decisions.loc[month])[0]
        residual_replay_differences.append(abs(core.loc[month] - baseline_core - errors.loc[month]))
    if max(residual_replay_differences, default=0.0) > 1e-10:
        raise AssertionError("provided independent error targets do not match the outer release-eve ridge")
    schedule_rows = []
    for month in origins:
        choice = select_correction(predictions, month, decisions.loc[month])
        now = predictions[(predictions.origin == month) & (predictions.forest == choice["forest"])].iloc[0]
        correction = float(choice["multiplier"] * now.correction)
        schedule_rows.append({"origin": month, "as_of": decisions.loc[month], **choice, "raw_correction": now.correction,
                              "applied_correction": correction, "n_errors": int(now.n_errors), "error_end": now.error_end,
                              "last_error_release": now.last_error_release, "forest_status": now.status})
    schedule = pd.DataFrame(schedule_rows)
    forecast_table["SELECTED"] = independent.HARD_BASE + independent.coreweight * schedule.set_index("origin").applied_correction
    for config in FORESTS:
        point = predictions[(predictions.forest == config.key) & predictions.origin.isin(origins)].set_index("origin").correction
        for multiplier in MULTIPLIERS:
            forecast_table[f"{config.key}_m{multiplier:g}"] = independent.HARD_BASE + independent.coreweight * multiplier * point
    actual_path = ROOT / "data" / "czcpmom_survey_history_extended.csv"
    release_data = pd.read_csv(actual_path)
    release_data = release_data[release_data.era != "flash_survey_suspect"]
    release_data.index = pd.PeriodIndex(release_data.target_month, freq="M")
    actual, consensus = release_data.actual.reindex(origins), release_data.survey_median.reindex(origins)
    if not np.isfinite(forecast_table.to_numpy()).all() or not np.isfinite(actual).all() or not np.isfinite(consensus).all():
        raise ValueError("every model must be scored on the same complete 90-origin sample")
    events, scores = event_scores(forecast_table, actual, consensus)
    releases = forecast_table.copy()
    releases.insert(0, "origin", origins)
    releases["actual"], releases["consensus"], releases["coreweight"] = actual, consensus, independent.coreweight
    core_scores = []
    for model, multiplier_column in (("HARD_BASE", None), ("SELECTED", "applied_correction")):
        resid = predictions.drop_duplicates("origin").set_index("origin").residual_actual.reindex(origins)
        if multiplier_column:
            resid = resid - schedule.set_index("origin")[multiplier_column]
        for split, mask in (("all", np.ones(len(origins), dtype=bool)), ("2024+", origins >= pd.Period("2024-01", "M")),
                            ("flash2025+", origins >= pd.Period("2025-01", "M"))):
            z = resid.loc[mask]
            core_scores.append({"model": model, "split": split, "n": len(z), "mae": float(z.abs().mean()), "rmse": float(np.sqrt(np.mean(z ** 2)))})
    fitted = predictions[predictions.n_errors >= MIN_ERRORS]
    validated = schedule[schedule.n_validation > 0]
    checks = {"future_error_month_violations": int((fitted.error_end >= fitted.origin).sum()),
              "unpublished_error_label_violations": int((fitted.last_error_release > fitted.as_of).sum()),
              "future_validation_month_violations": int((validated.validation_end >= validated.origin).sum()),
              "unpublished_validation_label_violations": int((validated.validation_last_release > validated.as_of).sum()),
              "forest_failures": int((predictions.status == "forest_failed").sum()), "fitted_forecasts": len(fitted),
              "cache_hits": int(predictions.cache_hit.sum()), "outer_origins": len(origins),
              "max_outer_residual_replay_difference": float(max(residual_replay_differences, default=0.0)),
              "insufficient_validation_origins": int((schedule.n_validation < 24).sum())}
    if any(value for key, value in checks.items() if key.endswith("violations")):
        raise AssertionError(checks)
    artifacts = {"schedule": schedule, "releases": releases.reset_index(drop=True), "events": events,
                 "scores": scores, "core_scores": pd.DataFrame(core_scores)}
    for name, data in artifacts.items():
        _atomic_csv(OUTPUT / f"forest_tuning_{name}.csv", data)
    inputs = {str(FIXTURE.relative_to(ROOT) / name): digest for name, digest in fixture_manifest.items()}
    for path in (error_path, independent_path, OUTPUT / "cz_struct_backtest.csv", actual_path, ROOT / "data" / "release_calendar_cz_cpi.csv"):
        inputs[str(path.relative_to(ROOT))] = _hash(path)
    source_paths = [Path(__file__), ROOT / "models" / "horizon_models.py", ROOT / "models" / "independent_nowcast.py",
                    ROOT / "models" / "core_tuning.py", ROOT / "cz_struct.py", ROOT / "config.py", ROOT / "test_forest_tuning_r9.py"]
    manifest = {"started_at_utc": started.isoformat(), "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": time.perf_counter() - timer, "workers": WORKERS, "forests": [dict(leaf=c.leaf, max_features=c.max_features) for c in FORESTS],
                "multipliers": MULTIPLIERS, "trees": TREES, "validation_errors": INNER_VALIDATION, "half_life": HALF_LIFE,
                "input_sha256": inputs, "source_sha256": {str(p.relative_to(ROOT)): _hash(p) for p in source_paths},
                "output_sha256": {f"forest_tuning_{name}.csv": _hash(OUTPUT / f"forest_tuning_{name}.csv") for name in (*artifacts, "predictions")},
                "checks": checks, "selected_multiplier_counts": schedule.multiplier.value_counts().to_dict(),
                "selected_forest_counts": schedule.forest.value_counts().to_dict(),
                "runtime": {"python": platform.python_version(), **{name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scipy", "quantile-forest", "scikit-learn")}},
                "evaluation_status": "predeclared follow-on pseudo-OOS search; not untouched historical holdout; no automatic promotion"}
    _atomic_json(OUTPUT / "forest_tuning_manifest.json", manifest)
    print(scores[scores.model.isin(["HARD_BASE", "SELECTED"])].to_string(index=False))
    print(json.dumps({"checks": checks, "multiplier_counts": manifest["selected_multiplier_counts"], "elapsed_seconds": manifest["elapsed_seconds"]}, indent=2))
    return predictions, schedule, releases, scores, manifest


if __name__ == "__main__":
    main()
