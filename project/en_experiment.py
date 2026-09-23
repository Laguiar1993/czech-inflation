"""Predeclared elastic-net experiment (EN_SPEC.md): ridge vs elastic net on
the incumbent feature sets, and elastic net on the incumbent sets plus the
foreign HICP series, for the core and food blocks. Single run, release-eve.
Usage: python en_experiment.py
Writes output/en_experiment.csv and output/en_selection.csv.
"""
import hashlib
import os
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNetCV
from sklearn.model_selection import TimeSeriesSplit

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cz_struct as S  # noqa: E402
from data import local_adapter as la  # noqa: E402
from flash_experiment import load_foreign, FOOD_F, CORE_F  # noqa: E402

L1_RATIO = 0.5
_X13 = {}


def _eve(m: pd.Period) -> pd.Timestamp:
    fr = S._first_release_dt(m)
    if pd.notna(fr):
        return fr.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=23, minutes=59)
    return m.to_timestamp(how="end").normalize() + pd.Timedelta(days=7, hours=23, minutes=59)


def enet_predict(Xdf: pd.DataFrame, ydf: pd.Series, origin: pd.Period, as_of):
    """_ridge_predict's data handling with ElasticNetCV (l1_ratio fixed,
    penalty by expanding time-series folds inside the training window)."""
    train_idx = ydf.dropna().index
    train_idx = train_idx[train_idx <= origin - 1]
    train_idx = train_idx[[S._cpi_family_released_by(u, as_of) for u in train_idx]]
    if len(train_idx) < 48 or origin not in Xdf.index:
        return np.nan, None, np.nan
    Xt = Xdf.loc[train_idx]; mu = Xt.mean(); Xt = Xt.fillna(mu)
    xrow = Xdf.loc[[origin]].fillna(mu)
    ys = ydf.loc[train_idx].values
    m, s = Xt.mean().values, Xt.std().replace(0, 1.0).values
    Z = (Xt.values - m) / s; z0 = (xrow.values - m) / s
    model = ElasticNetCV(l1_ratio=L1_RATIO, cv=TimeSeriesSplit(n_splits=5), n_alphas=50, max_iter=20000, fit_intercept=True)
    model.fit(Z, ys)
    pred = float(model.predict(z0)[0])
    coef = pd.Series(model.coef_, index=Xdf.columns)
    return pred, coef, float(model.alpha_)


def food_enet(food: pd.Series, feats: pd.DataFrame, origin: pd.Period, as_of):
    """food_forecast's recipe with the elastic net on the SA target."""
    from statsmodels.tsa.x13 import x13_arima_analysis
    hist = food.dropna(); hist = hist[hist.index <= origin - 1]; hist = hist[S._released_index(hist.index, as_of)]
    key = (str(origin), len(hist), hashlib.sha1(np.ascontiguousarray(hist.values, dtype=float).tobytes()).hexdigest())
    if key in _X13:
        sa, seas = _X13[key]
    else:
        ts = hist.copy(); ts.index = ts.index.to_timestamp()
        sa = x13_arima_analysis(ts, x12path=la._X13_PATH, prefer_x13=True).seasadj; sa.index = hist.index
        seas = (hist - sa).dropna(); _X13[key] = (sa, seas)
    s_m = seas[seas.index.month == origin.month]; s_add = float(s_m.iloc[-3:].mean()) if len(s_m) else 0.0
    p, coef, lam = enet_predict(feats, sa, origin, as_of)
    return (p + s_add if np.isfinite(p) else np.nan), coef, lam


def main():
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    alc = S.load_alc_tobacco_mm()
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period"); bt.index = pd.PeriodIndex(bt.index, freq="M")
    origins = list(bt.index)
    fx = load_foreign(); idx = feats.index
    cf2 = feats.copy(); ff2 = food_feats.copy()
    for c in CORE_F: cf2[c] = fx[c].reindex(idx)
    for c in FOOD_F: ff2[c] = fx[c].reindex(idx)
    rows, sel = [], []
    for t in origins:
        as_of = _eve(t)
        c0, _, _ = S._ridge_predict(feats, core, t, as_of=as_of)
        c1, k1, l1 = enet_predict(feats, core, t, as_of)
        c2, k2, l2 = enet_predict(cf2, core, t, as_of)
        f0 = S.food_forecast(comp["food"], food_feats, t, as_of=as_of)
        f1, kf1, lf1 = food_enet(comp["food"], food_feats, t, as_of)
        f2, kf2, lf2 = food_enet(comp["food"], ff2, t, as_of)
        w = S.solve_weights(y, comp, core, reg, t - 1, as_of=t.to_timestamp(how="end"), alc=alc)[S._regime(t)]
        rows.append({"period": t, "C0": c0, "C1": c1, "C2": c2, "F0": f0, "F1": f1, "F2": f2, "w_core": w["core"], "w_food": w["food"],
                     "bt_core": bt.loc[t, "core_pred_eve"], "bt_food": bt.loc[t, "food_pred_eve"],
                     "core_actual": bt.loc[t, "core_actual"], "food_actual": bt.loc[t, "food_actual"], "STRUCT_EVE": bt.loc[t, "STRUCT_EVE"],
                     "lam_C1": l1, "lam_C2": l2, "lam_F1": lf1, "lam_F2": lf2,
                     "nz_C1": int((k1 != 0).sum()) if k1 is not None else np.nan, "nz_C2": int((k2 != 0).sum()) if k2 is not None else np.nan,
                     "nz_F1": int((kf1 != 0).sum()) if kf1 is not None else np.nan, "nz_F2": int((kf2 != 0).sum()) if kf2 is not None else np.nan})
        for name, k in (("C1", k1), ("C2", k2), ("F1", kf1), ("F2", kf2)):
            if k is not None:
                for feat, v in k.items():
                    sel.append({"period": str(t), "cell": name, "feature": feat, "coef": float(v)})
    df = pd.DataFrame(rows).set_index("period"); pd.DataFrame(sel).to_csv(os.path.join(HERE, "output", "en_selection.csv"), index=False)
    ext = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history_extended.csv")); ext["p"] = pd.PeriodIndex(ext["target_month"], freq="M")
    ext = ext.set_index("p"); ext = ext[ext["era"] != "flash_survey_suspect"]
    df["actual"] = ext["actual"].reindex(df.index); df["survey"] = ext["survey_median"].reindex(df.index)
    for c in ("C1", "C2"): df[f"head_{c}"] = df["STRUCT_EVE"] + df["w_core"] * (df[c] - df["C0"])
    for c in ("F1", "F2"): df[f"head_{c}"] = df["STRUCT_EVE"] + df["w_food"] * (df[c] - df["F0"])
    df.to_csv(os.path.join(HERE, "output", "en_experiment.csv"))
    print(f"harness: C0 vs backtest {(df['C0']-df['bt_core']).abs().max():.2e}; F0 vs backtest {(df['F0']-df['bt_food']).abs().max():.2e}")

    def rmse(e): e = pd.Series(e).dropna(); return float(np.sqrt((e ** 2).mean()))
    splits = {"all 90": np.ones(len(df), bool), "ex-January": df.index.month != 1, "2024+": df.index >= pd.Period("2024-01", "M"),
              "2024+ ex-Jan": (df.index >= pd.Period("2024-01", "M")) & (df.index.month != 1), "2025+ flash era": df.index >= pd.Period("2025-01", "M")}
    res, hres = {}, {}
    print("\nCORE BLOCK RMSE | FOOD BLOCK RMSE | HEADLINE RMSE (release eve)")
    print(f"{'split':16s} {'n':>3s} | {'C0 ridge':>8s} {'C1 enet':>8s} {'C2 +fx':>8s} | {'F0 ridge':>8s} {'F1 enet':>8s} {'F2 +fx':>8s} | {'head':>7s} {'C1':>7s} {'C2':>7s} {'F1':>7s} {'F2':>7s} | survey")
    for name, m in splits.items():
        f = df[m]
        ce = {c: rmse(f[c] - f["core_actual"]) for c in ("C0", "C1", "C2")}; fe = {c: rmse(f[c] - f["food_actual"]) for c in ("F0", "F1", "F2")}
        he = {"head": rmse(f["STRUCT_EVE"] - f["actual"]), **{c: rmse(f[f"head_{c}"] - f["actual"]) for c in ("C1", "C2", "F1", "F2")}}
        res[name] = {**ce, **fe}; hres[name] = he
        print(f"{name:16s} {len(f):3d} | {ce['C0']:8.3f} {ce['C1']:8.3f} {ce['C2']:8.3f} | {fe['F0']:8.3f} {fe['F1']:8.3f} {fe['F2']:8.3f} | "
              f"{he['head']:7.4f} {he['C1']:7.4f} {he['C2']:7.4f} {he['F1']:7.4f} {he['F2']:7.4f} | {rmse(f['survey']-f['actual']):.4f}")
    s = df["actual"] - df["survey"]; big = s.abs() >= 0.4 - 1e-8
    for col, lab in (("STRUCT_EVE", "incumbent"), ("head_C1", "C1"), ("head_C2", "C2"), ("head_F1", "F1"), ("head_F2", "F2")):
        e = (df[col] - df["actual"]).abs(); g = s.abs() - e
        print(f"  {lab:10s} big-surprise MAE {e[big].mean():.3f}, W-L@0.15 {int((g[big]>=0.15).sum())}-{int((g[big]<=-0.15).sum())}")
    print("\nSELECTION: median non-zero coefficients per origin: " + ", ".join(f"{c} {df[f'nz_{c}'].median():.0f}" for c in ("C1", "C2", "F1", "F2"))
          + " | median penalty: " + ", ".join(f"{c} {df[f'lam_{c}'].median():.3f}" for c in ("C1", "C2", "F1", "F2")))
    sd = pd.DataFrame(sel)
    for cell in ("C1", "C2", "F1", "F2"):
        g = sd[sd.cell == cell]; share = (g.groupby("feature")["coef"].apply(lambda v: (v != 0).mean())).sort_values()
        print(f"  {cell}: kept in fewest origins -> {share.head(6).round(2).to_dict()}")
        if cell in ("C2", "F2"):
            print(f"      foreign features kept share -> {share[[f for f in share.index if f in CORE_F + FOOD_F]].round(2).to_dict()}")
    r, h = res, hres
    ok_c1 = r["all 90"]["C1"] <= 0.95 * r["all 90"]["C0"] and r["2024+"]["C1"] <= 0.95 * r["2024+"]["C0"] and h["all 90"]["C1"] <= h["all 90"]["head"] and h["2024+"]["C1"] <= h["2024+"]["head"]
    ok_f1 = r["all 90"]["F1"] <= 0.95 * r["all 90"]["F0"] and r["2024+"]["F1"] <= 0.95 * r["2024+"]["F0"] and h["all 90"]["F1"] <= h["all 90"]["head"] and h["2024+"]["F1"] <= h["2024+"]["head"]
    ok_c2 = all(r[w_]["C2"] <= 0.95 * min(r[w_]["C0"], r[w_]["C1"]) for w_ in ("all 90", "2024+")) and h["all 90"]["C2"] <= h["all 90"]["head"] and h["2024+"]["C2"] <= h["2024+"]["head"]
    ok_f2 = all(r[w_]["F2"] <= 0.95 * min(r[w_]["F0"], r[w_]["F1"]) for w_ in ("all 90", "2024+")) and h["all 90"]["F2"] <= h["all 90"]["head"] and h["2024+"]["F2"] <= h["2024+"]["head"]
    print(f"\nRULES: C1 replaces core ridge {ok_c1}; F1 replaces food ridge {ok_f1}; C2 to flash stage 2 {ok_c2}; F2 to flash stage 2 {ok_f2}")


if __name__ == "__main__":
    main()
