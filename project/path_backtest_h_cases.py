"""Companion to path_backtest_h.py: how far were we, month by month, from what
was realised, and how did the CNB staff forecast of the time do.
  1. Case tables for selected origins (every December origin plus the
     origins matched to CNB report dates): our path (b: h0 = print, a: h0 =
     nowcast), realised, naive, random walk, at h = 1..12.
  2. A hairy chart: realised y/y with every origin's twelve-month path (a)
     drawn from its starting point, plus the CNB report calendar-year
     forecasts as markers at the report dates.
Reads output/path_backtest_h.csv and output/path_backtest_h_cnb.csv.
Usage: python path_backtest_h_cases.py
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    df = pd.read_csv(os.path.join(HERE, "output", "path_backtest_h.csv"))
    df["tp"] = pd.PeriodIndex(df["target"], freq="M"); df["op"] = pd.PeriodIndex(df["origin"], freq="M")
    try:
        cnb = pd.read_csv(os.path.join(HERE, "output", "path_backtest_h_cnb.csv"))
    except Exception:  # noqa: BLE001
        cnb = pd.DataFrame()
    real = df.drop_duplicates("tp").set_index("tp")["real_yy"].sort_index()
    # realised y/y for the known months too (from the rows' h0 information): rebuild from the rows where target == origin + h; the origin month's own y/y is yy_last of the next origin
    pd.set_option("display.width", 250)
    decs = [o for o in sorted(df.op.unique()) if o.month == 12]
    print("CASE TABLES: y/y by horizon from December origins (release-eve of the December print, i.e. mid-January): realised | ours (b) | ours (a) | naive | RW")
    for o in decs:
        g = df[df.op == o].sort_values("h")
        if g.real_yy.isna().all():
            continue
        line = " ".join(f"{int(r.h)}:{r.real_yy:.1f}/{r.yy_b_P0:.1f}/{r.yy_a_P0:.1f}/{r.yy_b_naive:.1f}" for r in g.itertuples() if np.isfinite(r.yy_b_P0))
        rw = g.yy_rw.iloc[0]
        c = cnb[cnb.origin == str(o)] if len(cnb) else pd.DataFrame()
        ctxt = "; ".join(f"CNB {r.season} {r.report} for {int(r.year)}: {r.cnb:.1f} vs ours {r.ours_a:.1f} vs realised {r.realised:.1f}" for r in c.itertuples()) if len(c) else ""
        print(f"\norigin {o} (RW y/y {rw:.1f}): h: realised/ours(b)/ours(a)/naive")
        print("   " + line)
        if ctxt:
            print("   " + ctxt)
    # hairy chart
    fig, ax = plt.subplots(figsize=(13, 6))
    known = df.drop_duplicates("op").set_index("op")["yy_last"].sort_index()   # y/y of origin-1, realised
    series = pd.concat([known.rename("y"), real.rename("y")]).groupby(level=0).last().sort_index()
    x = [p.to_timestamp() for p in series.index]
    ax.plot(x, series.values, color="black", lw=2.2, label="realised y/y")
    for o, g in df.groupby("op"):
        g = g.sort_values("h"); g = g[np.isfinite(g.yy_a_P0)]
        if len(g) == 0:
            continue
        xs = [(o - 1).to_timestamp()] + [p.to_timestamp() for p in g.tp]
        ys = [known.get(o, np.nan)] + list(g.yy_a_P0)
        ax.plot(xs, ys, color="tab:blue", lw=0.8, alpha=0.45)
    if len(cnb):
        for r in cnb.itertuples():
            ax.scatter(pd.Timestamp(r.report), r.cnb, marker="s", s=22, color="tab:red", zorder=5)
            ax.scatter(pd.Timestamp(r.report), r.realised, marker="_", s=60, color="black", zorder=5)
        ax.scatter([], [], marker="s", color="tab:red", label="CNB report: calendar-year average forecast (at report date)")
    ax.plot([], [], color="tab:blue", lw=0.8, alpha=0.6, label="our 12-month path from each origin (product path a)")
    ax.axhline(2.0, color="grey", lw=0.6, ls="--")
    ax.set_title("Czech CPI y/y: realised, every origin's 12-month path, CNB report annual forecasts")
    ax.set_ylabel("percent"); ax.legend(loc="upper left"); ax.grid(alpha=0.3)
    out = os.path.join(HERE, "output", "path_backtest_h_hairy.png")
    fig.tight_layout(); fig.savefig(out, dpi=130)
    print("\nchart ->", out)


if __name__ == "__main__":
    main()
