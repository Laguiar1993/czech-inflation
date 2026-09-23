"""PATH_SPEC_v2 step 2b (declared in the RESULTS section before this run):
the combination of the publishable component bridge F1b for the near
months and the trend-and-gap F2 (selected variant D1-fixed) beyond, split
after h = 3 (C3) and after h = 6 (C6). Pure arithmetic on the stored
step-2 rows: no model is refitted. Rule (frozen): a combination replaces
F1b as the product engine only if its y/y RMSE (b) at h = 12 on the
component span improves on F1b by at least 5%, is not worse than F1b by
more than 2% in EITHER origin half (2019-02..2022-12, 2023-01..2026-07),
and passes the publish rule (naive by 10% at h 3, 6, 12; RW at 6, 12;
DM < 0 at lags h-1 and 12). Otherwise F1b stays and the combination is
published as a second line.
Usage: python path_step2_combo.py
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from data import local_adapter as la  # noqa: E402
from path_experiment import lg, pct, rmse, dm_stat  # noqa: E402

COMP0, SPLIT = pd.Period("2019-02", "M"), pd.Period("2023-01", "M")
F2 = "F2_D1_fixed"


def main():
    df = pd.read_csv(os.path.join(HERE, "output", "path_step2.csv"))
    df["tp"] = pd.PeriodIndex(df["target"], freq="M"); df["op"] = pd.PeriodIndex(df["origin"], freq="M")
    df = df[df.op >= COMP0].copy()
    y_ext = la.load_headline_cpi_mm_extended(); y_ext = y_ext[y_ext.index >= pd.Period("1998-01", "M")].dropna()
    ylog = pd.Series(np.asarray(lg(y_ext)), index=y_ext.index)
    for k in (3, 6):
        df[f"mm_C{k}"] = np.where(df.h <= k, df["mm_F1b"], df[f"mm_{F2}"])
    out = []
    for t, g in df.groupby("op"):
        g = g.sort_values("h"); known = ylog[ylog.index <= t - 1]
        h0r, h0m = float(g.h0_real.iloc[0]), float(g.h0_model.iloc[0])
        for _, r in g.iterrows():
            window = pd.period_range(r.tp - 11, r.tp, freq="M")
            base = float(known.reindex([m for m in window if m <= t - 1]).sum()); fut = [m for m in window if m >= t]
            rec = {"origin": str(t), "h": int(r.h)}
            for k in (3, 6):
                mm = dict(zip(g.tp, g[f"mm_C{k}"]))
                pb = {t: h0r}; pb.update(mm); pa = {t: h0m}; pa.update(mm)
                rec[f"yy_b_C{k}"] = pct(base + sum(lg([pb[m]])[0] for m in fut))
                rec[f"yy_a_C{k}"] = pct(base + sum(lg([pa[m]])[0] for m in fut)) if np.isfinite(h0m) else np.nan
            out.append(rec)
    df = df.merge(pd.DataFrame(out), on=["origin", "h"], how="left")
    df.to_csv(os.path.join(HERE, "output", "path_step2_combo.csv"), index=False)
    fams = ["F1b", "C3", "C6", F2]
    print("COMPONENT SPAN 2019-02..2026-07, y/y RMSE (b) | naive; and (a) for F1b / C3 / C6")
    res = {}
    for h in (1, 3, 6, 9, 12):
        g = df[(df.h == h)]; g = g[g[[f"yy_b_{f}" for f in fams] + ["yy_b_naive", "yy_rw", "real_yy"]].notna().all(axis=1)]
        res[h] = {f: rmse(g[f"yy_b_{f}"] - g.real_yy) for f in fams}; res[h]["naive"] = rmse(g.yy_b_naive - g.real_yy); res[h]["rw"] = rmse(g.yy_rw - g.real_yy); res[h]["g"] = g
        print(f"  h={h:2d} n={len(g):2d} | " + " ".join(f"{f} {res[h][f]:.3f}" for f in fams) + f" | naive {res[h]['naive']:.3f} RW {res[h]['rw']:.3f} | (a) " + " ".join(f"{f} {rmse(g[f'yy_a_{f}'] - g.real_yy):.3f}" for f in ["F1b", "C3", "C6"]))
    print("\nBY TARGET REGIME (b), h 7-12: F1b / C3 / C6 / F2 / naive")
    for name, lo, hi in (("2019-2021", "2019-02", "2021-12"), ("2022-2023", "2022-01", "2023-12"), ("2024-2026", "2024-01", "2026-12")):
        g = df[(df.tp >= pd.Period(lo, "M")) & (df.tp <= pd.Period(hi, "M")) & (df.h >= 7)]
        g = g[g[[f"yy_b_{f}" for f in fams] + ["yy_b_naive", "real_yy"]].notna().all(axis=1)]
        print(f"  {name} n={len(g):3d}: " + " / ".join(f"{rmse(g[f'yy_b_{f}'] - g.real_yy):.2f}" for f in fams) + f" / {rmse(g.yy_b_naive - g.real_yy):.2f}")
    print("\nRULE for replacing F1b (h=12, object b): >=5% better on the full span, not >2% worse in either origin half, publish rule")
    g12 = res[12]["g"]; first = g12.op < SPLIT
    for k in ("C3", "C6"):
        gain_full = 100 * (1 - res[12][k] / res[12]["F1b"])
        g1 = 100 * (1 - rmse(g12[first][f"yy_b_{k}"] - g12[first].real_yy) / rmse(g12[first].yy_b_F1b - g12[first].real_yy))
        g2 = 100 * (1 - rmse(g12[~first][f"yy_b_{k}"] - g12[~first].real_yy) / rmse(g12[~first].yy_b_F1b - g12[~first].real_yy))
        pub = True; parts = []
        for h in (3, 6, 12):
            g = res[h]["g"]; e = (g[f"yy_b_{k}"] - g.real_yy) ** 2; en = (g.yy_b_naive - g.real_yy) ** 2; er = (g.yy_rw - g.real_yy) ** 2
            gain = 100 * (1 - np.sqrt(e.mean() / en.mean())); d = (e - en).values; dm1, dm12 = dm_stat(d, max(h - 1, 0)), dm_stat(d, 12)
            cond = gain >= 10 and dm1 < 0 and dm12 < 0 and (np.sqrt(e.mean()) < np.sqrt(er.mean()) if h in (6, 12) else True)
            pub &= cond; parts.append(f"h{h} {gain:+.1f}% DM {dm1:+.2f}/{dm12:+.2f}")
        ok = gain_full >= 5 and g1 >= -2 and g2 >= -2 and pub
        print(f"  {k}: vs F1b full {gain_full:+.1f}% | first half {g1:+.1f}% | second half {g2:+.1f}% | publish: {' | '.join(parts)} -> {'REPLACES F1b' if ok else 'does not replace F1b'}")
    print("\nQUARTERLY AVERAGES (b), quarters ahead 1..4: F1b / C3 / C6")
    qrows = []
    for t, g in df.groupby("op"):
        g = g.set_index("tp"); q0 = t.asfreq("Q")
        for kq in range(1, 5):
            qq = q0 + kq; months = list(pd.period_range(qq.asfreq("M", "s"), qq.asfreq("M", "e"), freq="M"))
            if all(m in g.index for m in months):
                qrows.append({"k": kq, **{f: g.loc[months, f"yy_b_{f}"].mean() for f in ["F1b", "C3", "C6"]}, "real": g.loc[months, "real_yy"].mean()})
    qd = pd.DataFrame(qrows)
    for kq, g in qd.groupby("k"):
        g = g.dropna(); print(f"  {kq} ahead (n={len(g)}): " + " / ".join(f"{rmse(g[f] - g.real):.2f}" for f in ["F1b", "C3", "C6"]))


if __name__ == "__main__":
    main()
