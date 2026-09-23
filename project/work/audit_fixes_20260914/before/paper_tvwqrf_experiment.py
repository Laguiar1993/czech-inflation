"""TVW-QRF of CNB WP 9/2026 on the rebuilt Table A6 panels, with the paper's benchmarks.

Research lane only.  Nothing here changes the independent nowcast or the path
products.

``--convention paper`` uses ``paper_convention_panel.csv`` (reference-month rows,
full-sample X-13/Chow-Lin/imputation as the paper describes).  The data edge ``t``
runs from 2010-12 (the paper trains May 2002-December 2010, then rolls one month
at a time) and the target ``t+h`` ends in 2025-09.  This run is compared with the
published RMSEs.

``--convention realtime`` uses ``realtime_panel.csv``: row ``e`` holds what was
published on the eve of the first CPI release for month ``e+1``, so CPI for ``e``
is known.  Horizons 1..13 from edge ``e`` are path horizons 0..12 for path origin
``e+1``; ``paper_tvwqrf_path.py`` scores them on the existing path boards.

Point forecasts per origin and horizon: QRF median, QRF mean, TVW1, TVW2, TVW3,
plus RW, AR(3) iterated, AR(3) direct, ARIMA(3,1,3) and optionally the LQR
ensemble.  ``--include-month`` adds the calendar month of the data edge as a
feature (exploratory check E2 of ``docs/implementation/PAPER_TVWQRF_SPEC_2026-09-12.md``).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import time

import numpy as np
import pandas as pd

from models import paper_tvwqrf as engine
from tools.paper_replication.a6_catalog import BY_NUMBER

HERE = Path(__file__).resolve().parent
PANEL_DIR = HERE / "data" / "paper_replication" / "paper_model_panel_20260912"
TRAIN_START = pd.Period("2002-05", freq="M")
PAPER_BENCHMARKS = {
    "QRF_MEDIAN": {3: 0.731, 6: 0.708, 9: 0.748, 12: 0.707},
    "QRF_MEAN": {3: 0.713, 6: 0.723, 9: 0.737, 12: 0.700},
    "TVW1": {3: 0.694, 6: 0.688, 9: 0.732, 12: 0.687},
    "TVW2": {3: 0.701, 6: 0.693, 9: 0.738, 12: 0.690},
    "TVW3": {3: 0.669, 6: 0.661, 9: 0.712, 12: 0.662},
    "LQR_ENSEMBLE": {3: 0.739, 6: 0.748, 9: 0.765, 12: 0.659},
    "RW": {3: 0.896, 6: 0.715, 9: 1.005, 12: 0.874},
    "AR3": {3: 0.710, 6: 0.740, 9: 0.753, 12: 0.765},
    "ARIMA313": {3: 0.716, 6: 0.736, 9: 0.787, 12: 0.772},
}
PAPER_YOY6 = {"QRF_MEDIAN": 2.304, "QRF_MEAN": 2.224, "TVW1": 2.089, "TVW2": 2.173, "TVW3": 1.973,
              "LQR_ENSEMBLE": 2.567, "RW": 2.653, "AR3": 2.449, "ARIMA313": 2.944}
# The paper's benchmark RMSEs come out when a benchmark's information ends h months
# before the forecast edge (its random walk is lag 2h). The "_TMH" benchmarks use that alignment.
for _name in ("RW", "AR3", "ARIMA313"):
    PAPER_BENCHMARKS[f"{_name}_TMH"] = PAPER_BENCHMARKS[_name]
    PAPER_YOY6[f"{_name}_TMH"] = PAPER_YOY6[_name]


def policy_columns(columns, policy: str) -> list[str]:
    """Paper-panel policies by Table A6 kind: full, sentiment (no expectations), independent (hard data)."""
    keep = []
    for column in columns:
        kind = BY_NUMBER[int(column.split("_")[1])].kind
        if policy == "full" or (policy == "sentiment" and kind != "expectation") or (policy == "independent" and kind == "hard"):
            keep.append(column)
    return keep


def feature_columns(columns, policy: str, drop_rows=()) -> list[str]:
    """Policy columns without the Table A6 rows in ``drop_rows`` (e.g. inputs whose history is revised with hindsight)."""
    drop = {f"a6_{int(n):02d}" for n in drop_rows}
    return [c for c in policy_columns(columns, policy) if c not in drop]


def load_inputs(panel_dir: Path, convention: str) -> tuple[pd.DataFrame, pd.Series]:
    name = "paper_convention_panel.csv" if convention == "paper" else "realtime_panel.csv"
    panel = pd.read_csv(panel_dir / name, dtype={"period": str}).set_index("period")
    panel.index = pd.PeriodIndex(panel.index, freq="M")
    target = pd.read_csv(panel_dir / "target_cpi_mm.csv", dtype={"period": str}).set_index("period")["cpi_mm"]
    target.index = pd.PeriodIndex(target.index, freq="M")
    full = pd.period_range(target.index.min(), target.index.max(), freq="M")
    return panel.astype(float), target.reindex(full).astype(float)


def training_arrays(panel: pd.DataFrame, target: pd.Series, edge: pd.Period, horizon: int, convention: str,
                    include_month: bool = False):
    """Direct pairs (row s, target s+h) with s+h <= edge, and the origin row.

    ``include_month`` adds the calendar month of row ``s`` as a feature (exploratory
    check E2). Each forest is fitted for one horizon, so that month also fixes the
    month of the target ``s+h``.
    """
    if convention == "paper":
        history = panel.loc[TRAIN_START:edge]
        rows = history.index[history.index <= edge - horizon]
        y = target.reindex(rows + horizon)
        ok = y.notna().to_numpy()
        X, x_now, columns = history.loc[rows[ok]].to_numpy(float), history.loc[edge].to_numpy(float), list(panel.columns)
        if include_month:
            X = np.column_stack([X, rows[ok].month.to_numpy(float)])
            x_now, columns = np.append(x_now, float(edge.month)), columns + ["month"]
        return X, y.to_numpy(float)[ok], x_now, rows[ok], columns
    from models.paper_big import build_direct_supervised

    data = build_direct_supervised(target.loc[:edge], panel.loc[TRAIN_START:edge], horizon, origin=edge,
                                   stale_tolerance=2, y_lags=0, include_month=include_month)
    return (data["X_train"].to_numpy(float), data["y_train"].to_numpy(float), data["x_now"].to_numpy(float),
            data["prepared"].train_index, list(data["feature_columns"]))


def forecast_task(edge: str, horizon: int, panel: pd.DataFrame, target: pd.Series, convention: str,
                  forest: dict, lqr: bool, include_month: bool = False) -> dict:
    start = time.perf_counter()
    t = pd.Period(edge, freq="M")
    X, y, x_now, rows, columns = training_arrays(panel, target, t, horizon, convention, include_month)
    fit = engine.fit_forecast(X, y, x_now, forest=forest)
    points = dict(fit["points"])
    if lqr:
        lags = np.column_stack([target.reindex(rows - k).to_numpy(float) for k in range(3)])
        lags_now = np.array([target.get(t - k, np.nan) for k in range(3)], dtype=float)
        ok = np.isfinite(lags).all(axis=1)
        seed = int(hashlib.sha256(f"{edge}-{horizon}".encode()).hexdigest()[:8], 16)
        points["LQR_ENSEMBLE"] = engine.lqr_ensemble(X[ok], y[ok], x_now, lags[ok], lags_now, seed=seed)
    weights = [{"edge": edge, "horizon": horizon, "scheme": name, "quantile": float(q), "weight": float(w)}
               for name, ws in fit["weights"].items()
               for q, w in zip(engine.SCHEMES[name][0], ws)]
    quantiles = [{"edge": edge, "horizon": horizon, "quantile": float(q), "value": float(v)}
                 for q, v in fit["quantiles"].items()]
    return {"points": [{"edge": edge, "horizon": horizon, "model": m, "forecast": v} for m, v in points.items()],
            "weights": weights, "quantiles": quantiles,
            "diagnostics": {"edge": edge, "horizon": horizon, "n_train": fit["n_train"], "n_features": fit["n_features"],
                            "seconds": time.perf_counter() - start}}


def benchmark_rows(target: pd.Series, edges: list[pd.Period], horizons: list[int], tmh: bool = False) -> list[dict]:
    """RW, AR(3), ARIMA(3,1,3) and direct AR(3) at each edge; with ``tmh`` also the "_TMH" versions.

    A "_TMH" benchmark uses the target only up to ``t - h`` and forecasts ``t + h``, which is 2h steps ahead.
    """
    rows = []
    arima_early: dict = {}
    for t in edges:
        if tmh:
            for h in horizons:
                early = target.loc[TRAIN_START:t - h].dropna()
                rows.append({"edge": str(t), "horizon": h, "model": "RW_TMH", "forecast": float(early.iloc[-1])})
                rows.append({"edge": str(t), "horizon": h, "model": "AR3_TMH", "forecast": engine.ar_iterated(early, [2 * h])[2 * h]})
                if t - h not in arima_early:
                    try:
                        arima_early[t - h] = engine.arima_313(early, sorted({2 * g for g in horizons}))
                    except Exception:
                        arima_early[t - h] = {}
                if 2 * h in arima_early[t - h]:
                    rows.append({"edge": str(t), "horizon": h, "model": "ARIMA313_TMH", "forecast": arima_early[t - h][2 * h]})
        history = target.loc[TRAIN_START:t].dropna()
        for name, values in (("RW", engine.random_walk(history, horizons)), ("AR3", engine.ar_iterated(history, horizons))):
            rows += [{"edge": str(t), "horizon": h, "model": name, "forecast": v} for h, v in values.items()]
        try:
            rows += [{"edge": str(t), "horizon": h, "model": "ARIMA313", "forecast": v}
                     for h, v in engine.arima_313(history, horizons).items()]
        except Exception:
            pass
        rows += [{"edge": str(t), "horizon": h, "model": "AR3_DIRECT", "forecast": engine.ar_direct(history, h)} for h in horizons]
    return rows


def score(forecasts: pd.DataFrame, last_target: pd.Period, first_edge: pd.Period) -> tuple[pd.DataFrame, pd.DataFrame]:
    f = forecasts.dropna(subset=["actual", "forecast"]).copy()
    f["error"] = f.forecast - f.actual
    common_first = first_edge + int(f.horizon.max())
    rows, dm_rows = [], []
    for sample, frame in (("paper_window", f), ("common_targets", f[f.target_period >= common_first])):
        for (h, model), g in frame.groupby(["horizon", "model"]):
            e = g.error.to_numpy()
            rows.append({"sample": sample, "horizon": h, "model": model, "n": len(e), "rmse": float(np.sqrt(np.mean(e ** 2))),
                         "mae": float(np.mean(np.abs(e))), "bias": float(np.mean(e)),
                         "first_target": str(g.target_period.min()), "last_target": str(g.target_period.max())})
        for h, g in frame.groupby("horizon"):
            wide = g.pivot_table(index="target_period", columns="model", values="error")
            if "TVW3" not in wide:
                continue
            for other in wide.columns.drop("TVW3"):
                both = wide[["TVW3", other]].dropna()
                stat, p = engine.diebold_mariano(both[other].to_numpy(), both["TVW3"].to_numpy(), int(h))
                dm_rows.append({"sample": sample, "horizon": h, "benchmark": other, "n": len(both),
                                "dm_stat_tvw3_vs_benchmark": stat, "p_tvw3_better": p})
    table = pd.DataFrame(rows)
    table["paper_rmse"] = [PAPER_BENCHMARKS.get(m, {}).get(int(h)) for m, h in zip(table.model, table.horizon)]
    table["difference_vs_paper"] = table.rmse - table.paper_rmse
    return table, pd.DataFrame(dm_rows)


def yoy6(forecasts: pd.DataFrame, target: pd.Series) -> pd.DataFrame:
    """Table A4/A5 construction: six realised months to t, six h=6 forecasts for t+1..t+6."""
    h6 = forecasts[forecasts.horizon.eq(6)]
    index = (1 + target / 100.0).cumprod()
    rows = []
    for model, g in h6.groupby("model"):
        by_target = g.set_index("target_period").forecast
        errors = []
        for T in by_target.index:
            months = pd.period_range(T - 5, T, freq="M")
            if not all(m in by_target.index for m in months):
                continue
            realised = index.get(T - 6) / index.get(T - 12)
            predicted = np.prod([1 + by_target[m] / 100.0 for m in months])
            actual = index.get(T) / index.get(T - 12)
            if np.isfinite(realised) and np.isfinite(actual):
                errors.append(100.0 * (realised * predicted - actual))
        e = np.asarray(errors)
        rows.append({"model": model, "n": len(e), "rmse_yoy": float(np.sqrt(np.mean(e ** 2))) if len(e) else np.nan,
                     "paper_rmse_yoy": PAPER_YOY6.get(model)})
    return pd.DataFrame(rows).sort_values("rmse_yoy")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--convention", choices=["paper", "realtime"], required=True)
    parser.add_argument("--policy", choices=["full", "sentiment", "independent"], default="full")
    parser.add_argument("--horizons", type=int, nargs="+")
    parser.add_argument("--first-edge", default="2010-12")
    parser.add_argument("--last-target")
    parser.add_argument("--jobs", type=int, default=20)
    parser.add_argument("--lqr", action="store_true")
    parser.add_argument("--forest", default="{}", help='JSON overrides of the forest options')
    parser.add_argument("--panel-dir", type=Path, default=PANEL_DIR)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit-edges", type=int, help="smoke test: only the first N edges")
    parser.add_argument("--include-month", action="store_true",
                        help="add the calendar month of the data edge as a feature (exploratory check E2)")
    parser.add_argument("--tmh-benchmarks", action="store_true",
                        help="also run benchmarks whose information ends h months before the edge (reproduces the paper's Table 2)")
    parser.add_argument("--drop-rows", type=int, nargs="+", default=[],
                        help="Table A6 rows to leave out, e.g. 14 15 16 (Rushin, LUCI: histories re-estimated with later data)")
    args = parser.parse_args(argv)
    from joblib import Parallel, delayed

    horizons = args.horizons or ([3, 6, 9, 12] if args.convention == "paper" else list(range(1, 14)))
    panel, target = load_inputs(args.panel_dir, args.convention)
    panel = panel[feature_columns(panel.columns, args.policy, args.drop_rows)]
    last_target = pd.Period(args.last_target or ("2025-09" if args.convention == "paper" else str(target.dropna().index.max())), freq="M")
    first_edge = pd.Period(args.first_edge, freq="M")
    edges = list(pd.period_range(first_edge, last_target - min(horizons), freq="M"))
    if args.limit_edges:
        edges = edges[: args.limit_edges]
    tasks = [(str(t), h) for t in edges for h in horizons if t + h <= last_target and t <= panel.index.max()]
    forest = {**engine.FOREST_DEFAULTS, **json.loads(args.forest)}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    results = Parallel(n_jobs=args.jobs, verbose=5)(
        delayed(forecast_task)(edge, h, panel, target, args.convention, forest, args.lqr, args.include_month)
        for edge, h in tasks)
    points = pd.DataFrame([r for res in results for r in res["points"]])
    points = pd.concat([points, pd.DataFrame(benchmark_rows(target, edges, horizons, args.tmh_benchmarks))], ignore_index=True)
    points["edge"] = pd.PeriodIndex(points.edge, freq="M")
    points["target_period"] = points.edge + points.horizon
    points = points[points.target_period <= last_target]
    points["actual"] = target.reindex(pd.PeriodIndex(points.target_period)).to_numpy()
    points["convention"], points["policy"] = args.convention, args.policy
    points.to_csv(output / "forecasts.csv", index=False)
    pd.DataFrame([r for res in results for r in res["weights"]]).to_csv(output / "tvw_weights.csv", index=False)
    pd.DataFrame([r for res in results for r in res["quantiles"]]).to_csv(output / "quantiles.csv", index=False)
    pd.DataFrame([res["diagnostics"] for res in results]).to_csv(output / "diagnostics.csv", index=False)
    table, dm = score(points, last_target, first_edge)
    table.to_csv(output / "scores.csv", index=False)
    dm.to_csv(output / "dm_tests.csv", index=False)
    if args.convention == "paper" and 6 in horizons:
        yoy6(points, target).to_csv(output / "yoy6_table_a4_a5.csv", index=False)
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True).stdout.strip()
    except Exception:
        head = None
    manifest = {
        "tool": "paper_tvwqrf_experiment", "created_at": datetime.now(timezone.utc).isoformat(),
        "arguments": {k: str(v) for k, v in vars(args).items()}, "horizons": horizons,
        "edges": [str(edges[0]), str(edges[-1])], "tasks": len(tasks), "last_target": str(last_target),
        "features": list(panel.columns) + (["month"] if args.include_month else []), "forest": forest, "validation_window": engine.VALIDATION_WINDOW,
        "half_life": engine.HALF_LIFE, "schemes": {k: [list(v[0]), list(v[1]), list(v[2])] for k, v in engine.SCHEMES.items()},
        "panel_manifest_sha256": hashlib.sha256((args.panel_dir / "manifest.json").read_bytes()).hexdigest(),
        "engine_sha256": hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "packages": {p: importlib.metadata.version(p) for p in ("numpy", "pandas", "scikit-learn", "quantile-forest", "statsmodels", "scipy")},
        "git_head": head, "seconds": time.time() - started,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    view = table[table["sample"].eq("paper_window") & table.model.isin(list(PAPER_BENCHMARKS) + ["AR3_DIRECT"])]
    print(view.pivot_table(index="model", columns="horizon", values="rmse").round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
