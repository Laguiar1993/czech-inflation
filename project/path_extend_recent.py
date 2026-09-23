"""Forecast months beyond the last realised print for recent origins, so the
charts show the full twelve-month path of the product line (F1b), the trend
line (F2 D1-fixed) and the naive path. The backtest files store only
realised target months (the ones that can be scored); this script computes
the remaining months for origins whose window passes the data edge, with
exactly the same engines and the same release-eve clock. Overlapping months
are checked against the backtest rows.
Usage: python path_extend_recent.py
Writes output/path_step2_extended.csv.
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
from models.trend_gap import fit_forecast  # noqa: E402
from path_experiment import _eve, naive_mm, lg, pct, load_fmie_1y  # noqa: E402

START = pd.Period("1998-01", "M")
H = list(range(1, 13))


def main():
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    alc = S.load_alc_tobacco_mm()
    fuel_official = comp["fuel"].dropna()
    y_ext = la.load_headline_cpi_mm_extended(); y_ext = y_ext[y_ext.index >= START].dropna()
    fmie = load_fmie_1y()
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period"); bt.index = pd.PeriodIndex(bt.index, freq="M")
    step2 = pd.read_csv(os.path.join(HERE, "output", "path_step2.csv")); step2["op"] = pd.PeriodIndex(step2["origin"], freq="M")
    last_real = y_ext.index.max()
    origins = [t for t in bt.index if t + 12 > last_real]
    ylog = pd.Series(np.asarray(lg(y_ext)), index=y_ext.index)
    rows = []
    for t in origins:
        as_of = _eve(t)
        yh = y_ext[y_ext.index <= t - 1]; yh = yh[S._released_index(yh.index, as_of)]
        y_known = y.dropna(); y_known = y_known[y_known.index <= t - 1]; y_known = y_known[S._released_index(y_known.index, as_of)]
        wmap = S.solve_weights(y, comp, core, reg, t - 1, as_of=as_of, alc=alc); wt = wmap[S._regime(t)]
        wedge_tv = S._weighted_wedge(y, comp, alc, core, reg, wedge, wmap, as_of=as_of)
        food_hist = comp["food"].dropna(); food_hist = food_hist[food_hist.index <= t - 1]; food_hist = food_hist[S._released_index(food_hist.index, as_of)]
        mh = fmie[fmie.index <= t - 1] if fmie is not None else None
        f2 = fit_forecast(yh, range(1, 14), m_hist=mh, fixed_snr=True)
        h0m = float(bt.loc[t, "STRUCT_EVE"])
        base_known = ylog[ylog.index <= t - 1]
        mm = {}
        for h in H:
            tgt = t + h; wh = wmap.get(S._regime(tgt), wt)
            core_h, _, _ = S._ridge_predict(feats, core, t, h=h, as_of=as_of)           # F1b: plain frame at every horizon
            if h <= 3:
                food_h = S.food_forecast(comp["food"], food_feats, t, h=h, as_of=as_of)
            else:
                fm_ = food_hist[food_hist.index.month == tgt.month]
                food_h = float(fm_.tail(5).mean()) if len(fm_) >= 3 else float(food_hist.tail(24).mean())
            adm_h = S.admin_forecast(reg, tgt, known_through=t - 1, as_of=as_of, announce_mode="documented", w_adm=wh["administered"])
            alc_h = S.alc_forecast(alc, tgt, t - 1, as_of=as_of)
            fh = fuel_official[fuel_official.index <= t - 1]; fh = fh[S._released_index(fh.index, as_of)]
            fmf = fh[fh.index.month == tgt.month]
            fuel_h = float(fmf.tail(8).median()) if len(fmf) >= 3 else float(fh.tail(24).median())
            wdg = S._wedge_at(wedge_tv, tgt, t - 1)
            mm[h] = {"F1b": np.nan if (np.isnan(core_h) or np.isnan(food_h)) else (wh["fuel"] * fuel_h + wh["administered"] * adm_h + wh["alc"] * alc_h + wh["food"] * food_h + wh["core"] * core_h + wdg),
                     "F2_D1_fixed": float(f2["mm"].get(h + 1, np.nan)), "naive": naive_mm(y_known, tgt)}
        for h in H:
            tgt = t + h; window = pd.period_range(tgt - 11, tgt, freq="M")
            base = float(base_known.reindex([m for m in window if m <= t - 1]).sum()); fut = [m for m in window if m >= t]
            rec = {"origin": str(t), "h": h, "target": str(tgt), "realised": bool(tgt <= last_real), "h0_model": h0m}
            h0p = float(y_ext.loc[t]) if t <= last_real else np.nan      # the print at h0 once it exists (object b, used at CNB report dates)
            for k in ("F1b", "F2_D1_fixed", "naive"):
                rec[f"mm_{k}"] = mm[h][k]
                path = {t: h0m}; path.update({t + j: mm[j][k] for j in H})
                rec[f"yy_a_{k}"] = pct(base + sum(lg([path[m]])[0] for m in fut))
                if np.isfinite(h0p):
                    pathb = {t: h0p}; pathb.update({t + j: mm[j][k] for j in H})
                    rec[f"yy_b_{k}"] = pct(base + sum(lg([pathb[m]])[0] for m in fut))
                else:
                    rec[f"yy_b_{k}"] = np.nan
            rows.append(rec)
        print(f"origin {t}: F1b h1..12 " + " ".join(f"{mm[h]['F1b']:+.2f}" for h in H))
    ext = pd.DataFrame(rows)
    ext.to_csv(os.path.join(HERE, "output", "path_step2_extended.csv"), index=False)
    # harness: overlapping (origin, h) rows must reproduce the backtest columns
    chk = ext.merge(step2[["origin", "h", "yy_a_F1b", "yy_a_F2_D1_fixed", "yy_a_naive"]], on=["origin", "h"], suffixes=("", "_bt"), how="inner")
    for k in ("F1b", "F2_D1_fixed", "naive"):
        d = (chk[f"yy_a_{k}"] - chk[f"yy_a_{k}_bt"]).abs().max()
        print(f"overlap check {k}: n={len(chk)} max |diff| {d:.2e}")


if __name__ == "__main__":
    main()
