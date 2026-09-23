"""PATH_SPEC_v5, single run: semi-structural gap model S (anchored expectations A / model-consistent M),
market rate path, IS-curve transmission, random-walk exchange rate, handover from the component bridge
on the component span. Reuses the step-4 columns for every reference line.
Usage: python path_step5_backtest.py
Writes output/path_step5.csv, output/path_step5_params.csv, output/path_step5_summary.csv.
"""
import os
import sys
import warnings

import duckdb
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cz_struct as S  # noqa: E402
from data import local_adapter as la  # noqa: E402
from models.gap_model import fit_forecast_gap, fit_is_curve, market_rate_path, real_rate_gap, unemployment_gap, W_ANCHOR  # noqa: E402
from path_experiment import _eve, lg, pct, rmse, dm_stat  # noqa: E402

START = pd.Period("1998-01", "M")
ORIGIN0, ORIGIN_SEL_END, COMP0, SPLIT = pd.Period("2008-01", "M"), pd.Period("2018-12", "M"), pd.Period("2019-02", "M"), pd.Period("2023-01", "M")
H = list(range(1, 13))
BBG = os.path.expanduser("~/bbg_cache/bloomberg.duckdb")
FRA_TICKERS = {"pribor3m": "PRIB03M Index", "fra3x6": "CKFR0CF Curncy", "fra6x9": "CKFR0FI Curncy", "fra9x12": "CKFR0I1 Curncy",
               "fra12x15": "CKFR011C Curncy", "fra15x18": "CKFR1C1F Curncy", "fra18x21": "CKFR1F1I Curncy", "fra21x24": "CKFR1I2 Curncy"}


def load_curve() -> pd.DataFrame:
    con = duckdb.connect(BBG, read_only=True)
    q = "SELECT ticker, date, value FROM daily WHERE field='PX_LAST' AND ticker IN (" + ",".join(f"'{v}'" for v in FRA_TICKERS.values()) + ") ORDER BY date"
    d = con.sql(q).df(); con.close()
    d["date"] = pd.to_datetime(d["date"])
    w = d.pivot_table(index="date", columns="ticker", values="value").sort_index().ffill()
    inv = {v: k for k, v in FRA_TICKERS.items()}
    return w.rename(columns=inv)


def quotes_at(curve: pd.DataFrame, clock: pd.Timestamp):
    sub = curve[curve.index <= clock.normalize()]
    if sub.empty:
        return {}, None
    row = sub.iloc[-1]
    return {k: float(row[k]) for k in curve.columns if np.isfinite(row[k])}, sub.index[-1]


def main():
    y_ext = la.load_headline_cpi_mm_extended(); y_ext = y_ext[y_ext.index >= START].dropna()
    con = la._con()
    un = con.sql("SELECT data_month, rate_pct FROM czso.unemployment_ri WHERE series='unemployment' AND adjusted='trend_cycle' AND gender='total' ORDER BY 1").df()
    pr = con.sql("SELECT period, value, snapshot_id FROM monetary.arad_data WHERE indicator_id='SFTP04M2206' ORDER BY period, snapshot_id").df().drop_duplicates("period", keep="last")
    fx = con.sql("SELECT year, month, czk_per_unit FROM monetary.fx_monthly WHERE currency_code='EUR' ORDER BY 1,2").df()
    con.close()
    u = pd.Series(un.rate_pct.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(un.data_month), freq="M"))
    pribor = pd.Series(pr.value.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(pr.period), freq="M"))
    fxs = pd.Series(fx.czk_per_unit.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(dict(year=fx.year, month=fx.month, day=1)), freq="M"))
    ylog = pd.Series(np.asarray(lg(y_ext)), index=y_ext.index)
    pi12 = pd.Series({m: pct(float(ylog.loc[m - 11:m].sum())) for m in y_ext.index if (m - 11) in y_ext.index})
    ugap_full = unemployment_gap(u)
    ugap_avail = ugap_full.shift(1)                         # LFS month public a month later: row s carries month s-1
    rr_full = real_rate_gap(pribor, pi12)
    fx12_l3 = (100 * (fxs / fxs.shift(12) - 1)).shift(3)
    curve = load_curve()
    print(f"curve {curve.index.min().date()}..{curve.index.max().date()} cols {list(curve.columns)}; unemployment {u.index.min()}..{u.index.max()}")
    s4 = pd.read_csv(os.path.join(HERE, "output", "path_step4.csv")); s4["op"] = pd.PeriodIndex(s4["origin"], freq="M")
    bh = pd.read_csv(os.path.join(HERE, "output", "path_step2.csv"))          # F1b m/m as scored in step 2
    f1b_mm = {(o, h): v for o, h, v in zip(bh.origin, bh.h, bh.mm_F1b)}
    origins = sorted(s4.op.unique()); last_real = y_ext.index.max()
    rows, diag = [], []
    for i, t in enumerate(origins):
        as_of = _eve(t)
        yh = y_ext[y_ext.index <= t - 1]; yh = yh[S._released_index(yh.index, as_of)]
        if len(yh) < 96 or yh.index.max() != t - 1:
            continue
        X = pd.DataFrame({"ugap": ugap_avail, "fx12_l3": fx12_l3})[lambda d: d.index <= t - 1].reindex(yh.index).fillna(0.0)
        rr_hist = rr_full[rr_full.index <= t - 1]
        is_par = fit_is_curve(u[u.index <= t - 2], rr_full, t - 2)                      # LFS through t-2 is public at the eve (level, amendment 1)
        q, qdate = quotes_at(curve, as_of)
        rate = market_rate_path(q, t) if q else pd.Series(float(pribor.get(t - 1, np.nan)), index=pd.period_range(t, t + 23, freq="M"))
        stale = (qdate is None) or ((as_of.normalize() - qdate).days > 10)
        pi12_last = float(pi12.get(t - 1, np.nan)); rstar_last = float((pribor - pi12).rolling(120, min_periods=36).mean().get(t - 1, np.nan))
        if not np.isfinite(rstar_last):
            rstar_last = 0.0
        common = dict(X_hist=X, ugap_hist=u[u.index <= t - 2], fx_level=fxs[fxs.index <= t - 1], rr_hist=rr_hist, is_par=is_par, rate_path=rate,
                      pi12_last=pi12_last, rstar_last=rstar_last)
        fits = {"S_A": fit_forecast_gap(yh, expectations="A", **common), "S_M": fit_forecast_gap(yh, expectations="M", **common),
                "S_M25": fit_forecast_gap(yh, expectations="M", w=0.25, **common), "S_M75": fit_forecast_gap(yh, expectations="M", w=0.75, **common)}
        # handover variants on the component span: pseudo-observations = print at t (object b) + F1b m/m for t+1..t+3
        g4 = s4[s4.op == t]
        h0r = float(g4.h0_real.iloc[0]) if len(g4) else np.nan
        f13 = [f1b_mm.get((str(t), h), np.nan) for h in (1, 2, 3)]
        if np.isfinite(h0r) and all(np.isfinite(v) for v in f13) and t >= COMP0:
            po = pd.Series([h0r] + f13, index=pd.period_range(t, t + 3, freq="M"))
            fits["S_A_H"] = fit_forecast_gap(yh, expectations="A", pseudo_obs=po, **common)
            fits["S_M_H"] = fit_forecast_gap(yh, expectations="M", pseudo_obs=po, **common)
        for k, f in fits.items():
            gam = f.get("gamma", [np.nan, np.nan])
            diag.append({"origin": str(t), "variant": k, "rho": f.get("rho", np.nan), "phi": f.get("phi", np.nan), "b_u": gam[0] if len(gam) > 0 else np.nan,
                         "b_q": gam[1] if len(gam) > 1 else np.nan, "sigma": is_par["sigma"], "r_u": is_par.get("r_u", np.nan), "is_n": is_par["n"], "converged": f.get("converged", False),
                         "rate_path_stale": bool(stale), "curve_date": str(qdate.date()) if qdate is not None else None})
        for h in H:
            tgt = t + h
            if tgt > last_real:
                continue
            r = {"origin": str(t), "h": h, "target": str(tgt)}
            for k, f in fits.items():
                r[f"mm_{k}"] = f["mm"].get(h + 1, np.nan)
            rows.append(r)
        if i % 24 == 0:
            print(f"origin {t} done ({i + 1}/{len(origins)}) IS sigma {is_par['sigma']:+.3f} n {is_par['n']} | rate path from {qdate.date() if qdate is not None else None}", flush=True)
    df = pd.DataFrame(rows).merge(s4, on=["origin", "h", "target"], how="inner")
    df["op"] = pd.PeriodIndex(df["origin"], freq="M"); df["tp"] = pd.PeriodIndex(df["target"], freq="M")
    NEW = ["S_A", "S_M", "S_M25", "S_M75", "S_A_H", "S_M_H"]
    out = []
    for t, g in df.groupby("op"):
        g = g.sort_values("h"); known = ylog[ylog.index <= t - 1]
        h0r, h0m = float(g.h0_real.iloc[0]), float(g.h0_model.iloc[0])
        mm = {k: dict(zip(g.tp, g[f"mm_{k}"])) if f"mm_{k}" in g.columns else {} for k in NEW}
        for _, r in g.iterrows():
            window = pd.period_range(r.tp - 11, r.tp, freq="M")
            base = float(known.reindex([m for m in window if m <= t - 1]).sum()); fut = [m for m in window if m >= t]
            rec = {"origin": str(t), "h": int(r.h)}
            for k in NEW:
                if not mm[k] or any(not np.isfinite(mm[k].get(m, np.nan)) for m in fut if m != t):
                    rec[f"yy_b_{k}"] = np.nan; rec[f"yy_a_{k}"] = np.nan; continue
                pb = {t: h0r}; pb.update(mm[k]); rec[f"yy_b_{k}"] = pct(base + sum(lg([pb[m]])[0] for m in fut))
                if np.isfinite(h0m):
                    pa = {t: h0m}; pa.update(mm[k]); rec[f"yy_a_{k}"] = pct(base + sum(lg([pa[m]])[0] for m in fut))
                else:
                    rec[f"yy_a_{k}"] = np.nan
            out.append(rec)
    df = df.merge(pd.DataFrame(out), on=["origin", "h"], how="left")
    df.to_csv(os.path.join(HERE, "output", "path_step5.csv"), index=False)
    dg = pd.DataFrame(diag); dg.to_csv(os.path.join(HERE, "output", "path_step5_params.csv"), index=False)
    pd.set_option("display.width", 250)
    print("\nESTIMATED PARAMETERS (mean over origins; share with the expected sign):")
    g = dg[dg.variant == "S_A"]
    okb_u, okb_q, oks = float((g.b_u < 0).mean()), float((g.b_q > 0).mean()), float((g.sigma > 0).mean())
    print(f"  Phillips curve: b_u {g.b_u.mean():+.4f} (sign ok {okb_u:.2f}) b_q {g.b_q.mean():+.4f} (sign ok {okb_q:.2f}) phi {g.phi.mean():.2f} rho {g.rho.mean():.3f}")
    print(f"  IS curve (annual differences): sigma {g.sigma.mean():+.4f} (sign ok {oks:.2f}) n {g.is_n.mean():.0f} | rate path stale in {int(g.rate_path_stale.sum())} origins")
    eligible = okb_u >= 0.5 and okb_q >= 0.5 and oks >= 0.5
    print(f"  -> {'eligible' if eligible else 'NOT eligible (signs)'}")
    summ = []

    def table(mask, fams, label, obj="b"):
        print(f"\n{label}: y/y RMSE ({obj}) (bias) | naive | RW")
        for h in (1, 3, 6, 9, 12):
            g = df[mask & (df.h == h)]; cols = [f"yy_{obj}_{k}" for k in fams] + ["yy_b_naive", "yy_rw", "real_yy"]
            g = g[g[cols].notna().all(axis=1)]
            rec = {"table": label, "obj": obj, "h": h, "n": len(g), "naive": rmse(g.yy_b_naive - g.real_yy), "rw": rmse(g.yy_rw - g.real_yy)}
            for k in fams:
                rec[k] = rmse(g[f"yy_{obj}_{k}"] - g.real_yy); rec[f"bias_{k}"] = float((g[f"yy_{obj}_{k}"] - g.real_yy).mean())
            summ.append(rec)
            print(f"  h={h:2d} n={len(g):3d} | " + " ".join(f"{k} {rec[k]:.3f} ({rec[f'bias_{k}']:+.2f})" for k in fams) + f" | naive {rec['naive']:.3f} | RW {rec['rw']:.3f}")
    table(df.op >= ORIGIN0, ["S_A", "S_M", "S_M25", "S_M75", "E1_ML", "E5", "E7", "F2_D1_fixed"], "LONG SPAN 2008-01..2026-07")
    table(df.op >= COMP0, ["F1b", "S_A", "S_M", "S_A_H", "S_M_H", "F2_D1_fixed", "E7"], "COMPONENT SPAN 2019-02..2026-07 (b)")
    table(df.op >= COMP0, ["F1b", "S_A", "S_M", "S_A_H", "S_M_H", "F2_D1_fixed", "E7"], "COMPONENT SPAN 2019-02..2026-07 (a)", obj="a")
    sel = df[(df.op <= ORIGIN_SEL_END) & (df.h == 12)]; sel = sel[sel[["yy_b_S_A", "yy_b_S_M", "yy_b_E1_ML", "real_yy"]].notna().all(axis=1)]
    sA, sM, sE1 = rmse(sel.yy_b_S_A - sel.real_yy), rmse(sel.yy_b_S_M - sel.real_yy), rmse(sel.yy_b_E1_ML - sel.real_yy)
    lon = df[(df.op >= ORIGIN0) & (df.h == 12)]; lon = lon[lon[["yy_b_S_A", "yy_b_S_M", "yy_b_E1_ML", "yy_b_E7", "yy_b_F2_D1_fixed", "real_yy"]].notna().all(axis=1)]
    lA, lM, lE1, lE7, lF2 = (rmse(lon.yy_b_S_A - lon.real_yy), rmse(lon.yy_b_S_M - lon.real_yy), rmse(lon.yy_b_E1_ML - lon.real_yy), rmse(lon.yy_b_E7 - lon.real_yy), rmse(lon.yy_b_F2_D1_fixed - lon.real_yy))
    pick = "S_A" if sA <= sM else "S_M"; lpick = lA if pick == "S_A" else lM
    safeguard = lpick <= lE1
    print(f"\nSELECTION (2008-2018 h=12, n={len(sel)}): S_A {sA:.3f} S_M {sM:.3f} (E1 {sE1:.3f}) -> {pick}; long-span safeguard (n={len(lon)}): {pick} {lpick:.3f} vs E1 {lE1:.3f} -> {'passes' if safeguard else 'FAILS: not adopted'}")
    regimes = [("2008-2009", "2008-01", "2009-12"), ("2010-2012", "2010-01", "2012-12"), ("2013-2016", "2013-01", "2016-12"), ("2017-2019", "2017-01", "2019-12"),
               ("2020-2021", "2020-01", "2021-12"), ("2022-2023", "2022-01", "2023-12"), ("2024-2026", "2024-01", "2026-12")]
    print(f"\nREGIMES h 7-12, y/y RMSE (b): {pick} / S_M / E1 / E7 / F2 survey / naive")
    for name, lo, hi in regimes:
        g = df[(df.tp >= pd.Period(lo, "M")) & (df.tp <= pd.Period(hi, "M")) & (df.h >= 7)]
        g = g[g[[f"yy_b_{pick}", "yy_b_S_M", "yy_b_E1_ML", "yy_b_E7", "yy_b_F2_D1_fixed", "yy_b_naive", "real_yy"]].notna().all(axis=1)]
        if len(g):
            print(f"  {name} n={len(g):3d}: {rmse(g[f'yy_b_{pick}'] - g.real_yy):.2f} / {rmse(g.yy_b_S_M - g.real_yy):.2f} / {rmse(g.yy_b_E1_ML - g.real_yy):.2f} / {rmse(g.yy_b_E7 - g.real_yy):.2f} / {rmse(g.yy_b_F2_D1_fixed - g.real_yy):.2f} / {rmse(g.yy_b_naive - g.real_yy):.2f}")
    adopt = eligible and safeguard
    print(f"\nRULES: target line: {pick} {lpick:.3f} vs E7 {lE7:.3f} -> {(pick + ' replaces E7') if (adopt and lpick < lE7) else 'E7 stays'}")
    print(f"  second line: {pick} {lpick:.3f} vs F2 survey {lF2:.3f} ({100*(lpick/lF2-1):+.1f}%) -> {(pick + ' replaces F2') if (adopt and lpick <= 0.97 * lF2) else 'F2 stays'}")
    hk = pick + "_H"; comp = df.op >= COMP0
    parts, pub = [], True
    for h in (3, 6, 12):
        gg = df[comp & (df.h == h)]; gg = gg[gg[[f"yy_b_{hk}", "yy_b_naive", "yy_rw", "real_yy"]].notna().all(axis=1)]
        e = (gg[f"yy_b_{hk}"] - gg.real_yy) ** 2; en = (gg.yy_b_naive - gg.real_yy) ** 2; er = (gg.yy_rw - gg.real_yy) ** 2
        gain = 100 * (1 - np.sqrt(e.mean() / en.mean())); d = (e - en).values; dm1, dm12 = dm_stat(d, max(h - 1, 0)), dm_stat(d, 12)
        cond = gain >= 10 and dm1 < 0 and dm12 < 0 and (np.sqrt(e.mean()) < np.sqrt(er.mean()) if h in (6, 12) else True); pub &= cond
        parts.append(f"h{h} {gain:+.1f}% DM {dm1:+.2f}/{dm12:+.2f}")
    gg = df[comp & (df.h == 12)]; gg = gg[gg[[f"yy_b_{hk}", "yy_b_F1b", "real_yy"]].notna().all(axis=1)]; first = gg.op < SPLIT
    gf = 100 * (1 - rmse(gg[f"yy_b_{hk}"] - gg.real_yy) / rmse(gg.yy_b_F1b - gg.real_yy)); g1 = 100 * (1 - rmse(gg[first][f"yy_b_{hk}"] - gg[first].real_yy) / rmse(gg[first].yy_b_F1b - gg[first].real_yy)); g2 = 100 * (1 - rmse(gg[~first][f"yy_b_{hk}"] - gg[~first].real_yy) / rmse(gg[~first].yy_b_F1b - gg[~first].real_yy))
    print(f"  product engine ({hk}): publish rule {' | '.join(parts)} -> {'PUBLISHABLE' if pub else 'not publishable'}; vs F1b at h=12: full {gf:+.1f}% first half {g1:+.1f}% second half {g2:+.1f}% -> {(hk + ' replaces F1b') if (adopt and pub and gf >= 5 and g1 >= 5 and g2 >= 5) else 'F1b stays'}")
    pd.DataFrame(summ).to_csv(os.path.join(HERE, "output", "path_step5_summary.csv"), index=False)
    print(f"\nselected: {pick}; eligible {eligible}; safeguard {safeguard}")


if __name__ == "__main__":
    main()
