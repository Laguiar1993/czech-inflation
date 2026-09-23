"""Build 'CNB Rounds Replayed': each CNB Monetary Policy Report since 2022 against our model paths and realised CPI inflation."""
import json
import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from models.path_inputs import compound_path  # noqa: E402

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "cnb_rounds_template.html"
OUTPUT = REPO / "output/cnb_rounds_replayed_20260912/cnb_rounds_replayed.html"
PAPER = REPO / "output/paper_tvwqrf_20260912"
# CNB-paper forest on the real-time panel with all 72 predictors and a calendar-month feature. The full run stops at the
# last realised target; the recent run repeats the last edges with targets to 2027-07, so later runs override earlier ones.
FOREST_RUNS = [PAPER / "realtime_full_luci_month/forecasts.csv", PAPER / "realtime_full_luci_month_recent/forecasts.csv"]
FOREST_BOARD = PAPER / "path_scores_luci_month/board_a_forecasts.csv"   # scored board built from the full run: consistency check
FIRST_REPORT = "2022-01-01"
SEASONS = {"winter": ("Winter", "zima"), "spring": ("Spring", "jaro"), "summer": ("Summer", "léto"), "autumn": ("Autumn", "podzim")}
LATEST_RELEASES = {pd.Period("2026-08", freq="M"): 1.9}   # CZSO quick release of 10 Sep 2026: +0.3 % m/m, 1.9 % y/y

SERIES = [
    dict(id="realised", label="Realised CPI inflation", short="Realised", kind="realised", color="--realised", width=2.4, dash="", default=True),
    dict(id="cnb", label="CNB forecast", short="CNB", kind="cnb", color="--cnb", width=1.5, dash="", default=True),
    dict(id="INDEPENDENT_BRIDGE", label="Component bridge", short="Component bridge", kind="model", color="--s-bridge", width=2.2, dash="", default=True, source="board"),
    dict(id="STABLE_LOCAL_CORE_R14B", label="Bridge · current core", short="Bridge · current core", kind="model", color="--s-local", width=1.6, dash="", default=True, source="board"),
    dict(id="STABLE_PIPELINE_R14B", label="Bridge · cost-chain food", short="Bridge · cost-chain food", kind="model", color="--s-pipeline", width=1.6, dash="6 3", default=True, source="board"),
    dict(id="STABLE_LONG_CORE_R14B", label="Bridge · long-run core level", short="Bridge · long-run core level", kind="model", color="--s-longcore", width=1.4, dash="2 3", default=False, source="board"),
    dict(id="STABLE_LONG_GAP_R14B", label="Bridge · long-run core gap", short="Bridge · long-run core gap", kind="model", color="--s-longgap", width=1.4, dash="8 3 2 3", default=False, source="board"),
    dict(id="F1b", label="Earlier component engine", short="Earlier component engine", kind="model", color="--s-f1b", width=1.6, dash="", default=True, source="step2", column="F1b"),
    dict(id="F2", label="Trend-gap w/ market expectations", short="Trend-gap w/ expectations", kind="model", color="--s-f2", width=1.5, dash="6 3", default=False, source="step2", column="F2_D1_fixed"),
    dict(id="TVWQRF_TVW3_FULLM", label="CNB TVW3 w/ nowcast", short="CNB TVW3 w/ nowcast", kind="model", color="--s-tvw3", width=1.6, dash="", default=True, source="forest", run_model="TVW3"),
    dict(id="TVWQRF_QRF_MEAN_FULLM", label="CNB QRF mean w/ nowcast", short="CNB QRF mean w/ nowcast", kind="model", color="--s-qrfmean", width=1.5, dash="6 3", default=False, source="forest", run_model="QRF_MEAN"),
]


def quarter_months(quarter: str) -> pd.PeriodIndex:
    q = pd.Period(quarter, freq="Q")
    return pd.period_range(q.asfreq("M", "start"), q.asfreq("M", "end"), freq="M")


def require_unique(frame, keys, label):
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError(f"{label}: missing or duplicate {keys} keys")


def origin_clocks(board, label):
    require_unique(board, ["model", "origin", "h"], label)
    parsed = pd.to_datetime(board.as_of_utc, utc=True, errors="raise")
    if parsed.isna().any() or parsed.groupby(board.origin).nunique().ne(1).any():
        raise ValueError(f"{label}: inconsistent origin clock")
    return parsed.groupby(board.origin).first().sort_values()


def reconcile_forest(scored, forest, clocks, ids):
    """Require every stored scored forest month to agree at full precision."""
    scored_clocks = origin_clocks(scored, "forest scored board")
    aligned = clocks.reindex(scored_clocks.index)
    if aligned.isna().any() or not scored_clocks.eq(aligned).all():
        raise ValueError("forest scored board: origin clock differs from integration board")
    rows = scored[scored.model.isin(ids)].dropna(subset=["yy_exante"])
    if rows.empty or set(rows.model) != set(ids):
        raise ValueError("forest reconciliation: missing scored comparisons")
    differences = []
    for row in rows.itertuples():
        rebuilt = forest.get((row.model, row.origin), {}).get(row.target, np.nan)
        if not np.isfinite(rebuilt) or not np.isfinite(row.yy_exante):
            raise ValueError(f"forest reconciliation: missing comparison for {row.model}/{row.origin}/{row.target}")
        differences.append(abs(row.yy_exante - rebuilt))
    if max(differences) > 1e-10:
        raise ValueError(f"forest reconciliation: max difference {max(differences):.2e} exceeds 1e-10")
    return len(differences), max(differences)


def forest_paths(mm: pd.Series, hard: pd.Series, origins) -> dict:
    """Year-on-year forest paths per (series id, origin): month 0 is HARD_BASE, months 1-12 the forest's horizons 2-13."""
    paths = {}
    for run in FOREST_RUNS:
        forecasts = pd.read_csv(run, dtype={"edge": str}, float_precision="round_trip")
        require_unique(forecasts, ["model", "edge", "horizon"], f"forest run {run}")
        for s in (s for s in SERIES if s.get("source") == "forest"):
            for edge, g in forecasts[forecasts.model.eq(s["run_model"])].groupby("edge"):
                origin = pd.Period(edge, freq="M") + 1
                h0 = hard.get(str(origin), np.nan)
                if str(origin) not in origins or not np.isfinite(h0):
                    continue
                monthly = {int(k) - 1: float(v) for k, v in zip(g.horizon, g.forecast) if int(k) >= 2 and np.isfinite(v)}
                history = mm[mm.index < origin]
                points = {str(origin + h): compound_path(history, monthly, origin, h, float(h0)) for h in range(13)}
                points = {t: v for t, v in points.items() if np.isfinite(v)}
                if len(points) >= len(paths.get((s["id"], str(origin)), {})):
                    paths[(s["id"], str(origin))] = points
    return paths


def main(output=None) -> None:
    head = pd.read_csv(REPO / "output/independent_path_frozen_inputs.csv", dtype={"period": str})
    mm = pd.Series(head.headline_mm.to_numpy(float), index=pd.PeriodIndex(head.period, freq="M")).dropna()
    yy = (100 * np.expm1(np.log1p(mm / 100).rolling(12).sum())).dropna()
    for period, value in LATEST_RELEASES.items():
        if period not in yy.index:
            yy.loc[period] = value
    yy = yy.sort_index()

    board = pd.read_csv(REPO / "output/research_r14b/integration/forecasts.csv", dtype={"origin": str, "target": str}, float_precision="round_trip")
    clocks = origin_clocks(board, "integration board")
    step2 = pd.read_csv(REPO / "output/path_step2.csv", dtype={"origin": str, "target": str}, float_precision="round_trip")
    require_unique(step2, ["origin", "h"], "path_step2")
    coverage_a = float(step2[step2.origin >= "2019-02"][["yy_a_F1b", "yy_a_F2_D1_fixed"]].notna().mean().min())
    f_object = "a"
    print(f"path_step2 object (a) coverage from 2019-02: {coverage_a:.2f}; uncovered model quarters remain unscored")

    hard = pd.read_csv(REPO / "output/independent_nowcast_forecasts.csv", dtype={"period": str}, float_precision="round_trip").set_index("period").HARD_BASE
    forest = forest_paths(mm, hard, set(clocks.index))
    scored = pd.read_csv(FOREST_BOARD, dtype={"origin": str, "target": str}, float_precision="round_trip")
    ids = [s["id"] for s in SERIES if s.get("source") == "forest"]
    count, max_difference = reconcile_forest(scored, forest, clocks, ids)
    print(f"forest vs scored board: {count} of {count} scored months rebuilt, max |difference| {max_difference:.2e}; "
          f"{sum(len(p) for p in forest.values())} forest points in total")

    cnb = pd.read_csv(REPO / "data/cnb_mpr_cpi_quarterly.csv")
    cnb["report_date"] = cnb.report_date.astype(str).str[:10]
    cnb["cutoff_date"] = cnb.cutoff_date.astype(str).str[:10]
    cnb = cnb[cnb.report_date >= FIRST_REPORT].copy()
    cnb["forecast"] = cnb.is_forecast.astype(str).str.lower().eq("true")

    reports = []
    source_of = {s["id"]: s.get("source") for s in SERIES}
    for (report_date, cutoff, season, year), group in cnb.groupby(["report_date", "cutoff_date", "season", "vintage_year"], sort=True):
        report_clock = pd.Timestamp(report_date).tz_localize("Europe/Prague").tz_convert("UTC")
        eligible = clocks[clocks < report_clock]
        fc = group[group.forecast].sort_values("quarter")
        if eligible.empty or fc.empty:
            continue
        origin = eligible.index[-1]
        op = pd.Period(origin, freq="M")
        start, end = op - 12, pd.Period(fc.quarter.iloc[-1], freq="Q").asfreq("M", "end")

        paths = {}
        for s in (s for s in SERIES if s["kind"] == "model"):
            if s["source"] == "forest":
                points = [[t, float(v)] for t, v in sorted(forest.get((s["id"], origin), {}).items())]
            elif s["source"] == "board":
                rows = board[board.model.eq(s["id"]) & board.origin.eq(origin)].sort_values("h")
                points = [[t, float(v)] for t, v in zip(rows.target, rows.yy_exante) if np.isfinite(v)]
            else:
                rows = step2[step2.origin.eq(origin)].sort_values("h")
                column = f"yy_{f_object}_{s['column']}"
                points = [[t, float(v)] for t, v in zip(rows.target, rows[column]) if np.isfinite(v)]
            if points:
                paths[s["id"]] = points

        realised_q, series_q = {}, {sid: {} for sid in paths}
        for q in fc.quarter:
            months = quarter_months(q)
            if all(m in yy.index for m in months):
                realised_q[q] = float(yy.reindex(months).mean())
            for sid, points in paths.items():
                lookup = {pd.Period(t, freq="M"): v for t, v in points}
                values = [float(yy.get(m, np.nan)) if m < op else lookup.get(m, np.nan) for m in months]
                if np.isfinite(values).all():
                    series_q[sid][q] = float(np.mean(values))
        from_month0 = [sid for sid in paths if source_of[sid] in ("board", "forest") and len(paths[sid]) == 13]
        common = [q for q in fc.quarter if q in realised_q and all(q in series_q[sid] for sid in from_month0)]
        cnb_q = dict(zip(fc.quarter, fc.value.astype(float)))
        mae = {"cnb": round(float(np.mean([abs(cnb_q[q] - realised_q[q]) for q in common])), 3) if common else None}
        for sid in paths:
            ok = common and all(q in series_q[sid] for q in common)
            mae[sid] = round(float(np.mean([abs(series_q[sid][q] - realised_q[q]) for q in common])), 3) if ok else None

        name, name_cs = SEASONS[season]
        reports.append(dict(
            id=f"{int(year)}-{season}", season=name, season_cs=name_cs, year=int(year),
            report_date=report_date, cutoff_date=cutoff,
            origin=origin, origin_clock=clocks[origin].tz_convert("Europe/Prague").strftime("%Y-%m-%d %H:%M"),
            window=dict(start=str(start), end=str(end)),
            cnb=[dict(quarter=q, value=round(float(v), 3)) for q, v in zip(fc.quarter, fc.value)],
            realised_quarters=[dict(quarter=q, value=round(v, 3)) for q, v in realised_q.items()],
            quarter_points={sid: [[q, round(v, 3)] for q, v in sorted(values.items())] for sid, values in series_q.items() if values},
            paths={sid: [[t, round(v, 3)] for t, v in points] for sid, points in paths.items()},
            score=dict(quarters=common, n=len(common), mae=mae),
        ))
        forest_len = [len(paths.get(sid, [])) for sid in ids]
        best = sorted((v, k) for k, v in mae.items() if v is not None)[:3]
        print(f"{report_date} {name} {int(year)} origin {origin} | CNB {fc.quarter.iloc[0]}..{fc.quarter.iloc[-1]} | forest points {forest_len} | "
              f"scored {len(common)} | best {best}")

    realised = {str(m): round(float(v), 3) for m, v in yy.loc[reports[0]["window"]["start"]:].items()}
    method = [
        "<b>CNB forecast.</b> Quarterly averages of year-on-year CPI inflation from each report's chart data (<code>data/cnb_mpr_cpi_quarterly.csv</code>), forecast quarters only, drawn at the middle month of each quarter.",
        "<b>Model dots.</b> Each model's average inflation over the CNB's forecast quarters, drawn at the same mid-quarter point as the CNB's. Months before the model run use realised inflation, as in the misses; a quarter gets a dot only when all three of its months are available.",
        "<b>Historical replay and simulated cutoff.</b> For each report, select the latest simulated decision cutoff before 00:00 Prague on the report date: the eve of the CPI release for the origin month. These paths were reconstructed later, not archived forecasts made at those historical clocks. Month 0 of the component bridge, its four Bridge · variants and the two CNB forest lines is our release-eve nowcast (HARD_BASE); later months are forecasts. Year-on-year values are compounded from the monthly path and realised history.",
        "<b>Component bridge and its variants.</b> The component bridge forecasts core, food, administered prices, fuel and alcohol/tobacco separately and adds them with basket weights. The four Bridge · variants replace its food block with a cost-chain food model and its fuel block with constant pump prices; current core, long-run core level and long-run core gap also replace its core model.",
        "<b>Earlier component engine and trend-gap.</b> Taken from <code>output/path_step2.csv</code> for the same origin month. Only object (a), using their own nowcast for month 0, is eligible. Lines start at month 1; missing object (a) coverage remains unscored. The trend-gap model uses financial-market inflation expectations.",
        "<b>CNB TVW3 and QRF mean w/ nowcast.</b> Archived replication outputs from the CNB paper's quantile regression forest with all 72 predictors and a calendar-month feature: TVW3 weights five quantiles, QRF mean uses the forest's average. This page preserves those original forecasts, including the TVW calibration limitation identified in the September audit; it does not promote them as corrected production results. Predictor publication masks use the simulated cutoff, but inputs are current-vintage; LUCI and the Rushin index include histories the CNB has since re-estimated.",
        "<b>Realised.</b> Current-vintage CPI, compounded from monthly changes; first releases can differ by rounding. August 2026 is the year-on-year rate from CZSO's release of 10 September 2026 (1.9 %), added because the frozen backtest inputs end in July.",
        "<b>Average miss.</b> Absolute error on quarterly average inflation over the report's forecast quarters that have fully come in and that every complete path from month 0 covers. Quarterly means and errors use unrounded values; only the displayed payload is rounded. A model quarter uses realised months before its origin and forecasts from the origin onward. The CNB is scored on the same quarters. A line without the ranking bar does not cover all of those quarters. Neighbouring reports share outcomes, so the panels are not independent tests.",
    ]
    data = dict(series=SERIES, realised=realised, reports=reports, method=method, f_object=f_object)
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, allow_nan=False))
    output = Path(output) if output is not None else OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"wrote {output} ({output.stat().st_size / 1024:.0f} KB), {len(reports)} reports")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Destination HTML; use a separate path for audit corrections")
    main(output=parser.parse_args().output)
