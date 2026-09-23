"""Predeclared stage-1 experiment (FLASH_SPEC.md): same-month German and
euro-area HICP component moves as extra ridge features in the food and core
blocks, release-eve clock. Single run.
Usage: python flash_experiment.py
Writes output/flash_experiment.csv.
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

SRC = os.path.join(HERE, "data", "hicp_components_ecb_mirror.csv")
FOOD_F = ["de_foodun", "de_foodpr", "ea_foodun", "ea_foodpr"]
CORE_F = ["de_neig", "de_serv", "ea_neig", "ea_serv"]
MAP = {("DE", "FOODUN"): "de_foodun", ("DE", "FOODPR"): "de_foodpr", ("U2", "FOODUN"): "ea_foodun", ("U2", "FOODPR"): "ea_foodpr",
       ("DE", "IGXE00"): "de_neig", ("DE", "SERV00"): "de_serv", ("U2", "IGXE00"): "ea_neig", ("U2", "SERV00"): "ea_serv"}


def _eve(m: pd.Period) -> pd.Timestamp:
    fr = S._first_release_dt(m)
    if pd.notna(fr):
        return fr.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=23, minutes=59)
    return m.to_timestamp(how="end").normalize() + pd.Timedelta(days=7, hours=23, minutes=59)


def load_foreign() -> pd.DataFrame:
    raw = pd.read_csv(SRC)
    raw["p"] = pd.PeriodIndex(raw["TIME_PERIOD"], freq="M")
    out = {}
    for (area, item), name in MAP.items():
        s = raw[(raw["REF_AREA"] == area) & (raw["ICP_ITEM"] == item)].set_index("p")["OBS_VALUE"].sort_index()
        out[name] = 100.0 * s.pct_change()
    return pd.DataFrame(out)


def main():
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    alc = S.load_alc_tobacco_mm()
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period"); bt.index = pd.PeriodIndex(bt.index, freq="M")
    origins = list(bt.index)
    fx = load_foreign()
    idx = feats.index
    ff = food_feats.copy(); cf = feats.copy()
    for c in FOOD_F:
        ff[c] = fx[c].reindex(idx)
    for c in CORE_F:
        cf[c] = fx[c].reindex(idx)
    print(f"foreign data {fx.dropna().index.min()}..{fx.dropna().index.max()}; origins with data: "
          f"{int(sum(1 for t in origins if t in fx.dropna().index))} of {len(origins)}")
    rows = []
    last_coef = None
    for t in origins:
        as_of = _eve(t)
        inc_food = S.food_forecast(comp["food"], food_feats, t, as_of=as_of)
        aug_food = S.food_forecast(comp["food"], ff, t, as_of=as_of)
        inc_core, _, _ = S._ridge_predict(feats, core, t, as_of=as_of)
        aug_core, _, mats = S._ridge_predict(cf, core, t, as_of=as_of)
        wmap = S.solve_weights(y, comp, core, reg, t - 1, as_of=t.to_timestamp(how="end"), alc=alc)[S._regime(t)]
        rows.append({"period": t, "has_data": t in fx.dropna().index,
                     "inc_food": inc_food, "aug_food": aug_food, "bt_food": bt.loc[t, "food_pred_eve"], "food_actual": bt.loc[t, "food_actual"],
                     "inc_core": inc_core, "aug_core": aug_core, "bt_core": bt.loc[t, "core_pred_eve"], "core_actual": bt.loc[t, "core_actual"],
                     "w_food": wmap["food"], "w_core": wmap["core"], "STRUCT_EVE": bt.loc[t, "STRUCT_EVE"]})
        if t == origins[-1] and mats is not None:
            Z, z0, tri = mats
            Xt = cf.loc[tri]; mu = Xt.mean(); Xt = Xt.fillna(mu); sd = Xt.std().replace(0, 1.0); ys = core.loc[tri].values
            beta = np.linalg.solve(Z.T @ Z + S.RIDGE_ALPHA * np.eye(Z.shape[1]), Z.T @ (ys - ys.mean()))
            last_coef = pd.Series(beta / sd.values, index=cf.columns)[CORE_F]
    df = pd.DataFrame(rows).set_index("period")
    ext = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history_extended.csv")); ext["p"] = pd.PeriodIndex(ext["target_month"], freq="M")
    ext = ext.set_index("p"); ext = ext[ext["era"] != "flash_survey_suspect"]
    df["actual"] = ext["actual"].reindex(df.index); df["survey"] = ext["survey_median"].reindex(df.index)
    df["head_food"] = df["STRUCT_EVE"] + df["w_food"] * (df["aug_food"] - df["inc_food"])
    df["head_core"] = df["STRUCT_EVE"] + df["w_core"] * (df["aug_core"] - df["inc_core"])
    df["head_both"] = df["STRUCT_EVE"] + df["w_food"] * (df["aug_food"] - df["inc_food"]) + df["w_core"] * (df["aug_core"] - df["inc_core"])
    df.to_csv(os.path.join(HERE, "output", "flash_experiment.csv"))
    print(f"harness: food max|diff| {(df['inc_food']-df['bt_food']).abs().max():.2e}, core {(df['inc_core']-df['bt_core']).abs().max():.2e}")

    def rmse(e): e = pd.Series(e).dropna(); return float(np.sqrt((e ** 2).mean()))
    splits = {"all 90": np.ones(len(df), bool), "83 with data": df["has_data"].values, "ex-January": df.index.month != 1,
              "2024+": df.index >= pd.Period("2024-01", "M"), "2024+ ex-Jan": (df.index >= pd.Period("2024-01", "M")) & (df.index.month != 1),
              "2025+ flash era": df.index >= pd.Period("2025-01", "M")}
    res, hres = {}, {}
    print("\nBLOCK RMSE (MAE) vs realised block m/m, clock B | HEADLINE RMSE vs first release")
    print(f"{'split':16s} {'n':>3s} | {'food inc':>9s} {'food+fx':>9s} {'d%':>6s} | {'core inc':>9s} {'core+fx':>9s} {'d%':>6s} | {'head inc':>8s} {'+food':>7s} {'+core':>7s} {'+both':>7s} | survey")
    for name, m in splits.items():
        f = df[m]
        fi, fa = rmse(f["inc_food"] - f["food_actual"]), rmse(f["aug_food"] - f["food_actual"])
        ci, ca = rmse(f["inc_core"] - f["core_actual"]), rmse(f["aug_core"] - f["core_actual"])
        hi = rmse(f["STRUCT_EVE"] - f["actual"]); hf = rmse(f["head_food"] - f["actual"]); hc = rmse(f["head_core"] - f["actual"]); hb = rmse(f["head_both"] - f["actual"])
        res[name] = (fi, fa, ci, ca); hres[name] = (hi, hf, hc, hb)
        print(f"{name:16s} {len(f):3d} | {fi:9.3f} {fa:9.3f} {100*(fa/fi-1):+5.1f}% | {ci:9.3f} {ca:9.3f} {100*(ca/ci-1):+5.1f}% | {hi:8.4f} {hf:7.4f} {hc:7.4f} {hb:7.4f} | {rmse(f['survey']-f['actual']):.4f}")
    s = df["actual"] - df["survey"]; big = s.abs() >= 0.4 - 1e-8
    for col, lab in (("STRUCT_EVE", "incumbent"), ("head_food", "+food fx"), ("head_core", "+core fx"), ("head_both", "+both")):
        e = (df[col] - df["actual"]).abs(); g = s.abs() - e
        print(f"  {lab:10s} big-surprise MAE {e[big].mean():.3f} (n={int(big.sum())}), W-L@0.15 {int((g[big]>=0.15).sum())}-{int((g[big]<=-0.15).sum())}")
    print("\nDIAGNOSTICS: corr of foreign features with the CZ block m/m (same month, 2015+):")
    cz_food = comp["food"].reindex(fx.index); cz_core = core.reindex(fx.index)
    for c in FOOD_F: print(f"  {c:10s} vs CZ food m/m {fx[c].corr(cz_food):+.2f}")
    for c in CORE_F: print(f"  {c:10s} vs CZ core m/m {fx[c].corr(cz_core):+.2f}")
    if last_coef is not None: print("core ridge coefficients on foreign features at the last origin (pp per pp):", last_coef.round(3).to_dict())
    print(f"mean |aug-inc|: food {float((df['aug_food']-df['inc_food']).abs().mean()):.3f} pp, core {float((df['aug_core']-df['inc_core']).abs().mean()):.3f} pp")
    ok_food = res["all 90"][1] <= 0.95 * res["all 90"][0] and res["2024+"][1] <= 0.95 * res["2024+"][0] and hres["all 90"][1] <= hres["all 90"][0] and hres["2024+"][1] <= hres["2024+"][0]
    ok_core = res["all 90"][3] <= 0.95 * res["all 90"][2] and res["2024+"][3] <= 0.95 * res["2024+"][2] and hres["all 90"][2] <= hres["all 90"][0] and hres["2024+"][2] <= hres["2024+"][0]
    print(f"\nSTAGE-1 RULE: food features carry to stage 2: {ok_food}; core features carry to stage 2: {ok_core}")


if __name__ == "__main__":
    main()
