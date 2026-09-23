"""Predeclared alcohol-and-tobacco block experiment (ALC_TOBACCO_SPEC.md):
incumbent expanding same-month mean vs five-year same-month mean (W5) vs
five-year means of the alcohol and tobacco sub-indices aggregated with
price-updated basket shares (W5-split). Single run, two clocks.
Usage: python alc_tobacco_experiment.py
Writes output/alc_tobacco_experiment.csv.
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

WINDOW = 5
MIN_OBS = 3
SUB = {"021": "alcohol", "023": "tobacco"}
_BASKET_CODES = {"021": ["02.1"], "023": ["02.2", "02.3"]}   # ECOICOP vs COICOP-2018 file codes


def _eve(m: pd.Period) -> pd.Timestamp:
    fr = S._first_release_dt(m)
    if pd.notna(fr):
        return fr.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=23, minutes=59)
    return m.to_timestamp(how="end").normalize() + pd.Timedelta(days=7, hours=23, minutes=59)


def load_sub_levels() -> pd.DataFrame:
    con = la._con()
    df = con.sql("""SELECT date, subgroup_code, value FROM cpi_czso.cpi_long
                    WHERE coicop_code='02' AND base='base_2015_eq_100' AND hh_group_code='0'
                      AND subgroup_code IN ('021','023') ORDER BY date""").df()
    con.close()
    df["p"] = pd.PeriodIndex(pd.to_datetime(df["date"]), freq="M")
    return df.pivot_table(index="p", columns="subgroup_code", values="value", aggfunc="last").sort_index()


def load_sub_weights() -> pd.DataFrame:
    out = {}
    for f in sorted(os.listdir(os.path.join(HERE, "data", "baskets"))):
        if not (f.startswith("spot_kos") and f.endswith(".xlsx")):
            continue
        regime = int(f[8:12])
        x = pd.read_excel(os.path.join(HERE, "data", "baskets", f), header=None)
        codes = x[0].astype(str).str.strip().str.lstrip("E"); w = pd.to_numeric(x[4], errors="coerce")
        row = {}
        for sub, cands in _BASKET_CODES.items():
            for c in cands:
                hit = w[codes == c]
                if len(hit):
                    row[sub] = float(hit.iloc[0]); break
        out[regime] = row
    return pd.DataFrame(out).T.sort_index()


def shares_for(t: pd.Period, as_of, levels: pd.DataFrame, weights: pd.DataFrame) -> dict:
    reg = S._regime(t)
    if pd.Timestamp(as_of) < S._basket_available_from(reg):
        reg -= 2
    if reg not in weights.index:
        reg = weights.index[weights.index <= reg].max() if (weights.index <= reg).any() else weights.index.min()
    ref = pd.Period(f"{reg - 1}-12", freq="M"); prev = t - 1
    s = {}
    for sub in SUB:
        if ref in levels.index and prev in levels.index and np.isfinite(levels.loc[ref, sub]) and np.isfinite(levels.loc[prev, sub]):
            s[sub] = weights.loc[reg, sub] * levels.loc[prev, sub] / levels.loc[ref, sub]
        else:
            s[sub] = weights.loc[reg, sub]
    tot = sum(s.values())
    return {k: v / tot for k, v in s.items()}


def window_mean(series: pd.Series, target: pd.Period, known_through: pd.Period, as_of, window=WINDOW, min_obs=MIN_OBS):
    hist = series.dropna(); hist = hist[hist.index <= known_through]
    hist = hist[S._released_index(hist.index, as_of)]
    same = hist[hist.index.month == target.month]
    if len(same) >= min_obs:
        return float(same.tail(window).mean()), True
    return np.nan, False


def main():
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    alc = S.load_alc_tobacco_mm()
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period")
    bt.index = pd.PeriodIndex(bt.index, freq="M")
    origins = list(bt.index)
    lv = load_sub_levels(); mm = 100.0 * lv.pct_change(); wts = load_sub_weights()
    rows = []
    for t in origins:
        for clock, as_of in (("A", t.to_timestamp(how="end")), ("B", _eve(t))):
            r = {"period": t, "clock": clock}
            r["inc"] = S.alc_forecast(alc, t, t - 1, as_of=as_of)
            w5, ok = window_mean(alc, t, t - 1, as_of)
            r["W5"] = w5 if ok else r["inc"]
            sh = shares_for(t, as_of, lv, wts)
            parts = {}
            for sub in SUB:
                v, oks = window_mean(mm[sub], t, t - 1, as_of)
                parts[sub] = v if oks else r["W5"]
            r["W5_split"] = sum(sh[s_] * parts[s_] for s_ in SUB)
            r["share_tobacco"] = sh["023"]
            if clock == "A":
                wmap = S.solve_weights(y, comp, core, reg, t - 1, as_of=as_of, alc=alc)
                r["w_alc"] = wmap[S._regime(t)]["alc"]
            rows.append(r)
    df = pd.DataFrame(rows)
    df["w_alc"] = df.groupby("period")["w_alc"].transform("first")
    df["alc_actual"] = df["period"].map(bt["alc_actual"]); df["bt_alc_pred"] = df["period"].map(bt["alc_pred"])
    df["STRUCT"] = np.where(df["clock"] == "A", df["period"].map(bt["STRUCT"]), df["period"].map(bt["STRUCT_EVE"]))
    ext = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history_extended.csv"))
    ext["p"] = pd.PeriodIndex(ext["target_month"], freq="M"); ext = ext.set_index("p"); ext = ext[ext["era"] != "flash_survey_suspect"]
    df["actual"] = df["period"].map(ext["actual"]); df["survey"] = df["period"].map(ext["survey_median"])
    cells = ["inc", "W5", "W5_split"]
    for c in cells:
        df[f"head_{c}"] = df["STRUCT"] + df["w_alc"] * (df[c] - df["inc"])
    df.to_csv(os.path.join(HERE, "output", "alc_tobacco_experiment.csv"), index=False)

    a = df[df.clock == "A"].set_index("period")
    print(f"harness: incumbent vs backtest alc_pred max|diff| {(a['inc'] - a['bt_alc_pred']).abs().max():.2e}")
    b = df[df.clock == "B"].set_index("period")
    print(f"clock B vs A: max|diff| W5 {float((b['W5'] - a['W5']).abs().max()):.2e}, split {float((b['W5_split'] - a['W5_split']).abs().max()):.2e}")

    def rmse(e): e = pd.Series(e).dropna(); return float(np.sqrt((e ** 2).mean()))
    res, hres = {}, {}
    for clock in ("A", "B"):
        d = df[df.clock == clock].set_index("period")
        splits = {"all 90": np.ones(len(d), bool), "ex-January": d.index.month != 1,
                  "2024+": d.index >= pd.Period("2024-01", "M"),
                  "2024+ ex-Jan": (d.index >= pd.Period("2024-01", "M")) & (d.index.month != 1),
                  "2025+ flash era": d.index >= pd.Period("2025-01", "M"),
                  "January only": d.index.month == 1, "Feb-Apr only": d.index.month.isin([2, 3, 4])}
        print(f"\n=== clock {clock}: BLOCK RMSE (MAE) vs realised division-02 m/m | HEADLINE RMSE vs first release ===")
        print(f"{'split':16s} {'n':>3s} | {'inc':>13s} {'W5':>13s} {'W5-split':>13s} | {'head inc':>8s} {'W5':>7s} {'split':>7s} | survey")
        for name, m in splits.items():
            f = d[m]
            ce = {c: (rmse(f[c] - f["alc_actual"]), float((f[c] - f["alc_actual"]).abs().mean())) for c in cells}
            he = {c: rmse(f[f"head_{c}"] - f["actual"]) for c in cells}
            res[(clock, name)] = {c: ce[c][0] for c in cells}; hres[(clock, name)] = he
            print(f"{name:16s} {len(f):3d} | " + " ".join(f"{ce[c][0]:6.3f} ({ce[c][1]:.3f})" for c in cells)
                  + f" | {he['inc']:8.4f} {he['W5']:7.4f} {he['W5_split']:7.4f} | {rmse(f['survey'] - f['actual']):.4f}")
        s = d["actual"] - d["survey"]; big = s.abs() >= 0.4 - 1e-8
        for c in cells:
            e = (d[f"head_{c}"] - d["actual"]).abs(); g = s.abs() - e
            print(f"  {c:9s} big-surprise MAE {e[big].mean():.3f} (n={int(big.sum())}), W-L@0.15 {int((g[big]>=0.15).sum())}-{int((g[big]<=-0.15).sum())}, "
                  f"block bias {float((d[c]-d['alc_actual']).mean()):+.3f}, January bias {float((d.loc[d.index.month==1, c]-d.loc[d.index.month==1,'alc_actual']).mean()):+.3f}")

    def passes(c):
        rb = res[("B", "all 90")], res[("B", "2024+")]; hb = hres[("B", "all 90")], hres[("B", "2024+")]; ra = res[("A", "all 90")], res[("A", "2024+")]
        return (rb[0][c] <= 0.95 * rb[0]["inc"] and rb[1][c] <= 0.95 * rb[1]["inc"] and hb[0][c] <= hb[0]["inc"]
                and hb[1][c] <= hb[1]["inc"] and ra[0][c] <= ra[0]["inc"] and ra[1][c] <= ra[1]["inc"])
    ok_w5, ok_split = passes("W5"), passes("W5_split")
    choice = "none"
    if ok_w5:
        choice = "W5"
        if ok_split and res[("B", "all 90")]["W5_split"] <= 0.95 * res[("B", "all 90")]["W5"] and res[("B", "2024+")]["W5_split"] <= 0.95 * res[("B", "2024+")]["W5"]:
            choice = "W5_split"
    elif ok_split:
        choice = "W5_split"
    print(f"\nADOPTION: W5 passes {ok_w5}; W5-split passes {ok_split} -> {'ADOPT ' + choice if choice != 'none' else 'RECORD AND CLOSE'}")


if __name__ == "__main__":
    main()
