"""Read-only forest audit. Source files are not modified; output stays here."""
from pathlib import Path
import sys
import json
import hashlib
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'cz_struct.py').exists())
sys.path.insert(0, str(ROOT))
import paper_tvwqrf_experiment as ex
from models import paper_tvwqrf as engine
from tools.paper_replication import build_paper_panel as bp
from quantile_forest import RandomForestQuantileRegressor

out = {}
panel, target = ex.load_inputs(ROOT / 'data/paper_replication/paper_model_panel_20260912_luci', 'realtime')
edge = pd.Period('2023-12', freq='M')
timing = []
for h in (1, 3, 6, 9, 12, 13):
    X, y, now, rows, cols = ex.training_arrays(panel, target, edge, h, 'realtime')
    first_validation_edge = rows[-12]
    held_train_labels = rows[:-12] + h
    timing.append({'horizon': h, 'outer_edge': str(edge), 'last_outer_label': str((rows+h).max()),
                   'first_validation_edge': str(first_validation_edge), 'last_validation_edge': str(rows[-1]),
                   'last_held_training_label': str(held_train_labels[-1]),
                   'unavailable_labels_at_first_validation_edge': int((held_train_labels > first_validation_edge).sum())})
    if h == 12:
        opts = {**engine.FOREST_DEFAULTS, 'n_estimators': 100}
        fitted = RandomForestQuantileRegressor(**opts).fit(X[:-12], y[:-12])
        q1 = fitted.predict(X[-12:-11], quantiles=list(engine.ALL_QUANTILES))[0]
        changed_y = y[:-12].copy()
        changed_y[held_train_labels > first_validation_edge] += 10
        changed = RandomForestQuantileRegressor(**opts).fit(X[:-12], changed_y)
        q2 = changed.predict(X[-12:-11], quantiles=list(engine.ALL_QUANTILES))[0]
        out['validation_future_label_perturbation'] = {'first_validation_edge': str(first_validation_edge),
            'only_training_labels_after_this_edge_changed': True, 'quantiles_before': q1.tolist(),
            'quantiles_after': q2.tolist(), 'max_abs_change': float(np.max(np.abs(q2-q1)))}
out['training_and_validation_dates'] = timing

idx = pd.period_range('2002-05', periods=120, freq='M')
fake_panel = pd.DataFrame({'a6_11': np.ones(len(idx)), 'a6_12': np.arange(len(idx), dtype=float)}, index=idx)
fake_panel.iloc[0, 0] = np.nan
fake_target = pd.Series(np.sin(np.arange(len(idx))), index=idx)
X1, _, _, rr, _ = ex.training_arrays(fake_panel, fake_target, idx[-1], 6, 'realtime')
fake_panel.loc[rr[-12:], 'a6_11'] = 100.0
X2, _, _, _, _ = ex.training_arrays(fake_panel, fake_target, idx[-1], 6, 'realtime')
out['validation_imputation_perturbation'] = {'training_feature_row': str(rr[0]),
    'modified_validation_feature_rows': [str(rr[-12]), str(rr[-1])],
    'first_imputed_training_value_before': float(X1[0, 0]), 'first_imputed_training_value_after': float(X2[0, 0])}

# Prefix invariance: a future nonpositive value changes every earlier transform.
vals = pd.Series(100 + np.arange(len(idx), dtype=float), index=idx)
available = pd.Series(idx.to_timestamp(how='end').normalize() + pd.Timedelta(days=1), index=idx)
raw = bp.Raw(61, 'synthetic_positive_market_series', vals, available)
original, _ = bp.realtime_panel({61: raw}, end=idx[-1])
newvals = vals.copy()
newvals.iloc[-1] = -1.0
changed, _ = bp.realtime_panel({61: bp.Raw(61, raw.source, newvals, available)}, end=idx[-1])
old_edge = idx[60]
out['realtime_future_transform_perturbation'] = {'forecast_edge': str(old_edge), 'changed_raw_period': str(idx[-1]),
    'before': float(original.loc[old_edge, 'a6_61']), 'after': float(changed.loc[old_edge, 'a6_61'])}

# Outer arrays must be invariant to future targets and future panel rows.
X1, y1, now1, rr1, cc1 = ex.training_arrays(panel, target, edge, 12, 'realtime')
changed_panel, changed_target = panel.copy(), target.copy()
changed_panel.loc[changed_panel.index > edge] = 1e6
changed_target.loc[changed_target.index > edge] = 1e6
X2, y2, now2, rr2, cc2 = ex.training_arrays(changed_panel, changed_target, edge, 12, 'realtime')
out['outer_future_invariance_passes'] = bool(np.array_equal(X1, X2) and np.array_equal(y1, y2) and np.array_equal(now1, now2))

run = ROOT / 'output/paper_tvwqrf_20260912/paper_full_exact'
forecasts = pd.read_csv(run / 'forecasts.csv')
scores = []
for (h, model), g in forecasts.groupby(['horizon', 'model']):
    err = g['forecast'] - g['actual']
    published = ex.PAPER_BENCHMARKS.get(model, {}).get(h)
    scores.append({'h': int(h), 'model': model, 'n': int(err.notna().sum()),
        'rmse_recomputed': float(np.sqrt(np.mean(err.dropna() ** 2))), 'published': published})
pd.DataFrame(scores).to_csv(HERE / 'paper_scores_recomputed.csv', index=False)
out['tvw3_exact_scores'] = [x for x in scores if x['model'] == 'TVW3']
manifest = json.loads((run / 'manifest.json').read_text())
out['current_engine_matches_run_manifest'] = hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest() == manifest['engine_sha256']

# The stored "h6 YoY" is a cross-origin accumulation: list its six forecast edges.
T = pd.Period('2023-12', freq='M')
six = pd.period_range(T-5, T, freq='M')
out['yoy6_cross_origin_example'] = {'claimed_h6_target': str(T), 'common_decision_edge': str(T-6),
    'forecast_target_months': [str(x) for x in six], 'forecast_edges_used': [str(x-6) for x in six]}
(HERE / 'audit_evidence.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
print(json.dumps(out, indent=2))
