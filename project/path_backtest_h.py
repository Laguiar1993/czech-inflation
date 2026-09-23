"""PATH_BACKTEST_H_SPEC.md, single run: h = 1..12 diagnostics of the incumbent
path engine and seven declared candidates, frozen adoption rule.
Usage: python path_backtest_h.py
Writes output/path_backtest_h.csv (origin x h rows), output/path_backtest_h_summary.csv,
output/path_backtest_h_cnb.csv.
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
from data.struct_inputs import load_m3_yoy, load_housing_channel  # noqa: E402
from path_experiment import _eve, naive_mm, lg, pct, rmse, load_fmie_1y  # noqa: E402

H = list(range(1, 13))
CANDS = ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7"]
BLK = ("core", "food", "admin", "alc", "fuel", "wedge")
GROUPS = {"1-3": (1, 3), "4-6": (4, 6), "7-12": (7, 12)}
SPLIT = pd.Period("2023-01", "M")


def ridge_variant(Xdf, ydf, origin, h, as_of, window=None, local_level=False, alpha=S.RIDGE_ALPHA):
    """_ridge_predict's data handling with a rolling window and/or a local-level target."""
    y = ydf.copy()
    anchor = None
    if local_level:
        anchor = ydf.rolling(12).mean().shift(1)          # mean of the 12 months before u, known at u (u-1 released)
        y = ydf - 0                                        # placeholder; the transformed target is built below
    ys_full = ydf.shift(-h)                                 # y(u+h) indexed at u
    if local_level:
        ys_full = ys_full - anchor
    train_idx = ys_full.dropna().index
    train_idx = train_idx[train_idx <= origin - 1 - h]
    if as_of is not None and not pd.isna(as_of):
        train_idx = train_idx[[S._cpi_family_released_by(u + h, as_of) for u in train_idx]]
    if window is not None:
        train_idx = train_idx[-window:]
    if len(train_idx) < 48 or origin not in Xdf.index:
        return np.nan
    Xt = Xdf.loc[train_idx]; mu = Xt.mean(); Xt = Xt.fillna(mu)
    xrow = Xdf.loc[[origin]].fillna(mu)
    ys = ys_full.loc[train_idx].values
    m, s = Xt.mean().values, Xt.std().replace(0, 1.0).values
    Z = (Xt.values - m) / s; z0 = (xrow.values - m) / s
    beta = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (ys - ys.mean()))
    pred = float(ys.mean() + (z0 @ beta)[0])
    if local_level:
        a0 = anchor.get(origin, np.nan)
        if not np.isfinite(a0):
            # the anchor at the origin uses core through origin-1 (released at the release-eve clock)
            hist = ydf.dropna(); hist = hist[hist.index <= origin - 1]
            a0 = float(hist.tail(12).mean())
        pred += float(a0)
    return pred


def main():
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    alc = S.load_alc_tobacco_mm()
    slow = pd.concat([load_m3_yoy(), load_housing_channel()], axis=1)
    feats_slow = pd.concat([feats, slow.reindex(feats.index)], axis=1)
    fuel_official = comp["fuel"].dropna()
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period"); bt.index = pd.PeriodIndex(bt.index, freq="M")
    origins = list(bt.index)
    yk = y.dropna(); last_real = yk.index.max()
    fmie = load_fmie_1y()
    act_series = {"core": core.dropna(), "food": comp["food"].dropna(), "admin": reg.dropna(), "alc": alc.dropna(), "fuel": fuel_official}
    rows = []
    for t in origins:
        as_of = _eve(t)
        y_known = yk[yk.index <= t - 1]; y_known = y_known[S._released_index(y_known.index, as_of)]
        wmap = S.solve_weights(y, comp, core, reg, t - 1, as_of=as_of, alc=alc); wt = wmap[S._regime(t)]
        wedge_tv = S._weighted_wedge(y, comp, alc, core, reg, wedge, wmap, as_of=as_of)
        # FMIE drift and long-run seasonal deviations (released headline history)
        f_ok = fmie[fmie.index <= t] if fmie is not None else None
        drift = 100 * ((1 + float(f_ok.iloc[-1]) / 100) ** (1 / 12) - 1) if (f_ok is not None and len(f_ok)) else np.nan
        seas_dev = {m: float(y_known[y_known.index.month == m].mean() - y_known.mean()) for m in range(1, 13)}
        food_hist = comp["food"].dropna(); food_hist = food_hist[food_hist.index <= t - 1]; food_hist = food_hist[S._released_index(food_hist.index, as_of)]
        for h in H:
            tgt = t + h
            if tgt > last_real:
                continue
            frame0 = feats if h <= 3 else feats_slow
            wh = wmap.get(S._regime(tgt), wt)
            c = {"P0": S._ridge_predict(frame0, core, t, h=h, as_of=as_of)[0],
                 "P1": S._ridge_predict(feats, core, t, h=h, as_of=as_of)[0],
                 "P2": S._ridge_predict(feats_slow, core, t, h=h, as_of=as_of)[0],
                 "P3": ridge_variant(frame0, core, t, h, as_of, window=120),
                 "P4": ridge_variant(frame0, core, t, h, as_of, local_level=True)}
            food_h = S.food_forecast(comp["food"], food_feats, t, h=h, as_of=as_of)
            fm_ = food_hist[food_hist.index.month == tgt.month]
            food_naive = float(fm_.tail(5).mean()) if len(fm_) >= 3 else float(food_hist.tail(24).mean())
            adm_h = S.admin_forecast(reg, tgt, known_through=t - 1, as_of=as_of, announce_mode="documented", w_adm=wh["administered"])
            alc_h = S.alc_forecast(alc, tgt, t - 1, as_of=as_of)
            fh = fuel_official[fuel_official.index <= t - 1]; fh = fh[S._released_index(fh.index, as_of)]
            fmf = fh[fh.index.month == tgt.month]
            fuel_h = float(fmf.tail(8).median()) if len(fmf) >= 3 else float(fh.tail(24).median())
            wdg = S._wedge_at(wedge_tv, tgt, t - 1)
            other = wh["fuel"] * fuel_h + wh["administered"] * adm_h + wh["alc"] * alc_h + wdg

            def recomb(core_c, food_c):
                return np.nan if (np.isnan(core_c) or np.isnan(food_c)) else other + wh["food"] * food_c + wh["core"] * core_c
            nv = naive_mm(y_known, tgt)
            p = {k: recomb(c[k], food_h) for k in ("P0", "P1", "P2", "P3", "P4")}
            p["P5"] = p["P0"] if h <= 6 else (0.5 * p["P0"] + 0.5 * nv if np.isfinite(p["P0"]) else np.nan)
            p["P6"] = p["P0"] if h <= 6 else (drift + seas_dev[tgt.month] if np.isfinite(drift) else np.nan)
            p["P7"] = recomb(c["P0"], food_h if h <= 3 else food_naive)
            a = {k: float(act_series[k].get(tgt, np.nan)) for k in ("core", "food", "admin", "alc", "fuel")}
            wa = {"core": wh["core"] * a["core"], "food": wh["food"] * a["food"], "admin": wh["administered"] * a["admin"],
                  "alc": wh["alc"] * a["alc"], "fuel": wh["fuel"] * a["fuel"]}
            yt = float(yk.get(tgt, np.nan))
            wa["wedge"] = yt - sum(wa.values()) if np.isfinite(yt) and all(np.isfinite(v) for v in wa.values()) else np.nan
            rows.append({"origin": str(t), "h": h, "target": str(tgt), "mm_real": yt, "mm_naive": nv, "h0_model": float(bt.loc[t, "STRUCT_EVE"]),
                         "h0_real": float(yk.get(t, np.nan)), **{f"mm_{k}": v for k, v in p.items()},
                         "blk_core": wh["core"] * c["P0"], "blk_food": wh["food"] * food_h, "blk_admin": wh["administered"] * adm_h,
                         "blk_alc": wh["alc"] * alc_h, "blk_fuel": wh["fuel"] * fuel_h, "blk_wedge": wdg,
                         **{f"blkact_{k}": v for k, v in wa.items()}})
    df = pd.DataFrame(rows)
    # ---- y/y paths (exact percent) for objects (a) product and (b) horizon-only ----
    df["tp"] = pd.PeriodIndex(df["target"], freq="M"); df["op"] = pd.PeriodIndex(df["origin"], freq="M")
    ylog = lg(yk)  # log points x100, indexed like yk
    ylog = pd.Series(np.asarray(ylog), index=yk.index)
    out = []
    for t, g in df.groupby("op"):
        g = g.sort_values("h")
        known = ylog[ylog.index <= t - 1]
        for _, r in g.iterrows():
            tgt = r.tp; h = int(r.h)
            window = pd.period_range(tgt - 11, tgt, freq="M")
            base = float(known.reindex([m for m in window if m <= t - 1]).sum())
            fut = [m for m in window if m >= t]
            real = base + float(ylog.reindex(fut).sum())
            rec = {"origin": str(t), "h": h, "real_yy": pct(real)}
            for k in CANDS + ["naive"]:
                col = f"mm_{k}" if k != "naive" else "mm_naive"
                path_a = {t: float(r.h0_model)}; path_b = {t: float(r.h0_real)}
                for _, rr in g.iterrows():
                    path_a[rr.tp] = rr[col]; path_b[rr.tp] = rr[col]
                fa = base + sum(lg([path_a[m]])[0] for m in fut); fb = base + sum(lg([path_b[m]])[0] for m in fut)
                rec[f"yy_a_{k}"] = pct(fa); rec[f"yy_b_{k}"] = pct(fb)
            path_nn = {t: float(r.h0_model)}
            for _, rr in g.iterrows():
                path_nn[rr.tp] = rr["mm_naive"]
            rec["yy_a_nowcast_naive"] = pct(base + sum(lg([path_nn[m]])[0] for m in fut))
            rec["yy_rw"] = pct(float(known.loc[t - 12:t - 1].sum())) if (t - 12) in known.index else np.nan
            rec["yy_last"] = rec["yy_rw"]
            out.append(rec)
    yy = pd.DataFrame(out)
    df = df.merge(yy, on=["origin", "h"], how="left")
    df.to_csv(os.path.join(HERE, "output", "path_backtest_h.csv"), index=False)

    # ---------------- diagnostics ----------------
    pd.set_option("display.width", 250)
    print("\nD1 BY HORIZON (common sample per h): m/m RMSE / MAE / bias (P0, naive) | y/y RMSE (a) P0, nowcast+naive, naive | y/y RMSE (b) P0, naive, RW | y/y bias (b) P0 | direction hit (b) P0 / naive")
    summ = []
    for h, g0 in df.groupby("h"):
        g = g0[g0[[f"yy_b_{k}" for k in CANDS] + ["yy_b_naive", "yy_rw", "real_yy", "mm_real"]].notna().all(axis=1)]
        e_m = g.mm_P0 - g.mm_real; e_n = g.mm_naive - g.mm_real
        d_real = np.sign(g.real_yy - g.yy_last); d_p0 = np.sign(g.yy_b_P0 - g.yy_last); d_nv = np.sign(g.yy_b_naive - g.yy_last)
        rec = {"h": h, "n": len(g), "mm_rmse_P0": rmse(e_m), "mm_mae_P0": float(e_m.abs().mean()), "mm_bias_P0": float(e_m.mean()),
               "mm_rmse_naive": rmse(e_n), "yy_a_rmse_P0": rmse(g.yy_a_P0 - g.real_yy), "yy_a_rmse_nn": rmse(g.yy_a_nowcast_naive - g.real_yy),
               "yy_a_rmse_naive": rmse(g.yy_a_naive - g.real_yy), "yy_b_rmse_P0": rmse(g.yy_b_P0 - g.real_yy), "yy_b_rmse_naive": rmse(g.yy_b_naive - g.real_yy),
               "yy_rmse_rw": rmse(g.yy_rw - g.real_yy), "yy_b_bias_P0": float((g.yy_b_P0 - g.real_yy).mean()),
               "dir_hit_P0": float((d_p0 == d_real).mean()), "dir_hit_naive": float((d_nv == d_real).mean())}
        for k in CANDS[1:]:
            rec[f"yy_b_rmse_{k}"] = rmse(g[f"yy_b_{k}"] - g.real_yy)
        summ.append(rec)
        print(f"h={h:2d} n={len(g):2d} | {rec['mm_rmse_P0']:.3f} {rec['mm_mae_P0']:.3f} {rec['mm_bias_P0']:+.3f} (naive {rec['mm_rmse_naive']:.3f}) | "
              f"{rec['yy_a_rmse_P0']:.3f} {rec['yy_a_rmse_nn']:.3f} {rec['yy_a_rmse_naive']:.3f} | {rec['yy_b_rmse_P0']:.3f} {rec['yy_b_rmse_naive']:.3f} {rec['yy_rmse_rw']:.3f} | "
              f"{rec['yy_b_bias_P0']:+.3f} | {rec['dir_hit_P0']:.2f} / {rec['dir_hit_naive']:.2f}")
    sm = pd.DataFrame(summ); sm.to_csv(os.path.join(HERE, "output", "path_backtest_h_summary.csv"), index=False)

    def grp(h):
        return next(k for k, (lo, hi) in GROUPS.items() if lo <= h <= hi)
    df["grp"] = df.h.map(grp)
    regimes = [("2019-02..2021-12", pd.Period("2019-02", "M"), pd.Period("2021-12", "M")), ("2022-01..2023-12", pd.Period("2022-01", "M"), pd.Period("2023-12", "M")),
               ("2024-01..2026-07", pd.Period("2024-01", "M"), pd.Period("2026-07", "M"))]
    ok_all = df[[f"yy_b_{k}" for k in CANDS] + ["yy_b_naive", "yy_rw", "real_yy"]].notna().all(axis=1)
    print("\nD2 BY TARGET REGIME x HORIZON GROUP: y/y RMSE (b) P0 / naive / RW | bias (b) P0 | n")
    for name, lo, hi in regimes:
        for gname in GROUPS:
            g = df[ok_all & (df.tp >= lo) & (df.tp <= hi) & (df.grp == gname)]
            if len(g) == 0:
                continue
            print(f"  {name} h {gname:4s}: {rmse(g.yy_b_P0 - g.real_yy):.3f} / {rmse(g.yy_b_naive - g.real_yy):.3f} / {rmse(g.yy_rw - g.real_yy):.3f} | {(g.yy_b_P0 - g.real_yy).mean():+.3f} | n={len(g)}")
    print("\nD3 JANUARY TARGETS vs OTHER MONTHS, m/m RMSE P0 / naive by horizon group:")
    for gname in GROUPS:
        for lab, mk in (("January", df.tp.dt.month == 1), ("other", df.tp.dt.month != 1)):
            g = df[ok_all & mk & (df.grp == gname)]
            print(f"  h {gname:4s} {lab:8s}: {rmse(g.mm_P0 - g.mm_real):.3f} / {rmse(g.mm_naive - g.mm_real):.3f} (n={len(g)})")
    print("\nD4 BLOCK DECOMPOSITION of the m/m error (P0): RMS of weighted block error | share of m/m MSE incl. covariance, at h = 1, 3, 6, 12")
    for h in (1, 3, 6, 12):
        g = df[(df.h == h) & df[[f"blk_{k}" for k in BLK] + [f"blkact_{k}" for k in BLK]].notna().all(axis=1)]
        errs = {k: (g[f"blk_{k}"] - g[f"blkact_{k}"]) for k in BLK}
        tot = sum(errs.values()); mse = float((tot ** 2).mean())
        shares = {k: float((errs[k] * tot).mean() / mse) if mse > 0 else np.nan for k in BLK}
        print(f"  h={h:2d} (n={len(g)}): " + " | ".join(f"{k} {rmse(errs[k]):.3f} ({100*shares[k]:+.0f}%)" for k in BLK) + f" | total m/m RMSE {np.sqrt(mse):.3f}")
    print("\nD5 QUARTERLY AVERAGE y/y forecasts, quarters fully inside h<=12 (b) P0 / naive / RW  and (a) P0; RMSE by quarters ahead:")
    qrows = []
    for t, g in df[ok_all].groupby("op"):
        g = g.set_index("tp")
        q0 = t.asfreq("Q")
        for k in range(1, 5):
            qq = q0 + k if t.month != 1 or True else q0 + k
            months = [m for m in pd.period_range(qq.asfreq("M", "s"), qq.asfreq("M", "e"), freq="M")]
            if all(m in g.index for m in months):
                qrows.append({"origin": str(t), "k": k, "quarter": str(qq), "real": g.loc[months, "real_yy"].mean(), "b_P0": g.loc[months, "yy_b_P0"].mean(),
                              "b_naive": g.loc[months, "yy_b_naive"].mean(), "rw": g.loc[months, "yy_rw"].mean(), "a_P0": g.loc[months, "yy_a_P0"].mean()})
    qd = pd.DataFrame(qrows)
    for k, g in qd.groupby("k"):
        print(f"  {k} quarter(s) ahead (n={len(g)}): (b) P0 {rmse(g.b_P0-g.real):.3f} / naive {rmse(g.b_naive-g.real):.3f} / RW {rmse(g.rw-g.real):.3f} | (a) P0 {rmse(g.a_P0-g.real):.3f} | bias (b) P0 {(g.b_P0-g.real).mean():+.3f}")
    # D6 calendar-year averages vs CNB report vintages
    try:
        con = S.la._con()
        v = con.sql("""SELECT publication_date, season, period_year, value FROM cnb.mpr_vintages WHERE series_code='consumer_price_index' ORDER BY publication_date, period_year""").df()
        con.close()
        v["publication_date"] = pd.to_datetime(v["publication_date"])
        yy_real = pd.Series({m: pct(float(ylog.loc[m - 11:m].sum())) for m in yk.index if (m - 11) in yk.index})
        crows = []
        for _, r in v.iterrows():
            Y = int(r.period_year); d = r.publication_date
            if Y < d.year or Y > d.year + 1:
                continue
            cands = [t for t in origins if _eve(t) >= d]
            if not cands:
                continue
            t = min(cands)
            g = df[(df.op == t)].set_index("tp")
            months = pd.period_range(f"{Y}-01", f"{Y}-12", freq="M")
            vals = []
            for m in months:
                if m <= t - 1 and m in yy_real.index:
                    vals.append(yy_real.loc[m])
                elif m in g.index and np.isfinite(g.loc[m, "yy_a_P0"]):
                    vals.append(g.loc[m, "yy_a_P0"])
                else:
                    vals = None; break
            if vals is None or not all(m in yy_real.index for m in months):
                continue
            crows.append({"report": str(d.date()), "season": r.season, "year": Y, "origin": str(t), "cnb": float(r.value), "ours_a": float(np.mean(vals)),
                          "realised": float(yy_real.reindex(months).mean()), "n_forecast_months": int(sum(1 for m in months if m >= t))})
        cd = pd.DataFrame(crows)
        cd.to_csv(os.path.join(HERE, "output", "path_backtest_h_cnb.csv"), index=False)
        print("\nD6 CALENDAR-YEAR AVERAGE y/y: our product path (a) vs the CNB report forecast at matched dates (realised from the chain):")
        print(cd.round(2).to_string(index=False))
        for lab, m in (("current year", cd.year == pd.to_datetime(cd.report).dt.year), ("next year", cd.year == pd.to_datetime(cd.report).dt.year + 1)):
            g = cd[m]
            if len(g):
                print(f"  {lab}: n={len(g)} RMSE ours {rmse(g.ours_a - g.realised):.3f} vs CNB {rmse(g.cnb - g.realised):.3f}; bias ours {(g.ours_a - g.realised).mean():+.3f} CNB {(g.cnb - g.realised).mean():+.3f}")
    except Exception as e:  # noqa: BLE001
        print("D6 skipped:", str(e)[:120])
    print("\nD7 PERSISTENCE: lag-1 autocorrelation across consecutive origins of the y/y error (b) P0:")
    for h in (6, 12):
        g = df[(df.h == h) & ok_all].sort_values("op"); e = (g.yy_b_P0 - g.real_yy).values
        print(f"  h={h:2d}: rho1 = {np.corrcoef(e[1:], e[:-1])[0,1]:+.2f} (n={len(e)})")

    # ---------------- candidates and the frozen rule ----------------
    print("\nCANDIDATES: y/y RMSE (b), exact percent, by horizon group; full sample | first half origins (..2022-12) | second half (2023-01..) | 2024+ targets; gain vs P0 in %")
    first = df.op < SPLIT
    dec = []
    for gname in GROUPS:
        g = df[ok_all & (df.grp == gname)]
        base = {"full": rmse(g.yy_b_P0 - g.real_yy), "h1": rmse(g[first].yy_b_P0 - g[first].real_yy), "h2": rmse(g[~first].yy_b_P0 - g[~first].real_yy),
                "y24": rmse(g[g.tp >= pd.Period("2024-01", "M")].yy_b_P0 - g[g.tp >= pd.Period("2024-01", "M")].real_yy)}
        print(f"  group {gname}: P0 {base['full']:.3f} | {base['h1']:.3f} | {base['h2']:.3f} | {base['y24']:.3f}  (n={len(g)}, naive {rmse(g.yy_b_naive - g.real_yy):.3f})")
        winners = []
        for k in CANDS[1:]:
            e = g[f"yy_b_{k}"] - g.real_yy
            r_full, r1, r2 = rmse(e), rmse(e[first.loc[g.index]]), rmse(e[~first.loc[g.index]])
            r24 = rmse(e[g.tp >= pd.Period("2024-01", "M")])
            gain = lambda a, b: 100 * (1 - a / b) if b > 0 else np.nan
            ok = gain(r1, base["h1"]) >= 5 and gain(r2, base["h2"]) >= 5 and gain(r24, base["y24"]) >= -2
            print(f"     {k}: {r_full:.3f} ({gain(r_full, base['full']):+.1f}%) | {r1:.3f} ({gain(r1, base['h1']):+.1f}%) | {r2:.3f} ({gain(r2, base['h2']):+.1f}%) | {r24:.3f} ({gain(r24, base['y24']):+.1f}%) {'<- qualifies' if ok else ''}")
            if ok:
                winners.append((gain(r_full, base["full"]), k))
        pick = max(winners)[1] if winners else "none"
        dec.append({"group": gname, "adopt": pick})
        print(f"  -> adoption for h {gname}: {pick}")
    pd.DataFrame(dec).to_csv(os.path.join(HERE, "output", "path_backtest_h_adoption.csv"), index=False)
    # m/m level: mean forecast vs realised by horizon for P0, P3, P4 (the bias candidates)
    print("\nBIAS CHECK: mean m/m forecast by horizon group, P0 / P3 (rolling 120) / P4 (local level) vs realised, by target regime:")
    for name, lo, hi in regimes:
        for gname in GROUPS:
            g = df[ok_all & (df.tp >= lo) & (df.tp <= hi) & (df.grp == gname)]
            if len(g):
                print(f"  {name} h {gname:4s}: P0 {g.mm_P0.mean():+.3f} P3 {g.mm_P3.mean():+.3f} P4 {g.mm_P4.mean():+.3f} realised {g.mm_real.mean():+.3f} (n={len(g)})")


if __name__ == "__main__":
    main()
