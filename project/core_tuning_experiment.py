"""Run the fixed-grid nested CORE ridge experiment using frozen inputs only.

Usage: python core_tuning_experiment.py
Outputs: output/core_tuning_*.csv and output/core_tuning_manifest.json.
The core selector never sees headline actuals, surveys or noncore residuals.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib.metadata
import json
import platform
import time

import numpy as np
import pandas as pd

from models.core_tuning import DEFAULT, GRID, hard_features, nested_predictions


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "tests" / "fixtures" / "cleanup"


def headline_attribution(reference_headline, core_weight, reference_core, candidate_core):
    return np.asarray(reference_headline) - np.asarray(core_weight) * np.asarray(reference_core) + np.asarray(core_weight) * np.asarray(candidate_core)


def score_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    """Score every model on the same finite origin set, separately by object."""
    values = ["core_forecast", "headline_forecast", "core_actual", "headline_actual"]
    finite = np.isfinite(candidates[values]).all(axis=1)
    eligible = candidates.loc[finite]
    n_models = candidates.model.nunique()
    counts = eligible.groupby("origin").model.nunique()
    common = counts.index[counts == n_models]
    eligible = eligible[eligible.origin.isin(common)].copy()
    rows = []
    splits = {"all": lambda x: np.ones(len(x), dtype=bool),
              "ex-January": lambda x: np.array([p.month != 1 for p in x]),
              "2024+": lambda x: x >= pd.Period("2024-01", "M"),
              "2025+ flash era": lambda x: x >= pd.Period("2025-01", "M")}
    for model in candidates.model.unique():
        sample = eligible[eligible.model == model]
        for split, rule in splits.items():
            data = sample.loc[rule(sample.origin)]
            row = {"model": model, "split": split, "n": len(data)}
            for obj in ("core", "headline"):
                errors = data[f"{obj}_forecast"] - data[f"{obj}_actual"]
                row[f"{obj}_mae"] = float(errors.abs().mean())
                row[f"{obj}_rmse"] = float(np.sqrt(np.mean(errors ** 2)))
                row[f"{obj}_bias"] = float(errors.mean())
            rows.append(row)
    return pd.DataFrame(rows)


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_frame(path):
    frame = pd.read_csv(path, index_col=0)
    frame.index = pd.PeriodIndex(frame.index, freq="M")
    return frame


def main():
    started = datetime.now(timezone.utc)
    timer = time.perf_counter()
    import cz_struct as S

    fixture_manifest = json.loads((FIXTURE / "MANIFEST.json").read_text())
    for name, expected in fixture_manifest.items():
        if _hash(FIXTURE / name) != expected:
            raise ValueError(f"frozen fixture hash mismatch: {name}")
    features = _read_frame(FIXTURE / "core_features.csv")
    core = _read_frame(FIXTURE / "cnb_core_mm.csv").iloc[:, 0]
    headline = _read_frame(FIXTURE / "target_headline_cpi_mm.csv").iloc[:, 0]
    components = _read_frame(FIXTURE / "component_food_fuel_mm.csv")
    regulated = _read_frame(FIXTURE / "cnb_regulated_mm.csv").iloc[:, 0]
    alcohol = _read_frame(FIXTURE / "alcohol_tobacco.csv").iloc[:, 0]
    reference_path = ROOT / "output" / "cz_struct_backtest.csv"
    reference = _read_frame(reference_path)
    original = _read_frame(FIXTURE / "expected_backtest.csv")
    if len(reference) != 90 or not reference.index.equals(original.index):
        raise ValueError("release-eve reference must match all 90 frozen evaluation origins")
    origins = reference.index

    available = {}
    decisions = {}
    for month in core.index:
        detail = S._detail_release_dt(month)
        first = S._first_release_dt(month)
        if pd.isna(detail) and month < S._release_calendar().index.min():
            detail = (month + 1).to_timestamp() + pd.Timedelta(days=S._FALLBACK_DETAIL_DAY - 1, hours=S._RELEASE_HOUR)
        available[month] = detail
        if pd.notna(first):
            decisions[month] = first.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=23, minutes=59)
        else:
            decisions[month] = pd.NaT
    available = pd.Series(available, dtype="datetime64[ns]")
    decisions = pd.Series(decisions, dtype="datetime64[ns]")
    reference_clocks = pd.to_datetime(reference.as_of_eve)
    if not np.array_equal(decisions.loc[origins].values, reference_clocks.values):
        raise ValueError("stored release-eve reference clocks differ from the sourced release calendar")

    predictions, schedule = nested_predictions(features, core, decisions, available, origins)
    fitted = predictions[predictions.fit_status == "estimated"]
    checks = {
        "future_training_month_violations": int((fitted.train_end >= fitted.origin).sum()),
        "unpublished_training_label_violations": int((fitted.training_last_release > fitted.as_of).sum()),
        "future_validation_month_violations": int((schedule.validation_end >= schedule.origin).sum()),
        "unpublished_validation_label_violations": int((schedule.validation_last_release > schedule.as_of).sum()),
        "outer_origins": len(origins), "configurations": len(GRID),
        "sequential_predictions": len(fitted), "minimum_validation_count": int(schedule.n_validation.min()),
    }
    if any(value for key, value in checks.items() if key.endswith("violations")):
        raise AssertionError(checks)
    if not np.isfinite(schedule.prediction).all():
        raise AssertionError("every outer origin must receive a finite selected prediction")

    actual_path = ROOT / "data" / "czcpmom_survey_history_extended.csv"
    actual_rows = pd.read_csv(actual_path, usecols=["target_month", "actual", "era"])
    actual_rows = actual_rows[actual_rows.era != "flash_survey_suspect"]
    actual_rows.index = pd.PeriodIndex(actual_rows.target_month, freq="M")
    if not actual_rows.index.is_unique:
        raise ValueError("headline first-release actuals must have unique months")
    first_actual = actual_rows.actual.reindex(origins)
    if not np.isfinite(first_actual).all():
        raise ValueError("missing first-release headline actual")

    release_rows = []
    legacy_replay_differences = []
    hard_default_differences = []
    indexed_schedule = schedule.set_index("origin")
    default_predictions = predictions[predictions.config == DEFAULT.key].set_index("origin")
    for origin in origins:
        clock = decisions.loc[origin]
        weights = S.solve_weights(headline, components, core, regulated, origin - 1, as_of=clock, alc=alcohol)
        core_weight = weights[S._regime(origin)]["core"]
        legacy_core = float(reference.loc[origin, "core_pred_eve"])
        legacy_replay = S._ridge_predict(features, core, origin, alpha=3.0, as_of=clock)[0]
        hard_replay = S._ridge_predict(hard_features(features), core, origin, alpha=3.0, as_of=clock)[0]
        default_core = float(default_predictions.loc[origin, "prediction"])
        selected_core = float(indexed_schedule.loc[origin, "prediction"])
        legacy_replay_differences.append(abs(legacy_core - legacy_replay))
        hard_default_differences.append(abs(default_core - hard_replay))
        reference_headline = float(reference.loc[origin, "STRUCT_EVE"])
        release_rows.append({"origin": origin, "as_of": clock, "selected_config": indexed_schedule.loc[origin, "config"],
                             "core_actual": core.loc[origin], "headline_actual": first_actual.loc[origin],
                             "core_weight": core_weight, "legacy_core_forecast": legacy_core,
                             "legacy_headline_forecast": reference_headline,
                             "fixed_noncore_reference": reference_headline - core_weight * legacy_core,
                             "default_core_forecast": default_core, "selected_core_forecast": selected_core,
                             "default_headline_forecast": float(headline_attribution(reference_headline, core_weight, legacy_core, default_core)),
                             "selected_headline_forecast": float(headline_attribution(reference_headline, core_weight, legacy_core, selected_core))})
    releases = pd.DataFrame(release_rows)
    for model in ("default", "selected"):
        for obj in ("core", "headline"):
            releases[f"{model}_{obj}_error"] = releases[f"{model}_{obj}_forecast"] - releases[f"{obj}_actual"]
    checks["max_legacy_core_replay_difference"] = max(legacy_replay_differences)
    checks["max_hard_default_replay_difference"] = max(hard_default_differences)
    if max(legacy_replay_differences + hard_default_differences) > 1e-9:
        raise AssertionError(f"core baseline replay mismatch: {checks}")

    candidates = predictions[predictions.origin.isin(origins)].merge(
        releases[["origin", "core_actual", "headline_actual", "core_weight", "fixed_noncore_reference"]], on="origin", validate="many_to_one")
    candidates["model"] = candidates.config
    candidates["core_forecast"] = candidates.prediction
    candidates["headline_forecast"] = candidates.fixed_noncore_reference + candidates.core_weight * candidates.prediction
    score_rows = candidates[["origin", "model", "core_forecast", "headline_forecast", "core_actual", "headline_actual"]].copy()
    for model in ("default", "selected"):
        extra = releases[["origin", "core_actual", "headline_actual", f"{model}_core_forecast", f"{model}_headline_forecast"]].rename(
            columns={f"{model}_core_forecast": "core_forecast", f"{model}_headline_forecast": "headline_forecast"})
        extra["model"] = model
        score_rows = pd.concat([score_rows, extra], ignore_index=True)
    scores = score_candidates(score_rows)

    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    artifacts = {"predictions": predictions, "schedule": schedule, "releases": releases,
                 "outer_candidates": candidates, "scores": scores}
    for name, data in artifacts.items():
        data.to_csv(output / f"core_tuning_{name}.csv", index=False)
    inputs = {str(FIXTURE.relative_to(ROOT) / name): digest for name, digest in fixture_manifest.items()}
    for path in (reference_path, actual_path, FIXTURE / "expected_backtest.csv", ROOT / "data" / "release_calendar_cz_cpi.csv"):
        inputs[str(path.relative_to(ROOT))] = _hash(path)
    sources = [ROOT / "models" / "core_tuning.py", Path(__file__), ROOT / "cz_struct.py", ROOT / "test_core_tuning_r9.py"]
    manifest = {"started_at_utc": started.isoformat(), "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": time.perf_counter() - timer, "policy": "hard", "grid": [dict(alpha=c.alpha, window=c.window) for c in GRID],
                "selection": "monthly; prior 36 common sequential published core errors; minimum 24; minimum MSE; deterministic default/ties",
                "historical_vintage_status": "frozen reconstructed/latest-vintage research inputs; not real-time vintage certified",
                "input_sha256": inputs, "source_sha256": {str(p.relative_to(ROOT)): _hash(p) for p in sources},
                "output_sha256": {f"core_tuning_{name}.csv": _hash(output / f"core_tuning_{name}.csv") for name in artifacts},
                "runtime": {"python": platform.python_version(), **{name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scipy")}},
                "checks": checks, "selected_config_counts": schedule.config.value_counts().to_dict()}
    (output / "core_tuning_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(scores[scores.model.isin(["default", "selected"])].to_string(index=False))
    print(json.dumps({"checks": checks, "selection_counts": manifest["selected_config_counts"], "elapsed_seconds": manifest["elapsed_seconds"]}, indent=2))
    return predictions, schedule, releases, scores, manifest


if __name__ == "__main__":
    main()
