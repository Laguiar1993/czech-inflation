"""Charts: our path (product F1b and trend line F2) as it stood when each CNB
report came out (the last origin whose print was public on the report date,
re-based on that print; user rule 8 Sep 2026) against the report's quarterly forecast path
and the realised y/y, one panel per report; plus error summaries by
quarters ahead. Reads output/path_step2.csv, data/cnb_mpr_cpi_quarterly.csv,
output/path_step2_cnbq_F1b.csv, output/path_step2_cnbq_F2_D1_fixed.csv.
Writes output/path_vs_cnb_panels.png, output/path_vs_cnb_errors.png,
output/path_vs_cnb_scatter.png.
Usage: python path_step2_charts.py
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from data import local_adapter as la  # noqa: E402
from path_experiment import _eve, lg, pct, load_fmie_1y  # noqa: E402

C = {"real": "#111111", "cnb": "#c0392b", "f1b": "#1f5fbf", "f2": "#2e8b57", "naive": "#9a9a9a", "fmie": "#e67e22"}


def main():
    df = pd.read_csv(os.path.join(HERE, "output", "path_step2.csv"))
    # months beyond the last realised print (not scorable, so not in the backtest file) come from
    # path_extend_recent.py, computed with the same engines; overlapping rows are identical to 1e-15
    extp = os.path.join(HERE, "output", "path_step2_extended.csv")
    if os.path.exists(extp):
        ext = pd.read_csv(extp)
        keep = [c for c in ["origin", "h", "target", "h0_model", "yy_a_F1b", "yy_a_F2_D1_fixed", "yy_a_naive", "yy_b_F1b", "yy_b_F2_D1_fixed", "yy_b_naive"] if c in ext.columns]
        df = pd.concat([df, ext[keep]], ignore_index=True).drop_duplicates(["origin", "h"], keep="first")
    df["tp"] = pd.PeriodIndex(df["target"], freq="M"); df["op"] = pd.PeriodIndex(df["origin"], freq="M")
    origins = sorted(df.op.unique())
    cq = pd.read_csv(os.path.join(HERE, "data", "cnb_mpr_cpi_quarterly.csv")); cq["report_date"] = pd.to_datetime(cq["report_date"])
    y = la.load_headline_cpi_mm_extended(); y = y[y.index >= pd.Period("1998-01", "M")].dropna()
    ylog = pd.Series(np.asarray(lg(y)), index=y.index)
    yy_real = pd.Series({m: pct(float(ylog.loc[m - 11:m].sum())) for m in y.index if (m - 11) in y.index})
    reports = cq.groupby(["report_date", "season"]).size().reset_index()[["report_date", "season"]].sort_values("report_date")
    fmie = load_fmie_1y()
    n = len(reports); ncol = 4; nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(4.6 * ncol, 3.4 * nrow), squeeze=False)
    for k, (i, r) in enumerate(reports.iterrows()):
        ax = axes[k // ncol][k % ncol]
        d = r.report_date
        cands = [t for t in origins if (_eve(t) + pd.Timedelta(days=1)).normalize() <= d.normalize()]     # last origin whose print was out when the report came (user rule 8 Sep 2026)
        if not cands:
            ax.set_visible(False); continue
        t = max(cands); g = df[df.op == t].sort_values("h").set_index("tp")
        rm = pd.Period(d, freq="M")
        # forward-looking panel (user, 8 Sep 2026): a little history for the eye, then everything from the report on
        span = pd.period_range(t - 6, rm + 15, freq="M")
        real = yy_real.reindex(span)
        ax.plot([p_.to_timestamp() for p_ in span], real.values, color=C["real"], lw=2.0, label="realised")
        # ours, as they stood when the report came out: the print at h0, then the twelve months published the evening before it
        if t in yy_real.index and len(g) and "yy_b_F1b" in g.columns and g["yy_b_F1b"].notna().any():
            yy0 = float(yy_real.loc[t])
            xs = [t.to_timestamp()] + [p_.to_timestamp() for p_ in g.index]
            ax.plot(xs, [yy0] + list(g["yy_b_F1b"]), color=C["f1b"], lw=1.8, label="ours: product (F1b)")
            ax.plot(xs, [yy0] + list(g["yy_b_F2_D1_fixed"]), color=C["f2"], lw=1.6, ls="--", label="ours: trend line (F2)")
        # the analysts' survey at the same moment: CNB FMIE one-year-ahead expectation of the print month, drawn twelve months out
        if fmie is not None:
            fm_t = fmie[fmie.index <= t]
            if len(fm_t):
                sm = fm_t.index[-1]
                ax.plot([(sm + 12).to_timestamp()], [float(fm_t.iloc[-1])], marker="D", ms=6, color=C["fmie"], ls="none", label=f"analysts' survey (FMIE {sm}), 12m ahead")
        # the CNB report: its forecast quarters only, from the quarter that contains the publication date
        gc = cq[(cq.report_date == d)].copy(); gc["q"] = pd.PeriodIndex(gc["quarter"], freq="Q")
        gc = gc[(gc.q >= pd.Period(d, freq="Q")) & (gc.q <= (rm + 15).asfreq("Q"))].sort_values("q")
        xq = [(q.asfreq("M", "s") + 1).to_timestamp() for q in gc.q]
        ax.plot(xq, gc.value.values, color=C["cnb"], marker="s", ms=4, lw=1.4, ls="-.", label="CNB report (quarterly)")
        ax.axvline(d, color="#888888", lw=0.8)
        ax.set_title(f"CNB {r.season} {d.year}, out {d.date()}" + chr(10) + f"ours: {t} print + path published {_eve(t).date()}", fontsize=8)
        ax.grid(alpha=0.3); ax.tick_params(labelsize=7)
        for lab in ax.get_xticklabels():
            lab.set_rotation(30)
        ax.legend(fontsize=6.5, loc="best", framealpha=0.85)
    for k in range(n, nrow * ncol):
        axes[k // ncol][k % ncol].set_visible(False)
    fig.suptitle("Czech CPI y/y at each CNB report date: our path as published, the analysts' survey, the CNB forecast, and what happened (six months of history, then forward)", fontsize=11.5)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    out1 = os.path.join(HERE, "output", "path_vs_cnb_panels.png"); fig.savefig(out1, dpi=120); plt.close(fig)

    # error summary by quarters ahead
    f1 = pd.read_csv(os.path.join(HERE, "output", "path_step2_cnbq_F1b.csv")); f2 = pd.read_csv(os.path.join(HERE, "output", "path_step2_cnbq_F2_D1_fixed.csv"))
    f1["rep"] = pd.to_datetime(f1.report); f2["rep"] = pd.to_datetime(f2.report)
    def rmse(e): return float(np.sqrt(np.mean(np.asarray(e, dtype=float) ** 2)))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), sharey=False)
    for ax, (lab, m1, m2) in zip(axes, (("reports 2022-2023", f1.rep < "2024-01-01", f2.rep < "2024-01-01"), ("reports 2024-2026", f1.rep >= "2024-01-01", f2.rep >= "2024-01-01"))):
        ks = sorted(set(f1[m1].quarters_ahead))
        vals = {"CNB": [], "ours: product (F1b), print at h0": [], "ours: trend line (F2)": [], "naive": []}; ns = []
        for k in ks:
            a = f1[m1 & (f1.quarters_ahead == k)]; b = f2[m2 & (f2.quarters_ahead == k)]
            vals["CNB"].append(rmse(a.err_cnb)); vals["ours: product (F1b), print at h0"].append(rmse(a.err_ours_b)); vals["ours: trend line (F2)"].append(rmse(b.err_ours_b)); vals["naive"].append(rmse(a.err_naive)); ns.append(len(a))
        w = 0.2; x = np.arange(len(ks))
        for j, (name, col) in enumerate(zip(vals, (C["cnb"], C["f1b"], C["f2"], C["naive"]))):
            ax.bar(x + (j - 1.5) * w, vals[name], w, color=col, label=name)
        ax.set_xticks(x); ax.set_xticklabels([f"{k}Q ahead\n(n={nn})" for k, nn in zip(ks, ns)], fontsize=8)
        ax.set_title(f"y/y RMSE of quarterly averages, {lab}", fontsize=10); ax.grid(axis="y", alpha=0.3); ax.set_ylabel("percentage points")
        ax.legend(fontsize=8)
    fig.tight_layout(); out2 = os.path.join(HERE, "output", "path_vs_cnb_errors.png"); fig.savefig(out2, dpi=130); plt.close(fig)

    # scatter: absolute error ours vs CNB per quarter forecast
    fig, ax = plt.subplots(figsize=(6.2, 6))
    for lab, d_, col in (("product (F1b)", f1, C["f1b"]), ("trend line (F2)", f2, C["f2"])):
        ax.scatter(d_.err_cnb.abs(), d_.err_ours_b.abs(), s=28, color=col, alpha=0.75, label=lab)
    lim = max(f1.err_cnb.abs().max(), f1.err_ours_b.abs().max(), f2.err_ours_b.abs().max()) * 1.05
    ax.plot([0, lim], [0, lim], color="#555555", lw=0.8, ls="--"); ax.set_xlim(0, lim); ax.set_ylim(0, lim)
    ax.set_xlabel("CNB absolute error (pp)"); ax.set_ylabel("our absolute error (pp)")
    ax.set_title("Each point = one quarter forecast from one report (below the line: we were closer)", fontsize=10); ax.grid(alpha=0.3); ax.legend(fontsize=8)
    fig.tight_layout(); out3 = os.path.join(HERE, "output", "path_vs_cnb_scatter.png"); fig.savefig(out3, dpi=130); plt.close(fig)
    print("written:", out1, out2, out3)


if __name__ == "__main__":
    main()
