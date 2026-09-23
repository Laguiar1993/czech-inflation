"""PATH_SPEC_v4, single run: robust seasonal, proper lags, wages (Eurostat
labour cost index), import prices if obtainable; target-anchored survey-free
variants against the step-2/3 columns.
Usage: python path_step4_backtest.py
Writes output/path_step4.csv, output/path_step4_params.csv, output/path_step4_summary.csv,
data/eurostat_lci_cz_quarterly.csv (cache).
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
from path_experiment import _eve, lg, pct, rmse, dm_stat, load_fmie_1y  # noqa: E402
from path_step2_backtest import load_drivers  # noqa: E402

START = pd.Period("1998-01", "M")
ORIGIN0, ORIGIN_SEL_END, COMP0, SPLIT = pd.Period("2008-01", "M"), pd.Period("2018-12", "M"), pd.Period("2019-02", "M"), pd.Period("2023-01", "M")
H = list(range(1, 13))
DRIVERS = {"E1R": [], "E4": ["un_d", "fx_yoy_l3", "rr_gap12"], "E5": ["un_d", "fx_yoy_l3", "rr_gap18"], "E6": ["un_d", "fx_yoy_l3", "rr_gap12", "wage_yoy"],
           "E7": ["un_d", "fx_yoy_l3", "rr_gap12", "imp_mm"]}
EXPECTED_SIGN = {"un_d": -1, "fx_yoy_l3": +1, "rr_gap12": -1, "rr_gap18": -1, "wage_yoy": +1, "imp_mm": +1}
LCI_CACHE = os.path.join(HERE, "data", "eurostat_lci_cz_quarterly.csv")
IMP_CACHE = os.path.join(HERE, "data", "czso_import_prices_sitc_monthly.csv")


def eurostat_json(ds, params):
    import requests
    url = f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{ds}?" + "&".join(f"{k}={v}" for k, v in params.items())
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
    if r.status_code != 200:
        return None
    j = r.json(); t = j["dimension"]["time"]["category"]["index"]; inv = {v: k for k, v in t.items()}
    return pd.Series({inv[int(k)]: float(v) for k, v in j["value"].items()}).sort_index()


def load_lci() -> pd.Series:
    """Wages and salaries labour cost index, whole economy, NSA, quarterly; y/y growth used from quarter end + 3 months."""
    if os.path.exists(LCI_CACHE):
        c = pd.read_csv(LCI_CACHE); s = pd.Series(c.value.values, index=pd.PeriodIndex(c.quarter, freq="Q"))
    else:
        s = eurostat_json("lc_lci_r2_q", {"geo": "CZ", "lcstruct": "D11", "nace_r2": "B-S", "s_adj": "NSA", "unit": "I20", "sinceTimePeriod": "2000-Q1"})
        if s is None:
            return pd.Series(dtype=float)
        s.index = pd.PeriodIndex([k.replace("-", "") for k in s.index], freq="Q")
        pd.DataFrame({"quarter": [str(q) for q in s.index], "value": s.values}).to_csv(LCI_CACHE, index=False)
    yoy = 100 * (s / s.shift(4) - 1)
    out = {}
    for q, v in yoy.dropna().items():
        e = q.asfreq("M", "e")
        for k in range(3, 6):                      # available from e+3, holds until the next quarter's value takes over
            out[e + k] = v
    return pd.Series(out).sort_index()


def load_import_prices() -> pd.Series:
    """CZSO import price index, total, SITC set CEN0303 (not FX-adjusted), monthly m/m
    (index minus 100, percent), 2008-01 onward (amendment 2). Indexed by the month the
    value refers to; the availability shift (+1 month) is applied by the caller."""
    if os.path.exists(IMP_CACHE):
        c = pd.read_csv(IMP_CACHE); return pd.Series(c.value.values, index=pd.PeriodIndex(c.month, freq="M"))
    import io
    import requests
    r = requests.get("https://data.csu.gov.cz/opendata/sady/CEN0303/distribuce/csv", headers={"User-Agent": "Mozilla/5.0"}, timeout=300)
    if r.status_code != 200:
        return pd.Series(dtype=float)
    df = pd.read_csv(io.BytesIO(r.content), encoding="utf-8", low_memory=False)
    tcol = [c for c in df.columns if c.upper().startswith("CAS")][0]
    typ = [c for c in df.columns if c.upper().startswith("TYPUDAJE")][0]
    cls = [c for c in df.columns if "." in c]                      # classification code columns (section, division)
    d = df[df["Ukazatel"].str.contains("dovozních", na=False) & (df[typ] == "IM") & df[tcol].astype(str).str.match(r"^\d{4}-\d{2}$")]
    if len(cls) >= 2:
        d = d[d[cls[1]].isna()]                                     # total: no division code
    tot_code = d[cls[0]].value_counts().index[0] if len(cls) else None
    if tot_code is not None:
        d = d[d[cls[0]] == tot_code]
    d = d.drop_duplicates(tcol).sort_values(tcol)
    s = pd.Series(d["Hodnota"].astype(float).values - 100.0, index=pd.PeriodIndex(d[tcol].astype(str), freq="M"))
    pd.DataFrame({"month": [str(m) for m in s.index], "value": s.values, "source": "CZSO CEN0303 SITC total, Index dovozních cen, IM"}).to_csv(IMP_CACHE, index=False)
    return s


def main():
    y_ext = la.load_headline_cpi_mm_extended(); y_ext = y_ext[y_ext.index >= START].dropna()
    drv = load_drivers()
    con = la._con()
    pr = con.sql("SELECT period, value, snapshot_id FROM monetary.arad_data WHERE indicator_id='SFTP04M2206' ORDER BY period, snapshot_id").df().drop_duplicates("period", keep="last")
    fx = con.sql("SELECT year, month, czk_per_unit FROM monetary.fx_monthly WHERE currency_code='EUR' ORDER BY 1,2").df()
    con.close()
    pribor = pd.Series(pr.value.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(pr.period), freq="M"))
    fxs = pd.Series(fx.czk_per_unit.astype(float).values, index=pd.PeriodIndex(pd.to_datetime(dict(year=fx.year, month=fx.month, day=1)), freq="M"))
    ylog = pd.Series(np.asarray(lg(y_ext)), index=y_ext.index)
    yoy = pd.Series({m: pct(float(ylog.loc[m - 11:m].sum())) for m in y_ext.index if (m - 11) in y_ext.index})
    lci = load_lci(); imp = load_import_prices()
    imp_available = len(imp) > 0
    print(f"wages (LCI) months {lci.index.min() if len(lci) else None}..{lci.index.max() if len(lci) else None}; import prices available: {imp_available}" + (f" {imp.index.min()}..{imp.index.max()}" if imp_available else ""))
    X_all = pd.DataFrame({"un_d": drv["un_d"], "fx_yoy_l3": (100 * (fxs / fxs.shift(12) - 1)).shift(3), "rr_gap12": (pribor - yoy).shift(12),
                          "rr_gap18": (pribor - yoy).shift(18), "wage_yoy": lci, "imp_mm": imp.shift(1) if imp_available else np.nan})    # month s row carries month s-1 (public mid s+1)
    variants = ["E1R", "E4", "E5", "E6"] + (["E7"] if imp_available else [])
    s3 = pd.read_csv(os.path.join(HERE, "output", "path_step3.csv")); s3["op"] = pd.PeriodIndex(s3["origin"], freq="M")
    fmie = load_fmie_1y()
    origins = sorted(s3.op.unique()); last_real = y_ext.index.max()
    rows, diag = [], []
    for i, t in enumerate(origins):
        as_of = _eve(t)
        yh = y_ext[y_ext.index <= t - 1]; yh = yh[S._released_index(yh.index, as_of)]
        if len(yh) < 96 or yh.index.max() != t - 1:
            continue
        X = X_all[X_all.index <= t - 1].reindex(yh.index).fillna(0.0)
        fits = {v: fit_forecast(yh, range(1, 14), x_hist=(X[DRIVERS[v]] if DRIVERS[v] else None), anchored=True, robust_seasonal=True) for v in variants}
        mh = fmie[fmie.index <= t - 1] if fmie is not None else None
        fits["F2R"] = fit_forecast(yh, range(1, 14), m_hist=mh, fixed_snr=True, robust_seasonal=True)
        for k, f in fits.items():
            d = {"origin": str(t), "variant": k, "rho": f.get("rho", np.nan), "phi": f.get("phi", np.nan), "converged": f.get("converged", False)}
            for j, c in enumerate(DRIVERS.get(k, [])):
                d[f"gamma_{c}"] = (f.get("gamma") or [np.nan] * len(DRIVERS[k]))[j]
            diag.append(d)
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
    df = pd.DataFrame(rows).merge(s3, on=["origin", "h", "target"], how="inner")
    df["op"] = pd.PeriodIndex(df["origin"], freq="M"); df["tp"] = pd.PeriodIndex(df["target"], freq="M")
    NEW = variants + ["F2R"]
    out = []
    for t, g in df.groupby("op"):
        g = g.sort_values("h"); known = ylog[ylog.index <= t - 1]
        h0r, h0m = float(g.h0_real.iloc[0]), float(g.h0_model.iloc[0])
        mm = {k: dict(zip(g.tp, g[f"mm_{k}"])) for k in NEW}
        for _, r in g.iterrows():
            window = pd.period_range(r.tp - 11, r.tp, freq="M")
            base = float(known.reindex([m for m in window if m <= t - 1]).sum()); fut = [m for m in window if m >= t]
            rec = {"origin": str(t), "h": int(r.h)}
            for k in NEW:
                pb = {t: h0r}; pb.update(mm[k]); rec[f"yy_b_{k}"] = pct(base + sum(lg([pb[m]])[0] for m in fut))
                if np.isfinite(h0m):
                    pa = {t: h0m}; pa.update(mm[k]); rec[f"yy_a_{k}"] = pct(base + sum(lg([pa[m]])[0] for m in fut))
                else:
                    rec[f"yy_a_{k}"] = np.nan
            out.append(rec)
    df = df.merge(pd.DataFrame(out), on=["origin", "h"], how="left")
    df.to_csv(os.path.join(HERE, "output", "path_step4.csv"), index=False)
    dg = pd.DataFrame(diag); dg.to_csv(os.path.join(HERE, "output", "path_step4_params.csv"), index=False)
    pd.set_option("display.width", 250)
    print("\nESTIMATED PARAMETERS (mean over origins; share with the expected sign):")
    elig = {}
    for k in NEW:
        g = dg[dg.variant == k]; parts = [f"rho {g.rho.mean():.3f}", f"phi {g.phi.mean():.2f}", f"converged {g.converged.mean():.2f}"]; ok = True
        for c in DRIVERS.get(k, []):
            v = g[f"gamma_{c}"]; share = float((np.sign(v) == EXPECTED_SIGN[c]).mean()); ok &= share >= 0.5
            parts.append(f"gamma_{c} {v.mean():+.4f} (sign ok {share:.2f})")
        elig[k] = ok
        print(f"  {k}: " + " | ".join(parts) + ("" if k == "F2R" else f" -> {'eligible' if ok else 'NOT eligible (signs)'}"))
    sel = df[(df.op <= ORIGIN_SEL_END) & (df.h == 12)]; sel = sel[sel[[f"yy_b_{k}" for k in NEW] + ["yy_b_E1_ML", "yy_b_F2_D1_fixed", "real_yy"]].notna().all(axis=1)]
    scores = {k: rmse(sel[f"yy_b_{k}"] - sel.real_yy) for k in variants}
    cands = [k for k in variants if elig[k]]
    pick = min(cands, key=scores.get) if cands else None
    print(f"\nSELECTION (origins 2008-01..2018-12, h=12, n={len(sel)}): " + ", ".join(f"{k} {v:.3f}{'' if elig[k] else ' (ineligible)'}" for k, v in scores.items())
          + f" | E1 (step 3) {rmse(sel.yy_b_E1_ML - sel.real_yy):.3f} | F2 survey {rmse(sel.yy_b_F2_D1_fixed - sel.real_yy):.3f} | F2R survey robust {rmse(sel.yy_b_F2R - sel.real_yy):.3f} -> {pick}")
    if pick is None:
        pick = "E1R"
    df["yy_b_E"] = df[f"yy_b_{pick}"]; df["yy_a_E"] = df[f"yy_a_{pick}"]
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
    table(df.op >= ORIGIN0, variants + ["E1_ML", "F2_D1_fixed", "F2R"], "LONG SPAN 2008-01..2026-07")
    table(df.op >= COMP0, ["F1b", "F2_D1_fixed", "F2R", "E1_ML", "E"], "COMPONENT SPAN 2019-02..2026-07 (b)")
    table(df.op >= COMP0, ["F1b", "F2_D1_fixed", "F2R", "E1_ML", "E"], "COMPONENT SPAN 2019-02..2026-07 (a)", obj="a")
    regimes = [("2008-2009", "2008-01", "2009-12"), ("2010-2012", "2010-01", "2012-12"), ("2013-2016", "2013-01", "2016-12"), ("2017-2019", "2017-01", "2019-12"),
               ("2020-2021", "2020-01", "2021-12"), ("2022-2023", "2022-01", "2023-12"), ("2024-2026", "2024-01", "2026-12")]
    print(f"\nREGIMES h 7-12, y/y RMSE (b): {pick} / E1 / F2 survey / F2R / naive")
    for name, lo, hi in regimes:
        g = df[(df.tp >= pd.Period(lo, "M")) & (df.tp <= pd.Period(hi, "M")) & (df.h >= 7)]
        g = g[g[["yy_b_E", "yy_b_E1_ML", "yy_b_F2_D1_fixed", "yy_b_F2R", "yy_b_naive", "real_yy"]].notna().all(axis=1)]
        if len(g):
            print(f"  {name} n={len(g):3d}: {rmse(g.yy_b_E - g.real_yy):.2f} / {rmse(g.yy_b_E1_ML - g.real_yy):.2f} / {rmse(g.yy_b_F2_D1_fixed - g.real_yy):.2f} / {rmse(g.yy_b_F2R - g.real_yy):.2f} / {rmse(g.yy_b_naive - g.real_yy):.2f}")
    # rules
    g = df[(df.op >= ORIGIN0) & (df.h == 12)]; g = g[g[["yy_b_E", "yy_b_E1R", "yy_b_E1_ML", "yy_b_F2_D1_fixed", "yy_b_F2R", "real_yy"]].notna().all(axis=1)]
    rF, rFR, rE, rE1R, rE1 = (rmse(g.yy_b_F2_D1_fixed - g.real_yy), rmse(g.yy_b_F2R - g.real_yy), rmse(g.yy_b_E - g.real_yy), rmse(g.yy_b_E1R - g.real_yy), rmse(g.yy_b_E1_ML - g.real_yy))
    print(f"\nRULES (long span h=12, n={len(g)}): F2 survey {rF:.3f} vs F2R {rFR:.3f} ({100*(rFR/rF-1):+.1f}%) -> {'F2R becomes the scored second line' if rFR <= 0.97 * rF else 'F2 (mean seasonal) stays the second line'}")
    tl = pick if elig.get(pick, False) and pick in variants else ("E1R" if rE1R < rE1 else "E1_ML")
    print(f"  target line: selected {pick} {rE:.3f} (eligible {elig.get(pick)}), E1R {rE1R:.3f}, E1 {rE1:.3f} -> target line = {tl}")
    comp = df.op >= COMP0
    parts, pub = [], True
    for h in (3, 6, 12):
        gg = df[comp & (df.h == h)]; gg = gg[gg[["yy_b_E", "yy_b_naive", "yy_rw", "real_yy"]].notna().all(axis=1)]
        e = (gg.yy_b_E - gg.real_yy) ** 2; en = (gg.yy_b_naive - gg.real_yy) ** 2; er = (gg.yy_rw - gg.real_yy) ** 2
        gain = 100 * (1 - np.sqrt(e.mean() / en.mean())); d = (e - en).values; dm1, dm12 = dm_stat(d, max(h - 1, 0)), dm_stat(d, 12)
        cond = gain >= 10 and dm1 < 0 and dm12 < 0 and (np.sqrt(e.mean()) < np.sqrt(er.mean()) if h in (6, 12) else True); pub &= cond
        parts.append(f"h{h} {gain:+.1f}% DM {dm1:+.2f}/{dm12:+.2f}")
    gg = df[comp & (df.h == 12)]; gg = gg[gg[["yy_b_E", "yy_b_F1b", "real_yy"]].notna().all(axis=1)]; first = gg.op < SPLIT
    gf = 100 * (1 - rmse(gg.yy_b_E - gg.real_yy) / rmse(gg.yy_b_F1b - gg.real_yy)); g1 = 100 * (1 - rmse(gg[first].yy_b_E - gg[first].real_yy) / rmse(gg[first].yy_b_F1b - gg[first].real_yy)); g2 = 100 * (1 - rmse(gg[~first].yy_b_E - gg[~first].real_yy) / rmse(gg[~first].yy_b_F1b - gg[~first].real_yy))
    print(f"  publish rule for {pick}: {' | '.join(parts)} -> {'PUBLISHABLE' if pub else 'not publishable'}; vs F1b at h=12: full {gf:+.1f}% first half {g1:+.1f}% second half {g2:+.1f}% -> {'replaces F1b' if (gf >= 5 and g1 >= 5 and g2 >= 5 and pub) else 'F1b stays the product engine'}")
    pd.DataFrame(summ).to_csv(os.path.join(HERE, "output", "path_step4_summary.csv"), index=False)
    print(f"\nselected: {pick}; target line: {tl}; second line: {'F2R' if rFR <= 0.97 * rF else 'F2_D1_fixed'}")


if __name__ == "__main__":
    main()
