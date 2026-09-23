"""Predeclared food-block experiment -- see FOOD_EXPERIMENT_SPEC.md.
Usage: python food_experiment.py
"""
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from data import local_adapter as la  # noqa: E402


def food_levels() -> pd.Series:
    con = la._con()
    df = con.sql("""
        SELECT date, value FROM cpi_czso.cpi_long
        WHERE coicop_code = '01' AND base = 'base_2015_eq_100'
          AND hh_group_code = '0' AND subgroup_code = ''
        ORDER BY date
    """).df()
    con.close()
    s = pd.Series(df["value"].values,
                  index=pd.PeriodIndex(pd.to_datetime(df["date"]), freq="M")).groupby(level=0).last()
    return s.sort_index()


def main():
    from statsmodels.tsa.statespace.structural import UnobservedComponents
    lvl = food_levels()
    loglvl = np.log(lvl)
    bt = pd.read_csv("output/cz_struct_backtest.csv", index_col="period")
    bt.index = pd.PeriodIndex(bt.index, freq="M")
    origins = bt.index

    rows = []
    for t in origins:
        hist = loglvl[loglvl.index <= t - 1]
        fc = np.nan
        if len(hist) >= 60:
            try:
                ts = hist.copy()
                ts.index = ts.index.to_timestamp()
                m = UnobservedComponents(ts, level="lltrend", seasonal=12,
                                         stochastic_seasonal=True)
                r = m.fit(disp=0)
                fc = 100.0 * (np.exp(r.forecast(1).iloc[0] - hist.iloc[-1]) - 1)
            except Exception:
                fc = np.nan
        rows.append({"period": t, "food_ss": fc,
                     "food_x13": bt.loc[t, "food_pred"],
                     "food_actual": bt.loc[t, "food_actual"],
                     "STRUCT": bt.loc[t, "STRUCT"]})
    df = pd.DataFrame(rows).set_index("period")
    df.to_csv("output/food_experiment.csv")

    def sc(f, col):
        e = f[col] - f["food_actual"]
        return float(np.sqrt(np.nanmean(e ** 2))), int(e.notna().sum())

    for label, f in [("all", df), ("exJan", df[df.index.month != 1]),
                     ("2024+", df[df.index >= pd.Period("2024-01", "M")])]:
        r_ss, n_ss = sc(f, "food_ss")
        r_x, _ = sc(f, "food_x13")
        print(f"{label:6s} block RMSE: state-space {r_ss:.3f} (n={n_ss})  vs  X13+ridge {r_x:.3f}")

    # headline effect: swap food block, weights ~0.17 (regime-correct enough
    # for a diagnostic delta; adoption rule uses block RMSE primarily)
    w_food = 0.177
    df["STRUCT_ssfood"] = df["STRUCT"] + w_food * (df["food_ss"] - df["food_x13"])
    act = bt["actual"].reindex(df.index)
    for label, f in [("all", df), ("2024+", df[df.index >= pd.Period("2024-01", "M")])]:
        a = act.reindex(f.index)
        e1 = f["STRUCT"] - a
        e2 = f["STRUCT_ssfood"] - a
        print(f"headline {label:6s}: incumbent {np.sqrt(np.nanmean(e1**2)):.3f}  "
              f"ss-food {np.sqrt(np.nanmean(e2**2)):.3f}")


if __name__ == "__main__":
    main()
