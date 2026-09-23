"""Independent R21 artifact/timing/accounting audit; writes only this directory."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from models.released_error_research_r21 import offset_prediction, pool_weights
from tools.research_r21.path import prepare_training, EXPERTS

HERE = Path(__file__).resolve().parent
stats = {}


def read(path):
    return pd.read_csv(ROOT / path, float_precision="round_trip")


def monthly(path, key="period"):
    f = read(path).set_index(key)
    f.index = pd.PeriodIndex(f.index, freq="M")
    return f


def same(a, b, atol=1e-10):
    np.testing.assert_allclose(a, b, rtol=0, atol=atol, equal_nan=True)


cal = monthly("data/release_calendar_cz_cpi.csv", "target_month")
first = pd.to_datetime(cal.first_release_dt) + pd.Timedelta(hours=9)
detail = pd.to_datetime(cal.detail_release_dt) + pd.Timedelta(hours=9)
for folder in ["nowcast", "path"]:
    basepath = ROOT / "output/research_r21" / folder
    manifest = json.loads((basepath / "manifest.json").read_text())
    for filename, expected in manifest["inputs"].items():
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == expected, filename
    for filename, expected in manifest["outputs"].items():
        assert hashlib.sha256((basepath / filename).read_bytes()).hexdigest() == expected, filename
    stats[folder + "_verified_hashes"] = len(manifest["inputs"]) + len(manifest["outputs"])

base = monthly("output/independent_nowcast_forecasts.csv")
pred = read("output/research_r21/nowcast/predictions.csv")
diag = read("output/research_r21/nowcast/training.csv")
features = monthly("output/research_r21/nowcast/headline_features.csv")
core_features = monthly("output/research_r21/nowcast/core_features_at_decision.csv")
raw_features = monthly("tests/fixtures/cleanup/core_features.csv")
ev = read("work/model_briefing_20260914/nowcast_release_evidence.csv")
ev = ev[ev.model.eq("HARD_BASE")].set_index("period")
ev.index = pd.PeriodIndex(ev.index, freq="M")
labels = ev.actual - base.HARD_BASE
errors = monthly("output/independent_nowcast_hard_errors.csv").iloc[:, 0]
assert not pred.duplicated(["origin", "model"]).any()
assert pred.groupby("model").size().eq(90).all()
assert not set(["exp12", "exp36", "exp12_x_state", "household_exp", "esi"]) & set(features.columns)
for origin in base.index:
    clock = pd.Timestamp(base.loc[origin, "as_of_eve"])
    published = labels[(labels.index < origin) & first.reindex(labels.index).le(clock)].dropna()
    same(features.loc[origin, "released_headline_error_last"], published.iloc[-1] if len(published) else np.nan)
    same(features.loc[origin, "released_headline_error_last3"], published.tail(3).mean())
    for kind in ["mean", "enet"]:
        model = "HEADLINE_" + kind.upper() + "_R21"
        d = diag[diag.origin.eq(str(origin)) & diag.model.eq(model)].iloc[0]
        keys = published.tail(60).index
        assert str(d.train_origins) == ("|".join(map(str, keys)) if len(keys) else "nan")
        assert d.n == len(keys)
        want = offset_prediction(features, labels, first, origin, clock, kind)
        same(d.correction, want["correction"])
        point = pred[pred.origin.eq(str(origin)) & pred.model.eq(model)].iloc[0]
        same(point.forecast, base.loc[origin, "HARD_BASE"] + want["correction"])
        same(point.actual, ev.loc[origin, "actual"])
        same(point.consensus, ev.loc[origin, "consensus"])
    for kind in ["MEAN", "MEDIAN"]:
        d = diag[diag.origin.eq(str(origin)) & diag.model.eq("CORE_RF_" + kind + "_R21")].iloc[0]
        keys = errors[(errors.index < origin) & detail.reindex(errors.index).le(clock)].dropna().index
        assert d.train_origins == "|".join(map(str, keys))
        assert d.n == len(keys)
    for model in ["HARD_BASE", "HARD_HALF", "HARD_FULL"]:
        p = pred[pred.origin.eq(str(origin)) & pred.model.eq(model)].iloc[0]
        same(p.forecast, base.loc[origin, model])
stats["nowcast_rows_and_training_checked"] = [len(pred), len(diag)]
stats["headline_estimated_origins"] = int(diag[diag.model.eq("HEADLINE_ENET_R21")].status.eq("estimated").sum())
stats["headline_vs_detail_labels_different_months"] = int((ev.actual - monthly("output/independent_path_frozen_inputs.csv").headline_mm).abs().gt(1e-12).sum())

# Independent availability reconstruction, including pre-2019 historical rows.
rules = {"eurczk_mm": (1, 1), "core_l2": (0, 1), "core_l12": (0, 1), "import_l2": (0, 16)}
lagged_cpi = ["services_l1", "core_l1", "state"]
masked_cells = 0
for origin in sorted(set(errors.index) | set(base.index)):
    clock = pd.Timestamp(base.loc[origin, "as_of_eve"]) if origin in base.index else first.loc[origin] - pd.Timedelta(days=1)
    for col in core_features.columns:
        want = raw_features.loc[origin, col]
        feature = col.removesuffix("_x_state")
        hidden = False
        if feature in rules:
            shift, day = rules[feature]
            hidden |= clock < (origin + shift).to_timestamp() + pd.Timedelta(days=day - 1)
        if feature in lagged_cpi or col.endswith("_x_state"):
            hidden |= pd.isna(detail.get(origin - 1)) or detail.get(origin - 1) > clock
        if hidden:
            want = np.nan
            masked_cells += 1
        same(core_features.loc[origin, col], want)
stats["historical_mask_cells_checked"] = len(set(errors.index) | set(base.index)) * len(core_features.columns)
stats["cells_masked_on_frozen_eves"] = masked_cells

native = read("output/research_r21/path/native_forecasts.csv")
old = read("output/research_r17/path/native_forecasts.csv")
old = old[old.model.isin(EXPERTS)]
forecast = read("output/research_r21/path/forecasts.csv")
weights = read("output/research_r21/path/weights.csv")
ledger = read("output/research_r21/path/training.csv")
actual = monthly("output/independent_path_frozen_inputs.csv").headline_mm
components = monthly("output/research_r14b/attribution/actual_component_targets.csv")
biases = read("output/research_r21/path/biases.csv")
history = read("output/research_r21/path/feedback_error_history.csv")
assert not native.duplicated(["origin", "h", "model"]).any()
assert native.groupby("model").size().eq(1170).all()
assert not forecast.duplicated(["origin", "h", "model"]).any()
columns = [c for c in native if c.startswith("contribution_")]
active = native.h.gt(0)
conservation = (native.loc[active, columns].sum(axis=1) - native.loc[active, "mm_forecast"]).abs().max()
same(conservation, 0)
for col in columns:
    component = col.removeprefix("contribution_")
    weight = "weight_" + ("alc" if component == "alcohol_tobacco" else component)
    if weight in native:
        same(native.loc[active, col], native.loc[active, weight] * native.loc[active, "value_" + component])
stats["path_contribution_max_abs_error"] = float(conservation)

independent_ledger = []
global_objective_checks = []
for origin, group in old.groupby("origin"):
    t = pd.Period(origin, "M")
    clock = pd.Timestamp(group.as_of_utc.iloc[0]).tz_convert("Europe/Prague").tz_localize(None)
    paths = np.array([group[group.model.eq(m)].set_index("h").mm_forecast.loc[range(1, 13)] for m in EXPERTS])
    for row in weights[weights.origin.eq(origin)].itertuples():
        w = np.array([row.fast, row.current, row.gentle])
        assert w[0] >= .25 - 1e-12 and w.min() >= 0
        same(w.sum(), 1)
        got = native[native.origin.eq(origin) & native.model.eq(row.model)].set_index("h")
        same(got.mm_forecast.loc[range(1, 13)], w @ paths)
        if row.model == "POOL_PRIOR_R21":
            same(w, [.5, .25, .25])
            continue
        full = row.model == "POOL_COMPLETE_R21"
        count = np.zeros(12, int)
        for prior in sorted(old.origin.unique()):
            s = pd.Period(prior, "M")
            if s >= t:
                continue
            targets = [s + h for h in range(1, 13)]
            is_released = [u < t and pd.notna(detail.get(u)) and detail.get(u) <= clock for u in targets]
            if full and not all(is_released):
                continue
            for h, target in enumerate(targets, 1):
                if target < t - 36 or not all(is_released[:h]):
                    continue
                count[h - 1] += 1
                independent_ledger.append((origin, row.model, prior, h, str(target), detail.loc[target].isoformat()))
        if count.min() < 6:
            same(w, [.5, .25, .25])
        if origin in ["2021-01", "2024-01", "2026-07"] and count.min() >= 6:
            arrays, _ = prepare_training(old, actual, detail, t, clock, full)
            p, a, mask, age = arrays
            q = np.where(mask, np.exp2(-age / 12), 0)
            q /= q.sum(axis=0)
            def compound(wt):
                return 100 * np.log(np.cumprod(1 + np.einsum("nmh,m->nh", p, wt) / 100, axis=1))
            a = np.where(mask, a, 0)
            prior_loss = np.maximum(np.sum(q * (compound(np.array([.5, .25, .25])) - a) ** 2, axis=0), .0001)
            def objective(wt):
                return float(np.mean(np.sum(q * (compound(wt) - a) ** 2, axis=0) / prior_loss) + .05 * np.sum((wt - [.5, .25, .25]) ** 2))
            def unpack(v):
                fast = .25 + .75 * v[0]
                return np.array([fast, (1-fast)*v[1], (1-fast)*(1-v[1])])
            independent = differential_evolution(lambda v: objective(unpack(v)), [(0,1),(0,1)], seed=20260915, tol=1e-10, polish=True)
            gap = objective(w) - independent.fun
            assert gap < 1e-7, (origin, row.model, gap)
            global_objective_checks.append(dict(origin=origin, model=row.model, objective=objective(w), gap=gap))
    for model, g in forecast[forecast.origin.eq(origin)].groupby("model"):
        g = g.set_index("h")
        path = g.mm_forecast.to_dict()
        same(g.cumulative_log_forecast.loc[range(1,13)], 100 * np.log(np.cumprod(1 + g.mm_forecast.loc[range(1,13)].to_numpy()/100)))
        for h in range(13):
            months = pd.period_range(t + h - 11, t + h, freq="M")
            rates = [actual.loc[u] if u < t else path[u.ordinal - t.ordinal] for u in months]
            same(g.loc[h, "yy_exante"], 100 * (np.prod(1 + np.array(rates)/100) - 1))
        h0 = old[old.origin.eq(origin) & old.model.eq(EXPERTS[0]) & old.h.eq(0)].mm_forecast.iloc[0]
        same(path[0], h0)
    for b in biases[biases.origin.eq(origin)].itertuples():
        rows = history[history.block.eq(b.block)].copy()
        rows["month"] = pd.PeriodIndex(rows.target, freq="M")
        rows = rows[(rows.month < t) & pd.to_datetime(rows.available_from).le(clock)].sort_values("target").tail(24)
        assert b.n == len(rows)
        delta = 0.
        if len(rows) >= 12:
            ages = rows.month.max().ordinal - pd.PeriodIndex(rows.month, freq="M").asi8
            delta = np.average(rows.error, weights=np.exp2(-ages/12)) * len(rows)/(len(rows)+24)
        same(b.offset_log, delta)
        original = group[group.model.eq(EXPERTS[0])].set_index("h")["value_" + b.block].loc[range(1,13)].to_numpy()
        adjusted = native[native.origin.eq(origin) & native.model.eq(b.model)].set_index("h")["value_" + b.block].loc[range(1,13)].to_numpy()
        same(100*np.log((1+adjusted/100)/(1+original/100)), delta*.9**np.arange(12))

actual_ledger = [(r.origin,r.model,r.train_origin,r.h,r.target,r.available_from) for r in ledger.itertuples()]
assert sorted(independent_ledger) == sorted(actual_ledger)
stats["path_ledger_rows_independently_rebuilt"] = len(actual_ledger)
stats["path_forecast_rows_compounded_independently"] = len(forecast)
stats["pool_global_objective_checks"] = global_objective_checks
stats["bias_diagnostics_checked"] = len(biases)
for row in history.itertuples():
    target = pd.Period(row.target, "M")
    source = old[old.model.eq(EXPERTS[0]) & old.h.eq(1) & old.target.eq(row.target)].iloc[0]
    truth = components.loc[target, row.block] if target in components.index else np.nan
    expected = 100*np.log((1+truth/100)/(1+getattr(source,"value_"+row.block)/100))
    same(row.error, expected)
stats["component_error_rows_rebuilt"] = len(history)

# Adversarial publication hole: an already released h3 is unusable when h2 is not.
target = pd.period_range("2020-02", periods=12, freq="M")
tiny = pd.DataFrame([dict(origin="2020-01",h=h,model=m,mm_forecast=.2) for m in EXPERTS for h in range(1,13)])
truth = pd.Series(.1,index=target)
available = pd.Series(pd.Timestamp("2020-03-01"),index=target)
available.iloc[1] = pd.NaT
arrays, used = prepare_training(tiny,truth,available,pd.Period("2021-02","M"),pd.Timestamp("2021-03-01"))
assert [r["h"] for r in used] == [1]
truth.iloc[1:] = -1e30
poisoned, _ = prepare_training(tiny,truth,available,pd.Period("2021-02","M"),pd.Timestamp("2021-03-01"))
for a,b in zip(arrays,poisoned):
    same(a,b)
stats["publication_hole_poison_invariant"] = True

# A delayed pre-origin headline release and its feature cannot enter training.
ix = pd.period_range("2000-01",periods=40,freq="M")
x = pd.DataFrame({"a":np.arange(40,dtype=float),"b":np.nan},index=ix)
y = pd.Series(np.sin(np.arange(40))*.3,index=ix)
dates = pd.Series((ix+1).to_timestamp(),index=ix)
origin=ix[35]
dates.iloc[30]=pd.Timestamp("2050-01-01")
ref=offset_prediction(x,y,dates,origin,pd.Timestamp("2003-01-01"),"enet")
y.iloc[30]=1e50
x.iloc[30]=1e50
got=offset_prediction(x,y,dates,origin,pd.Timestamp("2003-01-01"),"enet")
assert ref == got
stats["delayed_headline_label_and_training_feature_poison_invariant"] = True

(HERE / "audit_results.json").write_text(json.dumps(stats, indent=2),encoding="utf-8")
print(json.dumps(stats,indent=2))
