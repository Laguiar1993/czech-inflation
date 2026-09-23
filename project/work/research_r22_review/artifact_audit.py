"""Verify R22 delivery accounting, reproducibility, and predictive responses."""
from pathlib import Path
import sys
import json
import hashlib
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from data.research_transmission_r22 import load_inputs
from models.transmission_r22 import run_origin


def main():
    out = ROOT / 'output/research_r22/full'
    native = pd.read_csv(out/'native_forecasts.csv', low_memory=False)
    manifest = json.loads((out/'manifest.json').read_text())
    for name, digest in manifest['inputs'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
    for name, digest in manifest['outputs'].items():
        assert hashlib.sha256((out/name).read_bytes()).hexdigest() == digest, name
    fast = native.query("model == 'STATE_FAST_R15'").set_index(['origin','h']).sort_index()
    learned_models = manifest['models']
    noncore = [col for col in native if (col.startswith('value_') or col.startswith('contribution_')) and col not in ['value_core','contribution_core']]
    weights = [col for col in native if col.startswith('weight_')]
    for model in learned_models:
        frame = native[native.model.eq(model)].set_index(['origin','h']).sort_index()
        assert len(frame) == 1170 and frame.index.is_unique
        pd.testing.assert_index_equal(frame.index, fast.index)
        np.testing.assert_allclose(frame[noncore + weights], fast[noncore + weights], rtol=0, atol=0, equal_nan=True)
        zero = frame.index.get_level_values('h') == 0
        np.testing.assert_allclose(frame.loc[zero, ['mm_forecast','value_core','contribution_core']],
                                   fast.loc[zero, ['mm_forecast','value_core','contribution_core']], rtol=0, atol=0, equal_nan=True)
        expected = fast.mm_forecast + fast.weight_core*(frame.value_core-fast.value_core)
        np.testing.assert_allclose(frame.loc[~zero].mm_forecast, expected.loc[~zero], rtol=1e-12, atol=1e-12)
    fits = [json.loads(line) for line in (out/'fits.jsonl').read_text().splitlines()]
    assert len(fits) == 90
    responses = pd.read_csv(out/'response_diagnostics.csv')
    max_response_delta = 0.
    for result in fits:
        origin = result['origin']
        for name, fit in result['fits'].items():
            cols = fit['columns']; k=len(cols); beta=np.array(fit['coefficients'])
            core=cols.index('core'); state=np.array(fit['state_at_internal_h0'])
            saved = native[native.origin.eq(origin)&native.model.eq(name)&native.h.gt(0)].sort_values('h')
            np.testing.assert_allclose(saved.value_core, result['paths'][name], rtol=1e-12, atol=1e-12)
            if fit['kind']=='forest': continue
            for variable, sub in responses[responses.origin.eq(origin)&responses.model.eq(name)].groupby('variable'):
                shock=sub.shock.iloc[0]; d=np.zeros(len(state))
                d[cols.index(variable)] = shock/result['preprocessing']['sigma'][variable]
                cumulative=[]; total=0.
                for h in range(1,13):
                    d=np.r_[d@beta[1:], d[:-k]]
                    total+=d[core]*result['preprocessing']['sigma']['core']; cumulative.append(total)
                for row in sub.itertuples():
                    delta=abs(cumulative[row.h-1]-row.core_cumulative_log_response)
                    max_response_delta=max(max_response_delta,delta)
                    assert delta<1e-10
    panel,available,*_=load_inputs()
    max_repeat_delta=0.
    for stored in (fits[0],fits[-1]):
        repeat=run_origin(panel,available,stored['origin'],stored['as_of'])
        for model in repeat['paths']:
            delta=float(np.max(np.abs(np.array(stored['paths'][model])-repeat['paths'][model])))
            max_repeat_delta=max(max_repeat_delta,delta)
            assert delta<1e-12
        for old,new in zip(stored['responses'],repeat['responses']):
            assert old==new
    status=pd.read_csv(out/'status.csv')
    report=dict(checks=['Every manifest source/output hash verifies',
        'All seven models retain the 90 x 13 FAST support and h0',
        'Every noncore component and weight preserved exactly',
        'Headline monthly changes equal frozen FAST plus weighted core substitution',
        'All 90 saved fitted core paths equal native forecasts',
        'All linear predictive responses reproduced independently from coefficient powers',
        'First and last origins, including ENET and RF paths/responses, reproduce'],
        max_linear_response_difference=max_response_delta,
        max_repeat_forecast_difference=max_repeat_delta,
        status_counts=status.status.value_counts().to_dict(),
        minimum_training_rows=int(status.n_train.min()), maximum_training_rows=int(status.n_train.max()))
    Path(__file__).with_name('artifact_audit_results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
