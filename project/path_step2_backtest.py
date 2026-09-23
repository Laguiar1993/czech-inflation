"""PATH_SPEC_v2 (with amendments 1 and 2), single run: the three families
backtested as year-on-year paths at h = 1..12, object (b) h0 = the print
(primary) over origins 2008-01..2026-07 and object (a) h0 = the frozen
nowcast over 2019-02..2026-07; benchmarks; publish rule.
  F1a = step-1 engine (P0 of the horizon backtest), F1b = plain frame at
        every horizon + food seasonal mean from h = 4 (from the horizon
        backtest rows; the blocks are additive);
  F2   = trend-and-gap state space (models/trend_gap.py): D1-ML, D1-fixed,
        D1-noFMIE (control), D2-ML, D2-fixed;
  F3   = Minnesota BVAR (models/bvar.py), direct h-step.
Usage: python path_step2_backtest.py
Writes output/path_step2.csv (origin x h rows), output/path_step2_summary.csv,
output/path_step2_rule.csv.
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
from models.trend_gap import fit_forecast, seasonal_means  # noqa: E402
from models.bvar import minnesota_bvar_forecast  # noqa: E402
from path_experiment import _eve, naive_mm, lg, pct, rmse, dm_stat, load_fmie_1y  # noqa: E402

START = pd.Period("1998-01", "M")
ORIGIN0, ORIGIN_SEL_END, COMP0 = pd.Period("2008-01", "M"), pd.Period("2018-12", "M"), pd.Period("2019-02", "M")
F3_ORIGIN0 = pd.Period("2013-01", "M")
H = list(range(1, 13))
F2V = ["F2_D1_ML", "F2_D1_fixed", "F2_D1_noFMIE", "F2_D2_ML", "F2_D2_fixed"]
FAMS_ALL = ["F1a", "F1b"] + F2V + ["F3", "naive"]
BOOT_DRAWS, BLOCK = 1000, 12


def load_drivers():
    con = la._con()
    fx = con.sql("SELECT year, month, czk_per_unit FROM monetary.fx_monthly WHERE currency_code='EUR' ORDER BY 1,2").df()
    fx = pd.Series(fx.czk_per_unit.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(dict(year=fx.year, month=fx.month, day=1)), freq="M"))
    fx_mm = 100 * fx.pct_change()
    un = con.sql("SELECT data_month, rate_pct FROM czso.unemployment_ri WHERE series='unemployment' AND adjusted='trend_cycle' AND gender='total' ORDER BY 1").df()
    un = pd.Series(un.rate_pct.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(un.data_month), freq="M"))
    un_d = un.diff().shift(1)                      # publication lag: the LFS month is public about a month later
    esi = con.sql("SELECT year, month, value FROM eurostat.bcs_survey WHERE indic_code='BS-ESI-I' ORDER BY 1,2").df()
    esi = pd.Series(esi.value.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(dict(year=esi.year, month=esi.month, day=1)), freq="M"))
    pr = con.sql("SELECT period, value, snapshot_id FROM monetary.arad_data WHERE indicator_id='SFTP04M2206' ORDER BY period, snapshot_id").df()
    con.close()
    pr = pr.drop_duplicates("period", keep="last")
    pribor = pd.Series(pr.value.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(pr.period), freq="M"))
    return {"fx_mm": fx_mm, "un_d": un_d, "esi": esi, "pribor_d": pribor.diff()}


def main():
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    y_ext = la.load_headline_cpi_mm_extended(); y_ext = y_ext[y_ext.index >= START].dropna()
    core = core.dropna()
    fmie = load_fmie_1y()
    drv = load_drivers()
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period"); bt.index = pd.PeriodIndex(bt.index, freq="M")
    hb = pd.read_csv(os.path.join(HERE, "output", "path_backtest_h.csv")); hb["op"] = pd.PeriodIndex(hb["origin"], freq="M")
    hb["mm_F1a"] = hb["mm_P0"]; hb["mm_F1b"] = hb["mm_P1"] + (hb["mm_P7"] - hb["mm_P0"])
    f1 = hb.set_index(["op", "h"])[["mm_F1a", "mm_F1b"]]
    last_real = y_ext.index.max()
    origins = [p for p in pd.period_range(ORIGIN0, last_real, freq="M")]
    rows = []
    for i, t in enumerate(origins):
        as_of = _eve(t)
        yh = y_ext[y_ext.index <= t - 1]; yh = yh[S._released_index(yh.index, as_of)]
        if len(yh) < 96 or yh.index.max() != t - 1:
            continue
        mh = fmie[fmie.index <= t - 1] if fmie is not None else None
        X2 = pd.DataFrame({"fx_mm": drv["fx_mm"], "un_d": drv["un_d"], "esi_dev": drv["esi"] - drv["esi"][drv["esi"].index <= t - 1].mean()})
        X2 = X2[X2.index <= t - 1].reindex(yh.index).fillna(0.0)
        # the history ends at t-1 and the path's h counts from the nowcast month t: the forecast for
        # target t+h is the model's (h+1)-step-ahead forecast (the first run mislabelled this by one month)
        H1 = range(1, 14)
        f2 = {"F2_D1_ML": fit_forecast(yh, H1, m_hist=mh), "F2_D1_fixed": fit_forecast(yh, H1, m_hist=mh, fixed_snr=True),
              "F2_D1_noFMIE": fit_forecast(yh, H1), "F2_D2_ML": fit_forecast(yh, H1, m_hist=mh, x_hist=X2),
              "F2_D2_fixed": fit_forecast(yh, H1, m_hist=mh, x_hist=X2, fixed_snr=True)}
        # F3 panel through t-1 (released), deseasonalised headline and core with the same expanding means
        f3 = {h: np.nan for h in H}
        if t >= F3_ORIGIN0:
            ch = core[core.index <= t - 1]; ch = ch[S._released_index(ch.index, as_of)]
            sy, sc = seasonal_means(yh), seasonal_means(ch)
            panel = pd.DataFrame({"y_sa": yh - np.array([sy[p.month] for p in yh.index]),
                                  "core_sa": ch - np.array([sc[p.month] for p in ch.index]),
                                  "fx_mm": drv["fx_mm"], "esi": drv["esi"], "pribor_d": drv["pribor_d"], "un_d": drv["un_d"]})
            panel = panel[(panel.index <= t - 1) & (panel.index >= core.index.min())].dropna()
            if len(panel) >= 74:
                for h in H:
                    try:
                        f3[h] = minnesota_bvar_forecast(panel, "y_sa", h + 1, p=3, lambda1=0.2, delta={"esi": 1.0}) + sy[(t + h).month]
                    except Exception:  # noqa: BLE001
                        f3[h] = np.nan
        nv = {h: naive_mm(yh, t + h) for h in H}
        for h in H:
            tgt = t + h
            if tgt > last_real:
                continue
            r = {"origin": str(t), "h": h, "target": str(tgt), "mm_real": float(y_ext.get(tgt, np.nan)), "mm_naive": nv[h], "mm_F3": f3[h],
                 "h0_real": float(y_ext.get(t, np.nan)), "h0_model": float(bt["STRUCT_EVE"].get(t, np.nan)) if t in bt.index else np.nan}
            for k in F2V:
                r[f"mm_{k}"] = f2[k]["mm"].get(h + 1, np.nan)
            r["f2_level"] = f2["F2_D1_ML"].get("level", np.nan); r["f2_phi"] = f2["F2_D1_ML"].get("phi", np.nan); r["f2_bias_m"] = f2["F2_D1_ML"].get("bias_m", np.nan)
            for k in ("F1a", "F1b"):
                r[f"mm_{k}"] = float(f1.loc[(t, h), f"mm_{k}"]) if (t, h) in f1.index else np.nan
            rows.append(r)
        if i % 24 == 0:
            print(f"origin {t} done ({i + 1}/{len(origins)})", flush=True)
    df = pd.DataFrame(rows)
    df["tp"] = pd.PeriodIndex(df["target"], freq="M"); df["op"] = pd.PeriodIndex(df["origin"], freq="M")
    # ---- y/y paths, exact percent ----
    ylog = pd.Series(np.asarray(lg(y_ext)), index=y_ext.index)
    out = []
    for t, g in df.groupby("op"):
        g = g.sort_values("h"); known = ylog[ylog.index <= t - 1]
        mm = {k: dict(zip(g.tp, g[f"mm_{k}"])) for k in FAMS_ALL}
        h0r, h0m = float(g.h0_real.iloc[0]), float(g.h0_model.iloc[0])
        for _, r in g.iterrows():
            tgt = r.tp; window = pd.period_range(tgt - 11, tgt, freq="M")
            base = float(known.reindex([m for m in window if m <= t - 1]).sum())
            fut = [m for m in window if m >= t]
            rec = {"origin": str(t), "h": int(r.h), "real_yy": pct(base + float(ylog.reindex(fut).sum()))}
            for k in FAMS_ALL:
                path_b = {t: h0r}; path_b.update(mm[k])
                rec[f"yy_b_{k}"] = pct(base + sum(lg([path_b[m]])[0] for m in fut))
                if np.isfinite(h0m):
                    path_a = {t: h0m}; path_a.update(mm[k])
                    rec[f"yy_a_{k}"] = pct(base + sum(lg([path_a[m]])[0] for m in fut))
                else:
                    rec[f"yy_a_{k}"] = np.nan
            rec["yy_rw"] = pct(float(known.loc[t - 12:t - 1].sum())) if (t - 12) in known.index else np.nan
            rec["fmie_1y"] = float(fmie[fmie.index <= t].iloc[-1]) if (fmie is not None and len(fmie[fmie.index <= t])) else np.nan
            out.append(rec)
    df = df.merge(pd.DataFrame(out), on=["origin", "h"], how="left")
    df.to_csv(os.path.join(HERE, "output", "path_step2.csv"), index=False)

    # ---- F2 variant selection on 2008-01..2018-12 origins (h = 12, object b) ----
    sel = df[(df.op <= ORIGIN_SEL_END) & (df.h == 12)]
    okv = sel[[f"yy_b_{k}" for k in F2V] + ["real_yy"]].notna().all(axis=1); sel = sel[okv]
    scores = {k: rmse(sel[f"yy_b_{k}"] - sel.real_yy) for k in F2V}
    f2_pick = min(scores, key=scores.get)
    print("\nF2 VARIANT SELECTION (origins 2008-01..2018-12, h=12, y/y RMSE, n=%d): " % len(sel) + ", ".join(f"{k} {v:.3f}" for k, v in scores.items()) + f" -> {f2_pick}")
    df["yy_b_F2"] = df[f"yy_b_{f2_pick}"]; df["yy_a_F2"] = df[f"yy_a_{f2_pick}"]; df["mm_F2"] = df[f"mm_{f2_pick}"]

    pd.set_option("display.width", 250)
    summ = []

    def table(span_mask, fams, label, obj="b"):
        print(f"\n{label}: y/y RMSE ({obj}) by horizon on the common sample | naive | RW")
        for h in (1, 3, 6, 9, 12):
            g = df[span_mask & (df.h == h)]
            cols = [f"yy_{obj}_{k}" for k in fams] + ["yy_b_naive", "yy_rw", "real_yy"]
            g = g[g[cols].notna().all(axis=1)]
            rec = {"table": label, "obj": obj, "h": h, "n": len(g), "naive": rmse(g.yy_b_naive - g.real_yy), "rw": rmse(g.yy_rw - g.real_yy)}
            for k in fams:
                rec[k] = rmse(g[f"yy_{obj}_{k}"] - g.real_yy); rec[f"bias_{k}"] = float((g[f"yy_{obj}_{k}"] - g.real_yy).mean())
            summ.append(rec)
            print(f"  h={h:2d} n={len(g):3d} | " + " ".join(f"{k} {rec[k]:.3f} (bias {rec[f'bias_{k}']:+.2f})" for k in fams) + f" | naive {rec['naive']:.3f} | RW {rec['rw']:.3f}")

    long_mask = df.op >= ORIGIN0
    table(long_mask, F2V, "LONG SPAN origins 2008-01..2026-07, F2 variants")
    table(df.op >= F3_ORIGIN0, ["F2", "F3"], "LONG SPAN origins 2013-01..2026-07, F2 (selected) vs F3")
    comp_mask = df.op >= COMP0
    table(comp_mask, ["F1a", "F1b", "F2", "F3"], "COMPONENT SPAN origins 2019-02..2026-07 (b: h0 = print)")
    table(comp_mask, ["F1a", "F1b", "F2", "F3"], "COMPONENT SPAN origins 2019-02..2026-07 (a: h0 = nowcast)", obj="a")
    # regimes on the long span, F2 vs naive vs RW, h groups
    regimes = [("2008-2009", "2008-01", "2009-12"), ("2010-2012", "2010-01", "2012-12"), ("2013-2016", "2013-01", "2016-12"), ("2017-2019", "2017-01", "2019-12"),
               ("2020-2021", "2020-01", "2021-12"), ("2022-2023", "2022-01", "2023-12"), ("2024-2026", "2024-01", "2026-12")]
    print("\nREGIMES of the target (long span), y/y RMSE (b): F2 / F3 / naive / RW and F2 bias, by horizon group")
    for name, lo, hi in regimes:
        for gname, (a, b) in {"1-3": (1, 3), "4-6": (4, 6), "7-12": (7, 12)}.items():
            g = df[(df.tp >= pd.Period(lo, "M")) & (df.tp <= pd.Period(hi, "M")) & (df.h >= a) & (df.h <= b)]
            g = g[g[["yy_b_F2", "yy_b_naive", "yy_rw", "real_yy"]].notna().all(axis=1)]
            if len(g) == 0:
                continue
            f3s = f"{rmse(g.yy_b_F3.dropna() - g.real_yy[g.yy_b_F3.notna()]):.2f}" if g.yy_b_F3.notna().sum() > 5 else "  -- "
            print(f"  {name} h {gname:4s} n={len(g):3d}: F2 {rmse(g.yy_b_F2 - g.real_yy):.2f} / F3 {f3s} / naive {rmse(g.yy_b_naive - g.real_yy):.2f} / RW {rmse(g.yy_rw - g.real_yy):.2f} | F2 bias {(g.yy_b_F2 - g.real_yy).mean():+.2f}")
    # FMIE at h=12 on the long span
    g = df[(df.h == 12) & df[["fmie_1y", "yy_b_F2", "yy_b_naive", "real_yy"]].notna().all(axis=1)]
    print(f"\nB4 FMIE at h=12 (long span, n={len(g)}): FMIE {rmse(g.fmie_1y - g.real_yy):.3f} | F2 {rmse(g.yy_b_F2 - g.real_yy):.3f} | naive {rmse(g.yy_b_naive - g.real_yy):.3f}; component span: "
          + (lambda gg: f"FMIE {rmse(gg.fmie_1y - gg.real_yy):.3f} | F2 {rmse(gg.yy_b_F2 - gg.real_yy):.3f} | F1a {rmse(gg.yy_b_F1a - gg.real_yy):.3f} (n={len(gg)})")(g[(g.op >= COMP0) & g.yy_b_F1a.notna()]))

    # ---- publish rule on the component span, object (b) ----
    rng = np.random.default_rng(20260908)

    def block_boot_p(d):
        """One-sided moving-block bootstrap p-value for H0: mean loss
        differential (model minus naive) >= 0. Centred draws of block means;
        p = share of centred draws at or below the observed mean."""
        d = np.asarray(d, dtype=float); n = len(d); nb = int(np.ceil(n / BLOCK)); m0 = d.mean()
        if m0 >= 0:
            return 1.0
        boots = []
        for _ in range(BOOT_DRAWS):
            starts = rng.integers(0, max(n - BLOCK, 1), size=nb)
            idx = np.concatenate([np.arange(s, s + BLOCK) for s in starts])[:n]
            boots.append(d[idx].mean())
        boots = np.array(boots) - m0
        return float(np.mean(boots <= m0))

    rule_rows = []
    print("\nPUBLISH RULE (component span 2019-02..2026-07, object b): beat naive by >=10% at h 3, 6, 12 AND RW at 6, 12; DM<0 at lag h-1 and 12; block-bootstrap p (block 12)")
    for k in ["F1a", "F1b", "F2", "F3"]:
        parts, ok_all = [], True
        for h in (3, 6, 12):
            g = df[comp_mask & (df.h == h)]; g = g[g[[f"yy_b_{k}", "yy_b_naive", "yy_rw", "real_yy"]].notna().all(axis=1)]
            e = (g[f"yy_b_{k}"] - g.real_yy) ** 2; en = (g.yy_b_naive - g.real_yy) ** 2; er = (g.yy_rw - g.real_yy) ** 2
            gain = 100 * (1 - np.sqrt(e.mean() / en.mean())); d = (e - en).values
            dm1, dm12 = dm_stat(d, max(h - 1, 0)), dm_stat(d, 12); pb = block_boot_p(d)
            beats_rw = np.sqrt(e.mean()) < np.sqrt(er.mean())
            cond = gain >= 10 and dm1 < 0 and dm12 < 0 and (beats_rw if h in (6, 12) else True)
            ok_all &= cond
            parts.append(f"h{h}: gain {gain:+.1f}% DM {dm1:+.2f}/{dm12:+.2f} boot p {pb:.2f} RW {'beat' if beats_rw else 'NOT beat'}")
            rule_rows.append({"family": k, "h": h, "n": len(g), "gain_vs_naive_pct": gain, "dm_lag_h1": dm1, "dm_lag_12": dm12, "boot_p": pb, "beats_rw": beats_rw, "passes": cond})
        print(f"  {k}: {' | '.join(parts)} -> {'PUBLISHABLE' if ok_all else 'not publishable'}")
    pd.DataFrame(rule_rows).to_csv(os.path.join(HERE, "output", "path_step2_rule.csv"), index=False)
    pd.DataFrame(summ).to_csv(os.path.join(HERE, "output", "path_step2_summary.csv"), index=False)
    # quarterly averages on the component span (b)
    print("\nQUARTERLY AVERAGES (component span, b): quarters fully inside h<=12; RMSE by quarters ahead: F1a / F1b / F2 / F3 / naive")
    qrows = []
    for t, g in df[comp_mask].groupby("op"):
        g = g.set_index("tp"); q0 = t.asfreq("Q")
        for k in range(1, 5):
            qq = q0 + k; months = list(pd.period_range(qq.asfreq("M", "s"), qq.asfreq("M", "e"), freq="M"))
            if all(m in g.index for m in months):
                qrows.append({"k": k, **{f: g.loc[months, f"yy_b_{f}"].mean() for f in ["F1a", "F1b", "F2", "F3", "naive"]}, "real": g.loc[months, "real_yy"].mean()})
    qd = pd.DataFrame(qrows)
    for k, g in qd.groupby("k"):
        g = g.dropna()
        print(f"  {k} ahead (n={len(g)}): " + " / ".join(f"{rmse(g[f] - g.real):.2f}" for f in ["F1a", "F1b", "F2", "F3", "naive"]))
    print(f"\nF2 selected variant: {f2_pick}; mean estimated level (m/m) over component-span origins {df[comp_mask].groupby('op').f2_level.first().mean():+.3f}, phi {df[comp_mask].groupby('op').f2_phi.first().mean():.2f}, survey bias term {df[comp_mask].groupby('op').f2_bias_m.first().mean():+.3f}")


if __name__ == "__main__":
    main()
