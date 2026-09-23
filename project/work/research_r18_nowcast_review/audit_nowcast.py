"""Independent arithmetic audit; deliberately does not import the fitted engine."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUN = ROOT / "output/research_r18_nowcast"


def read(path):
    return pd.read_csv(path, float_precision="round_trip")


def scale(past):
    values = np.abs(np.asarray(past, dtype=float))
    if len(values) == 0:
        return 0.25
    short = values[-12:]
    return max(0.05, (len(short) * sum(short) / len(short) + 12 * sum(values[-36:]) / len(values[-36:])) / (len(short) + 12))


def main():
    source = read(ROOT / "work/model_briefing_20260914/nowcast_release_evidence.csv")
    calendar = read(ROOT / "data/release_calendar_cz_cpi.csv").set_index("target_month")
    states = json.loads((ROOT / "output/research_r15/states.json").read_text())
    laws = json.loads((RUN / "laws.json").read_text())
    saved = read(RUN / "predictions.csv").set_index(["origin", "model", "family"])
    history_saved = read(RUN / "error_history.csv").set_index(["origin", "model"])
    models = sorted({law["model"] for law in laws})
    source = source[source.model.isin(models)].copy()
    points = source.pivot(index="period", columns="model", values="forecast").sort_index()
    source = source.set_index(["period", "model"])
    features = {t: np.array([abs(points.loc[t, "HARD_FULL"] - points.loc[t, "HARD_BASE"]),
                             abs(points.loc[t, "CATEGORY_RAW"] - points.loc[t, "HARD_BASE"])]) for t in points.index}
    errors = {(t, m): float(source.loc[(t, m), "actual"] - points.loc[t, m]) for t in points.index for m in models}
    release = {t: pd.Timestamp(calendar.loc[t, "first_release_dt"]) + pd.Timedelta(hours=9) for t in points.index}
    own = {}
    for t in points.index:
        clock = pd.Timestamp(states[t]["as_of"])
        assert clock.normalize() == release[t].normalize() - pd.Timedelta(days=1)
        for model in models:
            assert pd.Timestamp(source.loc[(t, model), "release_date"]).normalize() == release[t].normalize()
            prior = [s for s in points.index if s < t and release[s] <= clock]
            own[(t, model)] = scale([errors[(s, model)] for s in prior])
            assert abs(history_saved.loc[(t, model), "own_scale"] - own[(t, model)]) < 1e-12
    reconstructed = []
    maximum = {"support": 0., "weights": 0., "metrics": 0., "summaries": 0., "alerts": 0.}
    estimated = 0
    checks = []
    for law in laws:
        t, model, family = law["origin"], law["model"], law["family"]
        point = points.loc[t, model]
        clock = pd.Timestamp(states[t]["as_of"])
        prior = [s for s in points.index if s < t and release[s] <= clock]
        current_scale = scale([errors[(s, model)] for s in prior])
        pool = prior[-60:]
        assert law["n"] == len(pool) and law["training_origins"] == pool
        assert abs(law["current_scale"] - current_scale) < 1e-12
        assert pd.to_datetime(law["training_releases"]).tolist() == [release[s] for s in pool]
        if len(pool) < 24:
            assert law["status"] == "insufficient_history" and "support" not in law
            continue
        estimated += 1
        assert law["status"] == "estimated"
        sample = np.array([errors[(s, model)] for s in pool])
        if family == "POOLED":
            support = point + sample
            weights = np.repeat(1 / len(pool), len(pool))
        else:
            support = point + current_scale * sample / np.array([own[(s, model)] for s in pool])
            ages = np.array([pd.Period(t, "M").ordinal - pd.Period(s, "M").ordinal for s in pool])
            temporal = 2. ** (-ages / 24.)
            temporal /= temporal.sum()
            weights = temporal.copy()
            if family == "STATE":
                f = np.array([features[s] for s in pool])
                rms = np.maximum(np.sqrt((f * f).mean(axis=0)), 0.05)
                similarity = np.exp(-((f - features[t]) ** 2 / rms ** 2).sum(axis=1) / 2) * temporal
                if similarity.sum() > 1e-250:
                    weights = temporal / 2 + similarity / (2 * similarity.sum())
                    assert not law["kernel_fallback"]
                else:
                    assert law["kernel_fallback"]
        weights /= weights.sum()
        maximum["support"] = max(maximum["support"], float(np.max(abs(support - law["support"]))))
        maximum["weights"] = max(maximum["weights"], float(np.max(abs(weights - law["weights"]))))
        row = saved.loc[(t, model, family)]
        actual, consensus = source.loc[(t, model), ["actual", "consensus"]]
        gain = abs(actual - consensus) - abs(actual - point)
        # Direct pair summation, separate from the engine's matrix CRPS expression.
        pair = sum(weights[i] * weights[j] * abs(support[i] - support[j])
                   for i in range(len(pool)) for j in range(i + 1, len(pool)))
        crps = sum(weights * abs(support - actual)) - pair
        p_gain = sum(w for x, w in zip(support, weights) if abs(x - consensus) - abs(x - point) >= .15 - 1e-9)
        p_big = sum(w for x, w in zip(support, weights) if abs(x - consensus) >= .4 - 1e-9)
        ordered = sorted(zip(support, weights))
        def quantile(p):
            cumulative = 0.
            for x, w in ordered:
                cumulative += w
                if cumulative >= p:
                    return x
            return ordered[-1][0]
        metrics = dict(point=point, actual=actual, consensus=consensus, error=point-actual,
                       surprise=actual-consensus, deviation=point-consensus, gain=gain,
                       p_material_gain=p_gain, p_big=p_big, crps=crps, median=quantile(.5),
                       lo80=quantile(.1), hi80=quantile(.9), lo90=quantile(.05), hi90=quantile(.95),
                       ess=1/sum(weights*weights), current_scale=current_scale)
        for key, value in metrics.items():
            maximum["metrics"] = max(maximum["metrics"], float(abs(row[key] - value)))
        flags = dict(big=abs(actual-consensus)>=.4-1e-9, material_win=gain>=.15-1e-9,
                     material_loss=gain<=-.15+1e-9, alert=abs(point-consensus)>=.2-1e-9,
                     cover80=metrics["lo80"]<=actual<=metrics["hi80"],
                     cover90=metrics["lo90"]<=actual<=metrics["hi90"])
        assert all(row[key] == value for key, value in flags.items())
        reconstructed.append(dict(origin=t, model=model, family=family, release_kind=calendar.loc[t,"first_release_kind"], **metrics, **flags))
    data = pd.DataFrame(reconstructed)
    for summary in read(RUN / "scores.csv").itertuples():
        z = data[(data.model == summary.model) & (data.family == summary.family)]
        masks = {"all": np.ones(len(z), bool), "2024+": z.origin.ge("2024-01"),
                 "flash": z.release_kind.eq("flash"), "january": z.origin.str.endswith("-01"),
                 "ex_january": ~z.origin.str.endswith("-01"), "big": z.big}
        a = z.loc[masks[summary.frame]]
        numbers = dict(n=len(a), rmse=np.sqrt((a.error*a.error).mean()), mae=a.error.abs().mean(),
                       survey_mae=a.surprise.abs().mean(), crps=a.crps.mean(), coverage80=a.cover80.mean(),
                       coverage90=a.cover90.mean(), width80=(a.hi80-a.lo80).mean(), width90=(a.hi90-a.lo90).mean(),
                       brier_material=((a.p_material_gain-a.material_win)**2).mean(), brier_big=((a.p_big-a.big)**2).mean())
        for key,value in numbers.items():
            maximum["summaries"] = max(maximum["summaries"], float(abs(getattr(summary,key)-value)))
    for summary in read(RUN / "alerts.csv").itertuples():
        z = data[(data.model == summary.model) & (data.family == summary.family)]
        if summary.frame == "2024+": z = z[z.origin >= "2024-01"]
        if summary.frame == "flash": z = z[z.release_kind == "flash"]
        a = z[z.alert & (z.p_material_gain >= summary.threshold)]
        numbers = dict(n_eligible=len(z), n_alert=len(a), n_big=int(a.big.sum()), n_false=int((~a.big).sum()),
                       material_wins=int(a.material_win.sum()), material_losses=int(a.material_loss.sum()),
                       total_gain=a.gain.sum(), missed_big=int(z.big.sum()-a.big.sum()),
                       mae=a.error.abs().mean(), survey_mae=a.surprise.abs().mean())
        for key,value in numbers.items():
            old = getattr(summary,key)
            if pd.isna(value): assert pd.isna(old)
            else: maximum["alerts"] = max(maximum["alerts"], float(abs(old-value)))
    assert all(value < 1e-11 for value in maximum.values()), maximum
    # Same-direction overshoot is explicitly a losing material-gain outcome.
    assert abs(-.5-0.) - abs(-.5-(-1.2)) < 0
    manifest = json.loads((RUN / "manifest.json").read_text())
    for name,digest in manifest["outputs"].items():
        assert hashlib.sha256((RUN/name).read_bytes()).hexdigest() == digest
    report = dict(status="passed", origins=len(points), models=len(models), own_scales_verified=len(own),
                  laws_verified=len(laws), estimated_laws_verified=estimated,
                  eligible_dates_per_model_family=data.groupby(["model","family"]).size().unique().tolist(),
                  score_rows_verified=len(read(RUN/"scores.csv")), alert_rows_verified=len(read(RUN/"alerts.csv")),
                  maximum_absolute_differences=maximum,
                  limitations=["Release clocks and source vintages remain reconstructed assumptions; no live prospective claim.",
                               "False alarm here means alert on non-big outcome, not necessarily negative material gain; material wins/losses are separately reported.",
                               "Empirical probabilities and intervals are experimental and not guaranteed calibrated or conformal."])
    (OUT/"arithmetic_audit.json").write_text(json.dumps(report,indent=2)+"\n")
    data.to_csv(OUT/"independent_predictions.csv",index=False)
    print(json.dumps(report,indent=2))


if __name__ == "__main__": main()
