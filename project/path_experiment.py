"""Path product, step 1 (PATH_SPEC_v1.md): the existing direct-horizon blocks
evaluated as a year-on-year path at h = 0..12 against naive paths, with
base effects separated from forecast skill. Single run, release-eve clock.

v2 of the harness (7 September 2026, Codex R8 corrections; the declared
experiment is unchanged, its SCORING was wrong):
  - every method is scored on the COMMON valid sample per horizon (the
    model has fewer valid forecasts because the food direct-horizon ridge
    needs enough released labels; the first run let rmse() drop missing
    rows per method, so at h = 12 the model was scored on 66 rows and the
    naive paths on 78); coverage is reported separately;
  - year-on-year is reported in exact percent, 100 x (exp(L/100) - 1), next
    to the log points the spec declared (they differ by up to 1.4 pp in the
    2022-23 episode);
  - the "base share" is the full decomposition Var(base) / Var(fut) /
    2 Cov over Var(total), not Var(base) / Var(total) alone;
  - B4 (the CNB financial-market survey's one-year expectation) is scored
    at h = 12 on its own common sample, as declared;
  - the declared per-block cumulative error decomposition at h = 6 and 12
    is implemented (block forecasts and realised block m/m, weight applied);
  - Diebold-Mariano with HAC lag h - 1 (declared) and a lag-12 sensitivity;
  - the administered block is priced with the target month's administered
    weight (v2.7.1 announcement units).
Usage: python path_experiment.py
Writes output/path_experiment.csv (origin x horizon rows) and
output/path_experiment_summary.csv (per-horizon table).
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

H = list(range(0, 13))
NAIVE_YEARS = 5
BLK = ("core", "food", "admin", "alc", "fuel", "wedge")


def _eve(m: pd.Period) -> pd.Timestamp:
    fr = S._first_release_dt(m)
    if pd.notna(fr):
        return fr.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=23, minutes=59)
    return m.to_timestamp(how="end").normalize() + pd.Timedelta(days=7, hours=23, minutes=59)


def naive_mm(y_known: pd.Series, target: pd.Period) -> float:
    same = y_known[y_known.index.month == target.month]
    return float(same.tail(NAIVE_YEARS).mean()) if len(same) >= 3 else float(y_known.tail(24).mean())


def lg(x):  # percent m/m -> log points x100
    return 100.0 * np.log1p(np.asarray(x, dtype=float) / 100.0)


def pct(L):  # log points x100 -> exact percent
    return 100.0 * np.expm1(np.asarray(L, dtype=float) / 100.0)


def rmse(e):
    e = np.asarray(e, dtype=float); return float(np.sqrt(np.mean(e ** 2)))


def dm_stat(d, L):
    d = np.asarray(d, dtype=float); n = len(d); m_ = d.mean(); var = d.var(ddof=0)
    for l in range(1, L + 1):
        var += 2 * (1 - l / (L + 1)) * np.mean((d[l:] - m_) * (d[:-l] - m_))
    return m_ / np.sqrt(var / n) if var > 0 else np.nan


def load_fmie_1y():
    """CNB FMIE one-year-ahead CPI y/y expectation (mean), by survey month."""
    try:
        con = S.la._con()
        f = con.sql("""SELECT survey_date, value_pct FROM consensus.inflation_expectations
                       WHERE source='cnb_fmie' AND horizon_kind='rolling_months' AND horizon_value=12 AND metric='mean'
                       ORDER BY survey_date""").df()
        con.close()
        s = pd.Series(f["value_pct"].astype(float).values, index=pd.PeriodIndex(pd.to_datetime(f["survey_date"]), freq="M"))
        return s[~s.index.duplicated(keep="last")]
    except Exception as e:  # noqa: BLE001
        print("FMIE table not read:", str(e)[:80])
        return None


def main():
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    alc = S.load_alc_tobacco_mm()
    slow = pd.concat([load_m3_yoy(), load_housing_channel()], axis=1)
    feats_slow = pd.concat([feats, slow.reindex(feats.index)], axis=1)
    fuel_official = comp["fuel"].dropna()
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period"); bt.index = pd.PeriodIndex(bt.index, freq="M")
    origins = list(bt.index)
    yk = y.dropna()
    last_real = yk.index.max()
    fmie = load_fmie_1y()
    act_series = {"core": core.dropna(), "food": comp["food"].dropna(), "admin": reg.dropna(), "alc": alc.dropna(), "fuel": fuel_official}
    rows = []
    for t in origins:
        as_of = _eve(t)
        y_known = yk[yk.index <= t - 1]
        y_known = y_known[S._released_index(y_known.index, as_of)]
        wmap = S.solve_weights(y, comp, core, reg, t - 1, as_of=as_of, alc=alc)
        wt = wmap[S._regime(t)]
        wedge_tv = S._weighted_wedge(y, comp, alc, core, reg, wedge, wmap, as_of=as_of)
        fc = {0: float(bt.loc[t, "STRUCT_EVE"])}
        blocks, blocks_act = {}, {}
        for h in range(1, 13):
            frame = feats if h <= 3 else feats_slow
            wh = wmap.get(S._regime(t + h), wt)
            core_h, _, _ = S._ridge_predict(frame, core, t, h=h, as_of=as_of)
            food_h = S.food_forecast(comp["food"], food_feats, t, h=h, as_of=as_of)
            adm_h = S.admin_forecast(reg, t + h, known_through=t - 1, as_of=as_of, announce_mode="documented", w_adm=wh["administered"])
            alc_h = S.alc_forecast(alc, t + h, t - 1, as_of=as_of)
            fh = fuel_official[fuel_official.index <= t - 1]; fh = fh[S._released_index(fh.index, as_of)]
            fm = fh[fh.index.month == (t + h).month]
            fuel_h = float(fm.tail(8).median()) if len(fm) >= 3 else float(fh.tail(24).median())
            wdg = S._wedge_at(wedge_tv, t + h, t - 1)
            if np.isnan(core_h) or np.isnan(food_h):
                fc[h] = np.nan
            else:
                fc[h] = wh["fuel"] * fuel_h + wh["administered"] * adm_h + wh["alc"] * alc_h + wh["food"] * food_h + wh["core"] * core_h + wdg
            blocks[h] = {"core": wh["core"] * core_h, "food": wh["food"] * food_h, "admin": wh["administered"] * adm_h,
                         "alc": wh["alc"] * alc_h, "fuel": wh["fuel"] * fuel_h, "wedge": wdg}
            # realised weighted block m/m at t+h (current vintage) and the realised reconciliation
            tgt = t + h
            a = {k: float(act_series[k].get(tgt, np.nan)) for k in ("core", "food", "admin", "alc", "fuel")}
            wa = {"core": wh["core"] * a["core"], "food": wh["food"] * a["food"], "admin": wh["administered"] * a["admin"],
                  "alc": wh["alc"] * a["alc"], "fuel": wh["fuel"] * a["fuel"]}
            yt = float(yk.get(tgt, np.nan))
            wa["wedge"] = yt - sum(wa.values()) if np.isfinite(yt) and all(np.isfinite(v) for v in wa.values()) else np.nan
            blocks_act[h] = wa
        naive = {h: naive_mm(y_known, t + h) for h in H}
        yy_last = float(lg(y_known.loc[t - 12:t - 1]).sum()) if (t - 12) in y_known.index and len(y_known.loc[t - 12:t - 1]) == 12 else np.nan
        fm_val = np.nan
        if fmie is not None:
            f_ok = fmie[fmie.index <= t]      # the survey of month t is published mid-t, before the release-eve clock
            if len(f_ok):
                fm_val = float(f_ok.iloc[-1])
        for h in H:
            tgt = t + h
            if tgt > last_real:
                continue
            window = pd.period_range(tgt - 11, tgt, freq="M")
            known = [m for m in window if m <= t - 1]; fut = [m for m in window if m >= t]
            base = float(lg(y_known.reindex(known)).sum()) if known else 0.0
            real_fut = float(lg(yk.reindex(fut)).sum()) if fut else 0.0
            real_yy = base + real_fut
            model_fut = float(sum(lg([fc[(k.ordinal - t.ordinal)]])[0] for k in fut)) if fut else 0.0
            naive_fut = float(sum(lg([naive[(k.ordinal - t.ordinal)]])[0] for k in fut)) if fut else 0.0
            nown_fut = float(sum(lg([fc[0] if (k.ordinal - t.ordinal) == 0 else naive[(k.ordinal - t.ordinal)]])[0] for k in fut)) if fut else 0.0
            rows.append({"origin": str(t), "h": h, "target": str(tgt), "real_yy": real_yy, "base": base, "real_fut": real_fut,
                         "model_fut": model_fut, "naive_fut": naive_fut, "nowcast_naive_fut": nown_fut,
                         "model_yy": base + model_fut, "naive_yy": base + naive_fut, "nowcast_naive_yy": base + nown_fut, "rw_yy": yy_last,
                         "fmie_1y_pct": fm_val if h == 12 else np.nan,
                         "mm_model": fc[h], "mm_naive": naive[h], "mm_real": float(yk.get(tgt, np.nan)),
                         **({f"blk_{k}": v for k, v in blocks[h].items()} if h >= 1 else {}),
                         **({f"blkact_{k}": v for k, v in blocks_act[h].items()} if h >= 1 else {})})
    df = pd.DataFrame(rows)
    for c in ("real_yy", "model_yy", "naive_yy", "nowcast_naive_yy", "rw_yy"):
        df[c + "_pct"] = pct(df[c])
    df.to_csv(os.path.join(HERE, "output", "path_experiment.csv"), index=False)

    print(f"\nyear-on-year RMSE on the COMMON valid sample per horizon; origins {origins[0]}..{origins[-1]}, release-eve clock")
    print(f"{'h':>2s} {'targets':>7s} {'common':>6s} | log points x100: {'model':>6s} {'now+nv':>6s} {'naive':>6s} {'RW':>6s} | exact pct: {'model':>6s} {'now+nv':>6s} {'naive':>6s} {'RW':>6s} | cum m/m: {'model':>6s} {'naive':>6s} | var shares base/fut/2cov | m/m RMSE model naive")
    res, summ = {}, []
    KEY = ["model_yy", "naive_yy", "nowcast_naive_yy", "rw_yy", "real_yy"]
    for h, g0 in df.groupby("h"):
        ok = g0[KEY].notna().all(axis=1); g = g0[ok]
        r_m, r_nn, r_n, r_rw = (rmse(g.model_yy - g.real_yy), rmse(g.nowcast_naive_yy - g.real_yy), rmse(g.naive_yy - g.real_yy), rmse(g.rw_yy - g.real_yy))
        p_m, p_nn, p_n, p_rw = (rmse(g.model_yy_pct - g.real_yy_pct), rmse(g.nowcast_naive_yy_pct - g.real_yy_pct), rmse(g.naive_yy_pct - g.real_yy_pct), rmse(g.rw_yy_pct - g.real_yy_pct))
        s_m, s_n = rmse(g.model_fut - g.real_fut), rmse(g.naive_fut - g.real_fut)
        vt = g.real_yy.var()
        sh = (g.base.var() / vt, g.real_fut.var() / vt, 2 * g[["base", "real_fut"]].cov().iloc[0, 1] / vt) if vt > 0 else (np.nan,) * 3
        mmok = g0[["mm_model", "mm_naive", "mm_real"]].notna().all(axis=1); gm = g0[mmok]
        res[h] = dict(model=r_m, nn=r_nn, naive=r_n, rw=r_rw, model_pct=p_m, nn_pct=p_nn, naive_pct=p_n, rw_pct=p_rw, n=len(g), n_targets=len(g0))
        summ.append({"h": h, "n_targets": len(g0), "n_common": len(g), "model_log": r_m, "nowcast_naive_log": r_nn, "naive_log": r_n, "rw_log": r_rw,
                     "model_pct": p_m, "nowcast_naive_pct": p_nn, "naive_pct": p_n, "rw_pct": p_rw, "cum_mm_model": s_m, "cum_mm_naive": s_n,
                     "var_share_base": sh[0], "var_share_fut": sh[1], "var_share_2cov": sh[2],
                     "mm_rmse_model": rmse(gm.mm_model - gm.mm_real), "mm_rmse_naive": rmse(gm.mm_naive - gm.mm_real), "n_mm": len(gm)})
        print(f"{h:2d} {len(g0):7d} {len(g):6d} | {'':17s}{r_m:6.3f} {r_nn:6.3f} {r_n:6.3f} {r_rw:6.3f} | {'':11s}{p_m:6.3f} {p_nn:6.3f} {p_n:6.3f} {p_rw:6.3f} | {'':9s}{s_m:6.3f} {s_n:6.3f} | "
              f"{sh[0]:5.2f} {sh[1]:5.2f} {sh[2]:5.2f}         | {rmse(gm.mm_model - gm.mm_real):6.3f} {rmse(gm.mm_naive - gm.mm_real):6.3f} (n={len(gm)})")
    pd.DataFrame(summ).to_csv(os.path.join(HERE, "output", "path_experiment_summary.csv"), index=False)
    miss = df[(df.h >= 1) & df.model_yy.isna()]
    if len(miss):
        print(f"\nmodel forecasts missing (food direct-horizon ridge below its 48-label minimum): {len(miss)} origin x horizon rows, origins "
              f"{sorted(set(miss.origin))[0]}..{sorted(set(miss.origin))[-1]}; scored samples above exclude them for EVERY method")

    print("\nsplits (y/y RMSE, exact pct, common sample): h | window | n | model | nowcast+naive | naive | RW")
    for h in (3, 6, 12):
        g = df[df.h == h].copy(); g = g[g[KEY].notna().all(axis=1)]; g["tp"] = pd.PeriodIndex(g["target"], freq="M"); tpm = g["tp"].dt.month
        for name, m in (("ex-January targets", tpm != 1), ("2024+ targets", g.tp >= pd.Period("2024-01", "M")),
                        ("2022-2023 targets", (g.tp >= pd.Period("2022-01", "M")) & (g.tp <= pd.Period("2023-12", "M")))):
            f = g[m]
            print(f" {h:2d} | {name:18s} n={len(f):2d} | {rmse(f.model_yy_pct-f.real_yy_pct):.3f} | {rmse(f.nowcast_naive_yy_pct-f.real_yy_pct):13.3f} | {rmse(f.naive_yy_pct-f.real_yy_pct):.3f} | {rmse(f.rw_yy_pct-f.real_yy_pct):.3f}")

    print("\nDiebold-Mariano (squared errors, exact pct, common sample), model vs naive and vs nowcast+naive; negative favours the model; HAC lag h-1 (declared) and lag 12 (sensitivity):")
    for h in (3, 6, 12):
        g = df[df.h == h]; g = g[g[KEY].notna().all(axis=1)]
        for bname, bcol in (("naive", "naive_yy_pct"), ("nowcast+naive", "nowcast_naive_yy_pct")):
            d = ((g.model_yy_pct - g.real_yy_pct) ** 2 - (g[bcol] - g.real_yy_pct) ** 2).values
            print(f"  h={h:2d} vs {bname:14s}: mean sq-err diff {d.mean():+.3f}, DM lag {max(h-1,0):2d}: {dm_stat(d, max(h - 1, 0)):+.2f}, lag 12: {dm_stat(d, 12):+.2f} (n={len(d)})")

    # B4: FMIE one-year expectation at h = 12, on its own common sample
    g = df[(df.h == 12)]; g = g[g[KEY + ["fmie_1y_pct"]].notna().all(axis=1)]
    if len(g):
        print(f"\nB4 CNB FMIE one-year expectation at h=12 (survey month <= origin), common sample n={len(g)}: RMSE exact pct FMIE {rmse(g.fmie_1y_pct - g.real_yy_pct):.3f} | "
              f"model {rmse(g.model_yy_pct - g.real_yy_pct):.3f} | naive {rmse(g.naive_yy_pct - g.real_yy_pct):.3f} | RW {rmse(g.rw_yy_pct - g.real_yy_pct):.3f}; "
              f"mean error FMIE {(g.fmie_1y_pct - g.real_yy_pct).mean():+.2f}, model {(g.model_yy_pct - g.real_yy_pct).mean():+.2f}")

    # per-block cumulative contribution error at h = 6 and 12 (weight x forecast - weight x realised, summed over t+1..t+h)
    print("\nper-block CUMULATIVE contribution error over t+1..t+h (pp of headline, current-vintage block actuals; origins with all rows valid): mean / RMS")
    for hh in (6, 12):
        sub = df[(df.h >= 1) & (df.h <= hh)].copy()
        sub["ok"] = sub[[f"blk_{k}" for k in BLK] + [f"blkact_{k}" for k in BLK]].notna().all(axis=1)
        full = sub.groupby("origin")["ok"].all(); full = full[full & (sub.groupby("origin")["h"].max() >= hh)].index
        sub = sub[sub.origin.isin(full)]
        cum = {k: (sub.groupby("origin")[f"blk_{k}"].sum() - sub.groupby("origin")[f"blkact_{k}"].sum()) for k in BLK}
        tot = sum(cum.values())
        print(f"  h={hh:2d} (n={len(full)}): " + " | ".join(f"{k} {cum[k].mean():+.2f}/{np.sqrt((cum[k]**2).mean()):.2f}" for k in BLK) + f" | total {tot.mean():+.2f}/{np.sqrt((tot**2).mean()):.2f}")
    print("\nblock m/m forecast (weighted, pp of headline) averaged over origins, by horizon: core | food | admin | alc | fuel | wedge")
    for h in (1, 3, 6, 12):
        g = df[df.h == h]
        print(f"  h={h:2d}: " + " | ".join(f"{g[f'blk_{k}'].mean():+.3f}" for k in BLK) + f"   (mean realised m/m {g.mm_real.mean():+.3f}, model {g.mm_model.mean():+.3f})")

    ok_b1 = all(res[h]["model"] <= 0.90 * res[h]["naive"] for h in (3, 6, 12)); ok_b3 = all(res[h]["model"] <= res[h]["rw"] for h in (6, 12))
    ok_b1p = all(res[h]["model_pct"] <= 0.90 * res[h]["naive_pct"] for h in (3, 6, 12)); ok_b3p = all(res[h]["model_pct"] <= res[h]["rw_pct"] for h in (6, 12))
    add_over_nn = [100 * (1 - res[h]["model"] / res[h]["nn"]) for h in range(1, 13)]
    print(f"\nRULE (declared units, log points, common samples): beats naive by >=10% at h=3,6,12: {ok_b1} "
          f"({', '.join(f'h{h} {100*(1-res[h]['model']/res[h]['naive']):.1f}%' for h in (3, 6, 12))}); beats RW y/y at h=6,12: {ok_b3} -> "
          f"{'PUBLISHABLE as a product' if (ok_b1 and ok_b3) else 'NOT publishable yet'}")
    print(f"RULE in exact percent: beats naive by >=10%: {ok_b1p} ({', '.join(f'h{h} {100*(1-res[h]['model_pct']/res[h]['naive_pct']):.1f}%' for h in (3, 6, 12))}); beats RW: {ok_b3p}")
    print(f"gain over nowcast+naive by horizon (%, common samples): {[round(v, 1) for v in add_over_nn]} -> horizon blocks add {'something' if max(add_over_nn) >= 5 else 'less than 5% everywhere'}")


if __name__ == "__main__":
    main()
