"""Predeclared food-block experiment: weekly SZIF farmgate/processor prices
as one extra ridge feature -- see FOOD_SZIF_SPEC.md. Single run, two clocks.
Usage: python food_szif_experiment.py
Writes output/food_szif_experiment.csv and output/food_szif_signal.csv.
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
from data import szif_weekly as sw  # noqa: E402


def _eve(m: pd.Period) -> pd.Timestamp:
    fr = S._first_release_dt(m)
    if pd.notna(fr):
        return fr.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=23, minutes=59)
    # months before the calendar (training rows only): month end + 7 days
    return m.to_timestamp(how="end").normalize() + pd.Timedelta(days=7, hours=23, minutes=59)


def _rmse(e):
    e = pd.Series(e).dropna()
    return float(np.sqrt((e ** 2).mean())), int(len(e))


def main():
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    alc = S.load_alc_tobacco_mm()
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period")
    bt.index = pd.PeriodIndex(bt.index, freq="M")
    origins = list(bt.index)

    weekly = sw.load_weekly_czk()
    idx = food_feats.index
    clock_a = pd.Series({m: m.to_timestamp(how="end") for m in idx})
    clock_b = pd.Series({m: _eve(m) for m in idx})
    sig_a, diag_a = sw.month_signal(weekly, clock_a)
    sig_b, diag_b = sw.month_signal(weekly, clock_b)
    pd.concat({"szif_mm_A": sig_a, "szif_mm_B": sig_b,
               "weeks_used_A": diag_a["n_weeks_used"], "weeks_used_B": diag_b["n_weeks_used"],
               "weeks_month": diag_a["n_weeks_month"]}, axis=1).to_csv(
        os.path.join(HERE, "output", "food_szif_signal.csv"))
    print(f"signal: {sig_a.notna().sum()} months A / {sig_b.notna().sum()} months B, "
          f"{sig_a.dropna().index.min()}..{sig_a.dropna().index.max()}; "
          f"weeks unrecorded pub date: {int((~weekly['pub_recorded']).sum())} of {len(weekly)} rows")
    ff_a = food_feats.copy(); ff_a["szif_mm"] = sig_a.reindex(idx)
    ff_b = food_feats.copy(); ff_b["szif_mm"] = sig_b.reindex(idx)

    rows = []
    for t in origins:
        as_of_a = t.to_timestamp(how="end")
        as_of_b = _eve(t)
        inc_a = S.food_forecast(comp["food"], food_feats, t, as_of=as_of_a)
        aug_a = S.food_forecast(comp["food"], ff_a, t, as_of=as_of_a)
        inc_b = S.food_forecast(comp["food"], food_feats, t, as_of=as_of_b)
        aug_b = S.food_forecast(comp["food"], ff_b, t, as_of=as_of_b)
        wmap = S.solve_weights(y, comp, core, reg, t - 1, as_of=as_of_a, alc=alc)
        w_food = wmap[S._regime(t)]["food"]
        # ridge coefficient on szif_mm (diagnostic): refit the SA ridge design
        rows.append({"period": t, "food_actual": bt.loc[t, "food_actual"],
                     "inc_A": inc_a, "aug_A": aug_a, "inc_B": inc_b, "aug_B": aug_b,
                     "bt_food_pred": bt.loc[t, "food_pred"], "bt_food_pred_eve": bt.loc[t, "food_pred_eve"],
                     "w_food": w_food, "szif_A": ff_a.loc[t, "szif_mm"], "szif_B": ff_b.loc[t, "szif_mm"],
                     "STRUCT": bt.loc[t, "STRUCT"], "STRUCT_EVE": bt.loc[t, "STRUCT_EVE"],
                     "actual_current": bt.loc[t, "actual"]})
    df = pd.DataFrame(rows).set_index("period")
    df["STRUCT_szif_A"] = df["STRUCT"] + df["w_food"] * (df["aug_A"] - df["inc_A"])
    df["STRUCT_szif_B"] = df["STRUCT_EVE"] + df["w_food"] * (df["aug_B"] - df["inc_B"])
    df.to_csv(os.path.join(HERE, "output", "food_szif_experiment.csv"))

    # harness checks (spec section 5): incumbent must reproduce the backtest
    da = (df["inc_A"] - df["bt_food_pred"]).abs().max()
    db = (df["inc_B"] - df["bt_food_pred_eve"]).abs().max()
    print(f"harness: incumbent vs backtest food_pred max|diff| A {da:.2e}  B {db:.2e}")
    if not (da < 1e-9 and db < 1e-9):
        print("STOP: harness does not reproduce the backtest food block"); return

    # headline scoring exactly as scoreboards_codex_p0.board: FIRST-RELEASE
    # actual and survey median from the survey history; big surprise
    # |s| >= 0.4; g = |s| - |forecast error|; material W-L at 0.15 among bigs
    ext = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history_extended.csv"))
    ext["p"] = pd.PeriodIndex(ext["target_month"], freq="M")
    ext = ext.set_index("p")
    ext = ext[ext["era"] != "flash_survey_suspect"]
    df["actual"] = ext["actual"].reindex(df.index)
    df["survey"] = ext["survey_median"].reindex(df.index)
    df.to_csv(os.path.join(HERE, "output", "food_szif_experiment.csv"))

    splits = {"all 90": np.ones(len(df), bool),
              "ex-January": df.index.month != 1,
              "2024+": df.index >= pd.Period("2024-01", "M"),
              "2024+ ex-Jan": (df.index >= pd.Period("2024-01", "M")) & (df.index.month != 1),
              "2025+ flash era": df.index >= pd.Period("2025-01", "M")}
    print("\nFOOD BLOCK RMSE (MAE) vs realised food m/m")
    print(f"{'split':16s} {'n':>3s} | {'A incumbent':>12s} {'A +szif':>10s} {'d%':>7s} | {'B incumbent':>12s} {'B +szif':>10s} {'d%':>7s}")
    res = {}
    for name, mask in splits.items():
        f = df[mask]
        out = []
        for clk in ("A", "B"):
            ri, n = _rmse(f[f"inc_{clk}"] - f["food_actual"])
            ra, _ = _rmse(f[f"aug_{clk}"] - f["food_actual"])
            mi = float((f[f"inc_{clk}"] - f["food_actual"]).abs().mean())
            ma = float((f[f"aug_{clk}"] - f["food_actual"]).abs().mean())
            out.append((ri, ra, mi, ma, n))
            res[(name, clk)] = (ri, ra)
        (ri, ra, mi, ma, n), (ri2, ra2, mi2, ma2, _) = out
        print(f"{name:16s} {n:3d} | {ri:6.3f} ({mi:.3f}) {ra:6.3f} ({ma:.3f}) {100*(ra/ri-1):+6.1f}% | "
              f"{ri2:6.3f} ({mi2:.3f}) {ra2:6.3f} ({ma2:.3f}) {100*(ra2/ri2-1):+6.1f}%")

    print("\nHEADLINE RMSE vs first release (recombined with the origin's food weight)")
    print(f"{'split':16s} {'n':>3s} | {'A STRUCT':>9s} {'A +szif':>9s} {'d%':>7s} | {'B STRUCT':>9s} {'B +szif':>9s} {'d%':>7s} | survey")
    hres = {}
    for name, mask in splits.items():
        f = df[mask]
        ha, n = _rmse(f["STRUCT"] - f["actual"]); hsa, _ = _rmse(f["STRUCT_szif_A"] - f["actual"])
        hb, _ = _rmse(f["STRUCT_EVE"] - f["actual"]); hsb, _ = _rmse(f["STRUCT_szif_B"] - f["actual"])
        sv, _ = _rmse(f["survey"] - f["actual"])
        hres[(name, "A")] = (ha, hsa); hres[(name, "B")] = (hb, hsb)
        print(f"{name:16s} {n:3d} | {ha:9.4f} {hsa:9.4f} {100*(hsa/ha-1):+6.1f}% | {hb:9.4f} {hsb:9.4f} {100*(hsb/hb-1):+6.1f}% | {sv:.4f}")

    # big-surprise MAE and material W-L vs survey (information; board definitions)
    s = df["actual"] - df["survey"]
    big = s.abs() >= 0.4 - 1e-8
    for col, lab in (("STRUCT", "BASE_RIDGE A"), ("STRUCT_szif_A", "+szif A"),
                     ("STRUCT_EVE", "BASE_RIDGE B"), ("STRUCT_szif_B", "+szif B")):
        e = (df[col] - df["actual"]).abs(); g = s.abs() - e
        print(f"{lab:14s} big-surprise MAE {e[big].mean():.3f} (n={int(big.sum())}, consensus {s.abs()[big].mean():.3f}), "
              f"material W-L@0.15 {int((g[big] >= 0.15).sum())}-{int((g[big] <= -0.15).sum())}, halves {int((e[big] <= 0.5 * s.abs()[big]).sum())}")

    # diagnostics
    fe_a = df["inc_A"] - df["food_actual"]
    print("\nDIAGNOSTICS (not used for adoption)")
    print(f"corr(szif_A, food actual) {df['szif_A'].corr(df['food_actual']):+.3f}; "
          f"corr(szif_B, food actual) {df['szif_B'].corr(df['food_actual']):+.3f}; "
          f"corr(szif_A, incumbent error A) {df['szif_A'].corr(fe_a):+.3f}")
    used = diag_a.reindex(df.index)
    print(f"weeks used at A: mean {used['n_weeks_used'].mean():.2f} of {used['n_weeks_month'].mean():.2f}; "
          f"at B: {diag_b.reindex(df.index)['n_weeks_used'].mean():.2f}")
    print(f"mean |aug-inc| A {float((df['aug_A']-df['inc_A']).abs().mean()):.3f} pp, B {float((df['aug_B']-df['inc_B']).abs().mean()):.3f} pp")

    # adoption rule (spec section 6)
    ok_b = (res[("all 90", "B")][1] <= 0.95 * res[("all 90", "B")][0]
            and res[("2024+", "B")][1] <= 0.95 * res[("2024+", "B")][0]
            and hres[("all 90", "B")][1] <= hres[("all 90", "B")][0]
            and hres[("2024+", "B")][1] <= hres[("2024+", "B")][0])
    ok_a = (res[("all 90", "A")][1] <= res[("all 90", "A")][0]
            and res[("2024+", "A")][1] <= res[("2024+", "A")][0])
    print(f"\nADOPTION RULE: clock-B block >=5% on all and 2024+ with headline not worse: {ok_b}; "
          f"clock-A block not worse: {ok_a} -> {'ADOPT' if (ok_b and ok_a) else 'RECORD AND CLOSE'}")


if __name__ == "__main__":
    main()
