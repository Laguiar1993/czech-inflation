"""D6 of PATH_BACKTEST_H_SPEC recomputed standalone against all CNB report
vintages in cnb.mpr_vintages: our product path's calendar-year average of
y/y (known months from the official chain, the rest forecast, from the
first origin whose release-eve clock is at or after the report date) versus
the CNB staff forecast versus realised. Also the same comparison for
the FMIE one-year expectation is not possible on an annual basis and is
left to the h = 12 line of the main run.
Usage: python path_backtest_h_cnb.py
Writes output/path_backtest_h_cnb.csv.
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
    df = pd.read_csv(os.path.join(HERE, "output", "path_backtest_h.csv"))
    df["tp"] = pd.PeriodIndex(df["target"], freq="M"); df["op"] = pd.PeriodIndex(df["origin"], freq="M")
    origins = sorted(df.op.unique())
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    yk = y.dropna(); ylog = pd.Series(np.asarray(lg(yk)), index=yk.index)
    yy_real = pd.Series({m: pct(float(ylog.loc[m - 11:m].sum())) for m in yk.index if (m - 11) in yk.index})
    con = S.la._con()
    v = con.sql("""SELECT publication_date, season, period_year, value FROM cnb.mpr_vintages
                   WHERE series_code='consumer_price_index' ORDER BY publication_date, period_year""").df()
    con.close()
    v["publication_date"] = pd.to_datetime(v["publication_date"])
    rows = []
    for _, r in v.iterrows():
        Y = int(r.period_year); d = r.publication_date
        if Y < d.year or Y > d.year + 1:
            continue
        cands = [t for t in origins if _eve(t) >= d]
        if not cands:
            continue
        t = min(cands)
        g = df[df.op == t].set_index("tp")
        months = pd.period_range(f"{Y}-01", f"{Y}-12", freq="M")
        if not all(m in yy_real.index for m in months):
            continue                                   # realised year not complete
        vals_a, vals_b, vals_n = [], [], []
        ok = True
        h0_model = float(g["h0_model"].iloc[0]) if len(g) else np.nan
        for m in months:
            if m <= t - 1:
                vals_a.append(yy_real.loc[m]); vals_b.append(yy_real.loc[m]); vals_n.append(yy_real.loc[m])
            elif m == t:
                # the nowcast month: product path (a) uses the frozen nowcast, (b) and the naive path start from the print
                if not np.isfinite(h0_model) or (t - 11) not in ylog.index:
                    ok = False; break
                vals_a.append(pct(float(ylog.loc[t - 11:t - 1].sum()) + float(lg([h0_model])[0])))
                vals_b.append(yy_real.loc[m]); vals_n.append(yy_real.loc[m])
            elif m in g.index and np.isfinite(g.loc[m, "yy_a_P0"]):
                vals_a.append(g.loc[m, "yy_a_P0"]); vals_b.append(g.loc[m, "yy_b_P0"]); vals_n.append(g.loc[m, "yy_b_naive"])
            else:
                ok = False; break
        if not ok:
            continue
        rows.append({"report": str(d.date()), "season": r.season, "year": Y, "origin": str(t), "origin_clock": str(_eve(t).date()),
                     "n_forecast_months": int(sum(1 for m in months if m >= t)), "cnb": float(r.value), "ours_a": float(np.mean(vals_a)),
                     "ours_b": float(np.mean(vals_b)), "naive_b": float(np.mean(vals_n)), "realised": float(yy_real.reindex(months).mean())})
    cd = pd.DataFrame(rows)
    cd["err_cnb"] = cd.cnb - cd.realised; cd["err_ours_a"] = cd.ours_a - cd.realised; cd["err_naive"] = cd.naive_b - cd.realised
    cd.to_csv(os.path.join(HERE, "output", "path_backtest_h_cnb.csv"), index=False)
    pd.set_option("display.width", 250)
    print("CALENDAR-YEAR AVERAGE y/y: CNB report forecast vs our product path (a) vs naive path, all vs realised (chain), matched at the first origin clock after the report date")
    print(cd.round(2).to_string(index=False))
    cur = cd[cd.year == pd.to_datetime(cd.report).dt.year]; nxt = cd[cd.year == pd.to_datetime(cd.report).dt.year + 1]
    for lab, g in (("current year", cur), ("next year", nxt)):
        if len(g):
            print(f"\n{lab}: n={len(g)} | RMSE ours {rmse(g.err_ours_a):.3f}  CNB {rmse(g.err_cnb):.3f}  naive {rmse(g.err_naive):.3f} | "
                  f"MAE ours {g.err_ours_a.abs().mean():.3f}  CNB {g.err_cnb.abs().mean():.3f} | bias ours {g.err_ours_a.mean():+.3f}  CNB {g.err_cnb.mean():+.3f} | "
                  f"ours closer than CNB in {int((g.err_ours_a.abs() < g.err_cnb.abs()).sum())} of {len(g)}")
    if len(cur):
        print("\ncurrent year by number of forecast months remaining (ours vs CNB, absolute error):")
        for k, g in cur.groupby(pd.cut(cur.n_forecast_months, [0, 3, 6, 9, 12])):
            if len(g):
                print(f"  {k}: n={len(g)} ours {g.err_ours_a.abs().mean():.2f} CNB {g.err_cnb.abs().mean():.2f}")


if __name__ == "__main__":
    main()
