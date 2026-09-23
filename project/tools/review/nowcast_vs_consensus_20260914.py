"""Nowcast against the Bloomberg consensus: accuracy by frame, surprise regressions, out-of-sample consensus shrink."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from independent_nowcast_experiment import is_big_surprise
rel = pd.read_csv(REPO / "output/independent_nowcast_releases.csv", dtype={"period": str})
rel = rel.dropna(subset=["actual", "consensus", "forecast"])
print("rows", len(rel), "models", rel.model.unique().tolist())
print("periods", rel.period.min(), rel.period.max(), "n periods", rel.period.nunique())


def rmse(x):
    return float(np.sqrt(np.mean(np.square(x))))


frames = {
    "all": lambda p: p.notna(),
    "2019-21": lambda p: p < "2022-01",
    "2022-23": lambda p: (p >= "2022-01") & (p < "2024-01"),
    "2024+": lambda p: p >= "2024-01",
    "2025+": lambda p: p >= "2025-01",
}
rows = []
for model, g in rel.groupby("model"):
    g = g.sort_values("period")
    for name, f in frames.items():
        s = g[f(g.period)]
        rows.append(dict(model=model, frame=name, n=len(s), model_rmse=rmse(s.forecast - s.actual), consensus_rmse=rmse(s.consensus - s.actual),
                         model_bias=float((s.forecast - s.actual).mean()), consensus_bias=float((s.consensus - s.actual).mean())))
tab = pd.DataFrame(rows)
print(tab[tab.model.isin(["HARD_BASE", "HARD_HALF", "HARD_FULL", "LEGACY_BASE"])].round(3).to_string(index=False))

# Does the model's deviation from consensus predict the surprise?
for model in ["HARD_BASE", "HARD_HALF", "HARD_FULL"]:
    g = rel[rel.model == model].sort_values("period").reset_index(drop=True)
    surprise = g.actual - g.consensus
    dev = g.forecast - g.consensus
    for name, mask in [("all", np.ones(len(g), bool)), ("2024+", (g.period >= "2024-01").to_numpy())]:
        x, y = dev[mask].to_numpy(), surprise[mask].to_numpy()
        X = np.c_[np.ones_like(x), x]
        beta, res, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        s2 = resid @ resid / (len(y) - 2)
        se = np.sqrt(s2 * np.linalg.inv(X.T @ X)[1, 1])
        r2 = 1 - resid @ resid / ((y - y.mean()) @ (y - y.mean()))
        print(f"{model:10s} {name:6s} n={len(y):3d} slope={beta[1]:.3f} t={beta[1]/se:.2f} R2={r2:.3f}")
    # Out-of-sample: consensus + b_hat * deviation, b_hat from past months only (expanding, from 2021-02 start of scoring)
    b_hist = []
    oos = []
    for i in range(len(g)):
        if g.period[i] < "2021-02":
            continue
        past = g.iloc[:i]
        x, y = (past.forecast - past.consensus).to_numpy(), (past.actual - past.consensus).to_numpy()
        b = float((x @ y) / (x @ x)) if len(past) >= 12 and (x @ x) > 0 else 0.0
        b_hist.append(b)
        oos.append(dict(period=g.period[i], actual=g.actual[i], consensus=g.consensus[i], shrink=g.consensus[i] + b * (g.forecast[i] - g.consensus[i]),
                        model=g.forecast[i], b=b))
    o = pd.DataFrame(oos)
    big = is_big_surprise(o.actual - o.consensus)
    print(f"  OOS from {o.period.min()} n={len(o)}: consensus {rmse(o.consensus - o.actual):.3f} | shrink {rmse(o.shrink - o.actual):.3f} | model {rmse(o.model - o.actual):.3f}"
          f" | 2024+: consensus {rmse((o.consensus - o.actual)[o.period >= '2024-01']):.3f} shrink {rmse((o.shrink - o.actual)[o.period >= '2024-01']):.3f}"
          f" | big-surprise MAE consensus {float((o.consensus - o.actual)[big].abs().mean()):.3f} shrink {float((o.shrink - o.actual)[big].abs().mean()):.3f}"
          f" | b range {min(b_hist):.2f}..{max(b_hist):.2f}")
    # Diebold-Mariano (squared error) model vs consensus, HAC lag 0 (h0 forecasts, non-overlapping)
    for name, mask in [("all", np.ones(len(g), bool)), ("2024+", (g.period >= "2024-01").to_numpy())]:
        d = (np.square(g.forecast - g.actual) - np.square(g.consensus - g.actual))[mask].to_numpy()
        t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
        print(f"  DM sq-error model-consensus {name}: mean d={d.mean():+.4f} t={t:+.2f} (positive = model worse)")
