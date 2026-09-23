"""Predeclared category-level food experiment (FOOD_CATEGORY_SPEC.md):
ten ECOICOP classes, per-class one-sided X-13, candidates I1 (rolling mean),
I2 (class ridge), P (pooled ridge), Individual Weighting by inverse recent
MSFE, aggregation with price-updated basket shares. Single run, two clocks.
Usage: python food_category_experiment.py [--szif]
Writes output/food_category_experiment.csv and output/food_category_classes.csv.
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

INCLUDE_SZIF = "--szif" in sys.argv
RECURSION_START = pd.Period("2017-02", "M")
ROLL = 12          # I1 window
MSFE_WIN = 24      # IW window
MIN_ERRS = 12      # candidate needs this many realised errors to be weighted
POOL_MIN_MONTHS = 24
_SA_CACHE = {}


def _eve(m: pd.Period) -> pd.Timestamp:
    fr = S._first_release_dt(m)
    if pd.notna(fr):
        return fr.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=23, minutes=59)
    return m.to_timestamp(how="end").normalize() + pd.Timedelta(days=7, hours=23, minutes=59)


def seasonal_split(series: pd.Series, origin: pd.Period, as_of):
    """One-sided SA of the class history released at the clock. Returns
    (sa Series, s_add for the origin month, method)."""
    from statsmodels.tsa.x13 import x13_arima_analysis
    hist = series.dropna()
    hist = hist[hist.index <= origin - 1]
    hist = hist[S._released_index(hist.index, as_of)]
    key = (series.name, str(origin), len(hist),
           hashlib.sha1(np.ascontiguousarray(hist.values, dtype=float).tobytes()).hexdigest())
    if key in _SA_CACHE:
        return _SA_CACHE[key]
    try:
        if len(hist) < 36:
            raise ValueError("short")
        ts = hist.copy(); ts.index = ts.index.to_timestamp()
        sa = x13_arima_analysis(ts, x12path=la._X13_PATH, prefer_x13=True).seasadj
        sa.index = hist.index
        seas = (hist - sa).dropna()
        s_m = seas[seas.index.month == origin.month]
        s_add = float(s_m.iloc[-3:].mean()) if len(s_m) else 0.0
        out = (sa, s_add, "x13")
    except Exception:
        dev = hist - hist.expanding().mean().shift(1)
        smean = dev.groupby(dev.index.month).mean()
        sa = hist - hist.index.month.map(smean).values
        s_add = float(smean.get(origin.month, 0.0))
        out = (sa.dropna(), s_add, "fallback")
    _SA_CACHE[key] = out
    return out


def pooled_ridge(frames: dict, targets: dict, origin: pd.Period, as_of, alpha=S.RIDGE_ALPHA):
    """Common-slope ridge across classes with class fixed effects; returns
    {class: forecast} or {} when the panel is too short."""
    Xs, ys, means, rows_c = [], [], {}, {}
    for c, X in frames.items():
        yv = targets[c]
        tr = yv.dropna().index
        tr = tr[tr <= origin - 1]
        tr = tr[S._released_index(tr, as_of)]
        if len(tr) < POOL_MIN_MONTHS:
            continue
        means[c] = float(yv.loc[tr].mean())
        # within transformation (Codex R6): class fixed effects removed from
        # the predictors as well as the target, over the same training rows
        xm = X.loc[tr].mean()
        Xs.append(X.loc[tr] - xm); ys.append(yv.loc[tr] - means[c]); rows_c[c] = X.loc[[origin]] - xm
    if len(means) < 5:
        return {}
    Xt = pd.concat(Xs); yt = pd.concat(ys)
    mu = Xt.mean(); Xt = Xt.fillna(mu)
    m, s = Xt.mean().values, Xt.std().replace(0, 1.0).values
    Z = (Xt.values - m) / s
    beta = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ yt.values)
    out = {}
    for c, xr in rows_c.items():
        z0 = (xr.fillna(mu).values - m) / s
        out[c] = means[c] + float((z0 @ beta)[0])
    return out


def main():
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    alc = S.load_alc_tobacco_mm()
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period")
    bt.index = pd.PeriodIndex(bt.index, freq="M")
    eval_origins = list(bt.index)
    lv = fc.load_class_levels(); mm = fc.load_class_mm()
    weights = fc.load_class_weights()
    # basket publication gate (Codex R6): shares per clock; a January origin
    # uses the previous basket because the new one is published mid-February
    shares_by_clock = {
        "A": fc.price_updated_shares(lv, weights, S._regime, as_of_fn=lambda m: m.to_timestamp(how="end"),
                                     available_from_fn=S._basket_available_from),
        "B": fc.price_updated_shares(lv, weights, S._regime, as_of_fn=_eve,
                                     available_from_fn=S._basket_available_from)}
    full_idx = food_feats.index
    common = ["agri_l0", "agri_l1", "food_ppi_l1"]
    szif = {}
    if INCLUDE_SZIF:
        from data import szif_weekly as sw
        weekly = sw.load_weekly_czk()
        szif["A"], _ = sw.month_signal(weekly, pd.Series({m: m.to_timestamp(how="end") for m in full_idx}))
        szif["B"], _ = sw.month_signal(weekly, pd.Series({m: _eve(m) for m in full_idx}))

    def class_frames(clock):
        fr = {}
        for c in fc.CLASSES:
            f = pd.DataFrame(index=full_idx)
            f["y_l1"] = S._lag(mm[c].rename(c), 1, full_idx)
            f["y_l12"] = S._lag(mm[c].rename(c), 12, full_idx)
            for col in common:
                f[col] = food_feats[col]
            if INCLUDE_SZIF:
                f["szif_mm"] = szif[clock].reindex(full_idx)
            fr[c] = f
        return fr

    origins = [p for p in mm.index if p >= RECURSION_START and p <= eval_origins[-1]]
    results = {}
    for clock in ("A", "B"):
        shares = shares_by_clock[clock]
        frames = class_frames(clock)
        errs = {c: {k: [] for k in ("I1", "I2", "P")} for c in fc.CLASSES}   # (month, error)
        recs = []
        for t in origins:
            as_of = t.to_timestamp(how="end") if clock == "A" else _eve(t)
            sa_t, sadd_t = {}, {}
            for c in fc.CLASSES:
                sa, s_add, _ = seasonal_split(mm[c].rename(c), t, as_of)
                sa_t[c], sadd_t[c] = sa, s_add
            pooled = pooled_ridge(frames, sa_t, t, as_of)
            for c in fc.CLASSES:
                sa = sa_t[c]
                cand = {}
                if len(sa) >= ROLL:
                    cand["I1"] = float(sa.iloc[-ROLL:].mean())
                p2, _, _ = S._ridge_predict(frames[c], sa, t, as_of=as_of)
                if np.isfinite(p2):
                    cand["I2"] = p2
                if c in pooled:
                    cand["P"] = pooled[c]
                # IW weights from realised errors known at the clock
                wts = {}
                for k, f in cand.items():
                    hist_e = [e for (mth, e) in errs[c][k] if S._cpi_family_released_by(mth, as_of)]
                    if len(hist_e) >= MIN_ERRS:
                        wts[k] = 1.0 / max(np.mean(np.square(hist_e[-MSFE_WIN:])), 1e-9)
                if not wts:
                    wts = {k: 1.0 for k in cand}
                tot = sum(wts.values())
                comb = sum(wts[k] * cand[k] for k in wts) / tot if tot > 0 else np.nan
                actual_sa = np.nan   # realised SA value is not observable one-sidedly; errors use NSA
                rec = {"period": t, "cls": c, "comb": comb + sadd_t[c] if np.isfinite(comb) else np.nan,
                       "s_add": sadd_t[c], "actual": mm[c].get(t, np.nan),
                       "share": shares.loc[t, c] if t in shares.index else np.nan}
                for k in ("I1", "I2", "P"):
                    rec[k] = cand[k] + sadd_t[c] if k in cand else np.nan
                    rec[f"w_{k}"] = wts.get(k, 0.0) / tot if tot > 0 else np.nan
                recs.append(rec)
                # store realised NSA errors of each candidate for later IW
                if np.isfinite(rec["actual"]):
                    for k in cand:
                        errs[c][k].append((t, rec[k] - rec["actual"]))
        cls = pd.DataFrame(recs)
        results[clock] = cls
    for clock in ("A", "B"):
        results[clock] = results[clock].copy(); results[clock]["clock"] = clock
    allcls = pd.concat([results["A"], results["B"]], ignore_index=True)
    allcls.to_csv(os.path.join(HERE, "output", "food_category_classes.csv"), index=False)

    # aggregate per origin and clock
    rows = []
    for t in eval_origins:
        as_of_a = t.to_timestamp(how="end")
        inc = S.food_forecast(comp["food"], food_feats, t, as_of=as_of_a)
        wmap = S.solve_weights(y, comp, core, reg, t - 1, as_of=as_of_a, alc=alc)
        r = {"period": t, "food_actual": bt.loc[t, "food_actual"], "inc": inc, "bt_food_pred": bt.loc[t, "food_pred"],
             "w_food": wmap[S._regime(t)]["food"], "STRUCT": bt.loc[t, "STRUCT"], "STRUCT_EVE": bt.loc[t, "STRUCT_EVE"],
             "actual_current": bt.loc[t, "actual"]}
        for clock in ("A", "B"):
            g = results[clock][results[clock]["period"] == t].set_index("cls")
            sh = g["share"]
            r[f"cat_{clock}"] = float((g["comb"] * sh).sum()) if g["comb"].notna().all() else np.nan
            r[f"I1_{clock}"] = float((g["I1"] * sh).sum()) if g["I1"].notna().all() else np.nan
            r[f"P_{clock}"] = float((g["P"] * sh).sum()) if g["P"].notna().all() else np.nan
        rows.append(r)
    df = pd.DataFrame(rows).set_index("period")
    df["STRUCT_cat_A"] = df["STRUCT"] + df["w_food"] * (df["cat_A"] - df["inc"])
    df["STRUCT_cat_B"] = df["STRUCT_EVE"] + df["w_food"] * (df["cat_B"] - df["inc"])
    # headline scoring as scoreboards_codex_p0.board: FIRST-RELEASE actual and
    # survey median from the survey history
    ext = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history_extended.csv"))
    ext["p"] = pd.PeriodIndex(ext["target_month"], freq="M")
    ext = ext.set_index("p")
    ext = ext[ext["era"] != "flash_survey_suspect"]
    df["actual"] = ext["actual"].reindex(df.index)
    df["survey"] = ext["survey_median"].reindex(df.index)
    df.to_csv(os.path.join(HERE, "output", "food_category_experiment.csv"))
    d = (df["inc"] - df["bt_food_pred"]).abs().max()
    print(f"harness: incumbent vs backtest food_pred max|diff| {d:.2e}")
    if d >= 1e-9:
        print("STOP: harness mismatch"); return

    def rmse(e):
        e = pd.Series(e).dropna(); return float(np.sqrt((e ** 2).mean())), int(len(e))
    splits = {"all 90": np.ones(len(df), bool), "ex-January": df.index.month != 1,
              "2024+": df.index >= pd.Period("2024-01", "M"),
              "2024+ ex-Jan": (df.index >= pd.Period("2024-01", "M")) & (df.index.month != 1),
              "2025+ flash era": df.index >= pd.Period("2025-01", "M")}
    print("\nFOOD BLOCK RMSE vs realised food m/m (n = origins with a complete category forecast)")
    print(f"{'split':16s} | {'incumbent':>9s} | {'cat A':>7s} {'d%':>7s} | {'cat B':>7s} {'d%':>7s} | {'I1-only':>7s} {'P-only':>7s}")
    res, hres = {}, {}
    for name, mask in splits.items():
        f = df[mask]
        ri, n = rmse(f["inc"] - f["food_actual"]); ra, na = rmse(f["cat_A"] - f["food_actual"]); rb, _ = rmse(f["cat_B"] - f["food_actual"])
        r1, _ = rmse(f["I1_A"] - f["food_actual"]); rp, _ = rmse(f["P_A"] - f["food_actual"])
        res[(name, "A")] = (ri, ra); res[(name, "B")] = (ri, rb)
        print(f"{name:16s} | {ri:9.3f} | {ra:7.3f} {100*(ra/ri-1):+6.1f}% | {rb:7.3f} {100*(rb/ri-1):+6.1f}% | {r1:7.3f} {rp:7.3f}   (n={na})")
    print("\nHEADLINE RMSE vs first release")
    for name, mask in splits.items():
        f = df[mask]
        ha, _ = rmse(f["STRUCT"] - f["actual"]); hca, _ = rmse(f["STRUCT_cat_A"] - f["actual"])
        hb, _ = rmse(f["STRUCT_EVE"] - f["actual"]); hcb, _ = rmse(f["STRUCT_cat_B"] - f["actual"])
        hres[(name, "A")] = (ha, hca); hres[(name, "B")] = (hb, hcb)
        print(f"{name:16s} | A {ha:.4f} -> {hca:.4f} ({100*(hca/ha-1):+.1f}%) | B {hb:.4f} -> {hcb:.4f} ({100*(hcb/hb-1):+.1f}%)")
    s_ = df["actual"] - df["survey"]
    big = s_.abs() >= 0.4 - 1e-8
    for col, lab in (("STRUCT", "BASE_RIDGE A"), ("STRUCT_cat_A", "category A"),
                     ("STRUCT_EVE", "BASE_RIDGE B"), ("STRUCT_cat_B", "category B")):
        e = (df[col] - df["actual"]).abs(); g = s_.abs() - e
        print(f"{lab:14s} big-surprise MAE {e[big].mean():.3f} (n={int(big.sum())}, consensus {s_.abs()[big].mean():.3f}), "
              f"material W-L@0.15 {int((g[big] >= 0.15).sum())}-{int((g[big] <= -0.15).sum())}, halves {int((e[big] <= 0.5 * s_.abs()[big]).sum())}")
    # per-class attribution at clock A over the evaluated origins
    ca = results["A"][results["A"]["period"].isin(eval_origins)]
    print("\nPER-CLASS RMSE over the 90 origins (clock A): combined | I1 | I2 | P | naive same-month mean; mean IW weights")
    for c, g in ca.groupby("cls"):
        naive = []
        for t in g["period"]:
            h = mm[c][(mm[c].index < t) & (mm[c].index.month == t.month)]
            naive.append(h.mean() if len(h) else np.nan)
        naive = pd.Series(naive, index=g.index)
        e = lambda col: float(np.sqrt(np.nanmean((g[col] - g["actual"]) ** 2)))
        print(f"  {c:5s} {fc.LABELS[c]:24s} {e('comb'):.3f} | {e('I1'):.3f} | {e('I2'):.3f} | {e('P'):.3f} | "
              f"{float(np.sqrt(np.nanmean((naive - g['actual'])**2))):.3f}; w I1 {g['w_I1'].mean():.2f} I2 {g['w_I2'].mean():.2f} P {g['w_P'].mean():.2f}")
    ok_b = (res[("all 90", "B")][1] <= 0.95 * res[("all 90", "B")][0] and res[("2024+", "B")][1] <= 0.95 * res[("2024+", "B")][0]
            and hres[("all 90", "B")][1] <= hres[("all 90", "B")][0] and hres[("2024+", "B")][1] <= hres[("2024+", "B")][0])
    ok_a = res[("all 90", "A")][1] <= res[("all 90", "A")][0] and res[("2024+", "A")][1] <= res[("2024+", "A")][0]
    print(f"\nADOPTION RULE: B block >=5% on all and 2024+ with headline not worse: {ok_b}; A block not worse: {ok_a} -> "
          f"{'ADOPT' if (ok_b and ok_a) else 'RECORD AND CLOSE'}")


if __name__ == "__main__":
    main()
