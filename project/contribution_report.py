"""Contribution report (Codex R6 reporting layer). For each backtest origin:
  - block contribution = weight x block forecast;
  - a NEUTRAL SEASONAL BASELINE per block (expanding same-calendar-month
    median of the block's released history through t-1), and the block's
    deviation from it, weight x (forecast - baseline);
  - the identity that ties it to the consensus:
        model - consensus = (baseline headline - consensus) + sum(deviations) + wedge
    where baseline headline = sum(weight x baseline) with NO wedge;
  - the wedge shown separately as a reconciliation residual, never as a
    block contribution;
  - the wedge's ERROR (v2.7.1, Codex R8): forecast wedge minus the realised
    reconciliation, where realised reconciliation = first-release headline
    print - sum(weight x realised block m/m). The five block errors and the
    wedge error then sum exactly to the headline error (checked). The v2.7
    version had used the forecast wedge itself as its error.
  - uncertainty by block: percentiles of the historical contribution error
    weight x (forecast - actual) over the evaluated origins, plus the
    headline error percentiles.
Usage: python contribution_report.py [--origin 2026-07]
Writes output/contribution_report.csv (all origins) and prints the origin table.
"""
import argparse
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cz_struct as S  # noqa: E402

BLOCKS = ["core", "food", "administered", "alc", "fuel"]
LABEL = {"core": "core (ridge)", "food": "food (X-13 + ridge)", "administered": "administered (seasonal median + January gate)",
         "alc": "alcohol & tobacco (same-month mean)", "fuel": "fuel (measured weekly)"}


def seasonal_baseline(series: pd.Series, t: pd.Period, as_of) -> float:
    hist = series.dropna(); hist = hist[hist.index <= t - 1]
    hist = hist[S._released_index(hist.index, as_of)]
    same = hist[hist.index.month == t.month]
    return float(same.median()) if len(same) >= 3 else float(hist.tail(24).median())


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--origin", default=None); a = ap.parse_args()
    y, comp, core, reg, feats, feats_st, food_feats, wedge = S.load_all()
    alc = S.load_alc_tobacco_mm()
    bt = pd.read_csv(os.path.join(HERE, "output", "cz_struct_backtest.csv"), index_col="period"); bt.index = pd.PeriodIndex(bt.index, freq="M")
    ext = pd.read_csv(os.path.join(HERE, "data", "czcpmom_survey_history_extended.csv")); ext["p"] = pd.PeriodIndex(ext["target_month"], freq="M")
    ext = ext.set_index("p"); ext = ext[ext["era"] != "flash_survey_suspect"]
    actual_series = {"core": core, "food": comp["food"], "administered": reg, "alc": alc, "fuel": comp["fuel"]}
    rows = []
    for t in bt.index:
        as_of = t.to_timestamp(how="end")
        w = S.solve_weights(y, comp, core, reg, t - 1, as_of=as_of, alc=alc)[S._regime(t)]
        fc = {"core": bt.loc[t, "core_pred_eve"], "food": bt.loc[t, "food_pred_eve"], "administered": bt.loc[t, "adm_pred_eve"],
              "alc": bt.loc[t, "alc_pred_eve"], "fuel": bt.loc[t, "fuel_eve"]}
        act = {"core": bt.loc[t, "core_actual"], "food": bt.loc[t, "food_actual"], "administered": bt.loc[t, "adm_actual"],
               "alc": bt.loc[t, "alc_actual"], "fuel": float(comp["fuel"].get(t, np.nan))}
        base = {b: seasonal_baseline(actual_series[b], t, as_of) for b in BLOCKS}
        r = {"period": t, "consensus": float(ext["survey_median"].get(t, np.nan)), "actual": float(ext["actual"].get(t, np.nan)),
             "model": float(bt.loc[t, "STRUCT_EVE"]), "wedge": float(bt.loc[t, "wedge_eve"])}
        r["baseline_headline"] = sum(w[b] * base[b] for b in BLOCKS)
        for b in BLOCKS:
            r[f"w_{b}"] = w[b]; r[f"fc_{b}"] = fc[b]; r[f"base_{b}"] = base[b]; r[f"act_{b}"] = act[b]
            r[f"contrib_{b}"] = w[b] * fc[b]
            r[f"dev_{b}"] = w[b] * (fc[b] - base[b])
            r[f"err_{b}"] = w[b] * (fc[b] - act[b]) if np.isfinite(act[b]) else np.nan
        r["sum_dev"] = sum(r[f"dev_{b}"] for b in BLOCKS)
        r["baseline_minus_consensus"] = r["baseline_headline"] - r["consensus"]
        r["model_minus_consensus"] = r["model"] - r["consensus"]
        r["identity_check"] = r["model_minus_consensus"] - (r["baseline_minus_consensus"] + r["sum_dev"] + r["wedge"])
        # v2.7.1: the wedge's error against what it reconciles
        if all(np.isfinite(act[b]) for b in BLOCKS) and np.isfinite(r["actual"]):
            r["realised_reconciliation"] = r["actual"] - sum(w[b] * act[b] for b in BLOCKS)
            r["wedge_err"] = r["wedge"] - r["realised_reconciliation"]
            r["headline_err"] = r["model"] - r["actual"]
            r["error_identity_check"] = r["headline_err"] - (sum(r[f"err_{b}"] for b in BLOCKS) + r["wedge_err"])
        else:
            r["realised_reconciliation"] = r["wedge_err"] = r["headline_err"] = r["error_identity_check"] = np.nan
        rows.append(r)
    df = pd.DataFrame(rows).set_index("period")
    df.to_csv(os.path.join(HERE, "output", "contribution_report.csv"))
    print(f"identity model - consensus = (baseline - consensus) + sum(dev) + wedge: max |residual| {df['identity_check'].abs().max():.2e}")
    print(f"identity headline error = sum(block errors) + wedge error: max |residual| {df['error_identity_check'].abs().max():.2e} "
          f"(n={int(df['error_identity_check'].notna().sum())})")

    # uncertainty by block: percentiles of the contribution error over the evaluated origins (ex-January and all)
    print("\nUNCERTAINTY BY BLOCK (contribution error weight x (forecast - actual), pp of headline; 90 origins | ex-January)")
    print(f"{'block':44s} {'p10':>7s} {'p50':>7s} {'p90':>7s} {'RMS':>7s} | {'p10':>7s} {'p50':>7s} {'p90':>7s} {'RMS':>7s}")
    exj = df.index.month != 1
    for b in BLOCKS + ["wedge_err", "realised_reconciliation"]:
        e = df[f"err_{b}"] if b in BLOCKS else df[b]
        lab = LABEL.get(b, "wedge ERROR (forecast wedge - realised reconciliation)" if b == "wedge_err"
                        else "realised reconciliation (print - sum w x actual), info")
        q = e.quantile([0.1, 0.5, 0.9]); qx = e[exj].quantile([0.1, 0.5, 0.9])
        print(f"{lab:44s} {q[0.1]:+7.3f} {q[0.5]:+7.3f} {q[0.9]:+7.3f} {np.sqrt((e**2).mean()):7.3f} | "
              f"{qx[0.1]:+7.3f} {qx[0.5]:+7.3f} {qx[0.9]:+7.3f} {np.sqrt((e[exj]**2).mean()):7.3f}")
    eh = df["model"] - df["actual"]; qh = eh.quantile([0.1, 0.5, 0.9]); qhx = eh[exj].quantile([0.1, 0.5, 0.9])
    print(f"{'headline (model - print)':44s} {qh[0.1]:+7.3f} {qh[0.5]:+7.3f} {qh[0.9]:+7.3f} {np.sqrt((eh**2).mean()):7.3f} | {qhx[0.1]:+7.3f} {qhx[0.5]:+7.3f} {qhx[0.9]:+7.3f} {np.sqrt((eh[exj]**2).mean()):7.3f}")

    origins = [pd.Period(a.origin, freq="M")] if a.origin else list(df.index[-2:])
    for t in origins:
        r = df.loc[t]
        print(f"\n=== {t}: model {r['model']:+.2f}  consensus {r['consensus']:+.2f}  print {r['actual']:+.2f}  | neutral seasonal baseline {r['baseline_headline']:+.2f} ===")
        print(f"{'block':44s} {'weight':>7s} {'forecast':>9s} {'baseline':>9s} {'contribution':>13s} {'vs baseline':>12s} {'actual':>8s} {'contrib error':>14s}")
        for b in BLOCKS:
            act = r[f"act_{b}"]
            print(f"{LABEL[b]:44s} {r[f'w_{b}']:7.3f} {r[f'fc_{b}']:+9.2f} {r[f'base_{b}']:+9.2f} {r[f'contrib_{b}']:+13.3f} {r[f'dev_{b}']:+12.3f} "
                  f"{(f'{act:+8.2f}' if np.isfinite(act) else '     n/a'):>8s} {(f'{r[f'err_{b}']:+14.3f}' if np.isfinite(r[f'err_{b}']) else '           n/a'):>14s}")
        rr, we_ = r["realised_reconciliation"], r["wedge_err"]
        rr_s = f"{rr:+8.2f}" if np.isfinite(rr) else "     n/a"
        we_s = f"{we_:+14.3f}" if np.isfinite(we_) else "           n/a"
        print(f"{'wedge (reconciliation residual, not a block)':44s} {'':7s} {'':9s} {'':9s} {r['wedge']:+13.3f} {'':12s} {rr_s:>8s} {we_s:>14s}")
        print(f"model - consensus {r['model_minus_consensus']:+.3f} = baseline - consensus {r['baseline_minus_consensus']:+.3f} + sum of block deviations {r['sum_dev']:+.3f} + wedge {r['wedge']:+.3f}")


if __name__ == "__main__":
    main()
