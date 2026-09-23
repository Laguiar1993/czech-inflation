"""late_info_tilt.py -- post-survey-close information tilt on the consensus.

Template: Monteforte & Moretti (Banca d'Italia TD 767) -- an encompassing
combination of an anchor (there HICP futures, here the Bloomberg median)
with a model of information the anchor has not absorbed.

TIMING LOGIC (the design constraint that picks the features): the release
of CPI(M) happens ~10 days into M+1, so nothing that *prices* in the
pre-release window can affect month M's basket. What legitimately arrives
between typical survey submission and the release is late-PUBLISHED data
ABOUT month M:
  * the final CZSO weekly pump-price prints covering M's last weeks
    (published early M+1) -- domestic CZK prices, so excise changes and
    subsidies (e.g. the Jun-2022 diesel excise cut) are captured, which
    Brent/TTF in international markets structurally cannot show;
  * the survey's own mean-median skew (survey-internal information).
Two candidate features were tested and REMOVED for failing the timing test
in opposite directions: pre-release-window commodity moves price M+1, not M
(Brent/TTF, removed first); and the German HICP flash for M arrives ~8-10
days BEFORE the CZ release, so analysts see it before submitting -- it is
already in the consensus and cannot be post-close information (its
encompassing beta was +0.06, t=0.76 -- empirically dead too, and it carried
a final-for-flash vintage caveat).

Two models, both expanding, >=16 past releases before the first fitted
value, tilt clipped:
  LateInfo   -- shrunk ridge (prior strength 4) of the surprise on the two
                features, tilt clip +/-0.3pp.
  SurpriseRF -- random forest on the same features + the h0-hybrid's
                deviation from consensus + measured fuel_mm + January
                dummy, tilt clip +/-0.5pp.

STATUS: exploratory (spec written with this sample already studied).
Scored ONLY on disagreement-conditioned metrics + big-surprise direction,
per the leaderboard rulebook.

Usage: python late_info_tilt.py
"""
from __future__ import annotations
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import local_adapter as la

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
MIN_TRAIN = 16


def load_releases() -> pd.DataFrame:
    reg = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history.csv"))
    fl = pd.read_csv(os.path.join(HERE, "data", "czcpmom_flash_survey_history.csv"))
    reg["target_month"] = pd.PeriodIndex(pd.to_datetime(reg["target_month"]).dt.to_period("M"), freq="M")
    fl["target_month"] = pd.PeriodIndex(fl["target_month"], freq="M")
    reg = reg[reg["target_month"] <= pd.Period("2024-12", "M")]
    df = pd.concat([reg, fl], ignore_index=True)
    df["release_dt"] = pd.to_datetime(df["release_dt"])
    return df.sort_values("target_month").set_index("target_month")[
        ["release_dt", "actual", "survey_median", "survey_mean"]].rename(
        columns={"survey_median": "median", "survey_mean": "mean"}).dropna(subset=["median", "actual"])


def fuel_tail_feature(months: pd.PeriodIndex) -> pd.Series:
    """% change of the official-share petrol/diesel blend over the LAST TWO weekly
    prints inside each target month -- the observations most likely to
    postdate analyst submissions (they surface in CZSO's early-M+1 weekly
    release)."""
    from models.components import petrol_share_for_regime
    w = la.fetch_weekly_fuels_live()
    # v2.4: official per-regime petrol share (FUEL_SPEC_v23 F2), not the retired 0.6 constant
    share = pd.Series([petrol_share_for_regime(d.year - d.year % 2) for d in w.index], index=w.index)
    blend = share * w["petrol95"] + (1 - share) * w["diesel"]
    vals = {}
    for m in months:
        seg = blend[blend.index.to_period("M") == m]
        if len(seg) >= 3:
            vals[m] = 100.0 * (seg.iloc[-1] / seg.iloc[-3] - 1.0)
        elif len(seg) >= 2:
            vals[m] = 100.0 * (seg.iloc[-1] / seg.iloc[0] - 1.0)
        else:
            vals[m] = np.nan
    return pd.Series(vals, name="fuel_tail")




def main():
    rel = load_releases()
    print(f"releases: {len(rel)} ({rel.index.min()}..{rel.index.max()})")
    s = (rel["actual"] - rel["median"]).values

    feat = pd.DataFrame(index=rel.index)
    feat["fuel_tail"] = fuel_tail_feature(rel.index)
    feat["skew"] = rel["mean"] - rel["median"]
    print("feature coverage:", feat.notna().sum().to_dict())

    # LateInfo: expanding shrunk ridge, no intercept, standardized
    F = feat.values
    tilt = np.full(len(rel), np.nan)
    for i in range(len(rel)):
        ok = np.isfinite(F[:i]).all(1) & np.isfinite(s[:i])
        if ok.sum() < MIN_TRAIN or not np.isfinite(F[i]).all():
            continue
        Fp, sp = F[:i][ok], s[:i][ok]
        mu, sd = Fp.mean(0), Fp.std(0)
        sd[sd == 0] = 1.0
        Z = (Fp - mu) / sd
        beta = np.linalg.solve(Z.T @ Z + 4.0 * np.eye(Z.shape[1]), Z.T @ sp)
        tilt[i] = float(np.clip(((F[i] - mu) / sd) @ beta, -0.3, 0.3))
    out = rel.copy()
    out["tilt"] = tilt
    out["LateInfo"] = rel["median"] + out["tilt"]

    # SurpriseRF: + hybrid deviation, fuel_mm, January dummy
    from sklearn.ensemble import RandomForestRegressor
    champ = pd.read_csv(os.path.join(OUT, "backtest_h0_hybrid.csv"), index_col="period")
    champ.index = pd.PeriodIndex(champ.index, freq="M")
    feat2 = feat.copy()
    feat2["hyb_dev"] = champ["h0_hybrid"].reindex(rel.index) - rel["median"]
    feat2["fuel_mm"] = champ["fuel_mm"].reindex(rel.index)
    feat2["jan"] = (rel.index.month == 1).astype(float)
    Xf = feat2.values
    tilt2 = np.full(len(rel), np.nan)
    for i in range(len(rel)):
        ok = np.isfinite(Xf[:i]).all(1) & np.isfinite(s[:i])
        if ok.sum() < MIN_TRAIN + 2 or not np.isfinite(Xf[i]).all():
            continue
        rf = RandomForestRegressor(n_estimators=300, min_samples_leaf=4,
                                   max_features=0.6, random_state=42, n_jobs=-1)
        rf.fit(Xf[:i][ok], s[:i][ok])
        tilt2[i] = float(np.clip(rf.predict(Xf[i][None, :])[0], -0.5, 0.5))
    out["SurpriseRF"] = rel["median"] + tilt2

    out.to_csv(os.path.join(OUT, "late_info_tilt.csv"))

    def rulebook(pred, label):
        ok = pred.notna()
        d = np.round((pred - rel["median"])[ok], 8)
        sr = np.round(pd.Series(s, index=rel.index)[ok], 8)
        hit = (np.sign(d) == np.sign(sr)) & (sr != 0) & (d != 0)
        big = sr.abs() >= 0.4 - 1e-8
        al = d.abs() >= 0.2
        e = (pred - rel["actual"])[ok]
        es = (rel["median"] - rel["actual"])[ok]
        print(f"  {label:11s} n={ok.sum():2d}  RMSE={np.sqrt((e**2).mean()):.3f} "
              f"(cons {np.sqrt((es**2).mean()):.3f})  mean|tilt|={d.abs().mean():.3f}  "
              f"dev>=0.1: {int((d.abs()>=0.1).sum())} ({int((hit & (d.abs()>=0.1)).sum())} ok)  "
              f"alerts>=0.2: {int(al.sum())} ({int((hit & al).sum())} ok)  "
              f"big {int((hit & big).sum())}/{int(big.sum())}")

    print("\n== rulebook scoring (disagreement-conditioned) ==")
    rulebook(out["LateInfo"], "LateInfo")
    rulebook(out["SurpriseRF"], "SurpriseRF")

    for c in ["fuel_tail", "skew"]:
        f = feat[c].values
        ok = np.isfinite(f) & np.isfinite(s)
        if ok.sum() > 10:
            b = (f[ok] @ s[ok]) / (f[ok] @ f[ok])
            r = s[ok] - b * f[ok]
            se = np.sqrt((r @ r) / (ok.sum() - 1) / (f[ok] @ f[ok]))
            print(f"encompassing surprise ~ {c}: beta={b:+.3f} (t={b/se:+.2f}, n={ok.sum()})")


if __name__ == "__main__":
    main()
