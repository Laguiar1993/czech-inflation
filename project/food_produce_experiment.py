"""Predeclared produce-split experiment (FOOD_PRODUCE_SPEC.md): REST of food
with the incumbent recipe, PRODUCE (fruit + vegetables) with expanding
same-month means, recombined with price-updated shares. Single run.
Usage: python food_produce_experiment.py
Writes output/food_produce_experiment.csv.
"""
import hashlib
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cz_struct as S  # noqa: E402
from data import food_categories as fc  # noqa: E402
from data import local_adapter as la  # noqa: E402

PRODUCE = ["0116", "0117"]
REST = [c for c in fc.CLASSES if c not in PRODUCE]
_X13 = {}


def _eve(m: pd.Period) -> pd.Timestamp:
    fr = S._first_release_dt(m)
    if pd.notna(fr):
        return fr.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=23, minutes=59)
    return m.to_timestamp(how="end").normalize() + pd.Timedelta(days=7, hours=23, minutes=59)


def rest_forecast(rest_mm: pd.Series, rest_feats: pd.DataFrame, origin: pd.Period, as_of) -> float:
    """The incumbent recipe applied to the REST series."""
    from statsmodels.tsa.x13 import x13_arima_analysis
    hist = rest_mm.dropna(); hist = hist[hist.index <= origin - 1]; hist = hist[S._released_index(hist.index, as_of)]
    key = (str(origin), len(hist), hashlib.sha1(np.ascontiguousarray(hist.values, dtype=float).tobytes()).hexdigest())
    try:
        if key in _X13:
            sa, seas = _X13[key]
        else:
            ts = hist.copy(); ts.index = ts.index.to_timestamp()
            sa = x13_arima_analysis(ts, x12path=la._X13_PATH, prefer_x13=True).seasadj; sa.index = hist.index
            seas = (hist - sa).dropna(); _X13[key] = (sa, seas)
        s_m = seas[seas.index.month == origin.month]; s_add = float(s_m.iloc[-3:].mean()) if len(s_m) else 0.0
        p, _, _ = S._ridge_predict(rest_feats, sa, origin, as_of=as_of)
        if np.isnan(p):
            raise ValueError("nan")
        return p + s_add
    except Exception:
        ff = rest_feats.copy()
        ff["seas_mean"] = hist.groupby(hist.index.month).transform(lambda s: s.expanding().mean().shift(1)).reindex(ff.index)
        same = hist[hist.index.month == origin.month]
        if origin in ff.index and len(same):
            ff.loc[origin, "seas_mean"] = float(same.mean())
        p, _, _ = S._ridge_predict(ff, rest_mm, origin, as_of=as_of)
        return p


def same_month_mean(series: pd.Series, origin: pd.Period, as_of) -> float:
    hist = series.dropna(); hist = hist[hist.index <= origin - 1]; hist = hist[S._released_index(hist.index, as_of)]
    same = hist[hist.index.month == origin.month]
    return float(same.mean()) if len(same) >= 3 else float(hist.mean())


def main():
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    alc = S.load_alc_tobacco_mm()
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period"); bt.index = pd.PeriodIndex(bt.index, freq="M")
    origins = list(bt.index)
    lv = fc.load_class_levels(); mm = fc.load_class_mm(); wts = fc.load_class_weights()
    full_idx = food_feats.index
    shares = {"A": fc.price_updated_shares(lv, wts, S._regime, as_of_fn=lambda m: m.to_timestamp(how="end"), available_from_fn=S._basket_available_from),
              "B": fc.price_updated_shares(lv, wts, S._regime, as_of_fn=_eve, available_from_fn=S._basket_available_from)}
    rows = []
    for clock in ("A", "B"):
        sh = shares[clock]
        # REST m/m series: share-weighted aggregate of the eight non-produce classes (shares renormalised within REST)
        w_rest = sh[REST].div(sh[REST].sum(axis=1), axis=0)
        rest_mm = (mm[REST].reindex(w_rest.index) * w_rest).sum(axis=1).reindex(mm.index)
        rest_mm[rest_mm.index < w_rest.index.min()] = np.nan
        rest_mm.name = "rest_mm"
        rf = food_feats.copy()
        rf["food_l1"] = S._lag(rest_mm, 1, full_idx); rf["food_l12"] = S._lag(rest_mm, 12, full_idx)
        for t in origins:
            as_of = t.to_timestamp(how="end") if clock == "A" else _eve(t)
            inc = S.food_forecast(comp["food"], food_feats, t, as_of=as_of)
            rest = rest_forecast(rest_mm, rf, t, as_of)
            s_prod = float(sh.loc[t, PRODUCE].sum()) if t in sh.index else np.nan
            w_in = sh.loc[t, PRODUCE] / sh.loc[t, PRODUCE].sum()
            prod = sum(w_in[c] * same_month_mean(mm[c], t, as_of) for c in PRODUCE)
            split = (1 - s_prod) * rest + s_prod * prod
            r = {"period": t, "clock": clock, "inc": inc, "split": split, "rest_fc": rest, "prod_fc": prod, "s_prod": s_prod,
                 "food_actual": bt.loc[t, "food_actual"], "bt_food": bt.loc[t, "food_pred" if clock == "A" else "food_pred_eve"],
                 "STRUCT": bt.loc[t, "STRUCT" if clock == "A" else "STRUCT_EVE"]}
            if clock == "A":
                r["w_food"] = S.solve_weights(y, comp, core, reg, t - 1, as_of=as_of, alc=alc)[S._regime(t)]["food"]
            rows.append(r)
    df = pd.DataFrame(rows)
    df["w_food"] = df.groupby("period")["w_food"].transform("first")
    ext = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history_extended.csv")); ext["p"] = pd.PeriodIndex(ext["target_month"], freq="M")
    ext = ext.set_index("p"); ext = ext[ext["era"] != "flash_survey_suspect"]
    df["actual"] = df["period"].map(ext["actual"]); df["survey"] = df["period"].map(ext["survey_median"])
    df["head_split"] = df["STRUCT"] + df["w_food"] * (df["split"] - df["inc"])
    df.to_csv(os.path.join(HERE, "output", "food_produce_experiment.csv"), index=False)
    a = df[df.clock == "A"].set_index("period")
    print(f"harness: incumbent vs backtest food_pred max|diff| {(a['inc'] - a['bt_food']).abs().max():.2e}; mean produce share {a['s_prod'].mean():.3f}")

    def rmse(e): e = pd.Series(e).dropna(); return float(np.sqrt((e ** 2).mean()))
    res, hres = {}, {}
    for clock in ("A", "B"):
        d = df[df.clock == clock].set_index("period")
        splits = {"all 90": np.ones(len(d), bool), "ex-January": d.index.month != 1, "2024+": d.index >= pd.Period("2024-01", "M"),
                  "2024+ ex-Jan": (d.index >= pd.Period("2024-01", "M")) & (d.index.month != 1), "2025+ flash era": d.index >= pd.Period("2025-01", "M"),
                  "produce months": d.index.month.isin([4, 5, 9, 10])}
        print(f"\n=== clock {clock}: FOOD BLOCK RMSE (MAE) | HEADLINE RMSE ===")
        for name, m in splits.items():
            f = d[m]
            ri, ra = rmse(f["inc"] - f["food_actual"]), rmse(f["split"] - f["food_actual"])
            hi, ha = rmse(f["STRUCT"] - f["actual"]), rmse(f["head_split"] - f["actual"])
            res[(clock, name)] = (ri, ra); hres[(clock, name)] = (hi, ha)
            print(f"{name:16s} n={len(f):2d} | inc {ri:.3f} ({float((f['inc']-f['food_actual']).abs().mean()):.3f})  split {ra:.3f} ({float((f['split']-f['food_actual']).abs().mean()):.3f})  {100*(ra/ri-1):+5.1f}% | head {hi:.4f} -> {ha:.4f} ({100*(ha/hi-1):+.1f}%)")
    ok = (res[("B", "all 90")][1] <= 0.95 * res[("B", "all 90")][0] and res[("B", "2024+")][1] <= 0.95 * res[("B", "2024+")][0]
          and hres[("B", "all 90")][1] <= hres[("B", "all 90")][0] and hres[("B", "2024+")][1] <= hres[("B", "2024+")][0]
          and res[("A", "all 90")][1] <= res[("A", "all 90")][0] and res[("A", "2024+")][1] <= res[("A", "2024+")][0])
    print(f"\nADOPTION RULE: {'ADOPT produce split' if ok else 'RECORD AND CLOSE'}")


if __name__ == "__main__":
    main()
