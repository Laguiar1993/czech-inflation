"""PATH_SPEC_v3, single run: the survey-free trend-and-gap variants (target-
anchored level; hard-data gap drivers) against the step-2 columns (F1b,
survey-anchored F2, naive, RW, realised) reused from output/path_step2.csv.
Usage: python path_step3_backtest.py
Writes output/path_step3.csv, output/path_step3_summary.csv.
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cz_struct as S  # noqa: E402
from data import local_adapter as la  # noqa: E402
from models.trend_gap import fit_forecast  # noqa: E402
from path_experiment import _eve, lg, pct, rmse, dm_stat  # noqa: E402
from path_step2_backtest import load_drivers  # noqa: E402

START = pd.Period("1998-01", "M")
ORIGIN0, ORIGIN_SEL_END, COMP0, SPLIT = pd.Period("2008-01", "M"), pd.Period("2018-12", "M"), pd.Period("2019-02", "M"), pd.Period("2023-01", "M")
H = list(range(1, 13))
EV = ["E1_ML", "E1_fixed", "E2_ML", "E2_fixed", "E3_ML", "E3_fixed"]
DRIVERS = {"E1": [], "E2": ["fx_mm", "un_d", "rr_gap6"], "E3": ["fx_mm", "un_d", "rr_gap6", "reer_mm"]}
EXPECTED_SIGN = {"fx_mm": +1, "un_d": -1, "rr_gap6": -1, "reer_mm": -1}


def main():
    y_ext = la.load_headline_cpi_mm_extended(); y_ext = y_ext[y_ext.index >= START].dropna()
    drv = load_drivers()
    con = la._con()
    rr = con.sql("SELECT period, value, snapshot_id FROM monetary.arad_data WHERE indicator_id='SREERM101' ORDER BY period, snapshot_id").df().drop_duplicates("period", keep="last")
    pr = con.sql("SELECT period, value, snapshot_id FROM monetary.arad_data WHERE indicator_id='SFTP04M2206' ORDER BY period, snapshot_id").df().drop_duplicates("period", keep="last")
    con.close()
    reer = pd.Series(rr.value.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(rr.period), freq="M"))
    pribor = pd.Series(pr.value.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(pr.period), freq="M"))
    ylog = pd.Series(np.asarray(lg(y_ext)), index=y_ext.index)
    yoy = pd.Series({m: pct(float(ylog.loc[m - 11:m].sum())) for m in y_ext.index if (m - 11) in y_ext.index})
    X_all = pd.DataFrame({"fx_mm": drv["fx_mm"], "un_d": drv["un_d"], "rr_gap6": (pribor - yoy).shift(6), "reer_mm": 100 * reer.pct_change()})
    s2 = pd.read_csv(os.path.join(HERE, "output", "path_step2.csv"))
    s2["op"] = pd.PeriodIndex(s2["origin"], freq="M"); s2["tp"] = pd.PeriodIndex(s2["target"], freq="M")
    origins = sorted(s2.op.unique())
    last_real = y_ext.index.max()
    rows, diag = [], []
    for i, t in enumerate(origins):
        as_of = _eve(t)
        yh = y_ext[y_ext.index <= t - 1]; yh = yh[S._released_index(yh.index, as_of)]
        if len(yh) < 96 or yh.index.max() != t - 1:
            continue
        X = X_all[X_all.index <= t - 1].reindex(yh.index).fillna(0.0)
        fits = {}
        for name, cols in DRIVERS.items():
            xh = X[cols] if cols else None
            fits[f"{name}_ML"] = fit_forecast(yh, range(1, 14), x_hist=xh, anchored=True)
            fits[f"{name}_fixed"] = fit_forecast(yh, range(1, 14), x_hist=xh, anchored=True, fixed_snr=True)
        for k, f in fits.items():
            diag.append({"origin": str(t), "variant": k, "rho": f.get("rho", np.nan), "phi": f.get("phi", np.nan), "level": f.get("level", np.nan),
                         "converged": f.get("converged", False), **{f"gamma_{c}": (f.get("gamma") or [np.nan] * len(DRIVERS[k.split('_')[0]]))[j] for j, c in enumerate(DRIVERS[k.split('_')[0]])}})
        for h in H:
            tgt = t + h
            if tgt > last_real:
                continue
            r = {"origin": str(t), "h": h, "target": str(tgt)}
            for k, f in fits.items():
                r[f"mm_{k}"] = f["mm"].get(h + 1, np.nan)
            rows.append(r)
        if i % 24 == 0:
            print(f"origin {t} done ({i + 1}/{len(origins)})", flush=True)
    df = pd.DataFrame(rows).merge(s2, on=["origin", "h", "target"], how="inner")
    df["op"] = pd.PeriodIndex(df["origin"], freq="M"); df["tp"] = pd.PeriodIndex(df["target"], freq="M")
    # y/y for the new variants (objects b and a)
    out = []
    for t, g in df.groupby("op"):
        g = g.sort_values("h"); known = ylog[ylog.index <= t - 1]
        h0r, h0m = float(g.h0_real.iloc[0]), float(g.h0_model.iloc[0])
        mm = {k: dict(zip(g.tp, g[f"mm_{k}"])) for k in EV}
        for _, r in g.iterrows():
            window = pd.period_range(r.tp - 11, r.tp, freq="M")
            base = float(known.reindex([m for m in window if m <= t - 1]).sum()); fut = [m for m in window if m >= t]
            rec = {"origin": str(t), "h": int(r.h)}
            for k in EV:
                pb = {t: h0r}; pb.update(mm[k]); rec[f"yy_b_{k}"] = pct(base + sum(lg([pb[m]])[0] for m in fut))
                if np.isfinite(h0m):
                    pa = {t: h0m}; pa.update(mm[k]); rec[f"yy_a_{k}"] = pct(base + sum(lg([pa[m]])[0] for m in fut))
                else:
                    rec[f"yy_a_{k}"] = np.nan
            out.append(rec)
    df = df.merge(pd.DataFrame(out), on=["origin", "h"], how="left")
    df.to_csv(os.path.join(HERE, "output", "path_step3.csv"), index=False)
    dg = pd.DataFrame(diag); dg.to_csv(os.path.join(HERE, "output", "path_step3_params.csv"), index=False)
    pd.set_option("display.width", 250)

    # economic-soundness check: mean estimated parameters and sign shares
    print("\nESTIMATED PARAMETERS across origins (mean; share of origins with the expected sign):")
    for k in EV:
        g = dg[dg.variant == k]; fam = k.split("_")[0]
        parts = [f"rho {g.rho.mean():.3f} (half-life of the level deviation {np.log(0.5)/np.log(g.rho.mean()):.0f} months)", f"phi {g.phi.mean():.2f}", f"converged {g.converged.mean():.2f}"]
        for c in DRIVERS[fam]:
            v = g[f"gamma_{c}"]; parts.append(f"gamma_{c} {v.mean():+.3f} (sign ok {float((np.sign(v) == EXPECTED_SIGN[c]).mean()):.2f})")
        print(f"  {k}: " + " | ".join(parts))
    # variant selection 2008-2018, h=12
    sel = df[(df.op <= ORIGIN_SEL_END) & (df.h == 12)]; sel = sel[sel[[f"yy_b_{k}" for k in EV] + ["yy_b_F2_D1_noFMIE", "yy_b_F2_D1_fixed", "real_yy"]].notna().all(axis=1)]
    scores = {k: rmse(sel[f"yy_b_{k}"] - sel.real_yy) for k in EV}
    pick = min(scores, key=scores.get)
    print(f"\nVARIANT SELECTION (origins 2008-01..2018-12, h=12, y/y RMSE (b), n={len(sel)}): " + ", ".join(f"{k} {v:.3f}" for k, v in scores.items())
          + f" | E0 (RW level, no survey) {rmse(sel.yy_b_F2_D1_noFMIE - sel.real_yy):.3f} | F2 with survey {rmse(sel.yy_b_F2_D1_fixed - sel.real_yy):.3f} -> {pick}")
    df["yy_b_E"] = df[f"yy_b_{pick}"]; df["yy_a_E"] = df[f"yy_a_{pick}"]; df["mm_E"] = df[f"mm_{pick}"]
    summ = []

    def table(mask, fams, label, obj="b"):
        print(f"\n{label}: y/y RMSE ({obj}) | naive | RW")
        for h in (1, 3, 6, 9, 12):
            g = df[mask & (df.h == h)]; cols = [f"yy_{obj}_{k}" for k in fams] + ["yy_b_naive", "yy_rw", "real_yy"]
            g = g[g[cols].notna().all(axis=1)]
            rec = {"table": label, "obj": obj, "h": h, "n": len(g), "naive": rmse(g.yy_b_naive - g.real_yy), "rw": rmse(g.yy_rw - g.real_yy)}
            for k in fams:
                rec[k] = rmse(g[f"yy_{obj}_{k}"] - g.real_yy); rec[f"bias_{k}"] = float((g[f"yy_{obj}_{k}"] - g.real_yy).mean())
            summ.append(rec)
            print(f"  h={h:2d} n={len(g):3d} | " + " ".join(f"{k} {rec[k]:.3f} ({rec[f'bias_{k}']:+.2f})" for k in fams) + f" | naive {rec['naive']:.3f} | RW {rec['rw']:.3f}")
    table(df.op >= ORIGIN0, EV + ["F2_D1_noFMIE", "F2_D1_fixed"], "LONG SPAN 2008-01..2026-07: survey-free variants, E0 control, F2 with survey")
    table(df.op >= COMP0, ["F1b", "F2_D1_fixed", "E", "F2_D1_noFMIE"], "COMPONENT SPAN 2019-02..2026-07 (b: h0 = print)")
    table(df.op >= COMP0, ["F1b", "F2_D1_fixed", "E"], "COMPONENT SPAN 2019-02..2026-07 (a: h0 = nowcast)", obj="a")
    regimes = [("2008-2009", "2008-01", "2009-12"), ("2010-2012", "2010-01", "2012-12"), ("2013-2016", "2013-01", "2016-12"), ("2017-2019", "2017-01", "2019-12"),
               ("2020-2021", "2020-01", "2021-12"), ("2022-2023", "2022-01", "2023-12"), ("2024-2026", "2024-01", "2026-12")]
    print("\nREGIMES of the target, h 7-12, y/y RMSE (b): E (survey-free) / F2 with survey / E0 / naive | E bias")
    for name, lo, hi in regimes:
        g = df[(df.tp >= pd.Period(lo, "M")) & (df.tp <= pd.Period(hi, "M")) & (df.h >= 7)]
        g = g[g[["yy_b_E", "yy_b_F2_D1_fixed", "yy_b_F2_D1_noFMIE", "yy_b_naive", "real_yy"]].notna().all(axis=1)]
        if len(g):
            print(f"  {name} n={len(g):3d}: {rmse(g.yy_b_E - g.real_yy):.2f} / {rmse(g.yy_b_F2_D1_fixed - g.real_yy):.2f} / {rmse(g.yy_b_F2_D1_noFMIE - g.real_yy):.2f} / {rmse(g.yy_b_naive - g.real_yy):.2f} | {(g.yy_b_E - g.real_yy).mean():+.2f}")
    # second-line rule
    g = df[(df.op >= ORIGIN0) & (df.h == 12)]; g = g[g[["yy_b_E", "yy_b_F2_D1_fixed", "real_yy"]].notna().all(axis=1)]
    rE, rF = rmse(g.yy_b_E - g.real_yy), rmse(g.yy_b_F2_D1_fixed - g.real_yy)
    signs_ok = all((np.sign(dg[dg.variant == pick][f"gamma_{c}"]).eq(EXPECTED_SIGN[c]).mean() >= 0.5) for c in DRIVERS[pick.split("_")[0]])
    print(f"\nSECOND-LINE RULE (long span h=12, n={len(g)}): survey-free {pick} {rE:.3f} vs survey version {rF:.3f} ({100*(rE/rF-1):+.1f}%); signs ok {signs_ok} -> "
          f"{'survey-free trend becomes the second line' if (rE <= 1.05 * rF and signs_ok) else 'survey version stays the second line; both reported'}")
    # publish rule and product rule on the component span
    comp = df.op >= COMP0
    print("\nPUBLISH RULE (component span, b) for E:")
    parts, pub = [], True
    for h in (3, 6, 12):
        g = df[comp & (df.h == h)]; g = g[g[["yy_b_E", "yy_b_naive", "yy_rw", "real_yy"]].notna().all(axis=1)]
        e = (g.yy_b_E - g.real_yy) ** 2; en = (g.yy_b_naive - g.real_yy) ** 2; er = (g.yy_rw - g.real_yy) ** 2
        gain = 100 * (1 - np.sqrt(e.mean() / en.mean())); d = (e - en).values; dm1, dm12 = dm_stat(d, max(h - 1, 0)), dm_stat(d, 12)
        cond = gain >= 10 and dm1 < 0 and dm12 < 0 and (np.sqrt(e.mean()) < np.sqrt(er.mean()) if h in (6, 12) else True); pub &= cond
        parts.append(f"h{h} gain {gain:+.1f}% DM {dm1:+.2f}/{dm12:+.2f} RW {'beat' if np.sqrt(e.mean()) < np.sqrt(er.mean()) else 'NOT beat'}")
    print("  " + " | ".join(parts) + f" -> {'PUBLISHABLE' if pub else 'not publishable'}")
    g = df[comp & (df.h == 12)]; g = g[g[["yy_b_E", "yy_b_F1b", "real_yy"]].notna().all(axis=1)]; first = g.op < SPLIT
    gain_full = 100 * (1 - rmse(g.yy_b_E - g.real_yy) / rmse(g.yy_b_F1b - g.real_yy))
    g1 = 100 * (1 - rmse(g[first].yy_b_E - g[first].real_yy) / rmse(g[first].yy_b_F1b - g[first].real_yy)); g2 = 100 * (1 - rmse(g[~first].yy_b_E - g[~first].real_yy) / rmse(g[~first].yy_b_F1b - g[~first].real_yy))
    print(f"PRODUCT RULE: E vs F1b at h=12: full {gain_full:+.1f}% | first half {g1:+.1f}% | second half {g2:+.1f}% -> {'E replaces F1b' if (gain_full >= 5 and g1 >= 5 and g2 >= 5 and pub) else 'F1b stays the product engine'}")
    pd.DataFrame(summ).to_csv(os.path.join(HERE, "output", "path_step3_summary.csv"), index=False)
    print(f"\nselected survey-free variant: {pick}")


if __name__ == "__main__":
    main()
