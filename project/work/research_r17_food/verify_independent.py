"""Independent arithmetic/lineage checks of saved food output; never refits a choice."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/research_r17_food'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(name):
    return pd.read_csv(ROOT/name, float_precision='round_trip')


def main():
    manifest = json.loads((OUT/'manifest.json').read_text())
    for filename, expected in manifest['inputs'].items():
        assert digest(ROOT/filename) == expected, filename
    for filename, expected in manifest['outputs'].items():
        assert digest(OUT/filename) == expected, filename
    states = json.loads((OUT/'snapshots.json').read_text())
    fits = json.loads((OUT/'fits.json').read_text())
    calendars = json.loads((OUT/'training_calendars.json').read_text())
    levels = read('data/research_r14/food/pipeline_log_levels.csv').set_index('period')
    levels.index = pd.PeriodIndex(levels.index, freq='M'); actual_log = levels.food.diff()
    releases = read('data/research_r14/food/pipeline_available_from.csv').set_index('period')
    releases.index = pd.PeriodIndex(releases.index, freq='M')
    columns = {'own': [0, 1], 'symmetric': list(range(6)), 'asymmetric': [0, 1]+list(range(6, 14))}
    matrix_cache = {}; endpoint_checks = 0
    for key, rows in calendars.items():
        origin, h = key.split('|'); t = pd.Period(origin); clock = pd.Timestamp(states[origin]['as_of'])
        assert len(rows) <= 96
        for row in rows:
            target = pd.Period(row['target']); source = pd.Period(row['origin'])
            assert source+int(h) == target < t
            assert row['feature_as_of'] == states[str(source)]['as_of']
            assert pd.Timestamp(row['feature_as_of']) < clock
            for endpoint in (target-1, target):
                assert pd.Timestamp(releases.food.loc[endpoint]) <= clock
                endpoint_checks += 1
            assert row['saved_seasonal'] == states[str(source)]['seasonal'][target.month-1]
        x = np.array([states[r['origin']]['features'] for r in rows])
        y = np.array([actual_log.loc[r['target']]-r['saved_seasonal'] for r in rows])
        matrix_cache[key] = x, y
    coefficient_error = 0.; fitted_rows = 0
    predictions = read('output/research_r17_food/food_predictions.csv')
    fixed = read('output/research_r17_food/fixed_candidates.csv')
    fixed_lookup = fixed.set_index(['origin','family','penalty','h'])
    own_lookup = predictions.loc[predictions.model.eq('FOOD_OWN_R17')].set_index(['origin','h'])
    forecast_error = 0.
    for fit in fits:
        if fit['status'] != 'estimated':
            assert fit['reason'] in ('insufficient_training_rows','missing_current_predictor','unavailable_seasonality')
            continue
        fitted_rows += 1
        x, y = matrix_cache[fit['training_calendar_id']]; x = x[:, columns[fit['family']]]
        assert len(y) >= 24
        scale = np.sqrt(np.mean(x*x, axis=0)); scale[scale <= 1e-12] = 1
        z = x/scale
        beta = np.linalg.solve(z.T@z/len(y)+np.diag(fit['penalties']), z.T@y/len(y))
        coefficient_error = max(coefficient_error, float(np.max(np.abs(beta-fit['coefficients']))))
        assert np.max(np.abs(scale-fit['scale'])) < 1e-12
        state = states[fit['origin']]; target = pd.Period(fit['origin'])+fit['h']
        now = np.array(state['features'])[columns[fit['family']]]
        forecast = state['seasonal'][target.month-1]+(now/scale)@beta
        saved = own_lookup.loc[(fit['origin'],fit['h'])].log_rate_forecast if fit['family']=='own' else fixed_lookup.loc[(fit['origin'],fit['family'],fit['penalty'],fit['h'])].log_rate_forecast
        forecast_error = max(forecast_error, abs(float(saved)-forecast))
    assert coefficient_error < 1e-11 and forecast_error < 1e-11

    # Rebuild each whole-path selection loss from its saved fixed candidate forecasts.
    selection_checks = 0
    selections = json.loads((OUT/'selections.json').read_text())
    fold_rows = []
    for (origin, family, penalty), group in fixed.groupby(['origin','family','penalty']):
        if group.all_path_estimated.all():
            truth = actual_log.reindex(pd.PeriodIndex(group.target, freq='M')).to_numpy()
            if np.isfinite(truth).all():
                fold_rows.append(dict(origin=origin,family=family,penalty=penalty,
                                      mse=float(np.mean((group.log_rate_forecast.to_numpy()-truth)**2))))
    folds = pd.DataFrame(fold_rows)
    for selection in selections:
        if selection['family']=='own':
            continue
        t = pd.Period(selection['origin']); clock = pd.Timestamp(selection['as_of'])
        previous = folds.loc[folds.family.eq(selection['family']) & folds.origin.map(lambda s:pd.Period(s)+12<t)].copy()
        wide = previous.pivot(index='origin', columns='penalty', values='mse').dropna().sort_index()
        eligible = []
        for origin in wide.index:
            endpoints = pd.period_range(pd.Period(origin), pd.Period(origin)+12, freq='M')
            if all(pd.Timestamp(releases.food.loc[e]) <= clock for e in endpoints):
                eligible.append(origin)
        eligible = eligible[-36:]
        assert selection['validation_origins']==eligible
        if len(eligible)>=12:
            loss = wide.loc[eligible].mean()
            best = min((1.,10.,.1),key=lambda p:loss[p])
            assert selection['penalty']==best
        else:
            assert selection['penalty']==1.
        selection_checks += 1

    native = read('output/research_r17_food/native_forecasts.csv')
    baseline = read('output/research_r15/native_forecasts.csv'); baseline = baseline.loc[baseline.model.eq('STATE_FAST_R15')]
    invariant = [c for c in baseline if c.startswith('weight_') or (c.startswith('value_') and c!='value_food') or (c.startswith('contribution_') and c!='contribution_food')]
    hist = read('output/independent_path_frozen_inputs.csv').set_index('period').headline_mm
    hist.index = pd.PeriodIndex(hist.index, freq='M')
    annual_error, sum_error = 0., 0.
    for name, group in native.groupby('model'):
        a = group.set_index(['origin','h']).sort_index(); b = baseline.set_index(['origin','h']).sort_index()
        pd.testing.assert_frame_equal(a[invariant],b[invariant],check_exact=True)
        np.testing.assert_array_equal(a.xs(0,level='h').mm_forecast,b.xs(0,level='h').mm_forecast)
        for origin, path in a.groupby(level='origin'):
            path = path.droplevel('origin'); t = pd.Period(origin)
            for h, row in path.iterrows():
                values = [hist.get(m,np.nan) if m<t else path.loc[m.ordinal-t.ordinal,'mm_forecast'] for m in pd.period_range(t+h-11,t+h,freq='M')]
                expected = 100*(np.prod(1+np.array(values)/100)-1)
                annual_error = max(annual_error,abs(expected-row.yy_exante))
                if h>0:
                    parts = [row['contribution_'+c] for c in ('core','food','administered','alcohol_tobacco','fuel','wedge')]
                    sum_error = max(sum_error,abs(sum(parts)-row.mm_forecast))
    assert annual_error<1e-10 and sum_error<1e-12
    assert len(native)==6*90*13 and len(predictions)==6*126*12
    outer = predictions.loc[predictions.outer_origin]
    assert np.isfinite(outer.mm_forecast).all()
    assert not outer.status.str.startswith('fallback').any()
    result = dict(status='passed',source_hashes=len(manifest['inputs']),output_hashes=len(manifest['outputs']),
                  audited_training_calendars=len(calendars),response_endpoint_checks=endpoint_checks,
                  independently_rebuilt_fits=fitted_rows,coefficient_max_error=coefficient_error,
                  fixed_forecast_max_error=forecast_error,chronological_path_selection_checks=selection_checks,
                  annual_product_max_error=float(annual_error),monthly_component_sum_max_error=float(sum_error),
                  all_h0_nonfood_values_weights_exact=True,outer_origins=90,own_origin_snapshots=126,
                  outer_food_fallback_rows=0,outer_food_missing_rows=0)
    (ROOT/'work/research_r17_food/independent_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
