"""Three-scoreboard evaluation for the codex-p0 corrected model.

Frames and metric definitions follow the Codex audit exactly: 90 first
releases Feb-2019..Jul-2026, regular consensus/actual through 2024-12 and
flash from 2025-01, Aug-2026 excluded; large surprise |s|>=0.4; material
win/loss at 0.15 (0.10/0.20 sensitivity shown); exact squared-error
improvement 2ds - d^2; absolute improvement g = |s| - |actual-forecast|;
all alerts (|d|>=0.2) reported including false calls; January and
ex-January panels separate. Historical January announcement skill is NOT
claimed as verified ex ante: the reconstructed-scenario board is labelled.

Usage: python scoreboards_codex_p0.py
"""
from pathlib import Path

from evaluation.prospective import classify_shadow_row

import numpy as np
import pandas as pd

def board(df, col, label):
    f = df.dropna(subset=[col])
    e = (f[col] - f["actual"]).abs()
    es = f["s"].abs()
    d = f[col] - f["survey_median"]
    g = es - e                                  # absolute improvement vs consensus
    sq_gain = 2 * d * f["s"] - d ** 2           # exact squared-error improvement
    big = es >= 0.4 - 1e-8
    alerts = d.abs() >= 0.2
    rows = {
        "n": len(f),
        "RMSE": float(np.sqrt((e ** 2).mean())),
        "RMSE_2024p": float(np.sqrt((e[f.index >= pd.Period('2024-01','M')] ** 2).mean())),
        "big_n": int(big.sum()),
        "big_MAE": float(e[big].mean()),
        "big_MAE_consensus": float(es[big].mean()),
        "big_agg_err_reduction_pct": float(100 * g[big].sum() / es[big].sum()),
        "big_direction": int(((np.sign(d) == np.sign(f['s'])) & big & (d != 0)).sum()),
        "big_halves_consensus": int((e[big] <= 0.5 * es[big]).sum()),
        "W-L@0.10": f"{int((g[big] >= 0.10).sum())}-{int((g[big] <= -0.10).sum())}",
        "W-L@0.15": f"{int((g[big] >= 0.15).sum())}-{int((g[big] <= -0.15).sum())}",
        "W-L@0.20": f"{int((g[big] >= 0.20).sum())}-{int((g[big] <= -0.20).sum())}",
        "alerts|d|>=0.2": int(alerts.sum()),
        "alerts_closer": int((alerts & (g > 0)).sum()),
        "alerts_material": int((alerts & (g >= 0.15)).sum()),
        "sum_sq_gain": float(sq_gain.sum()),
        "Jan_RMSE": float(np.sqrt((e[f.index.month == 1] ** 2).mean())),
        "exJan_RMSE": float(np.sqrt((e[f.index.month != 1] ** 2).mean())),
    }
    return pd.Series(rows, name=label)



def main(root=None):
    root = Path(root).resolve() if root is not None else Path(__file__).resolve().parent
    bt = pd.read_csv(root / "output/cz_struct_backtest.csv", index_col="period")
    bt.index = pd.PeriodIndex(bt.index, freq="M")
    ext = pd.read_csv(root / "data/czcpmom_survey_history_extended.csv")
    ext["p"] = pd.PeriodIndex(ext["target_month"], freq="M")
    ext = ext.set_index("p").sort_index()
    ext = ext[ext["era"] != "flash_survey_suspect"]

    CAND = ["STRUCT", "STRUCT_QRF", "STRUCT_R", "STRUCT_QRF_R",
            "STRUCT_PE", "STRUCT_PEH", "STRUCT_PE_R", "STRUCT_PEH_R",
            "STRUCT_PRE", "STRUCT_PE_PRE",
            "STRUCT_PE_WARM", "STRUCT_PEH_WARM",   # v2.4: the adopted warm challenger, in-repo
            "STRUCT_NOANN"]                        # v2.7: reference with the announcement gate closed
    df = ext.join(bt[[c for c in CAND if c in bt.columns]], how="left")
    df = df.dropna(subset=["STRUCT"])   # frame defined by the reference model (Codex R2)
    df["s"] = df["actual"] - df["survey_median"]
    print(f"frame: {len(df)} first releases {df.index.min()}..{df.index.max()}")

    _boards = [board(df, "STRUCT", "HISTORICAL ridge = BASE_RIDGE (v2.7: documented January entries)"),
               board(df, "STRUCT_QRF", "HISTORICAL qrf (legacy)")]
    if "STRUCT_NOANN" in df.columns:   # v2.7: the same reference with the gate closed, always shown
        _boards.append(board(df, "STRUCT_NOANN", "HISTORICAL ridge, announcement gate CLOSED (= v2.6 STRUCT)"))
    if "STRUCT_PE_WARM" in df.columns:   # v2.4: the adopted challenger, computed in-repo
        _boards += [board(df, "STRUCT_PE_WARM", "HISTORICAL past-error WARM = PAST_FULL (adopted)"),
                    board(df, "STRUCT_PEH_WARM", "HISTORICAL past-error WARM half = PAST_HALF")]
    _boards += [board(df, "STRUCT_PE", "HISTORICAL past-error COLD (research)"),
                board(df, "STRUCT_PEH", "HISTORICAL past-error COLD half"),
                board(df, "STRUCT_PRE", "HISTORICAL ridge PRE-RELEASE fuel"),
                board(df, "STRUCT_PE_PRE", "HISTORICAL past-error COLD PRE-RELEASE"),
                board(df, "STRUCT_R", "RECONSTRUCTED ridge (scenario)"),
                board(df, "STRUCT_QRF_R", "RECONSTRUCTED qrf (scenario)"),
                board(df, "STRUCT_PE_R", "RECONSTRUCTED past-error COLD (scenario)")]
    boards = pd.concat(_boards, axis=1)
    print("\n=== SCOREBOARDS (consensus RMSE "
          f"{np.sqrt((df['s']**2).mean()):.3f}, 2024+ "
          f"{np.sqrt((df.loc[df.index>=pd.Period('2024-01','M'),'s']**2).mean()):.3f}, "
          f"big MAE {df.loc[df['s'].abs()>=0.4-1e-8,'s'].abs().mean():.3f}) ===")
    print(boards.round(3).to_string())

    # v2.5 (TIMING_SPEC T7): the same metrics at the two decision times.
    # A = month-end (the model has strictly less information than the survey,
    # which closes at release eve); B = the day before the FIRST release,
    # the like-for-like comparison with the consensus. Accuracy at one
    # cutoff does not establish accuracy at the other.
    eve_cols = {"STRUCT_EVE": "BASE_RIDGE", "STRUCT_PE_WARM_EVE": "PAST_FULL",
                "STRUCT_PEH_WARM_EVE": "PAST_HALF", "STRUCT_QRF_EVE": "legacy qrf"}
    if any(c in bt.columns for c in eve_cols):
        dfb = ext.join(bt[[c for c in eve_cols if c in bt.columns]], how="left").dropna(subset=["STRUCT_EVE"])
        dfb["s"] = dfb["actual"] - dfb["survey_median"]
        a_cols = {"STRUCT": "BASE_RIDGE", "STRUCT_PE_WARM": "PAST_FULL",
                  "STRUCT_PEH_WARM": "PAST_HALF", "STRUCT_QRF": "legacy qrf"}
        two = pd.concat([board(df, c, f"A month-end: {n}") for c, n in a_cols.items() if c in df.columns]
                        + [board(dfb, c, f"B release eve: {n}") for c, n in eve_cols.items() if c in dfb.columns],
                        axis=1)
        keep = ["n", "RMSE", "RMSE_2024p", "exJan_RMSE", "big_n", "big_MAE", "big_MAE_consensus",
                "big_agg_err_reduction_pct", "big_halves_consensus", "W-L@0.15", "alerts|d|>=0.2", "alerts_closer"]
        print("\n=== TWO DECISION TIMES: A = month-end of the target month, B = day before its first release ===")
        print(two.loc[keep].round(3).to_string())
        for a_c, b_c in [("STRUCT", "STRUCT_EVE"), ("STRUCT_PE_WARM", "STRUCT_PE_WARM_EVE")]:
            if a_c in bt.columns and b_c in bt.columns:
                d = (bt[b_c] - bt[a_c]).dropna()
                print(f"  {a_c}: B-A mean {d.mean():+.4f} pp, |B-A| max {d.abs().max():.3f} pp at {d.abs().idxmax()}, "
                      f"months with |B-A|>0.05: {int((d.abs()>0.05).sum())} of {len(d)}")

    print("\n=== SHADOW LOG (diagnostic comparisons, not certified prospective skill) ===")
    try:
        log = pd.read_csv(root / "output/struct_shadow_log.csv")
        log["p"] = pd.PeriodIndex(log["target"], freq="M")
        rel_all = pd.read_csv(root / "data/czcpmom_survey_history_extended.csv")
        rel_all["p"] = pd.PeriodIndex(rel_all["target_month"], freq="M")
        relm = rel_all.set_index("p")[["release_dt", "actual", "survey_median"]]
        if not relm.index.is_unique:
            raise ValueError("First-release table must contain exactly one event per target month")
        log = log.join(relm, on="p", validate="many_to_one")
        # The calendar's dates are Prague dates. Naive forecast clocks are not
        # retroactively assigned a zone by the classifier.
        log["release_ts"] = (pd.to_datetime(log["release_dt"]).dt.normalize()
                             + pd.Timedelta(hours=9)).dt.tz_localize("Europe/Prague")
        log["status"] = log.apply(classify_shadow_row, axis=1)
        # A pre-final forecast must never be compared with the earlier flash
        # under the guise of a final-release score. A separate event table is needed.
        if "release_stage" in log.columns:
            log.loc[log["release_stage"].eq("pre_final"), ["actual", "survey_median"]] = np.nan
        # Diagnostic errors only; these do not establish prospective eligibility.
        for m in ["h0_base_ridge", "h0_past_full", "h0_past_half"]:
            if m in log.columns:
                log[f"diagnostic_ae_{m[3:]}"] = (log[m] - log["actual"]).abs()
        log["diagnostic_ae_consensus"] = (log["survey_median"] - log["actual"]).abs()
        cols = [c for c in ["run_ts", "spec", "target", "release_stage", "h0_edge_gap",
                            "n_imputed", "archive_ok", "h0_base_ridge", "h0_past_full",
                            "h0_past_half", "h0_struct_qrf", "survey_median", "actual",
                            "diagnostic_ae_base_ridge", "diagnostic_ae_past_full", "diagnostic_ae_consensus", "status"]
                if c in log.columns]
        print(log[cols].to_string(index=False))
        print("\nCertified prospective rows: 0. Archive integrity, completion clocks, "
              "event identity and survey receipts are not yet validated by this tool.")
        print("rows at spec <= v2.3 were produced with defective feature construction "
              "(LIVE_PARITY_SPEC_v24.md) and are retained as such, never edited")
    except FileNotFoundError:
        print("no forecast log yet")
    print("Announcement evidence requires dated source receipts and a frozen conversion rule;")
    print("this scoreboard does not certify announcement provenance.")

    _rel_cols = ["STRUCT", "STRUCT_QRF", "STRUCT_R", "STRUCT_QRF_R"] + \
        [c for c in ["STRUCT_PE_WARM", "STRUCT_PEH_WARM", "STRUCT_PE"] if c in df.columns]
    rel = df[["release_dt", "actual", "survey_median", "s"] + _rel_cols].copy()
    for c in _rel_cols:
        rel[f"g_{c}"] = rel["s"].abs() - (rel[c] - rel["actual"]).abs()
        rel[f"alert_{c}"] = ((rel[c] - rel["survey_median"]).abs() >= 0.2)
    rel.to_csv(root / "output/release_by_release_codex_p0.csv")
    print(f"\nrelease-by-release table (every forecast, every alert incl. false "
          f"calls) -> output/release_by_release_codex_p0.csv ({len(rel)} rows)")

    jan = rel[rel.index.month == 1]
    print("\n=== January panel (all releases) ===")
    print(jan[["actual", "survey_median", "STRUCT_QRF", "STRUCT_QRF_R"]].round(2).to_string())


if __name__ == "__main__":
    main()
