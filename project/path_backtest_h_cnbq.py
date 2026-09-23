"""D6, quarterly version: the CNB report's quarterly CPI y/y forecasts versus
our path versus realised, by quarters ahead. Matching (--match): "before"
(default since 8 Sep 2026, user rule: compare with the CNB when its report
is out, using the path we had on the table) = the last origin whose first
release is on or before the report date, ours(b) = the known print at h0
plus that origin's release-eve path; "after" = the first origin whose
release-eve clock is at or after the report date (earlier convention,
gives us up to a month more information than the CNB had). Ours (a) = product
path (h0 = frozen nowcast), ours (b) = h0 = print; naive = seasonal-naive
path from the print. Reads data/cnb_mpr_cpi_quarterly.csv and
output/path_backtest_h.csv. Writes output/path_backtest_h_cnbq.csv.
Usage: python path_backtest_h_cnbq.py
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cz_struct as S  # noqa: E402
from path_experiment import _eve, lg, pct, rmse  # noqa: E402


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=os.path.join(HERE, "output", "path_backtest_h.csv"))
    ap.add_argument("--col-a", default="yy_a_P0", help="product-path column (h0 = nowcast)")
    ap.add_argument("--col-b", default="yy_b_P0", help="horizon-only column (h0 = print)")
    ap.add_argument("--out", default=os.path.join(HERE, "output", "path_backtest_h_cnbq.csv"))
    ap.add_argument("--match", choices=["before", "after"], default="before",
                    help="before (default, user rule 8 Sep 2026): the last origin whose first release is on or before the report date, "
                         "i.e. the path we had already published when the report came out, re-based on the known print (object b); "
                         "after: the first origin whose release-eve clock is on or after the report date (the earlier convention)")
    args = ap.parse_args()
    df = pd.read_csv(args.file)
    df["yy_a_P0"] = df[args.col_a]; df["yy_b_P0"] = df[args.col_b]
    if "yy_b_naive" not in df.columns and "yy_b_naive" in df.columns:
        pass
    df["tp"] = pd.PeriodIndex(df["target"], freq="M"); df["op"] = pd.PeriodIndex(df["origin"], freq="M")
    origins = sorted(df.op.unique())
    cq = pd.read_csv(os.path.join(HERE, "data", "cnb_mpr_cpi_quarterly.csv")); cq["report_date"] = pd.to_datetime(cq["report_date"])
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    yk = y.dropna(); ylog = pd.Series(np.asarray(lg(yk)), index=yk.index)
    yy_real = pd.Series({m: pct(float(ylog.loc[m - 11:m].sum())) for m in yk.index if (m - 11) in yk.index})
    rows = []
    for (d, season), g_c in cq.groupby(["report_date", "season"]):
        if args.match == "after":
            cands = [t for t in origins if _eve(t) >= d]
            t = min(cands) if cands else None
        else:
            cands = [t for t in origins if (_eve(t) + pd.Timedelta(days=1)).normalize() <= d.normalize()]     # first release (eve + 1) on or before the report date
            t = max(cands) if cands else None
        if t is None:
            continue
        g = df[df.op == t].set_index("tp")
        h0 = float(g["h0_model"].iloc[0]) if len(g) and np.isfinite(g["h0_model"].iloc[0]) else np.nan
        yy_a0 = pct(float(ylog.loc[t - 11:t - 1].sum()) + float(lg([h0])[0])) if np.isfinite(h0) else np.nan
        q0 = (t - 1).asfreq("Q")   # last quarter with a released month
        for r in g_c.itertuples():
            qp = pd.Period(r.quarter, freq="Q")
            months = list(pd.period_range(qp.asfreq("M", "s"), qp.asfreq("M", "e"), freq="M"))
            if not all(m in yy_real.index for m in months):
                continue
            k = (qp - q0).n           # quarters ahead of the last released quarter
            if k < 1:
                continue
            va, vb, vn = [], [], []
            ok = True
            for m in months:
                if m <= t - 1:
                    va.append(yy_real.loc[m]); vb.append(yy_real.loc[m]); vn.append(yy_real.loc[m])
                elif m == t:
                    if not np.isfinite(yy_a0):
                        ok = False; break
                    va.append(yy_a0); vb.append(yy_real.loc[m]); vn.append(yy_real.loc[m])
                elif m in g.index and np.isfinite(g.loc[m, "yy_a_P0"]):
                    va.append(g.loc[m, "yy_a_P0"]); vb.append(g.loc[m, "yy_b_P0"]); vn.append(g.loc[m, "yy_b_naive"])
                else:
                    ok = False; break
            if not ok:
                continue
            rows.append({"report": str(d.date()), "season": season, "origin": str(t), "origin_clock": str(_eve(t).date()), "quarter": r.quarter,
                         "quarters_ahead": k, "cnb": float(r.value), "ours_a": float(np.mean(va)), "ours_b": float(np.mean(vb)),
                         "naive": float(np.mean(vn)), "realised": float(np.mean([yy_real.loc[m] for m in months]))})
    cd = pd.DataFrame(rows)
    for c in ("cnb", "ours_a", "ours_b", "naive"):
        cd[f"err_{c}"] = cd[c] - cd["realised"]
    cd.to_csv(args.out, index=False)
    pd.set_option("display.width", 250)
    print("QUARTERLY y/y: CNB report forecast vs our path vs naive, all vs realised; matching = " + ("the last origin published before the report date (ours(b) = print at h0 + the path from that origin's release eve; the fair column)" if args.match == "before" else "the first origin clock after the report date"))
    print(cd.round(2).to_string(index=False))
    print("\nBY QUARTERS AHEAD (of the last released quarter): n | RMSE CNB / ours(a) / ours(b) / naive | MAE CNB / ours(a) | bias CNB / ours(a) | ours(a) closer than CNB")
    for k, g in cd.groupby("quarters_ahead"):
        print(f"  {k}: n={len(g):2d} | {rmse(g.err_cnb):.2f} / {rmse(g.err_ours_a):.2f} / {rmse(g.err_ours_b):.2f} / {rmse(g.err_naive):.2f} | "
              f"{g.err_cnb.abs().mean():.2f} / {g.err_ours_a.abs().mean():.2f} | {g.err_cnb.mean():+.2f} / {g.err_ours_a.mean():+.2f} | {int((g.err_ours_a.abs() < g.err_cnb.abs()).sum())} of {len(g)}")
    rep = pd.to_datetime(cd.report)
    for lab, m in (("reports 2022-2023", rep < "2024-01-01"), ("reports 2024+", rep >= "2024-01-01")):
        g = cd[m]
        if len(g):
            print(f"\n{lab}: n={len(g)} | RMSE CNB {rmse(g.err_cnb):.2f} ours(a) {rmse(g.err_ours_a):.2f} ours(b) {rmse(g.err_ours_b):.2f} naive {rmse(g.err_naive):.2f} | bias CNB {g.err_cnb.mean():+.2f} ours(a) {g.err_ours_a.mean():+.2f} ours(b) {g.err_ours_b.mean():+.2f} | ours(b) closer in {int((g.err_ours_b.abs() < g.err_cnb.abs()).sum())} of {len(g)}")
            for k, gg in g.groupby("quarters_ahead"):
                print(f"    {k} ahead: n={len(gg):2d} RMSE CNB {rmse(gg.err_cnb):.2f} ours(a) {rmse(gg.err_ours_a):.2f} ours(b) {rmse(gg.err_ours_b):.2f} naive {rmse(gg.err_naive):.2f}")


if __name__ == "__main__":
    main()
