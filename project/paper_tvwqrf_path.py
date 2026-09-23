"""Score real-time TVW-QRF forecasts as monthly CPI inflation paths on the existing path boards.

Forecast horizon ``k`` from data edge ``e`` (``paper_tvwqrf_experiment.py --convention
realtime``) is path horizon ``k - 1`` for path origin ``e + 1``: row ``e`` of the
real-time panel holds what was published on the eve of the first CPI release for
``e + 1``, which is the decision clock of every existing path board.

Board A (Codex R14B integration, origins 2019-02..2026-07) is scored with the
board's own functions: exact year-on-year compounding, common-sample RMSE,
the circular block bootstrap against INDEPENDENT_BRIDGE and CNB report matching.
h0 is HARD_BASE for every model as on the board; ``_OWNH0`` rows use the model's
own h0.  The long span (origins 2011-01 onward, own h0) adds the seasonal naive
and the year-on-year random walk.  Board C compares object (b), h0 = the print,
with F1b and F2 from ``output/path_step2.csv``.  The decision rule is the one
declared in ``docs/implementation/PAPER_TVWQRF_SPEC_2026-09-12.md``.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from models.path_inputs import compound_path

HERE = Path(__file__).resolve().parent
BOARD_A = HERE / "output" / "research_r14b" / "integration" / "forecasts.csv"
BRIDGE = HERE / "output" / "independent_bridge_forecasts.csv"
NOWCAST = HERE / "output" / "independent_nowcast_forecasts.csv"
HEADLINE = HERE / "output" / "independent_path_frozen_inputs.csv"
BOARD_C = HERE / "output" / "path_step2.csv"
CNB = HERE / "data" / "cnb_mpr_cpi_quarterly.csv"
BASE = "INDEPENDENT_BRIDGE"
BOARD_MODELS = [BASE, "STABLE_PIPELINE_R14B", "STABLE_LOCAL_CORE_R14B", "STABLE_LONG_CORE_R14B", "STABLE_LONG_GAP_R14B"]
PAPER_MODELS = ("TVW3", "QRF_MEDIAN", "QRF_MEAN")
LONG_SPAN_START = pd.Period("2011-01", freq="M")


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def headline_series(path: Path = HEADLINE) -> pd.Series:
    frame = pd.read_csv(path, dtype={"period": str})
    s = pd.Series(frame.headline_mm.to_numpy(float), index=pd.PeriodIndex(frame.period, freq="M"))
    return s.dropna()


def load_paths(folder: Path, label: str) -> pd.DataFrame:
    """Model horizons 1..13 from edge e -> path origin e+1, h 0..12."""
    f = pd.read_csv(Path(folder) / "forecasts.csv", dtype={"edge": str})
    f = f[f.model.isin(PAPER_MODELS)].copy()
    f["origin"] = pd.PeriodIndex(f.edge, freq="M") + 1
    f["h"] = f.horizon.astype(int) - 1
    f = f[f.h.between(0, 12)]
    f["target"] = f.origin + f.h
    f["model"] = "TVWQRF_" + f.model + "_" + label
    return f[["origin", "h", "target", "model", "forecast"]].rename(columns={"forecast": "mm_forecast"})


def _naive_mm(history: pd.Series, month: pd.Period) -> float:
    same = history[history.index.month == month.month].iloc[-5:]
    if len(same) >= 3:
        return float(same.mean())
    return float(history.iloc[-24:].mean())


def board_a(paths: pd.DataFrame, headline: pd.Series) -> dict[str, pd.DataFrame]:
    from independent_bridge_experiment import _quarter_metrics, match_cnb_quarters
    from path_improvements_experiment_r12 import add_outcomes_and_compound, score_panel
    from path_integration_r14 import bootstrap

    board = pd.read_csv(BOARD_A, dtype={"origin": str, "target": str}, float_precision="round_trip")
    stored = pd.read_csv(BRIDGE, dtype={"origin": str, "target": str}, float_precision="round_trip")
    clocks = board.drop_duplicates("origin").set_index("origin").as_of_utc
    hard = pd.read_csv(NOWCAST, dtype={"period": str}).set_index("period").HARD_BASE
    keys = stored[["origin", "h"]].drop_duplicates()
    rows = []
    for model, g in paths.groupby("model"):
        g = g.assign(origin=g.origin.astype(str))
        merged = keys.merge(g[["origin", "h", "mm_forecast"]], on=["origin", "h"], how="left")
        merged["target"] = (pd.PeriodIndex(merged.origin, freq="M") + merged.h).astype(str)
        merged["as_of_utc"] = merged.origin.map(clocks)
        own = merged.assign(model=model + "_OWNH0")
        board_h0 = merged.copy()
        h0 = board_h0.h.eq(0)
        board_h0.loc[h0, "mm_forecast"] = board_h0.loc[h0, "origin"].map(hard).to_numpy()
        rows += [board_h0.assign(model=model), own]
    frame = pd.concat(rows, ignore_index=True)[["origin", "h", "target", "as_of_utc", "model", "mm_forecast"]]
    ours, delta = add_outcomes_and_compound(frame, headline, stored)
    combined = pd.concat([board[board.model.isin(BOARD_MODELS)], ours], ignore_index=True)
    new_models = sorted(ours.model.unique())
    models = BOARD_MODELS + new_models
    tables = [score_panel(combined, models, "all_common")]
    for model in new_models:
        tables.append(score_panel(combined, [BASE, model], f"paired_{model}"))
        tables.append(score_panel(combined, [model], "own_coverage"))
    summary = pd.concat(tables, ignore_index=True)
    boot = bootstrap(combined, [BASE] + new_models)
    cnb = pd.read_csv(CNB)
    quarters = match_cnb_quarters(combined, cnb, headline, models)
    cnb_rows = []
    for sample, group in (("all_reports", quarters), ("recent_reports", quarters[quarters.report_date >= "2024-01-01"])):
        cnb_rows.append(_quarter_metrics(group, models + ["CNB"], "all_common", sample))
        for model in new_models:
            cnb_rows.append(_quarter_metrics(group, [BASE, model, "CNB"], f"paired_{model}", sample))
    return {"forecasts": ours, "summary": summary, "bootstrap": boot, "cnb_quarters": quarters,
            "cnb_summary": pd.concat(cnb_rows, ignore_index=True), "actual_delta": pd.DataFrame([{"max_actual_delta": delta}])}


def long_span(paths: pd.DataFrame, headline: pd.Series) -> pd.DataFrame:
    """Own-h0 paths from 2011-01 against the seasonal naive and the year-on-year random walk."""
    last = headline.index.max()
    records = []
    origins = sorted(o for o in paths.origin.unique() if o >= LONG_SPAN_START)
    by_model = {m: g.set_index(["origin", "h"]).mm_forecast for m, g in paths.groupby("model")}
    for origin in origins:
        history = headline.loc[headline.index < origin]
        naive = {h: _naive_mm(history, origin + h) for h in range(13)}
        rw = float(100 * np.expm1(np.log1p(history.iloc[-12:] / 100).sum()))
        for h in range(1, 13):
            target = origin + h
            if target > last:
                continue
            window = headline.reindex(pd.period_range(target - 11, target, freq="M"))
            actual = float(100 * np.expm1(np.log1p(window / 100).sum()))
            row = {"origin": str(origin), "h": h, "target": str(target), "yy_actual": actual,
                   "NAIVE": compound_path(history, naive, origin, h, naive[0]), "RW_YOY": rw}
            for model, series in by_model.items():
                path = {k: series.get((origin, k), np.nan) for k in range(13)}
                row[model] = compound_path(history, path, origin, h, path[0])
            records.append(row)
    frame = pd.DataFrame(records)
    models = [c for c in frame.columns if c not in ("origin", "h", "target", "yy_actual")]
    out = []
    samples = {"2011_2026": np.ones(len(frame), bool), "targets_2011_2019": frame.target < "2020-01",
               "targets_2020_2023": frame.target.between("2020-01", "2023-12"), "targets_2024_on": frame.target >= "2024-01",
               "origins_2019_02_on": frame.origin >= "2019-02"}
    for sample, mask in samples.items():
        for h, g in frame[mask].groupby("h"):
            common = g[models + ["yy_actual"]].dropna()
            for model in models:
                e = common[model] - common.yy_actual
                out.append({"sample": sample, "h": h, "model": model, "n": len(e),
                            "yy_rmse": float(np.sqrt(np.mean(e ** 2))) if len(e) else np.nan,
                            "yy_bias": float(e.mean()) if len(e) else np.nan})
    return pd.DataFrame(out)


def board_c(paths: pd.DataFrame, headline: pd.Series) -> pd.DataFrame:
    """Object (b): h0 = the print; compared with F1b, F2 (survey trend) and the naive on common origins."""
    c = pd.read_csv(BOARD_C, dtype={"origin": str, "target": str})
    rows = []
    by_model = {m: g.set_index(["origin", "h"]).mm_forecast for m, g in paths.groupby("model")}
    for (origin_text, h), g in c.groupby(["origin", "h"]):
        if h < 1:
            continue
        origin = pd.Period(origin_text, freq="M")
        history = headline.loc[headline.index < origin]
        print_h0 = headline.get(origin, np.nan)
        record = {"origin": origin_text, "h": int(h), "real_yy": float(g.real_yy.iloc[0]),
                  "F1b": float(g.yy_b_F1b.iloc[0]), "F2_D1_fixed": float(g.yy_b_F2_D1_fixed.iloc[0]),
                  "NAIVE_C": float(g.yy_b_naive.iloc[0]), "RW_C": float(g.yy_rw.iloc[0])}
        for model, series in by_model.items():
            path = {k: series.get((origin, k), np.nan) for k in range(13)}
            record[model] = compound_path(history, path, origin, int(h), print_h0)
        rows.append(record)
    frame = pd.DataFrame(rows)
    models = [c for c in frame.columns if c not in ("origin", "h", "real_yy")]
    out = []
    for sample, mask in (("all", np.ones(len(frame), bool)), ("origins_2024_on", frame.origin >= "2024-01")):
        for h, g in frame[mask].groupby("h"):
            common = g[models + ["real_yy"]].dropna()
            for model in models:
                e = common[model] - common.real_yy
                out.append({"sample": sample, "h": h, "model": model, "n": len(e),
                            "yy_rmse": float(np.sqrt(np.mean(e ** 2))) if len(e) else np.nan,
                            "yy_bias": float(e.mean()) if len(e) else np.nan})
    return pd.DataFrame(out)


def decision(summary: pd.DataFrame, boot: pd.DataFrame, model: str) -> dict:
    paired = summary[summary.scope.eq(f"paired_{model}")]

    def rmse(sample, h, name):
        row = paired[paired["sample"].eq(sample) & paired.h.eq(h) & paired.model.eq(name)]
        return float(row.yy_rmse.iloc[0]) if len(row) else np.nan

    full = boot[boot["sample"].eq("full") & boot.model.eq(model)]
    lower_better = {int(h): bool(u < 0) for h, u in zip(full.h, full.upper)}
    upper_worse = {int(h): bool(l > 0) for h, l in zip(full.h, full.lower)}
    checks = {
        "rmse_below_bridge_h6": rmse("full", 6, model) < rmse("full", 6, BASE),
        "rmse_below_bridge_h12": rmse("full", 12, model) < rmse("full", 12, BASE),
        "bootstrap_better_at_h3_h6_or_h12": any(lower_better.get(h, False) for h in (3, 6, 12)),
        "no_bootstrap_loss_h1_to_h12": not any(upper_worse.values()),
        "recent_origins_h12_within_10pct": rmse("recent_origins", 12, model) <= 1.10 * rmse("recent_origins", 12, BASE),
    }
    return {"model": model, "checks": checks, "path_challenger": all(checks.values()),
            "rmse": {s: {h: {"model": rmse(s, h, model), "bridge": rmse(s, h, BASE)} for h in (1, 3, 6, 9, 12)}
                     for s in ("full", "recent_targets", "recent_origins")}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", required=True, help="LABEL=FOLDER of a realtime run")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    headline = headline_series()
    runs = dict(item.split("=", 1) for item in args.run)
    paths = pd.concat([load_paths(Path(folder), label) for label, folder in runs.items()], ignore_index=True)
    a = board_a(paths, headline)
    for name, frame in a.items():
        frame.to_csv(output / f"board_a_{name}.csv", index=False)
    long = long_span(paths, headline)
    long.to_csv(output / "long_span_summary.csv", index=False)
    c = board_c(paths, headline)
    c.to_csv(output / "board_c_summary.csv", index=False)
    decisions = [decision(a["summary"], a["bootstrap"], m) for m in sorted(paths.model.unique())]
    (output / "decision.json").write_text(json.dumps(decisions, indent=2), encoding="utf-8")
    manifest = {"tool": "paper_tvwqrf_path", "created_at": datetime.now(timezone.utc).isoformat(), "runs": runs,
                "inputs": {str(p): _sha(p) for p in (BOARD_A, BRIDGE, NOWCAST, HEADLINE, BOARD_C, CNB)},
                "run_manifests": {label: _sha(Path(folder) / "manifest.json") for label, folder in runs.items()},
                "scorer_sha256": _sha(Path(__file__))}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    view = a["summary"][a["summary"].scope.eq("all_common") & a["summary"]["sample"].eq("full")]
    print(view.pivot_table(index="model", columns="h", values="yy_rmse")[[1, 3, 6, 9, 12]].round(3).to_string())
    for d in decisions:
        print(d["model"], "path_challenger" if d["path_challenger"] else "not a challenger", d["checks"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
