"""SURVEY_ABLATION_SPEC.md, single run: the core block without its survey
columns, at h = 0 (headline effect through the solved core weight) and at
h = 1, 3, 6, 12 (block only). Release-eve clock, 90 backtest origins.
Usage: python survey_ablation.py
Writes output/survey_ablation.csv and output/survey_ablation_h.csv.
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
from path_experiment import _eve, rmse  # noqa: E402

CELLS = {"A0": [], "A1": ["exp12", "exp36", "exp12_x_state"], "A2": ["household_exp"], "A3": ["esi"],
         "A4": ["exp12", "exp36", "exp12_x_state", "household_exp", "esi"]}


def main():
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    alc = S.load_alc_tobacco_mm()
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period"); bt.index = pd.PeriodIndex(bt.index, freq="M")
    ext = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history_extended.csv")); ext["p"] = pd.PeriodIndex(ext["target_month"], freq="M")
    ext = ext.set_index("p"); ext = ext[ext["era"] != "flash_survey_suspect"]
    rows, hrows = [], []
    for t in bt.index:
        as_of = _eve(t)
        w = S.solve_weights(y, comp, core, reg, t - 1, as_of=as_of, alc=alc)[S._regime(t)]
        r = {"period": t, "w_core": w["core"], "STRUCT_EVE": float(bt.loc[t, "STRUCT_EVE"]), "core_actual": float(bt.loc[t, "core_actual"]),
             "actual": float(ext["actual"].get(t, np.nan)), "survey": float(ext["survey_median"].get(t, np.nan))}
        for cell, drop in CELLS.items():
            fr = feats.drop(columns=drop)
            r[cell] = S._ridge_predict(fr, core, t, as_of=as_of)[0]
            for h in (1, 3, 6, 12):
                hrows.append({"period": t, "target": t + h, "h": h, "cell": cell, "pred": S._ridge_predict(fr, core, t, h=h, as_of=as_of)[0],
                              "actual": float(core.get(t + h, np.nan))})
        rows.append(r)
    df = pd.DataFrame(rows).set_index("period")
    for cell in CELLS:
        df[f"head_{cell}"] = df["STRUCT_EVE"] + df["w_core"] * (df[cell] - df["A0"])
    df.to_csv(os.path.join(HERE, "output", "survey_ablation.csv"))
    hd = pd.DataFrame(hrows); hd.to_csv(os.path.join(HERE, "output", "survey_ablation_h.csv"), index=False)
    print(f"harness: A0 vs backtest core_pred_eve max |diff| {(df['A0'] - bt['core_pred_eve']).abs().max():.2e}")
    splits = {"all 90": np.ones(len(df), bool), "ex-January": df.index.month != 1, "2024+": df.index >= pd.Period("2024-01", "M"),
              "2025+": df.index >= pd.Period("2025-01", "M")}
    print("\nNOWCAST (release eve): core block RMSE | headline RMSE by cell | survey headline RMSE")
    print(f"{'split':12s} {'n':>3s} | " + " ".join(f"{c:>6s}" for c in CELLS) + " | " + " ".join(f"{c:>6s}" for c in CELLS) + " | survey")
    for name, m in splits.items():
        f = df[m]
        ce = [rmse(f[c] - f["core_actual"]) for c in CELLS]; he = [rmse(f[f"head_{c}"] - f["actual"]) for c in CELLS]
        print(f"{name:12s} {len(f):3d} | " + " ".join(f"{v:6.3f}" for v in ce) + " | " + " ".join(f"{v:6.3f}" for v in he) + f" | {rmse(f['survey'] - f['actual']):.3f}")
    s = df["actual"] - df["survey"]; big = s.abs() >= 0.4 - 1e-9
    print("\nbig surprises (n=%d): MAE and W-L@0.15 by cell" % int(big.sum()))
    for c in CELLS:
        e = (df[f"head_{c}"] - df["actual"]).abs(); g = s.abs() - e
        print(f"  {c}: MAE {e[big].mean():.3f}  W-L {int((g[big] >= 0.15).sum())}-{int((g[big] <= -0.15).sum())}  | mean |headline change vs A0| {(df[f'head_{c}'] - df['head_A0']).abs().mean():.3f} pp, max {(df[f'head_{c}'] - df['head_A0']).abs().max():.3f}")
    print("\nDIRECT HORIZONS, core block RMSE by cell (common valid sample; all origins | 2024+ targets):")
    hd["tp"] = pd.PeriodIndex(hd["target"].astype(str), freq="M")
    for h, g in hd.groupby("h"):
        piv = g.pivot(index="period", columns="cell", values="pred"); act = g.drop_duplicates("period").set_index("period")["actual"]
        ok = piv.notna().all(axis=1) & act.reindex(piv.index).notna()
        piv = piv[ok]; a = act.reindex(piv.index)
        rec = " ".join(f"{c} {rmse(piv[c] - a):.3f}" for c in CELLS)
        m24 = pd.PeriodIndex(piv.index, freq="M") + h >= pd.Period("2024-01", "M")
        rec24 = " ".join(f"{c} {rmse(piv.loc[m24, c] - a[m24]):.3f}" for c in CELLS)
        print(f"  h={h:2d} n={int(ok.sum()):2d}: {rec} | 2024+ (n={int(m24.sum())}): {rec24}")


if __name__ == "__main__":
    main()
