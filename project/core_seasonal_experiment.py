"""Predeclared core seasonal experiment (CORE_SEASONAL_SPEC.md): month
dummies (incumbent) vs per-origin one-sided X-13 on the core target (S),
each with and without an Easter-month dummy (E). Single run, two clocks.
Usage: python core_seasonal_experiment.py
Writes output/core_seasonal_experiment.csv.
"""
import hashlib
import os
import sys
import warnings
from datetime import date

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cz_struct as S  # noqa: E402
from data import local_adapter as la  # noqa: E402

_SA_CACHE = {}
FALLBACKS = []


def easter_sunday(year: int) -> date:
    a = year % 19; b = year // 100; c = year % 100; d = b // 4; e = b % 4
    f = (b + 8) // 25; g = (b - f + 1) // 3; h = (19 * a + b - d - g + 15) % 30
    i = c // 4; k = c % 4; l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31; day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _eve(m: pd.Period) -> pd.Timestamp:
    fr = S._first_release_dt(m)
    if pd.notna(fr):
        return fr.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=23, minutes=59)
    return m.to_timestamp(how="end").normalize() + pd.Timedelta(days=7, hours=23, minutes=59)


def core_x13(core: pd.Series, origin: pd.Period, as_of):
    """(sa history, seasonal factor for origin, ok flag) -- food_forecast's recipe."""
    from statsmodels.tsa.x13 import x13_arima_analysis
    hist = core.dropna()
    hist = hist[hist.index <= origin - 1]
    hist = hist[S._released_index(hist.index, as_of)]
    key = (str(origin), len(hist), hashlib.sha1(np.ascontiguousarray(hist.values, dtype=float).tobytes()).hexdigest())
    if key in _SA_CACHE:
        return _SA_CACHE[key]
    try:
        ts = hist.copy(); ts.index = ts.index.to_timestamp()
        sa = x13_arima_analysis(ts, x12path=la._X13_PATH, prefer_x13=True).seasadj
        sa.index = hist.index
        seas = (hist - sa).dropna()
        s_m = seas[seas.index.month == origin.month]
        s_add = float(s_m.iloc[-3:].mean()) if len(s_m) else 0.0
        out = (sa, s_add, True)
    except Exception as e:
        FALLBACKS.append((str(origin), f"{type(e).__name__}: {str(e)[:80]}"))
        out = (None, np.nan, False)
    _SA_CACHE[key] = out
    return out


def main():
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    alc = S.load_alc_tobacco_mm()
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period")
    bt.index = pd.PeriodIndex(bt.index, freq="M")
    origins = list(bt.index)
    idx = feats.index
    mon_cols = [c for c in feats.columns if c.startswith("mon_")]
    easter_months = {pd.Period(easter_sunday(yr), freq="M") for yr in range(idx.min().year, idx.max().year + 2)}
    easter = pd.Series([1.0 if p in easter_months else 0.0 for p in idx], index=idx, name="easter_m")
    f_inc = feats
    f_inc_e = feats.assign(easter_m=easter)
    f_s = feats.drop(columns=mon_cols)
    f_s_e = f_s.assign(easter_m=easter)

    rows = []
    for t in origins:
        for clock, as_of in (("A", t.to_timestamp(how="end")), ("B", _eve(t))):
            r = {"period": t, "clock": clock}
            r["inc"], _, _ = S._ridge_predict(f_inc, core, t, as_of=as_of)
            r["inc_E"], _, _ = S._ridge_predict(f_inc_e, core, t, as_of=as_of)
            sa, s_add, ok = core_x13(core, t, as_of)
            if ok:
                p1, _, _ = S._ridge_predict(f_s, sa, t, as_of=as_of)
                p2, _, _ = S._ridge_predict(f_s_e, sa, t, as_of=as_of)
                r["S"], r["S_E"], r["x13_ok"] = p1 + s_add, p2 + s_add, True
            else:
                r["S"], r["S_E"], r["x13_ok"] = r["inc"], r["inc_E"], False
            if clock == "A":
                wmap = S.solve_weights(y, comp, core, reg, t - 1, as_of=as_of, alc=alc)
                r["w_core"] = wmap[S._regime(t)]["core"]
            rows.append(r)
    df = pd.DataFrame(rows)
    df["w_core"] = df.groupby("period")["w_core"].transform("first")
    df["core_actual"] = df["period"].map(bt["core_actual"])
    df["bt_core_pred"] = df["period"].map(bt["core_pred"])
    df["STRUCT"] = np.where(df["clock"] == "A", df["period"].map(bt["STRUCT"]), df["period"].map(bt["STRUCT_EVE"]))
    ext = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history_extended.csv"))
    ext["p"] = pd.PeriodIndex(ext["target_month"], freq="M"); ext = ext.set_index("p")
    ext = ext[ext["era"] != "flash_survey_suspect"]
    df["actual"] = df["period"].map(ext["actual"]); df["survey"] = df["period"].map(ext["survey_median"])
    cells = ["inc", "inc_E", "S", "S_E"]
    for c in cells:
        df[f"head_{c}"] = df["STRUCT"] + df["w_core"] * (df[c] - df["inc"])
    df.to_csv(os.path.join(HERE, "output", "core_seasonal_experiment.csv"), index=False)

    a = df[df.clock == "A"].set_index("period")
    print(f"harness: incumbent vs backtest core_pred max|diff| {(a['inc'] - a['bt_core_pred']).abs().max():.2e}")
    print(f"X-13 fallbacks: {len(FALLBACKS)} " + (str(FALLBACKS[:5]) if FALLBACKS else ""))
    print(f"clock B vs A identical for S: max|diff| {float((df[df.clock=='B'].set_index('period')['S'] - a['S']).abs().max()):.2e}")

    def rmse(e): e = pd.Series(e).dropna(); return float(np.sqrt((e ** 2).mean()))
    res, hres = {}, {}
    for clock in ("A", "B"):
        d = df[df.clock == clock].set_index("period")
        splits = {"all 90": np.ones(len(d), bool), "ex-January": d.index.month != 1,
                  "2024+": d.index >= pd.Period("2024-01", "M"),
                  "2024+ ex-Jan": (d.index >= pd.Period("2024-01", "M")) & (d.index.month != 1),
                  "2025+ flash era": d.index >= pd.Period("2025-01", "M")}
        print(f"\n=== clock {clock}: CORE BLOCK RMSE vs realised core m/m | HEADLINE RMSE vs first release ===")
        print(f"{'split':16s} | {'inc':>6s} {'inc+E':>6s} {'S':>6s} {'S+E':>6s} | {'head inc':>8s} {'inc+E':>7s} {'S':>7s} {'S+E':>7s} | survey")
        for name, m in splits.items():
            f = d[m]
            ce = {c: rmse(f[c] - f["core_actual"]) for c in cells}
            he = {c: rmse(f[f"head_{c}"] - f["actual"]) for c in cells}
            res[(clock, name)] = ce; hres[(clock, name)] = he
            print(f"{name:16s} | {ce['inc']:6.3f} {ce['inc_E']:6.3f} {ce['S']:6.3f} {ce['S_E']:6.3f} | "
                  f"{he['inc']:8.4f} {he['inc_E']:7.4f} {he['S']:7.4f} {he['S_E']:7.4f} | {rmse(f['survey']-f['actual']):.4f}")
        # Easter diagnostics: March + April core errors
        ma = d[d.index.month.isin([3, 4])]
        print("March+April core RMSE: " + ", ".join(f"{c} {rmse(ma[c]-ma['core_actual']):.3f}" for c in cells) + f" (n={len(ma)})")
        em = ma[[p in easter_months for p in ma.index]]
        print("  Easter-month core error mean (forecast - actual): " + ", ".join(f"{c} {(em[c]-em['core_actual']).mean():+.3f}" for c in cells) + f" (n={len(em)})")
        s = d["actual"] - d["survey"]; big = s.abs() >= 0.4 - 1e-8
        for c in cells:
            e = (d[f"head_{c}"] - d["actual"]).abs(); g = s.abs() - e
            print(f"  {c:6s} big-surprise MAE {e[big].mean():.3f} (n={int(big.sum())}), W-L@0.15 {int((g[big]>=0.15).sum())}-{int((g[big]<=-0.15).sum())}")

    # adoption rules
    rb = res[("B", "all 90")], res[("B", "2024+")]; hb = hres[("B", "all 90")], hres[("B", "2024+")]
    ra = res[("A", "all 90")], res[("A", "2024+")]
    ok_s = (rb[0]["S"] <= 0.95 * rb[0]["inc"] and rb[1]["S"] <= 0.95 * rb[1]["inc"]
            and hb[0]["S"] <= hb[0]["inc"] and hb[1]["S"] <= hb[1]["inc"]
            and ra[0]["S"] <= ra[0]["inc"] and ra[1]["S"] <= ra[1]["inc"])
    base = "S" if ok_s else "inc"; base_e = base + "_E"
    ok_e = True
    for clock in ("A", "B"):
        d = df[df.clock == clock].set_index("period"); ma = d[d.index.month.isin([3, 4])]
        ok_e &= rmse(ma[base_e] - ma["core_actual"]) <= 0.90 * rmse(ma[base] - ma["core_actual"])
        ok_e &= res[(clock, "all 90")][base_e] <= res[(clock, "all 90")][base]
        ok_e &= res[(clock, "2024+")][base_e] <= res[(clock, "2024+")][base]
    print(f"\nADOPTION: X-13 core (S) passes the 5% rule at B with A not worse: {ok_s} -> {'ADOPT S' if ok_s else 'month dummies stay'}; "
          f"Easter dummy on {base}: {ok_e} -> {'ADOPT E' if ok_e else 'no Easter term'}")


if __name__ == "__main__":
    main()
