"""BANDS_SPEC_v1.md, single run: calibrated bands for BASE_RIDGE, PAST_FULL and
PAST_HALF from their own past release-eve first-release errors, five
declared variants, coverage / PIT / CRPS evaluation and the frozen
selection rule. Points are never touched.
Usage: python bands_trio.py
Writes output/bands_trio.csv (origin x model x variant), output/bands_trio_summary.csv,
output/bands_trio_selection.csv.
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cz_struct as S  # noqa: E402
from models.bands import VARIANTS, LEVELS, build_pool, band  # noqa: E402

MODELS = {"BASE_RIDGE": "STRUCT_EVE", "PAST_FULL": "STRUCT_PE_WARM_EVE", "PAST_HALF": "STRUCT_PEH_WARM_EVE"}
BIG = 0.4


def main():
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period"); bt.index = pd.PeriodIndex(bt.index, freq="M")
    ext = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history_extended.csv")); ext["p"] = pd.PeriodIndex(ext["target_month"], freq="M")
    ext = ext.set_index("p"); ext = ext[ext["era"] != "flash_survey_suspect"]
    actual = ext["actual"].astype(float); survey = ext["survey_median"].astype(float)
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    state = feats["state"].reindex(bt.index)          # trailing y/y > 4% through t-1, the model's own line
    rows = []
    for name, col in MODELS.items():
        f = bt[col].astype(float); e = (f - actual.reindex(bt.index))
        hist = pd.DataFrame({"e": e, "month": [p.month for p in bt.index], "state": state.values}, index=bt.index)
        for i, t in enumerate(bt.index):
            past = hist.iloc[:i].dropna(subset=["e"]).copy()
            past["age_months"] = [(t - u).n for u in past.index]
            for v in VARIANTS:
                pool, note = build_pool(past, v, t.month, float(state.loc[t]) if np.isfinite(state.loc[t]) else None)
                r = {"origin": str(t), "model": name, "variant": v, "note": note, "forecast": f.loc[t], "actual": actual.get(t, np.nan),
                     "survey": survey.get(t, np.nan), "error": e.loc[t], "n_pool": 0 if pool is None else len(pool)}
                if pool is not None:
                    for lv in LEVELS:
                        lo, hi = band(f.loc[t], pool, lv); r[f"lo{lv}"], r[f"hi{lv}"] = lo, hi
                    r["pit"] = pool.cdf(e.loc[t]); r["crps"] = pool.crps(e.loc[t])
                    r["width80"] = r["hi80"] - r["lo80"]
                    # threshold-weighted CRPS: weight 1 on price-level thresholds at least 0.4 away from the survey
                    if pool.t_scale:
                        grid = np.linspace(f.loc[t] - 6, f.loc[t] + 6, 2401)
                        F = np.array([pool.cdf(f.loc[t] - g) for g in grid])  # placeholder, replaced below
                    # empirical / weighted version on the print scale: forecast distribution = f - e_pool
                    fx = f.loc[t] - pool.e; w = pool.w / pool.w.sum()
                    grid = np.linspace(min(fx.min(), r["actual"]) - 0.5, max(fx.max(), r["actual"]) + 0.5, 1201)
                    if pool.t_scale:
                        Fg = np.array([1.0 - pool.cdf(f.loc[t] - g) for g in grid])
                    else:
                        Fg = np.array([np.sum(w * (fx <= g)) for g in grid])
                    wgt = (np.abs(grid - r["survey"]) >= BIG).astype(float) if np.isfinite(r["survey"]) else np.ones_like(grid)
                    r["twcrps"] = float(np.trapezoid(wgt * (Fg - (grid >= r["actual"])) ** 2, grid)) if np.isfinite(r["actual"]) else np.nan
                rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "output", "bands_trio.csv"), index=False)
    df["p"] = pd.PeriodIndex(df["origin"], freq="M"); df["jan"] = df.p.dt.month == 1
    df["big"] = (df["actual"] - df["survey"]).abs() >= BIG - 1e-9
    df["y2024"] = df.p >= pd.Period("2024-01", "M")

    def cov(g, lv):
        ok = g[f"lo{lv}"].notna(); gg = g[ok]
        return float(((gg["actual"] >= gg[f"lo{lv}"]) & (gg["actual"] <= gg[f"hi{lv}"])).mean()) if len(gg) else np.nan, int(len(gg))
    summ = []
    print("\nCOVERAGE (share of prints inside the band) | width80 | PIT KS | CRPS | twCRPS(big) ; per model x variant")
    print(f"{'model':10s} {'var':3s} {'n':>3s} | {'50':>5s} {'80':>5s} {'90':>5s} | exJan {'80':>5s} {'90':>5s} | 2024+ {'80':>5s} {'90':>5s} | big {'80':>5s} {'90':>5s} | {'w80':>5s} {'KS':>5s} {'CRPS':>6s} {'twCRPS':>7s}")
    for (m, v), g in df.groupby(["model", "variant"]):
        has = g["lo80"].notna()
        c = {lv: cov(g, lv) for lv in LEVELS}
        cx = {lv: cov(g[~g.jan], lv)[0] for lv in (80, 90)}
        c24 = {lv: cov(g[g.y2024], lv)[0] for lv in (80, 90)}
        cb = {lv: cov(g[g.big], lv)[0] for lv in (80, 90)}
        pit = g.loc[has, "pit"].dropna(); ks = float(stats.kstest(pit, "uniform").statistic) if len(pit) > 5 else np.nan
        crps = float(g.loc[has, "crps"].mean()); tw = float(g.loc[has & g.big, "twcrps"].mean()) if (has & g.big).any() else np.nan
        w80 = float(g.loc[has, "width80"].mean())
        summ.append({"model": m, "variant": v, "n": c[80][1], "cov50": c[50][0], "cov80": c[80][0], "cov90": c[90][0],
                     "cov80_exjan": cx[80], "cov90_exjan": cx[90], "cov80_2024": c24[80], "cov90_2024": c24[90], "cov80_big": cb[80], "cov90_big": cb[90],
                     "width80": w80, "pit_ks": ks, "crps": crps, "twcrps_big": tw})
        print(f"{m:10s} {v:3s} {c[80][1]:3d} | {c[50][0]:5.2f} {c[80][0]:5.2f} {c[90][0]:5.2f} |       {cx[80]:5.2f} {cx[90]:5.2f} |       {c24[80]:5.2f} {c24[90]:5.2f} |     {cb[80]:5.2f} {cb[90]:5.2f} | {w80:5.2f} {ks:5.2f} {crps:6.3f} {tw:7.3f}")
    sm = pd.DataFrame(summ); sm.to_csv(os.path.join(HERE, "output", "bands_trio_summary.csv"), index=False)
    # frozen selection rule
    order = {"V0": 0, "V1": 1, "V3": 2, "V4": 3, "V2": 4}
    sel = []
    print("\nSELECTION (80 and 90 coverage within 5 points of nominal on all origins AND 2024+; lowest CRPS; ties to the simpler variant)")
    for m, g in sm.groupby("model"):
        ok = g[(g.cov80.sub(0.80).abs() <= 0.05) & (g.cov90.sub(0.90).abs() <= 0.05) & (g.cov80_2024.sub(0.80).abs() <= 0.05) & (g.cov90_2024.sub(0.90).abs() <= 0.05)]
        if len(ok):
            ok = ok.assign(rank=ok.variant.map(order)).sort_values(["crps", "rank"]); pick = ok.iloc[0]; status = "calibrated"
        else:
            pick = g[g.variant == "V1"].iloc[0]; status = "uncalibrated (no variant met the coverage condition; V1 published as such)"
        sel.append({"model": m, "variant": pick.variant, "status": status, "cov80": pick.cov80, "cov90": pick.cov90, "cov80_2024": pick.cov80_2024, "cov90_2024": pick.cov90_2024, "crps": pick.crps})
        print(f"  {m:10s} -> {pick.variant}  ({status}); cov80 {pick.cov80:.2f} cov90 {pick.cov90:.2f} | 2024+ {pick.cov80_2024:.2f} {pick.cov90_2024:.2f} | CRPS {pick.crps:.3f}")
    pd.DataFrame(sel).to_csv(os.path.join(HERE, "output", "bands_trio_selection.csv"), index=False)
    # reliability of the deviation from the survey (V0 rows carry the shared point columns; use one variant to avoid duplicates)
    print("\nRELIABILITY of |model - survey| (release eve, 90 origins): bucket | n | share of months the model was closer to the print than the survey | mean gain g = |s| - |e| (pp)")
    one = df[df.variant == "V0"]
    for m, g in one.groupby("model"):
        dev = (g.forecast - g.survey).abs(); closer = (g.forecast - g.actual).abs() < (g.survey - g.actual).abs(); gain = (g.survey - g.actual).abs() - (g.forecast - g.actual).abs()
        parts = []
        for lo, hi in ((0, 0.1), (0.1, 0.2), (0.2, 0.4), (0.4, 99)):
            mk = (dev >= lo) & (dev < hi)
            parts.append(f"[{lo},{hi if hi < 99 else 'inf'}) n={int(mk.sum()):2d} closer {closer[mk].mean() if mk.any() else float('nan'):.2f} gain {gain[mk].mean() if mk.any() else float('nan'):+.3f}")
        print(f"  {m:10s}: " + " | ".join(parts))


if __name__ == "__main__":
    main()
